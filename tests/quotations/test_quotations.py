import pytest
from pathlib import Path
from decimal import Decimal
from datetime import date
from app.quotation_extraction.pdf_extractor import parse_date, extract_pdf_quotation
from app.quotation_extraction.validator import to_decimal, validate_row_arithmetic, validate_quotation_totals

def test_to_decimal():
    assert to_decimal(None) == Decimal("0.00")
    assert to_decimal(10) == Decimal("10.00")
    assert to_decimal(2.5) == Decimal("2.50")
    assert to_decimal("1,250.75") == Decimal("1250.75")
    assert to_decimal("-") == Decimal("0.00")


def test_parse_date():
    assert parse_date("15-Jun-2026") == date(2026, 6, 15)
    assert parse_date("12-07-2026") == date(2026, 7, 12)
    assert parse_date("15-July-2026") == date(2026, 7, 15)
    assert parse_date(None) is None


def test_validate_row_arithmetic():
    # A valid row
    valid_row = {
        "qty": Decimal("2"),
        "rate": Decimal("100.00"),
        "gross_amount": Decimal("200.00"),
        "discount_pct": Decimal("10.00"),
        "discount_amount": Decimal("20.00"),
        "taxable_amount": Decimal("180.00"),
        "cgst_pct": Decimal("9.00"),
        "cgst_amount": Decimal("16.20"),
        "sgst_pct": Decimal("9.00"),
        "sgst_amount": Decimal("16.20"),
        "final_value": Decimal("212.40"),
    }
    validated = validate_row_arithmetic(valid_row)
    assert validated["needs_review"] is False
    assert validated["review_reason"] is None

    # An invalid row (Gross Amount mismatch)
    invalid_row = {
        "qty": Decimal("2"),
        "rate": Decimal("100.00"),
        "gross_amount": Decimal("250.00"), # should be 200
        "discount_pct": Decimal("10.00"),
        "discount_amount": Decimal("20.00"),
        "taxable_amount": Decimal("180.00"),
        "cgst_pct": Decimal("9.00"),
        "cgst_amount": Decimal("16.20"),
        "sgst_pct": Decimal("9.00"),
        "sgst_amount": Decimal("16.20"),
        "final_value": Decimal("212.40"),
    }
    validated_invalid = validate_row_arithmetic(invalid_row)
    assert validated_invalid["needs_review"] is True
    assert "Gross Amount mismatch" in validated_invalid["review_reason"]


def test_validate_quotation_totals():
    quotation = {
        "grand_total_taxable": Decimal("180.00"),
        "grand_total_cgst": Decimal("16.20"),
        "grand_total_sgst": Decimal("16.20"),
        "grand_total_final": Decimal("212.40"),
    }
    items = [{
        "taxable_amount": Decimal("180.00"),
        "cgst_amount": Decimal("16.20"),
        "sgst_amount": Decimal("16.20"),
        "final_value": Decimal("212.40"),
        "needs_review": False
    }]
    validated_q = validate_quotation_totals(quotation, items)
    assert validated_q["extraction_status"] == "ok"
    assert validated_q["review_reason"] is None

    # Mismatch in totals
    mismatched_q = {
        "grand_total_taxable": Decimal("200.00"), # should be 180
        "grand_total_cgst": Decimal("16.20"),
        "grand_total_sgst": Decimal("16.20"),
        "grand_total_final": Decimal("212.40"),
    }
    validated_mismatched = validate_quotation_totals(mismatched_q, items)
    assert validated_mismatched["extraction_status"] == "needs_review"
    assert "Taxable total mismatch" in validated_mismatched["review_reason"]


def test_pdf_extraction_real_file():
    sample_pdf_path = Path("./input_files/d92c764f-3b4f-463d-b131-d2071fa5d2cc_AIC ENTERP Price list.pdf")
    if not sample_pdf_path.exists():
        sample_pdf_path = Path("./bill_image/AIC ENTERP Price list.pdf")
    
    if not sample_pdf_path.exists():
        pytest.skip("Sample PDF not found in workspace")

    results = extract_pdf_quotation(sample_pdf_path)
    assert len(results) == 3

    # Quotation 1 check
    q1, items1 = results[0]
    assert q1["quotation_no"] == "470114429"
    assert len(items1) == 59
    assert q1["grand_total_taxable"] == Decimal("324537.45")
    assert q1["grand_total_cgst"] == Decimal("28559.51")
    assert q1["grand_total_sgst"] == Decimal("28559.51")
    assert q1["grand_total_final"] == Decimal("381656.00")

    # Quotation 2 check
    q2, items2 = results[1]
    assert q2["quotation_no"] == "470114596"
    assert len(items2) == 69
    assert q2["grand_total_taxable"] == Decimal("188994.85")
    assert q2["grand_total_cgst"] == Decimal("15492.14")
    assert q2["grand_total_sgst"] == Decimal("15492.14")
    assert q2["grand_total_final"] == Decimal("219979.00")

    # Quotation 3 check
    q3, items3 = results[2]
    assert q3["quotation_no"] == "470114575"
    assert len(items3) == 87
    assert q3["grand_total_taxable"] == Decimal("225655.50")
    assert q3["grand_total_cgst"] == Decimal("18504.57")
    assert q3["grand_total_sgst"] == Decimal("18504.57")
    assert q3["grand_total_final"] == Decimal("262665.00")
