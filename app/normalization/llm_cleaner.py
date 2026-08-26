import json
import logging
import re
import subprocess
from typing import Any, List, Dict

try:
    from config.settings import OLLAMA_MODEL
except ImportError:
    OLLAMA_MODEL = "richardyoung/olmocr2:7b-q8"

logger = logging.getLogger(__name__)

SCHEMA_KEYS = [
    "Item Code",
    "Description",
    "Brand",
    "Packing",
    "Qty",
    "Rate",
    "Disc %",
    "Taxable",
    "Final Value",
]


def is_ollama_available(model: str = OLLAMA_MODEL) -> bool:
    """Quick check if Ollama service is running and has the model loaded."""
    try:
        res = subprocess.run(
            ["ollama", "show", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
        )
        return res.returncode == 0
    except Exception:
        return False


def call_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Call Ollama model via subprocess."""
    try:
        process = subprocess.Popen(
            ["ollama", "run", model],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            output, error = process.communicate(input=prompt, timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            output, error = process.communicate()
            raise RuntimeError("Ollama call timed out")

        if process.returncode != 0:
            raise RuntimeError(error or "Ollama process returned non-zero")
        if not output.strip():
            raise RuntimeError("Ollama response empty")
        return output
    except Exception as e:
        logger.error("Ollama call failed: %s", e)
        raise


def clean_catalog_batch_with_llm(rows: List[Dict[str, Any]], model: str = OLLAMA_MODEL) -> List[Dict[str, Any]]:
    """Clean a single batch of catalog rows using local Ollama model."""
    prompt = f"""You are a table data normalization assistant. You will be given a batch of raw table rows extracted via OCR from a chemical catalog.
The raw rows may contain column shifts (e.g., Description values shifted into the Brand column, or columns shifted due to OCR alignment issues) and OCR transcription typos (e.g., "BOOml" instead of "500ml", "_SOOGM" instead of "500GM", "|25.00|" instead of "25.00").

Your task is to:
1. Map the fields of each row to the following structured schema keys:
   - "Item Code" (e.g., catalog/part numbers like "88639-500GM", "19661-500Gms")
   - "Description" (chemical names or item descriptions)
   - "Brand" (brand name, e.g., "SRL", "LOBA", "MERCK", "CDH", "NICE")
   - "Packing" (packaging unit, e.g., "500ML", "500GM", "1 Each")
   - "Qty" (quantity, numeric value)
   - "Rate" (unit price, numeric value)
   - "Disc %" (discount percentage, numeric value)
   - "Taxable" (taxable amount, numeric value)
   - "Final Value" (grand total / final price for the line, numeric value)

2. Fix column shifts: Use the semantic context of each value to place it under the correct schema key. For example, if a chemical description like "Agar Powder" is found in a column that is normally for something else, place it under "Description".
3. Clean transcription typos and vertical line artifacts (like |, }}, ], /). For example:
   - "BOOml" or "SOOml" -> "500ml"
   - "_SOOGM" or "SOOGM" -> "500GM"
   - "|25.00|" or "25.00/" -> "25.00"
   - "1OO" -> "100"

Respond with ONLY a valid JSON array of objects, with each object containing the keys "Item Code", "Description", "Brand", "Packing", "Qty", "Rate", "Disc %", "Taxable", "Final Value".
Do NOT include any markdown code blocks, explanation, or notes. Return only the raw JSON array.

Raw table rows to clean:
{json.dumps(rows, indent=2)}
"""
    raw_response = call_ollama(prompt, model=model)
    cleaned = raw_response.strip()

    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)

    # Extract JSON array
    match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)

    parsed = json.loads(cleaned)
    if not isinstance(parsed, list):
        raise ValueError("LLM response is not a JSON list")

    return parsed


def map_llm_keys(llm_row: Dict[str, Any]) -> Dict[str, Any]:
    """Map LLM-cleaned keys to standard keys and col_X keys, preserving original keys if any."""
    cleaned_row = {}
    normalized_keys = {
        "item code": "Item Code",
        "itemcode": "Item Code",
        "item_code": "Item Code",
        "code": "Item Code",

        "description": "Description",
        "desc": "Description",

        "brand": "Brand",

        "packing": "Packing",
        "pack": "Packing",
        "uom": "Packing",

        "qty": "Qty",
        "quantity": "Qty",

        "rate": "Rate",
        "price": "Rate",
        "unit price": "Rate",

        "disc %": "Disc %",
        "disc": "Disc %",
        "discount": "Disc %",
        "discount %": "Disc %",
        "disc_pct": "Disc %",

        "taxable": "Taxable",
        "taxable amount": "Taxable",
        "taxable value": "Taxable",
        "taxable_value": "Taxable",

        "final value": "Final Value",
        "final_value": "Final Value",
        "final value (₹)": "Final Value",
        "gross amt": "Final Value",
        "gross_amt": "Final Value",
        "amount": "Final Value",
        "total": "Final Value",
    }

    # Initialize all standard keys with None
    for k in SCHEMA_KEYS:
        cleaned_row[k] = None

    for k, v in llm_row.items():
        norm_k = str(k).lower().replace("_", " ").strip()
        canonical_k = normalized_keys.get(norm_k)
        if canonical_k:
            cleaned_row[canonical_k] = v
        else:
            cleaned_row[k] = v

    # Also map to the col_X fields expected by the UI / tests:
    cleaned_row["col_1"] = cleaned_row.get("Item Code")
    cleaned_row["col_47"] = cleaned_row.get("Description")
    cleaned_row["col_48"] = cleaned_row.get("Brand")
    cleaned_row["col_66"] = cleaned_row.get("Packing")
    cleaned_row["col_71"] = cleaned_row.get("Qty")
    cleaned_row["col_14"] = cleaned_row.get("Rate")
    cleaned_row["col_24"] = cleaned_row.get("Disc %")
    cleaned_row["col_26"] = cleaned_row.get("Taxable")
    cleaned_row["col_35"] = cleaned_row.get("Final Value")

    cleaned_row["_normalization_warnings"] = []

    return cleaned_row


def clean_rows_with_llm(
    rows: List[Dict[str, Any]],
    column_types: Dict[str, str],
    batch_size: int = 10,
    model: str = OLLAMA_MODEL,
) -> List[Dict[str, Any]]:
    """Clean all catalog rows in batches using LLM, with fallback to local regex-based cleaning."""
    from app.normalization.agent import normalize_row

    # 1. Quick check if Ollama is available
    if not is_ollama_available(model):
        logger.warning(f"Ollama or model {model} is not available. Falling back to regex cleaning for all rows.")
        return [normalize_row(row, column_types) for row in rows]

    normalized_rows = []

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        try:
            cleaned_batch = clean_catalog_batch_with_llm(batch, model=model)
            if len(cleaned_batch) == len(batch):
                for cleaned_row in cleaned_batch:
                    normalized_rows.append(map_llm_keys(cleaned_row))
            else:
                logger.warning(
                    f"Batch size mismatch (expected {len(batch)}, got {len(cleaned_batch)}). Falling back for this batch."
                )
                for row in batch:
                    normalized_rows.append(normalize_row(row, column_types))
        except Exception as e:
            logger.error(f"Error cleaning batch using LLM: {e}. Falling back to regex cleaning for this batch.")
            for row in batch:
                normalized_rows.append(normalize_row(row, column_types))

    return normalized_rows
