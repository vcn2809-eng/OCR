"""
Tests for the dynamic Learning Memory Store.
"""
from decimal import Decimal
import pytest
from app.learning.memory_store import (
    record_document_correction,
    get_relevant_few_shots,
    apply_learned_memory_corrections,
    load_memory,
)
from app.quotation_extraction.ai_extractor import build_extraction_prompt, validate_and_reconcile


class TestLearningMemoryStore:
    def test_record_document_correction_learns_vendor_items(self):
        line_items = [
            {"description": "20 \" Wound Filter slim", "rate": 650.0, "qty": 5.0, "hsn_code": "8421", "uom": "Nos"}
        ]
        record_document_correction(
            vendor_name="TEST ION WATER",
            document_no="TEST-001",
            document_type="tax_invoice",
            line_items=line_items
        )
        mem = load_memory()
        assert "TEST ION WATER" in mem["vendors"]
        v_items = mem["vendors"]["TEST ION WATER"]["known_items"]
        assert any("Wound Filter" in it["description"] for it in v_items)

    def test_get_relevant_few_shots_matches_vendor(self):
        shots = get_relevant_few_shots("TAX INVOICE\nM/s. ION SOFT WATER INDIA PRIVATE LIMITED\nNo.42 Mallappa Layout")
        assert len(shots) > 0
        assert any("ION SOFT WATER" in (s.get("vendor_name") or "") for s in shots)

    def test_apply_learned_memory_corrections_fixes_noisy_description(self):
        header = {"vendor_name": "M/s. ION SOFT WATER INDIA PRIVATE LIMITED"}
        # Simulate noisy OCR description
        items = [
            {"description": "20\" WoundFilter slim", "rate": Decimal("650.00"), "qty": Decimal("5.00"), "amount": Decimal("3250.00")}
        ]
        h_out, cleaned = apply_learned_memory_corrections(header, items)
        assert len(cleaned) == 1
        # Description should be normalized to canonical and HSN auto-filled
        assert cleaned[0]["description"] == "20 \" Wound Filter slim"
        assert cleaned[0].get("hsn_code") == "8421"

    def test_build_extraction_prompt_injects_learned_memory(self):
        prompt = build_extraction_prompt("M/s. ION SOFT WATER INDIA PRIVATE LIMITED\nInvoice 060/26-27")
        assert "ACTIVE USER MEMORY" in prompt
        assert "ION SOFT WATER" in prompt
