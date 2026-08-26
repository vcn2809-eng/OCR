"""SQLAlchemy ORM models for the Persistence Agent and EAV Schema."""

from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey,
    UniqueConstraint, Index, func, Date, Numeric
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Vendor(Base):
    """ORM model for Vendor entity."""
    __tablename__ = 'vendors'

    vendor_id: Mapped[str] = mapped_column(String, primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index('idx_vendors_name', 'vendor_name', unique=True),
    )


class Document(Base):
    """Core Document entity that all extracted fields and processing logs attach to."""
    __tablename__ = 'documents'

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    file_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    document_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    vendor_id: Mapped[str | None] = mapped_column(String, ForeignKey('vendors.vendor_id'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default='queued')
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    fields: Mapped[list['DocumentField']] = relationship(
        'DocumentField', back_populates='document', cascade='all, delete-orphan'
    )

    __table_args__ = (
        Index('idx_documents_type', 'document_type'),
        Index('idx_documents_vendor', 'vendor_id'),
    )


class DocumentField(Base):
    """Entity-Attribute-Value (EAV) table storing individual extracted fields."""
    __tablename__ = 'document_fields'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey('documents.document_id', ondelete='CASCADE'), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    field_value: Mapped[str] = mapped_column(Text, nullable=False)
    field_type: Mapped[str] = mapped_column(String, nullable=False)  # text, number, date, currency

    document: Mapped['Document'] = relationship('Document', back_populates='fields')

    __table_args__ = (
        UniqueConstraint('document_id', 'field_name', name='uq_document_field_name'),
        Index('idx_document_fields_name', 'field_name'),
        Index('idx_document_fields_doc', 'document_id'),
    )


class RawDocument(Base):
    """Maintained for backward compatibility and raw archiving."""
    __tablename__ = 'raw_documents'

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    file_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String)
    file_type: Mapped[str] = mapped_column(String)
    document_type: Mapped[str | None] = mapped_column(String, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    raw_extracted_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class Invoice(Base):
    __tablename__ = 'invoices'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey('raw_documents.document_id'), unique=True)
    invoice_number: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    vendor_name: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String, nullable=True)
    purchase_order_number: Mapped[str | None] = mapped_column(String, nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String, nullable=True)
    due_date: Mapped[str | None] = mapped_column(String, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class Resume(Base):
    __tablename__ = 'resumes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, ForeignKey('raw_documents.document_id'), unique=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    github_url: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    certifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    achievements: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class GenericRecord(Base):
    __tablename__ = 'generic_records'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    document_type: Mapped[str] = mapped_column(String, default='generic')
    record_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Quarantine(Base):
    __tablename__ = 'quarantine'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    document_type: Mapped[str] = mapped_column(String)
    record_json: Mapped[str] = mapped_column(Text)
    reasons: Mapped[str] = mapped_column(Text)
    flagged_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)


class ProcessingLog(Base):
    __tablename__ = 'processing_log'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String, index=True)
    stage: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(String, default='')
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class ProcessingQueue(Base):
    __tablename__ = 'processing_queue'

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    file_path: Mapped[str] = mapped_column(String)
    file_hash: Mapped[str] = mapped_column(String)
    file_type: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='queued')
    document_type: Mapped[str | None] = mapped_column(String, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class LearnedAlias(Base):
    __tablename__ = 'learned_aliases'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String, index=True, unique=True)
    canonical_name: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String, default='header')
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    learned_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class Quotation(Base):
    __tablename__ = 'quotations'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vendor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_gstin: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_gstin: Mapped[str | None] = mapped_column(Text, nullable=True)
    quotation_no: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    quotation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    validity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    enquiry_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    enquiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    grand_total_taxable: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_cgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_sgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_final: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_words: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    line_items: Mapped[list['QuotationLineItem']] = relationship(
        'QuotationLineItem', back_populates='quotation', cascade='all, delete-orphan'
    )


class QuotationLineItem(Base):
    __tablename__ = 'quotation_line_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quotation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('quotations.id', ondelete='CASCADE'), nullable=False
    )
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hsn_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    uom: Mapped[str | None] = mapped_column(Text, nullable=True)
    packing: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    taxable_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cgst_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    sgst_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    final_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status_eta: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    quotation: Mapped['Quotation'] = relationship('Quotation', back_populates='line_items')


class BillingVendor(Base):
    __tablename__ = 'billing_vendors'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    gstin: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    pan: Mapped[str | None] = mapped_column(Text, nullable=True)
    msme_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_account_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(Text, nullable=True)
    dl_20b: Mapped[str | None] = mapped_column(Text, nullable=True)
    dl_21b: Mapped[str | None] = mapped_column(Text, nullable=True)
    cin: Mapped[str | None] = mapped_column(Text, nullable=True)
    enterprise_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    documents: Mapped[list['BillingDocument']] = relationship('BillingDocument', back_populates='vendor')


class BillingCustomer(Base):
    __tablename__ = 'billing_customers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    gstin: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    documents: Mapped[list['BillingDocument']] = relationship('BillingDocument', back_populates='customer')


class BillingDocument(Base):
    __tablename__ = 'billing_documents'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    document_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    classification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    classification_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    vendor_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('billing_vendors.id', ondelete='SET NULL'), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('billing_customers.id', ondelete='SET NULL'), nullable=True)
    
    validity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, default='INR')
    enquiry_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    enquiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    po_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    grand_total_taxable: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_cgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_sgst: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_final: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    grand_total_words: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    vendor: Mapped['BillingVendor | None'] = relationship('BillingVendor', back_populates='documents')
    customer: Mapped['BillingCustomer | None'] = relationship('BillingCustomer', back_populates='documents')
    line_items: Mapped[list['BillingDocumentLineItem']] = relationship(
        'BillingDocumentLineItem', back_populates='document', cascade='all, delete-orphan'
    )


class BillingDocumentLineItem(Base):
    __tablename__ = 'billing_document_line_items'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey('billing_documents.id', ondelete='CASCADE'), nullable=False
    )
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    hsn_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    uom: Mapped[str | None] = mapped_column(Text, nullable=True)
    packing: Mapped[str | None] = mapped_column(Text, nullable=True)
    qty: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    taxable_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cgst_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    cgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    sgst_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    sgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    final_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    item_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_eta: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped['BillingDocument'] = relationship('BillingDocument', back_populates='line_items')


class SearchAlias(Base):
    __tablename__ = 'search_aliases'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    canonical: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)  # description, vendor, global
    source: Mapped[str] = mapped_column(Text, default='seed')      # seed, learned
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal('1.000'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

