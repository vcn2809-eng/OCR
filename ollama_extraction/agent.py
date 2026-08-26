import json
import logging
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from config.settings import OLLAMA_MODEL, OLLAMA_CONFIDENCE_THRESHOLD
from persistence.db import (
    save_raw_document,
    save_extracted_document,
    save_to_quarantine,
    log_stage,
)

logger = logging.getLogger(__name__)


def build_extraction_prompt(text: str) -> str:
    return f"""You are a document analysis assistant. You will be given OCR text
extracted from a scanned document. Do two things:

1. Classify the document into ONE short category (e.g. "invoice",
   "receipt", "resume", "bank_statement", "contract", "letter",
   "report"). If nothing fits well, use "other".

2. Extract every piece of structured data actually present in the
   text as key-value pairs, using short snake_case field names (e.g.
   invoice_number, total_amount, date, sender_name, recipient_name).
   Only include fields that are genuinely present in the text --
   do NOT invent, guess, or fill in data that isn't there.

Respond with ONLY valid JSON, in exactly this shape, and nothing else
-- no explanation, no markdown code fences, just the raw JSON object:

{{
  "document_type": "<category>",
  "confidence": <number between 0 and 1, how confident you are in the classification>,
  "fields": {{ <extracted key-value pairs, or an empty object if none found> }}
}}

Document text:
\"\"\"
{text}
\"\"\"
"""


def call_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    try:
        process = subprocess.Popen(
            ["ollama", "run", model],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output, error = process.communicate(input=prompt)
        if process.returncode != 0:
            raise RuntimeError(error or "Ollama process returned non-zero")
        if not output.strip():
            raise RuntimeError("Ollama response empty")
        return output
    except Exception as e:
        logger.error("Ollama call failed: %s", e)
        raise


class OllamaConnectionError(Exception):
    pass


def parse_response(raw_response: str) -> dict | None:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None
    if "document_type" not in parsed or "fields" not in parsed:
        return None

    parsed.setdefault("confidence", 0.0)
    try:
        parsed["confidence"] = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        parsed["confidence"] = 0.0

    if not isinstance(parsed["fields"], dict):
        return None

    return parsed


def process_text_file(text_file_path: Path, document_id: str | None = None, model: str = OLLAMA_MODEL) -> dict:
    text = text_file_path.read_text(encoding="utf-8", errors="ignore")

    if document_id is None:
        document_id = str(uuid4())

    file_hash = None
    try:
        import hashlib
        file_hash = hashlib.sha256(text_file_path.read_bytes()).hexdigest()
    except Exception:
        file_hash = "unknown"

    try:
        log_stage(document_id, "ocr_to_prompt", "started", "Accepted OCR text for model extraction")
        prompt = build_extraction_prompt(text)
        raw_response = call_ollama(prompt, model=model)
        parsed = parse_response(raw_response)

        if parsed is None:
            save_to_quarantine(document_id, "unknown", {"raw_response": raw_response}, ["unparseable"])
            log_stage(document_id, "ollama_parse", "failed", "Model response was not JSON")
            return {
                "status": "quarantined",
                "document_id": document_id,
                "reason": "unparseable",
            }

        if parsed.get("confidence", 0.0) < OLLAMA_CONFIDENCE_THRESHOLD:
            save_to_quarantine(document_id, "unknown", parsed, ["low_confidence"])
            log_stage(document_id, "ollama_confidence", "quarantined", "Confidence below threshold")
            return {
                "status": "quarantined",
                "document_id": document_id,
                "reason": "low_confidence",
                "document_type": parsed.get("document_type"),
                "confidence": parsed.get("confidence"),
            }

        save_raw_document(document_id, file_hash or "unknown", text_file_path.name, "text", parsed.get("document_type"), {"text": text})
        save_extracted_document(document_id, parsed.get("document_type", "other"), parsed.get("confidence"), parsed.get("fields", {}), model)
        log_stage(document_id, "completed", "success", "Extracted and stored")
        return {
            "status": "success",
            "document_id": document_id,
            "document_type": parsed.get("document_type"),
            "confidence": parsed.get("confidence"),
            "fields": parsed.get("fields", {}),
        }

    except Exception as e:
        log_stage(document_id, "ollama_gateway", "failed", str(e))
        return {
            "status": "failed",
            "document_id": document_id,
            "reason": str(e),
        }
