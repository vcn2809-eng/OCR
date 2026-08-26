"""Pydantic models for the Validation Agent."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class InvoiceRecord(BaseModel):
    """Validated invoice record. All fields optional to accommodate partial extractions."""
    model_config = {"arbitrary_types_allowed": True}

    document_id: str = ''
    invoice_number: Optional[str] = None
    customer_name: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    total_amount: Optional[Decimal] = Field(None, ge=0)
    subtotal: Optional[Decimal] = Field(None, ge=0)
    tax_amount: Optional[Decimal] = Field(None, ge=0)
    discount_amount: Optional[Decimal] = Field(None, ge=0)
    payment_terms: Optional[str] = None
    purchase_order_number: Optional[str] = None
    notes: Optional[str] = None
    extras: dict = Field(default_factory=dict)

    @field_validator('invoice_date', 'due_date', mode='before')
    @classmethod
    def parse_date(cls, v: Any) -> Any:
        if isinstance(v, str) and v:
            try:
                return date.fromisoformat(v)
            except ValueError:
                return None
        return v

    @field_validator('total_amount', 'subtotal', 'tax_amount', 'discount_amount', mode='before')
    @classmethod
    def parse_decimal(cls, v: Any) -> Any:
        if isinstance(v, str) and v:
            try:
                return Decimal(v.replace(',', '').strip())
            except Exception:
                return None
        return v


class ResumeRecord(BaseModel):
    """Validated resume record."""
    document_id: str = ''
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    objective: Optional[str] = None
    skills: Optional[str] = None
    education: Optional[str] = None
    work_experience: Optional[str] = None
    certifications: Optional[str] = None
    achievements: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    extras: dict = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Outcome of validating a single record."""
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    record: Optional[Any] = None
    routing: str = 'accept'
    quarantine_reasons: list[str] = Field(default_factory=list)
