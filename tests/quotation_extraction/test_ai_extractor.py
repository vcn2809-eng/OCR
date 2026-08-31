"""Tests for the AI-powered universal document extraction engine."""
import json
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.quotation_extraction.ai_extractor import (
    build_extraction_prompt,
    parse_llm_response,
    validate_and_reconcile,
    ai_extract_document,
    _to_decimal,
    split_merged_qty_total,
    split_qty_uom,
    filter_handwritten_rows,
)


class TestBuildExtractionPrompt:
    """Tests for the prompt builder."""

    def test_prompt_contains_ocr_text(self):
        prompt = build_extraction_prompt("TAX INVOICE\nVendor: ABC Corp")
        assert "TAX INVOICE" in prompt
        assert "Vendor: ABC Corp" in prompt

    def test_prompt_contains_schema_instructions(self):
        prompt = build_extraction_prompt("some text")
        assert "vendor_name" in prompt
        assert "line_items" in prompt
        assert "header" in prompt
        assert "description" in prompt
        assert "qty" in prompt
        assert "rate" in prompt
        assert "amount" in prompt

    def test_prompt_truncates_long_text(self):
        long_text = "x" * 20000
        prompt = build_extraction_prompt(long_text)
        assert "[truncated]" in prompt
        # Prompt template itself contains some 'x' chars (e.g. in "extraction", "example").
        # With 20000 x's truncated to 12000, total x count should be < 12200
        assert prompt.count("x") < 12200


class TestParseLlmResponse:
    """Tests for parsing LLM JSON responses."""

    def test_valid_json(self):
        response = json.dumps({
            "header": {"vendor_name": "Test Corp", "document_no": "INV-001"},
            "line_items": [{"line_no": 1, "description": "Widget", "amount": 100.00}]
        })
        result = parse_llm_response(response)
        assert result is not None
        assert result["header"]["vendor_name"] == "Test Corp"
        assert len(result["line_items"]) == 1

    def test_strips_markdown_fences(self):
        response = '```json\n{"header": {"vendor_name": "Test"}, "line_items": [{"line_no": 1, "description": "A", "amount": 50}]}\n```'
        result = parse_llm_response(response)
        assert result is not None
        assert result["header"]["vendor_name"] == "Test"

    def test_extracts_json_from_surrounding_text(self):
        response = 'Here is the data:\n{"header": {"vendor_name": "X"}, "line_items": []}\nDone!'
        result = parse_llm_response(response)
        assert result is not None
        assert result["header"]["vendor_name"] == "X"

    def test_malformed_json_returns_none(self):
        result = parse_llm_response("This is not JSON at all")
        assert result is None

    def test_missing_required_keys_returns_none(self):
        response = json.dumps({"data": "something"})
        result = parse_llm_response(response)
        assert result is None


