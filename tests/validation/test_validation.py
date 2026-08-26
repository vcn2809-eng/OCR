import pytest
from decimal import Decimal
from app.validation.agent import validate_record, check_invoice_line_items, check_ocr_confidence, route_record, validate_document
from app.validation.models import InvoiceRecord, ResumeRecord, ValidationResult

def test_validate_valid_invoice():
    data = {
        'document_id': 'INV-123',
        'invoice_number': '1001',
        'customer_name': 'Acme Corp',
        'total_amount': '150.00'
    }
    result = validate_record(data, 'invoice')
    assert result.is_valid is True
    assert isinstance(result.record, InvoiceRecord)
    assert result.record.total_amount == Decimal('150.00')

def test_validate_invoice_negative_total():
    data = {
        'total_amount': '-100'
    }
    result = validate_record(data, 'invoice')
    assert result.is_valid is False
    assert len(result.errors) > 0

def test_validate_invoice_all_optional():
    data = {
        'invoice_number': 'INV-001'
    }
    result = validate_record(data, 'invoice')
    assert result.is_valid is True
    assert result.record.invoice_number == 'INV-001'
    assert result.record.total_amount is None

def test_cross_field_check_passes():
    record = InvoiceRecord(
        subtotal=Decimal('100.00'),
        tax_amount=Decimal('10.00'),
        discount_amount=Decimal('0.00'),
        total_amount=Decimal('110.00')
    )
    errors = check_invoice_line_items(record)
    assert errors == []

def test_cross_field_check_fails():
    record = InvoiceRecord(
        subtotal=Decimal('100.00'),
        tax_amount=Decimal('10.00'),
        total_amount=Decimal('500.00')
    )
    errors = check_invoice_line_items(record)
    assert len(errors) > 0
    assert "Line item consistency check failed" in errors[0]

def test_ocr_confidence_high():
    assert check_ocr_confidence(0.9) is True

def test_ocr_confidence_low():
    assert check_ocr_confidence(0.2) is False

def test_route_accept():
    data = {'invoice_number': '123', 'total_amount': '100'}
    routing, result = route_record(data, 'invoice', ocr_confidence=0.9)
    assert routing == 'accept'
    assert result == data

def test_route_quarantine_invalid():
    data = {'total_amount': '-999'}
    routing, result = route_record(data, 'invoice')
    assert routing == 'quarantine'
    assert 'reasons' in result

def test_route_quarantine_low_confidence():
    data = {'invoice_number': '123', 'total_amount': '100'}
    routing, result = route_record(data, 'invoice', ocr_confidence=0.1)
    assert routing == 'quarantine'
    assert any('Low OCR confidence' in reason for reason in result['reasons'])

def test_route_quarantine_consistency_fail():
    data = {'subtotal': '100', 'tax_amount': '10', 'total_amount': '999'}
    routing, result = route_record(data, 'invoice')
    assert routing == 'quarantine'
    assert any('Line item consistency check failed' in reason for reason in result['reasons'])

def test_unknown_doc_type_passes_through():
    data = {'some_field': 'value'}
    routing, result = route_record(data, 'unknown_xyz')
    assert routing == 'accept'
    assert result == data
