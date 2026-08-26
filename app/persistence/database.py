"""
Database engine and session management for the Persistence Agent.
All other agents access the database exclusively through app.persistence.agent.

PostgreSQL is the production database. Tests override _engine directly via monkeypatch
to use an in-memory SQLite instance — this is the only sanctioned use of SQLite.
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, Engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from app.config import settings
from app.persistence.models import Base

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def get_engine() -> Engine:
    """Return (and lazily create) the SQLAlchemy engine.

    Uses DATABASE_URL from settings, which defaults to PostgreSQL.
    Connection pool is tuned for a web-service workload:
      - pool_size=5 keeps 5 persistent connections
      - max_overflow=10 allows burst up to 15 total
      - pool_pre_ping=True drops stale connections before use
    """
    global _engine
    if _engine is None:
        url = settings.DATABASE_URL
        is_sqlite = url.startswith("sqlite")

        connect_args: dict = {}
        pool_kwargs: dict = {}

        if is_sqlite:
            # SQLite-only: used only by test fixtures that override this engine
            connect_args["check_same_thread"] = False
            pool_kwargs["poolclass"] = NullPool
        else:
            # PostgreSQL production settings
            pool_kwargs.update(
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=1800,    # recycle connections every 30 min
                pool_pre_ping=True,   # verify connection health before use
            )

        _engine = create_engine(
            url,
            connect_args=connect_args,
            echo=False,
            **pool_kwargs,
        )
        logger.info("Database engine created. Backend: %s", url.split("://")[0])
    return _engine


def get_session_factory() -> sessionmaker:
    """Return (and lazily create) the SQLAlchemy session factory."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionFactory


def init_db() -> None:
    """Create all tables if they do not already exist.

    Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS semantics
    via SQLAlchemy's create_all(checkfirst=True).
    """
    engine = get_engine()
    Base.metadata.create_all(engine, checkfirst=True)
    logger.info("Database tables initialised.")
    migrate_legacy_data()


def migrate_legacy_data() -> None:
    """Migrates legacy quotation data to the normalized billing tables."""
    from sqlalchemy import inspect
    from decimal import Decimal
    from app.persistence.models import Quotation, QuotationLineItem, BillingDocument, BillingDocumentLineItem, BillingVendor, BillingCustomer
    
    engine = get_engine()
    inspector = inspect(engine)
    if not (inspector.has_table('quotations') and inspector.has_table('billing_documents')):
        return

    try:
        with get_db_session() as session:
            # Check if there is anything in quotations
            legacy_count = session.query(Quotation).count()
            if legacy_count == 0:
                return

            logger.info(f"Found {legacy_count} legacy quotations. Checking for migration...")
            
            # Map legacy records
            for legacy_q in session.query(Quotation).all():
                # Check if already migrated
                exists = session.query(BillingDocument).filter(BillingDocument.document_no == legacy_q.quotation_no).first()
                if exists:
                    continue

                logger.info(f"Migrating legacy quotation No: {legacy_q.quotation_no}...")

                # 1. Resolve / Create vendor
                v_id = None
                if legacy_q.vendor_name:
                    vendor = session.query(BillingVendor).filter(
                        (BillingVendor.gstin == legacy_q.vendor_gstin) if legacy_q.vendor_gstin else (BillingVendor.name == legacy_q.vendor_name)
                    ).first()
                    if not vendor:
                        vendor = BillingVendor(
                            name=legacy_q.vendor_name,
                            gstin=legacy_q.vendor_gstin
                        )
                        session.add(vendor)
                        session.flush()
                    v_id = vendor.id

                # 2. Resolve / Create customer
                c_id = None
                if legacy_q.customer_name:
                    customer = session.query(BillingCustomer).filter(
                        (BillingCustomer.gstin == legacy_q.customer_gstin) if legacy_q.customer_gstin else (BillingCustomer.name == legacy_q.customer_name)
                    ).first()
                    if not customer:
                        customer = BillingCustomer(
                            name=legacy_q.customer_name,
                            gstin=legacy_q.customer_gstin
                        )
                        session.add(customer)
                        session.flush()
                    c_id = customer.id

                # 3. Create BillingDocument
                doc = BillingDocument(
                    document_type='quotation',
                    document_no=legacy_q.quotation_no,
                    document_date=legacy_q.quotation_date,
                    classification_confidence=Decimal('1.000'),
                    classification_reasoning='Migrated from legacy quotations table',
                    vendor_id=v_id,
                    customer_id=c_id,
                    validity_date=legacy_q.validity_date,
                    payment_terms=legacy_q.payment_terms,
                    currency=legacy_q.currency or 'INR',
                    enquiry_ref=legacy_q.enquiry_ref,
                    enquiry_date=legacy_q.enquiry_date,
                    grand_total_taxable=legacy_q.grand_total_taxable,
                    grand_total_cgst=legacy_q.grand_total_cgst,
                    grand_total_sgst=legacy_q.grand_total_sgst,
                    grand_total_final=legacy_q.grand_total_final,
                    grand_total_words=legacy_q.grand_total_words,
                    source_file=legacy_q.source_file,
                    extraction_status=legacy_q.extraction_status,
                )
                session.add(doc)
                session.flush()

                # 4. Migrate line items
                legacy_items = session.query(QuotationLineItem).filter(QuotationLineItem.quotation_id == legacy_q.id).all()
                for li in legacy_items:
                    new_li = BillingDocumentLineItem(
                        document_id=doc.id,
                        line_no=li.line_no,
                        item_code=li.item_code,
                        description=li.description,
                        hsn_code=li.hsn_code,
                        brand=li.brand,
                        uom=li.uom,
                        packing=li.packing,
                        qty=li.qty,
                        rate=li.rate,
                        gross_amount=li.gross_amount,
                        discount_pct=li.discount_pct,
                        discount_amount=li.discount_amount,
                        taxable_amount=li.taxable_amount,
                        cgst_pct=li.cgst_pct,
                        cgst_amount=li.cgst_amount,
                        sgst_pct=li.sgst_pct,
                        sgst_amount=li.sgst_amount,
                        final_value=li.final_value,
                        status_eta=li.status_eta,
                        needs_review=li.needs_review,
                        review_reason=li.review_reason,
                    )
                    session.add(new_li)
            logger.info("Legacy quotation data migration completed successfully.")
    except Exception as e:
        logger.error(f"Failed to migrate legacy data: {e}", exc_info=True)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager that yields a Session, commits on success, rolls back on error."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