class TestValidateAndReconcile:
    """Tests for post-LLM arithmetic validation."""

    def test_qty_times_rate_equals_amount(self):
        header = {"grand_total_final": 1000}
        items = [{"description": "Widget", "qty": 10, "rate": 100, "amount": 1000}]
        h, cleaned = validate_and_reconcile(header, items)
        assert cleaned[0]["qty"] == Decimal("10.00")
        assert cleaned[0]["rate"] == Decimal("100.00")
        assert cleaned[0]["gross_amount"] == Decimal("1000.00")

    def test_corrects_qty_from_rate_and_amount(self):
        """When qty × rate != amount, recalculate qty from amount / rate."""
        header = {}
        items = [{"description": "Filter", "qty": 110, "rate": 550, "amount": 5500}]
        _, cleaned = validate_and_reconcile(header, items)
        assert cleaned[0]["qty"] == Decimal("10.00")

    def test_infers_qty_when_zero(self):
        header = {}
        items = [{"description": "Item", "qty": 0, "rate": 50, "amount": 250}]
        _, cleaned = validate_and_reconcile(header, items)
        assert cleaned[0]["qty"] == Decimal("5.00")

    def test_infers_rate_when_zero(self):
        header = {}
        items = [{"description": "Item", "qty": 5, "rate": 0, "amount": 250}]
        _, cleaned = validate_and_reconcile(header, items)
        assert cleaned[0]["rate"] == Decimal("50.00")

    def test_calculates_tax_amounts(self):
        header = {}
        items = [{"description": "Item", "qty": 1, "rate": 1000, "amount": 1000, "cgst_pct": 9, "sgst_pct": 9}]
        _, cleaned = validate_and_reconcile(header, items)
        assert cleaned[0]["cgst_amount"] == Decimal("90.00")
        assert cleaned[0]["sgst_amount"] == Decimal("90.00")

    def test_reconciles_header_totals_from_items(self):
        header = {"grand_total_taxable": 0, "grand_total_final": 0}
        items = [
            {"description": "A", "qty": 1, "rate": 500, "amount": 500},
            {"description": "B", "qty": 1, "rate": 300, "amount": 300},
        ]
        h, _ = validate_and_reconcile(header, items)
        assert h["grand_total_taxable"] == Decimal("800.00")

    def test_handles_null_values_gracefully(self):
        header = {}
        items = [{"description": "Item", "qty": None, "rate": None, "amount": 100}]
        _, cleaned = validate_and_reconcile(header, items)
        assert cleaned[0]["qty"] == Decimal("1.00")
        assert cleaned[0]["gross_amount"] == Decimal("100.00")

    def test_line_numbering(self):
        header = {}
        items = [
            {"description": "A", "amount": 100},
            {"description": "B", "amount": 200},
            {"description": "C", "amount": 300},
        ]
        _, cleaned = validate_and_reconcile(header, items)
        assert [i["line_no"] for i in cleaned] == [1, 2, 3]


class TestToDecimal:
    """Tests for safe decimal conversion."""

    def test_from_int(self):
        assert _to_decimal(100) == Decimal("100.00")

    def test_from_float(self):
        assert _to_decimal(99.99) == Decimal("99.99")

    def test_from_string(self):
        assert _to_decimal("250.50") == Decimal("250.50")

    def test_from_none(self):
        assert _to_decimal(None) == Decimal("0.00")

    def test_from_invalid(self):
        assert _to_decimal("not_a_number") == Decimal("0.00")


class TestAiExtractDocumentWithMock:
    """Tests for the main ai_extract_document entry point using mocked LLM calls."""

    @patch("app.quotation_extraction.ai_extractor.call_llm_for_extraction")
    def test_successful_extraction(self, mock_llm):
        mock_llm.return_value = {
            "header": {
                "vendor_name": "ION SOFT WATER INDIA PRIVATE LIMITED",
                "customer_name": "Helios Construction LLP",
                "document_no": "060/26-27",
                "document_date": "2026-05-21",
                "grand_total_taxable": 29250.00,
                "grand_total_cgst": 2632.50,
                "grand_total_sgst": 2632.50,
                "grand_total_final": 34515.00,
                "currency": "INR",
            },
            "line_items": [
                {"description": "Anti Scalent High concentrate", "qty": 10, "rate": 550, "amount": 5500, "hsn_code": "3824", "uom": "L"},
                {"description": "20\" Wound Filter slim", "qty": 5, "rate": 650, "amount": 3250, "hsn_code": "8421"},
            ],
        }
        result = ai_extract_document("TAX INVOICE\nION SOFT WATER...", "test.jpg")
        assert result is not None
        q_dict, items = result
        assert q_dict["vendor_name"] == "ION SOFT WATER INDIA PRIVATE LIMITED"
        assert len(items) == 2
        assert items[0]["description"] == "Anti Scalent High concentrate"
        assert items[0]["qty"] == Decimal("10.00")
        assert items[0]["rate"] == Decimal("550.00")

    @patch("app.quotation_extraction.ai_extractor.call_llm_for_extraction")
    def test_returns_none_when_llm_fails(self, mock_llm):
        mock_llm.return_value = None
        result = ai_extract_document("some text here", "test.jpg")
        assert result is None

    @patch("app.quotation_extraction.ai_extractor.AI_EXTRACTION_ENABLED", False)
    def test_returns_none_when_disabled(self):
        result = ai_extract_document("some text", "test.jpg")
        assert result is None


    def test_returns_none_for_short_text(self):
        result = ai_extract_document("hi", "test.jpg")
        assert result is None


