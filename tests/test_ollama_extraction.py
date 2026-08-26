import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import persistence.db as db
import ollama_extraction.agent as agent


class OllamaExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = str(Path(self.tmp_dir.name) / "test_scanner.db")
        self.original_database_path = db.DATABASE_PATH
        db.DATABASE_PATH = self.test_db_path
        db.initialize_database()

    def tearDown(self):
        db.DATABASE_PATH = self.original_database_path
        self.tmp_dir.cleanup()

    def _fake_ollama_response(self, document_type="invoice", confidence=0.9, fields=None):
        body = {
            "document_type": document_type,
            "confidence": confidence,
            "fields": fields or {"invoice_number": "INV-001", "total_amount": 199.99},
        }
        return json.dumps(body)

    def test_parse_response_valid_json(self):
        raw = json.dumps({"document_type": "invoice", "confidence": 0.9, "fields": {"a": 1}})
        parsed = agent.parse_response(raw)
        self.assertEqual(parsed["document_type"], "invoice")
        self.assertEqual(parsed["confidence"], 0.9)
        self.assertEqual(parsed["fields"], {"a": 1})

    def test_parse_response_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps({"document_type": "invoice", "confidence": 0.9, "fields": {}}) + "\n```"
        parsed = agent.parse_response(raw)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["document_type"], "invoice")

    def test_parse_response_malformed_json_returns_none(self):
        parsed = agent.parse_response("this is not json at all { broken")
        self.assertIsNone(parsed)

    def test_parse_response_missing_required_key_returns_none(self):
        raw = json.dumps({"confidence": 0.9, "fields": {}})
        self.assertIsNone(agent.parse_response(raw))

    def test_parse_response_bad_confidence_type_defaults_safely(self):
        raw = json.dumps({"document_type": "invoice", "confidence": "high", "fields": {}})
        parsed = agent.parse_response(raw)
        self.assertEqual(parsed["confidence"], 0.0)

    def test_process_text_file_success_path(self):
        text_file = Path(self.tmp_dir.name) / "sample.txt"
        text_file.write_text("Invoice #INV-001, Total: $199.99", encoding="utf-8")

        with patch("ollama_extraction.agent.call_ollama", return_value=self._fake_ollama_response()):
            result = agent.process_text_file(text_file, model="fake-model")

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["document_type"], "invoice")

        stored = db.get_extracted_document(result["document_id"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored["extracted_json"]["invoice_number"], "INV-001")

    def test_process_text_file_low_confidence_goes_to_quarantine(self):
        text_file = Path(self.tmp_dir.name) / "sample.txt"
        text_file.write_text("some ambiguous text", encoding="utf-8")

        with patch("ollama_extraction.agent.call_ollama", return_value=self._fake_ollama_response(confidence=0.2)):
            result = agent.process_text_file(text_file, model="fake-model")

        self.assertEqual(result["status"], "quarantined")
        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM quarantine WHERE document_id = ?",
                (result["document_id"],),
            ).fetchone()
        self.assertIsNotNone(row)

    def test_process_text_file_unparseable_response_goes_to_quarantine(self):
        text_file = Path(self.tmp_dir.name) / "sample.txt"
        text_file.write_text("some text", encoding="utf-8")

        with patch("ollama_extraction.agent.call_ollama", return_value="not json"):
            result = agent.process_text_file(text_file, model="fake-model")

        self.assertEqual(result["status"], "quarantined")
        self.assertEqual(result["reason"], "unparseable")

    def test_process_text_file_ollama_unreachable(self):
        text_file = Path(self.tmp_dir.name) / "sample.txt"
        text_file.write_text("some text", encoding="utf-8")

        with patch("ollama_extraction.agent.call_ollama", side_effect=ConnectionError("no server")):
            result = agent.process_text_file(text_file, model="fake-model")

        self.assertEqual(result["status"], "failed")


if __name__ == "__main__":
    unittest.main()
