"""
Validation Agent — validates mapped, normalised records against Pydantic models and
cross-field consistency rules. Last gate before persistence. Routes records to
'accept' or 'quarantine'.
"""

import logging
from decimal import Decimal
from typing import Any, Optional

from pydantic import ValidationError as PydanticValidationError

from app.config.settings import LINE_TOTAL_TOLERANCE, OCR_CONFIDENCE_THRESHOLD
from app.validation.exceptions import ValidationError
from app.validation.models import InvoiceRecord, ResumeRecord, ValidationResult

logger = logging.getLogger(__name__)

def validate_record(mapped_row: dict, document_type: str) -> ValidationResult:
    document_id = mapped_row.get('document_id', '')
    try:
        if document_type == 'invoice':
            model_instance = InvoiceRecord(**mapped_row)
        elif document_type == 'resume':
            model_instance = ResumeRecord(**mapped_row)
        else:
            logger.warning(f"Unknown document type '{document_type}'. Passing through.")
            return ValidationResult(is_valid=True, record=mapped_row, routing='accept')
            
        return ValidationResult(is_valid=True, record=model_instance)
    except PydanticValidationError as exc:
        errors = [f"{e['loc']}: {e['msg']}" for e in exc.errors()]
        return ValidationResult(is_valid=False, errors=errors, routing='quarantine')

def check_invoice_line_items(record: InvoiceRecord) -> list[str]:
    if record.subtotal is not None and record.total_amount is not None:
        expected = record.subtotal + (record.tax_amount or Decimal('0')) - (record.discount_amount or Decimal('0'))
        tolerance = record.total_amount * Decimal(str(LINE_TOTAL_TOLERANCE))
        if abs(expected - record.total_amount) > tolerance:
            return [f"Line item consistency check failed: Expected total {expected}, found {record.total_amount}"]
    return []

def check_ocr_confidence(record_confidence: float, threshold: float = OCR_CONFIDENCE_THRESHOLD) -> bool:
    return record_confidence >= threshold

def route_record(mapped_row: dict, document_type: str, ocr_confidence: Optional[float] = None) -> tuple[str, dict]:
    result = validate_record(mapped_row, document_type)
    if not result.is_valid:
        return ('quarantine', {'record': mapped_row, 'reasons': result.errors})
        
    quarantine_reasons = []
    if document_type == 'invoice' and isinstance(result.record, InvoiceRecord):
        consistency_errors = check_invoice_line_items(result.record)
        quarantine_reasons.extend(consistency_errors)
        
    if ocr_confidence is not None and not check_ocr_confidence(ocr_confidence):
        quarantine_reasons.append(f'Low OCR confidence: {ocr_confidence:.2f}')
        
    if quarantine_reasons:
        logger.info(f"Quarantined record {mapped_row.get('document_id', '')}: {quarantine_reasons}")
        return ('quarantine', {'record': mapped_row, 'reasons': quarantine_reasons})
        
    logger.info(f"Accepted record {mapped_row.get('document_id', '')}")
    return ('accept', mapped_row)

def validate_document(document_id: str, mapped_rows: list[dict], document_type: str, ocr_confidence: Optional[float] = None) -> list[tuple[str, dict]]:
    results = []
    accepted = 0
    quarantined = 0
    
    for row in mapped_rows:
        row.setdefault('document_id', document_id)
        routing, result_dict = route_record(row, document_type, ocr_confidence)
        if routing == 'accept':
            accepted += 1
        else:
            quarantined += 1
        results.append((routing, result_dict))
        
    logger.info(f"Document {document_id} validation summary: {accepted} accepted, {quarantined} quarantined.")
    return results