class TestSplitMergedQtyTotal:
    """Tests for the Mushak-6.3 Bangladesh retail invoice merged Qty+Total column splitter."""

    # ── Clean split: qty × rate = total exactly ───────────────────────────────

    def test_soybean_oil_clean_split(self):
        """6.00383.04 → qty=6.00, total=383.04 (6 × 63.84 = 383.04)."""
        qty, total = split_merged_qty_total("6.00383.04", Decimal("63.84"))
        assert qty == Decimal("6.00")
        assert total == Decimal("383.04")

    def test_milk_powder_clean_split(self):
        """2.00184.62 → qty=2.00, total=184.62 (2 × 92.31 = 184.62)."""
        qty, total = split_merged_qty_total("2.00184.62", Decimal("92.31"))
        assert qty == Decimal("2.00")
        assert total == Decimal("184.62")

    def test_new_alu_clean_split(self):
        """5.00693.25 → qty=5.00, total=693.25 (5 × 138.65 = 693.25)."""
        qty, total = split_merged_qty_total("5.00693.25", Decimal("138.65"))
        assert qty == Decimal("5.00")
        assert total == Decimal("693.25")

    def test_red_amaranth_clean_split(self):
        """4.00307.36 → qty=4.00, total=307.36 (4 × 76.84 = 307.36)."""
        qty, total = split_merged_qty_total("4.00307.36", Decimal("76.84"))
        assert qty == Decimal("4.00")
        assert total == Decimal("307.36")

    # ── Dropped leading digit recovery ────────────────────────────────────────

    def test_indian_spinach_dropped_leading_digit(self):
        """7.002439.85 or OCR-truncated 7.00439.85 → qty=7.00, total=2439.85 (7 × 348.55 = 2439.85)."""
        # Full merged string (leading digit not dropped)
        qty, total = split_merged_qty_total("7.002439.85", Decimal("348.55"))
        assert qty == Decimal("7.00")
        assert total == Decimal("2439.85")

    def test_indian_spinach_ocr_dropped_leading_digit(self):
        """OCR reads 7.00439.85 (leading '2' of 2439.85 absorbed into N.00 boundary)."""
        qty, total = split_merged_qty_total("7.00439.85", Decimal("348.55"))
        assert qty == Decimal("7.00")
        # Should recover: 7 × 348.55 = 2439.85, prepend '2' → 2439.85
        assert total == Decimal("2439.85")

    def test_miniket_rice_ocr_dropped_leading_digit(self):
        """8.001111.20 or OCR 8.00111.20 → qty=8.00, total=1111.20 (8 × 138.90 = 1111.20)."""
        # Full
        qty, total = split_merged_qty_total("8.001111.20", Decimal("138.90"))
        assert qty == Decimal("8.00")
        assert total == Decimal("1111.20")

    def test_miniket_rice_ocr_dropped_leading_digit_short(self):
        """OCR reads 8.00111.20 (leading '1' of 1111.20 merged into .001)."""
        qty, total = split_merged_qty_total("8.00111.20", Decimal("138.90"))
        assert qty == Decimal("8.00")
        assert total == Decimal("1111.20")

    # ── OCR noise: Q/O artefacts ──────────────────────────────────────────────

    def test_ocr_noise_Q_for_0(self):
        """7.QQ439.85 — Q is OCR artefact for 0."""
        qty, total = split_merged_qty_total("7.QQ439.85", Decimal("348.55"))
        assert qty == Decimal("7.00")
        assert total == Decimal("2439.85")

    def test_ocr_noise_uppercase_O_for_0(self):
        """8.OO111.20 — O is OCR artefact for 0."""
        qty, total = split_merged_qty_total("8.OO111.20", Decimal("138.90"))
        assert qty == Decimal("8.00")
        assert total == Decimal("1111.20")

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_no_unit_price_heuristic_split(self):
        """With no unit price, should split at first N.NN boundary if total > qty."""
        qty, total = split_merged_qty_total("3.00527.01", Decimal("0"))
        assert qty == Decimal("3.00")
        assert total == Decimal("527.01")

    def test_single_decimal_not_split(self):
        """A normal number like '63.84' has only one decimal — should not be split."""
        qty, total = split_merged_qty_total("63.84", Decimal("63.84"))
        # No second decimal → fallback: qty=1, total=63.84
        assert qty == Decimal("1.00")
        assert total == Decimal("63.84")

    # ── End-to-end validate_and_reconcile repair ──────────────────────────────

    def test_validate_and_reconcile_repairs_merged_qty_total(self):
        """validate_and_reconcile should recover correct qty/amount from a Mushak-6.3 item
        where the LLM extracted a merged qty+total token as a single large qty value."""
        header = {"vendor_name": "Motijheel Supershop", "document_no": "CM-368066", "grand_total_final": 3762.70}
        # Simulate LLM returning merged "6.00383.04" in the _raw_qty_total field
        items = [
            {
                "description": "Soybean Oil 1L",
                "qty": 6.00383,      # LLM misread the merged token as one big number
                "rate": 63.84,
                "amount": 0.04,     # LLM put the trailing ".04" here
                "_raw_qty_total": "6.00383.04",
            }
        ]
        _, cleaned = validate_and_reconcile(header, items)
        assert len(cleaned) == 1
        assert cleaned[0]["qty"] == Decimal("6.00")
        assert cleaned[0]["gross_amount"] == Decimal("383.04")


