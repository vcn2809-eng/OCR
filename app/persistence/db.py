"""
Database Access Layer for Core Document, EAV Document Fields, Vendor, and Legacy Migration.
All database access goes through app.persistence.db (or app.persistence.agent).
"""
import logging
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid4
from typing import Generator, Any, Optional

from sqlalchemy import select, delete, update, text, func
from sqlalchemy.orm import Session

from app.persistence.database import get_db_session, get_engine, init_db
from app.persistence.models import Base, Document, DocumentField, Vendor

logger = logging.getLogger(__name__)


@contextmanager
def get_connection() -> Generator[Session, None, None]:
    """Context manager for acquiring a database session."""
    with get_db_session() as session:
        yield session


# ── VENDOR PERSISTENCE ──────────────────────────────────────

def save_vendor(vendor_name: str, address: str = "") -> str:
    """Inserts a new vendor with a generated UUID, or updates the address if vendor_name already exists.

    Returns the vendor_id.
    """
    v_name = (vendor_name or "").strip()
    if not v_name:
        raise ValueError("vendor_name cannot be empty")

    now_iso = datetime.now().isoformat()

    with get_connection() as session:
        existing = session.execute(
            select(Vendor).where(Vendor.vendor_name == v_name)
        ).scalar_one_or_none()

        if existing:
            existing.address = address
            existing.updated_at = now_iso
            session.add(existing)
            session.flush()
            return existing.vendor_id
        else:
            new_id = str(uuid4())
            vendor = Vendor(
                vendor_id=new_id,
                vendor_name=v_name,
                address=address,
                created_at=now_iso,
                updated_at=now_iso,
            )
            session.add(vendor)
            session.flush()
            return new_id


def list_vendors() -> list[dict[str, str]]:
    """Returns ONLY vendor_id and vendor_name (not address), sorted alphabetically by vendor_name."""
    with get_connection() as session:
        stmt = select(Vendor.vendor_id, Vendor.vendor_name).order_by(Vendor.vendor_name.asc())
        rows = session.execute(stmt).all()
        return [
            {
                "vendor_id": r.vendor_id,
                "vendor_name": r.vendor_name,
            }
            for r in rows
        ]


def get_vendor_by_id(vendor_id: str) -> dict[str, Any] | None:
    """Returns the full vendor record (name + address + created_at + updated_at), or None if not found."""
    with get_connection() as session:
        vendor = session.get(Vendor, vendor_id)
        if not vendor:
            return None
        return {
            "vendor_id": vendor.vendor_id,
            "vendor_name": vendor.vendor_name,
            "address": vendor.address or "",
            "created_at": vendor.created_at,
            "updated_at": vendor.updated_at,
        }


# ── CORE DOCUMENT PERSISTENCE ───────────────────────────────

