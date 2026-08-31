"""Regression tests for the invoice scanning pipeline, quantity self-correction, and financial total reconciliation."""
import pytest
from decimal import Decimal
from typing import Dict, Any, List

from app.quotation_extraction.validator import validate_row_arithmetic, validate_quotation_totals
from app.quotation_extraction.ai_extractor import validate_and_reconcile


def test_row_level_self_correction():
    """Verify that quantity leakage into the description is corrected and the quantity is mathematically restored."""
    # Bug scenario: Qty 5 leaked into description "5 High Lighter", Qty extracted incorrectly as 3
    item = {
        "description": "5 High Lighter",
        "qty": 3,
        "rate": 2859.12,
        "amount": 14295.60,
    }
    
    header = {}
    _, cleaned = validate_and_reconcile(header, [item])
    
    assert len(cleaned) == 1
    corrected_item = cleaned[0]
    assert corrected_item["qty"] == Decimal("5.00")
    assert corrected_item["description"] == "High Lighter"
    assert corrected_item["rate"] == Decimal("2859.12")
    assert corrected_item["gross_amount"] == Decimal("14295.60")


def test_row_level_self_correction_line_2():
    """Verify that quantity leakage for line 2 is also corrected properly."""
    item = {
        "description": "3 Voucher Box",
        "qty": 3,
        "rate": 527.01,
        "amount": 1581.03,
    }
    
    header = {}
    _, cleaned = validate_and_reconcile(header, [item])
    
    assert len(cleaned) == 1
    corrected_item = cleaned[0]
    assert corrected_item["qty"] == Decimal("3.00")
    assert corrected_item["description"] == "Voucher Box"
    assert corrected_item["rate"] == Decimal("527.01")
    assert corrected_item["gross_amount"] == Decimal("1581.03")


def test_invoice_reconciliation_exact_numbers_success():
    """Verify that the document reconciles correctly when line items match the printed subtotal."""
    # Printed Subtotal: 15,876.63, Total Due: 15,836.94
    # Line items:
    # 5 High Lighter @ 2859.12 = 14295.60
    # 3 Voucher Box @ 527.01 = 1581.03
    quotation = {
        "grand_total_taxable": Decimal("15876.63"),
        "grand_total_final": Decimal("15836.94"),
        "total_discount": Decimal("39.69"),
    }
    
    items = [
        {
            "qty": Decimal("5.00"),
            "rate": Decimal("2859.12"),
            "gross_amount": Decimal("14295.60"),
            "taxable_amount": Decimal("14295.60"),
            "final_value": Decimal("14295.60"),
        },
        {
            "qty": Decimal("3.00"),
            "rate": Decimal("527.01"),
            "gross_amount": Decimal("1581.03"),
            "taxable_amount": Decimal("1581.03"),
            "final_value": Decimal("1581.03"),
        }
    ]
    
    # Run through validators
    validated_items = [validate_row_arithmetic(item) for item in items]
    validated_quotation = validate_quotation_totals(quotation, validated_items)
    
    assert validated_quotation["extraction_status"] == "ok"
    assert validated_quotation["review_reason"] is None


def test_invoice_reconciliation_exact_numbers_failure():
    """Verify that a mismatch in extracted line items correctly flags the document as needs_review."""
    # Mismatch scenario: extracted Qty is 3 for both (sum = 10,158.39), but printed subtotal is 15,876.63
    quotation = {
        "grand_total_taxable": Decimal("15876.63"),
        "grand_total_final": Decimal("15836.94"),
    }
    
    items = [
        {
            "qty": Decimal("3.00"),
            "rate": Decimal("2859.12"),
            "gross_amount": Decimal("8577.36"),
            "taxable_amount": Decimal("8577.36"),
            "final_value": Decimal("8577.36"),
        },
        {
            "qty": Decimal("3.00"),
            "rate": Decimal("527.01"),
            "gross_amount": Decimal("1581.03"),
            "taxable_amount": Decimal("1581.03"),
            "final_value": Decimal("1581.03"),
        }
    ]
    
    # Run through validators
    validated_items = [validate_row_arithmetic(item) for item in items]
    validated_quotation = validate_quotation_totals(quotation, validated_items)
    
    assert validated_quotation["extraction_status"] == "needs_review"
    assert "total mismatch" in validated_quotation["review_reason"]