class TestSplitQtyUom:
    """Tests for embedded UOM splitting in Indian GST tax invoices."""

    def test_qty_with_L_uom(self):
        """'10 L' → qty=10.00, uom='L'."""
        qty, uom = split_qty_uom("10 L")
        assert qty == Decimal("10.00")
        assert uom == "L"

    def test_qty_with_Nos_uom(self):
        """'5 Nos' → qty=5.00, uom='Nos'."""
        qty, uom = split_qty_uom("5 Nos")
        assert qty == Decimal("5.00")
        assert uom == "Nos"

    def test_qty_with_10_Nos_uom(self):
        """'10 Nos' → qty=10.00, uom='Nos'."""
        qty, uom = split_qty_uom("10 Nos")
        assert qty == Decimal("10.00")
        assert uom == "Nos"

    def test_pure_number_no_uom(self):
        """'100' → qty=100.00, uom=''."""
        qty, uom = split_qty_uom("100")
        assert qty == Decimal("100.00")
        assert uom == ""

    def test_pure_number_int(self):
        """Integer 5 → qty=5.00, uom=''."""
        qty, uom = split_qty_uom(5)
        assert qty == Decimal("5.00")
        assert uom == ""

    def test_qty_with_kg(self):
        """'25 kg' → qty=25.00, uom='kg'."""
        qty, uom = split_qty_uom("25 kg")
        assert qty == Decimal("25.00")
        assert uom == "kg"

    def test_qty_with_Pcs(self):
        """'3 Pcs' → qty=3.00, uom='Pcs'."""
        qty, uom = split_qty_uom("3 Pcs")
        assert qty == Decimal("3.00")
        assert uom == "Pcs"

    def test_none_returns_zero(self):
        """None → qty=0.00, uom=''."""
        qty, uom = split_qty_uom(None)
        assert qty == Decimal("0.00")
        assert uom == ""