def save_document(
    document_id: str,
    file_hash: str,
    filename: str,
    file_type: str,
    document_type: Optional[str] = None,
    vendor_id: Optional[str] = None,
    status: str = "stored",
    confidence: Optional[float] = None,
    raw_text: Optional[str] = None,
) -> str:
    """UPSERT into documents table. Returns document_id."""
    now_iso = datetime.now().isoformat()

    with get_connection() as session:
        existing = session.get(Document, document_id)
        if existing is None:
            dup = session.execute(
                select(Document).where(Document.file_hash == file_hash)
            ).scalar_one_or_none()
            if dup is not None and dup.document_id != document_id:
                old_id = dup.document_id
                session.delete(dup)
                from app.persistence.models import RawDocument, Invoice, Resume, GenericRecord, Quarantine, ProcessingLog, ProcessingQueue
                session.query(RawDocument).filter(RawDocument.document_id == old_id).delete()
                session.query(Invoice).filter(Invoice.document_id == old_id).delete()
                session.query(Resume).filter(Resume.document_id == old_id).delete()
                session.query(GenericRecord).filter(GenericRecord.document_id == old_id).delete()
                session.query(Quarantine).filter(Quarantine.document_id == old_id).delete()
                session.query(ProcessingLog).filter(ProcessingLog.document_id == old_id).delete()
                session.query(ProcessingQueue).filter(ProcessingQueue.document_id == old_id).delete()
                session.flush()

        if existing:

            existing.file_hash = file_hash
            existing.original_filename = filename
            existing.file_type = file_type
            if document_type is not None:
                existing.document_type = document_type
            if vendor_id is not None:
                existing.vendor_id = vendor_id
            existing.status = status
            if confidence is not None:
                existing.confidence = confidence
            if raw_text is not None:
                existing.raw_ocr_text = raw_text
            existing.updated_at = now_iso
            session.add(existing)
            session.flush()
            return existing.document_id
        else:
            doc = Document(
                document_id=document_id,
                file_hash=file_hash,
                original_filename=filename,
                file_type=file_type,
                document_type=document_type,
                vendor_id=vendor_id,
                status=status,
                confidence=confidence,
                raw_ocr_text=raw_text,
                uploaded_at=now_iso,
                updated_at=now_iso,
            )
            session.add(doc)
            session.flush()
            return doc.document_id


def save_document_fields(
    document_id: str,
    fields: dict[str, Any],
) -> int:
    """Deletes existing fields for document_id, then bulk-inserts new ones in a single transaction.

    Accepts fields as:
      { field_name: (field_value, field_type) }
    or:
      { field_name: field_value } (defaults field_type to 'text')

    Returns the count of inserted fields.
    """
    with get_connection() as session:
        # Delete existing fields atomically inside transaction
        session.execute(delete(DocumentField).where(DocumentField.document_id == document_id))

        count = 0
        for name, val in fields.items():
            if val is None:
                continue

            if isinstance(val, tuple) and len(val) == 2:
                field_val, field_type = val
            else:
                field_val = val
                if isinstance(field_val, (int, float)):
                    field_type = "number"
                elif isinstance(field_val, datetime):
                    field_type = "date"
                else:
                    field_type = "text"

            str_val = str(field_val) if not isinstance(field_val, str) else field_val
            field_name_clean = str(name).strip().lower().replace(" ", "_")

            df = DocumentField(
                document_id=document_id,
                field_name=field_name_clean,
                field_value=str_val,
                field_type=field_type,
            )
            session.add(df)
            count += 1

        session.flush()
        return count


def get_document_with_fields(document_id: str) -> dict[str, Any] | None:
    """Combines documents row with all its document_fields rows reassembled into a nested dict."""
    with get_connection() as session:
        doc = session.get(Document, document_id)
        if not doc:
            return None

        fields_stmt = select(DocumentField).where(DocumentField.document_id == document_id)
        field_rows = session.execute(fields_stmt).scalars().all()

        fields_dict = {}
        for f in field_rows:
            val: Any = f.field_value
            if f.field_type == "number":
                try:
                    val = float(f.field_value) if "." in f.field_value else int(f.field_value)
                except ValueError:
                    pass
            fields_dict[f.field_name] = val

        return {
            "document_id": doc.document_id,
            "file_hash": doc.file_hash,
            "original_filename": doc.original_filename,
            "file_type": doc.file_type,
            "document_type": doc.document_type,
            "vendor_id": doc.vendor_id,
            "status": doc.status,
            "confidence": doc.confidence,
            "raw_ocr_text": doc.raw_ocr_text,
            "uploaded_at": doc.uploaded_at,
            "updated_at": doc.updated_at,
            "fields": fields_dict,
        }


