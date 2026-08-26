"""Pydantic response models for the API Layer."""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    file_type: str
    message: str


class DocumentStatus(BaseModel):
    document_id: str
    current_stage: str
    status: str
    stages: list[dict]
    error_message: Optional[str] = None


class DocumentRecord(BaseModel):
    document_id: str
    document_type: str
    record: Optional[dict] = None
    status: str
    message: str


class DocumentListItem(BaseModel):
    document_id: str
    original_filename: str
    file_type: str
    document_type: Optional[str] = None
    uploaded_at: Optional[str] = None
    current_stage: Optional[str] = None


class DocumentList(BaseModel):
    items: list[DocumentListItem]
    total: int
    page: int
    page_size: int


class QuarantineItem(BaseModel):
    id: int
    document_id: str
    document_type: str
    record: dict
    reasons: list[str]
    flagged_at: Optional[str] = None
    reviewed: bool


class QuarantineList(BaseModel):
    items: list[QuarantineItem]
    total: int
    page: int
    page_size: int


class QuarantineResolveRequest(BaseModel):
    action: str  # 'accept' or 'dismiss'
    corrected_record: Optional[dict] = None


class QuarantineResolveResponse(BaseModel):
    id: int
    action: str
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str


class LearnAliasRequest(BaseModel):
    alias: str
    canonical_name: str
    category: str = "header"
    confidence: float = 1.0


class LearnAliasResponse(BaseModel):
    alias: str
    canonical_name: str
    category: str
    message: str


class AliasItem(BaseModel):
    alias: str
    canonical_name: str
    category: str
    confidence: float
    occurrence_count: int


class AliasListResponse(BaseModel):
    items: list[AliasItem]
    total: int


class VendorCreateRequest(BaseModel):
    vendor_name: str
    address: Optional[str] = ""


class VendorCreateResponse(BaseModel):
    vendor_id: str


class VendorListItem(BaseModel):
    vendor_id: str
    vendor_name: str


class VendorDetailResponse(BaseModel):
    vendor_id: str
    vendor_name: str
    address: Optional[str] = ""
    created_at: str
    updated_at: str