class TestFilterHandwrittenRows:
    """Tests for handwritten annotation row filtering in Indian GST invoices."""

    def test_removes_above_items_annotation(self):
        """Row with 'above items' text and no rate/amount should be filtered."""
        items = [
            {"description": "66 above items 07-22/5/2026", "rate": 0, "amount": 0, "hsn_code": ""},
            {"description": "Anti Scalent High concentrate", "rate": 550.0, "amount": 5500.0, "hsn_code": "3824"},
        ]
        result = filter_handwritten_rows(items)
        assert len(result) == 1
        assert result[0]["description"] == "Anti Scalent High concentrate"

    def test_keeps_real_line_items(self):
        """Rows with valid rate/amount are always kept."""
        items = [
            {"description": "20 Wound Filter slim", "rate": 650.0, "amount": 3250.0, "hsn_code": "8421"},
            {"description": "20 Sediment cartridge Filter slim", "rate": 700.0, "amount": 3500.0, "hsn_code": "8421"},
        ]
        result = filter_handwritten_rows(items)
        assert len(result) == 2

    def test_removes_inward_stamp_row(self):
        """Row with 'inward' stamp text and no financials is filtered."""
        items = [
            {"description": "INWARD 21/5/26", "rate": 0, "amount": 0, "hsn_code": ""},
            {"description": "Wound Filter Jumbo", "rate": 800.0, "amount": 8000.0, "hsn_code": "8421"},
        ]
        result = filter_handwritten_rows(items)
        assert len(result) == 1
        assert result[0]["description"] == "Wound Filter Jumbo"

    def test_removes_received_annotation(self):
        """Row with 'received' text and zero financials is filtered."""
        items = [
            {"description": "rcvd 22/5/2026", "rate": None, "amount": None, "hsn_code": ""},
        ]
        result = filter_handwritten_rows(items)
        assert len(result) == 0

    def test_keeps_real_item_with_annotation_keyword_in_description(self):
        """A real item that happens to have a financial value is kept even if description
        contains a keyword like 'received'. Rate/amount overrides the filter."""
        items = [
            {"description": "received goods pack", "rate": 100.0, "amount": 500.0, "hsn_code": ""},
        ]
        result = filter_handwritten_rows(items)
        assert len(result) == 1

    def test_end_to_end_ion_soft_water_invoice(self):
        """Full 5-item ION SOFT WATER invoice with handwritten annotation row in between
        should produce exactly 5 cleaned items."""
        items = [
            {"description": "Anti Scalent High concentrate 100 ML to 100 Litres", "rate": 550.0, "amount": 5500.0, "qty": "10 L",    "hsn_code": "3824", "cgst_pct": 9.0, "sgst_pct": 9.0},
            {"description": "20 Wound Filter slim",                                "rate": 650.0, "amount": 3250.0, "qty": "5 Nos",   "hsn_code": "8421", "cgst_pct": 9.0, "sgst_pct": 9.0},
            {"description": "20 Sediment cartridge Filter slim",                   "rate": 700.0, "amount": 3500.0, "qty": "5 Nos",   "hsn_code": "8421", "cgst_pct": 9.0, "sgst_pct": 9.0},
            {"description": "20 Wound Filter Jumbo",                               "rate": 800.0, "amount": 8000.0, "qty": "10 Nos",  "hsn_code": "8421", "cgst_pct": 9.0, "sgst_pct": 9.0},
            {"description": "20 Sediment cartridge Filter Jumbo",                  "rate": 900.0, "amount": 9000.0, "qty": "10 Nos",  "hsn_code": "8421", "cgst_pct": 9.0, "sgst_pct": 9.0},
            # Handwritten annotation row — must be filtered
            {"description": "66 above items 07-22/5/2026", "rate": 0, "amount": 0, "qty": 0, "hsn_code": ""},
        ]
        header = {
            "vendor_name": "ION SOFT WATER INDIA PRIVATE LIMITED",
            "document_no": "060/26-27",
            "grand_total_taxable": 29250.0,
            "grand_total_cgst": 2632.50,
            "grand_total_sgst": 2632.50,
            "grand_total_final": 34515.0,
        }
        _, cleaned = validate_and_reconcile(header, items)
        # Should have exactly 5 real items (handwritten row filtered)
        assert len(cleaned) == 5
        # Verify qty was split from "10 L" → qty=10
        assert cleaned[0]["qty"] == Decimal("10.00")
        assert cleaned[0]["uom"] == "L"
        # Verify qty "5 Nos" → qty=5
        assert cleaned[1]["qty"] == Decimal("5.00")
        assert cleaned[1]["uom"] == "Nos"
        # Verify subtotal sum = 29250
        gross_sum = sum(i["gross_amount"] for i in cleaned)
        assert gross_sum == Decimal("29250.00")