def list_documents(
    document_type: Optional[str] = None,
    vendor_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Paginated, filterable list of documents with reassembled fields."""
    with get_connection() as session:
        stmt = select(Document)

        if document_type:
            stmt = stmt.where(Document.document_type == document_type)
        if vendor_id:
            stmt = stmt.where(Document.vendor_id == vendor_id)
        if status:
            stmt = stmt.where(Document.status == status)

        stmt = stmt.order_by(Document.uploaded_at.desc()).limit(limit).offset(offset)
        docs = session.execute(stmt).scalars().all()

        results = []
        for doc in docs:
            fields_stmt = select(DocumentField).where(DocumentField.document_id == doc.document_id)
            field_rows = session.execute(fields_stmt).scalars().all()

            fields_dict = {f.field_name: f.field_value for f in field_rows}

            results.append({
                "document_id": doc.document_id,
                "file_hash": doc.file_hash,
                "original_filename": doc.original_filename,
                "file_type": doc.file_type,
                "document_type": doc.document_type,
                "vendor_id": doc.vendor_id,
                "status": doc.status,
                "confidence": doc.confidence,
                "uploaded_at": doc.uploaded_at,
                "updated_at": doc.updated_at,
                "fields": fields_dict,
            })
        return results


def link_vendor_to_document(document_id: str, vendor_id: str) -> bool:
    """Updates documents.vendor_id for a document."""
    with get_connection() as session:
        doc = session.get(Document, document_id)
        if not doc:
            return False
        doc.vendor_id = vendor_id
        doc.updated_at = datetime.now().isoformat()
        session.add(doc)
        session.flush()
        return True


# ── LEGACY DATA MIGRATION ────────────────────────────────────

def migrate_legacy_data() -> dict[str, int]:
    """One-time migration function that reads legacy rows from invoices, resumes, and raw_documents,

    converts them into the new documents + document_fields EAV schema, and logs summary.
    """
    init_db()
    migrated_docs = 0
    migrated_fields = 0

    with get_connection() as session:
        # 1. Inspect raw_documents for legacy documents
        from app.persistence.models import RawDocument, Invoice, Resume
        raw_docs = session.execute(select(RawDocument)).scalars().all()

        for rd in raw_docs:
            doc_id = rd.document_id
            now_iso = datetime.now().isoformat()

            # Save core document
            save_document(
                document_id=doc_id,
                file_hash=rd.file_hash or f"legacy_hash_{doc_id}",
                filename=rd.original_filename or "legacy_file.pdf",
                file_type=rd.file_type or "pdf",
                document_type=rd.document_type or "generic",
                status="stored",
                raw_text=rd.raw_extracted_json,
            )
            migrated_docs += 1

            # Extract fields from legacy Invoice or Resume table
            fields_dict = {}
            if rd.document_type == "invoice":
                inv = session.execute(select(Invoice).where(Invoice.document_id == doc_id)).scalar_one_or_none()
                if inv:
                    if inv.invoice_number: fields_dict["invoice_number"] = (inv.invoice_number, "text")
                    if inv.customer_name: fields_dict["customer_name"] = (inv.customer_name, "text")
                    if inv.vendor_name: fields_dict["vendor_name"] = (inv.vendor_name, "text")
                    if inv.total_amount: fields_dict["total_amount"] = (str(inv.total_amount), "number")
                    if inv.invoice_date: fields_dict["invoice_date"] = (str(inv.invoice_date), "date")

            elif rd.document_type == "resume":
                res = session.execute(select(Resume).where(Resume.document_id == doc_id)).scalar_one_or_none()
                if res:
                    if res.name: fields_dict["name"] = (res.name, "text")
                    if res.email: fields_dict["email"] = (res.email, "text")
                    if res.phone: fields_dict["phone"] = (res.phone, "text")
                    if res.skills: fields_dict["skills"] = (res.skills, "text")

            if fields_dict:
                count = save_document_fields(doc_id, fields_dict)
                migrated_fields += count

    logger.info("Legacy data migration completed. Documents: %d, Fields: %d", migrated_docs, migrated_fields)
    return {"migrated_documents": migrated_docs, "migrated_fields": migrated_fields}
