"""
AI-powered universal document extraction engine.

Uses a local Ollama LLM to intelligently parse any noisy OCR text into structured
header + line items JSON. Handles any document type (invoices, quotations, patient
statements, purchase orders, etc.) without hardcoded regex rules or vendor-specific
typo maps.
"""
import json
import logging
import re
import subprocess
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from app.config.settings import (
    AI_EXTRACTION_ENABLED,
    AI_EXTRACTION_MODEL,
    AI_EXTRACTION_FALLBACK_MODEL,
    AI_EXTRACTION_TIMEOUT,
)

logger = logging.getLogger(__name__)


def validate_extracted_json(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Strict JSON schema validator to enforce explicit typed fields and reject quantity leaks (Requirement 2)."""
    if not isinstance(data, dict):
        return False, "Root must be a JSON object"
    if "header" not in data or "line_items" not in data:
        return False, "Missing 'header' or 'line_items' root keys"

    header = data["header"]
    items = data["line_items"]

    if not isinstance(header, dict) or not isinstance(items, list):
        return False, "'header' must be a JSON object and 'line_items' must be a list"

    # Check required header keys
    required_header = ["vendor_name", "document_no", "grand_total_final"]
    for k in required_header:
        if k not in header:
            return False, f"Missing required header field: {k}"

    # Check line items
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            return False, f"Line item at index {idx} must be a JSON object"
        if "description" not in item or "qty" not in item or "rate" not in item:
            return False, f"Line item at index {idx} missing required fields (description, qty, rate)"

        desc = item.get("description")
        if not isinstance(desc, str):
            return False, f"Line item at index {idx} description must be a string"
        
        # Enforce description must not contain leading digits/qty leaking (Requirement 2)
        desc_stripped = desc.strip()
        if desc_stripped:
            first_word = desc_stripped.split()[0]
            if first_word.isdigit() and len(first_word) < 4:
                return False, f"Line item description starts with digit/quantity prefix: '{desc}'"

    return True, None


# ── Prompt Construction ───────────────────────────────────────────────────────

EXTRACTION_PROMPT_TEMPLATE = """You are a VLM data extraction AI. You will receive an image of a scanned document (invoice, quotation, purchase order, etc.) alongside optional OCR text.

Your job is to read the image directly, locate columns, and return clean, structured JSON data conforming strictly to the requested schema.

### CHAIN-OF-VERIFICATION (CoV) INSTRUCTIONS (Requirement 3):
1. For each line item in the table, first locate the Quantity column value alone, then the Description column value alone, then the Unit Price, and then the printed Line Amount.
2. Do NOT infer Quantity from the Description text (e.g. if the cell text is "5 High Lighter" but it is located in the Description column, the quantity is 5, but description is just "High Lighter" without the leading "5").
3. Do NOT merge columns. If quantity and description are printed close to each other, separate them by coordinates.
4. If Qty × Unit Price does not equal the printed Line Amount within rounding tolerance, set "needs_review": true on that row and explain why in a "review_reason" field.
5. Independently compute computed_subtotal = sum(line_items.amount) and compare it against the document's own printed taxable subtotal. Return both values and a boolean "subtotal_reconciled" flag.

### FEW-SHOT EXAMPLES (Requirement 4):

#### Example 1: Qty column printed close to Description (Negative/Avoid example)
- Image shows column Qty has "5", column Description has "High Lighter". Because they are close, naive OCR returns "5 High Lighter".
- WRONG EXTRACTION: {{"qty": 3, "description": "5 High Lighter", "rate": 2859.12, "amount": 14295.60}}
- CORRECT EXTRACTION: {{"qty": 5, "description": "High Lighter", "rate": 2859.12, "amount": 14295.60}}

#### Example 2: Qty column printed close to Description (Example 2)
- Image shows column Qty has "3", column Description has "Voucher Box".
- CORRECT EXTRACTION: {{"qty": 3, "description": "Voucher Box", "rate": 527.01, "amount": 1581.03}}

#### Example 6: Indian GST Tax Invoice — Qty with embedded UOM (e.g. "10 L", "5 Nos")
Some Indian tax invoices (like ION SOFT WATER INDIA type) print the Qty and Unit of Measure in the same column cell.
- Column Qty shows: "10 L"  → qty=10.0, uom="L"
- Column Qty shows: "5 Nos" → qty=5.0, uom="Nos"
- Column Qty shows: "10 Nos" → qty=10.0, uom="Nos"
- WRONG EXTRACTION: {{"qty": "10 L", "uom": null}} or {{"qty": 0, "uom": null}}
- CORRECT EXTRACTION: {{"qty": 10.0, "uom": "L"}} and {{"qty": 5.0, "uom": "Nos"}}
Rule: split on the first whitespace; the left part is qty (number), the right part is uom (string).

#### Example 7: Indian GST Tax Invoice — Handwritten annotation mid-table (CRITICAL: DO NOT EXTRACT)
Some invoices have handwritten stamps or annotations superimposed on the table area.
For example, a document may have cursive handwriting like "66 above items 07-22/5/2026" or a stamp
overlapping the printed rows. These are NOT line items — they are approval notes or delivery annotations.
- If a "row" in the table contains only non-numeric handwritten text with no HSN code, no rate, no amount → SKIP IT entirely.
- WRONG EXTRACTION: adding {{"description": "66 above items", "qty": 0, "rate": 0}} as a line item
- CORRECT EXTRACTION: extract only the 5 printed typed/pre-printed line items; handwritten text is IGNORED.

#### Example 8: Indian GST Tax Invoice — CGST/SGST split at 9%+9%=18% total
Indian GST invoices show CGST and SGST separately, each at half the total GST rate.
- GST Rate column shows "18%" → cgst_pct=9.0, sgst_pct=9.0
- SGST amount = taxable_amount × 9% (e.g. 29250 × 9% = 2632.50)
- CGST amount = taxable_amount × 9% (e.g. 29250 × 9% = 2632.50)
- Total = Taxable + CGST + SGST (e.g. 29250 + 2632.50 + 2632.50 = 34515.00)
- Do NOT confuse IGST (inter-state, 0 if within same state) with CGST+SGST.

#### Example 9: Indian GST Tax Invoice — complete worked example (ION SOFT WATER type)
Document: Tax Invoice 060/26-27, Vendor: ION SOFT WATER INDIA PVT LTD (GSTIN 29AACCI4435N1Z6)
Table has columns: SI No | Description of Goods | HSN CODE | GST Rate | Qty | Rate | AMOUNT
- Row 1: "Anti Scalent High concentrate 100 ML to 100 Litres" | HSN=3824 | GST=18% | Qty="10 L" | Rate=550.00 | Amount=5500.00
- Row 2: "20 Wound Filter slim" | HSN=8421 | GST=18% | Qty="5 Nos" | Rate=650.00 | Amount=3250.00
- Row 3: "20 Sediment cartridge Filter slim" | HSN=8421 | GST=18% | Qty="5 Nos" | Rate=700.00 | Amount=3500.00
- Row 4: "20 Wound Filter Jumbo" | HSN=8421 | GST=18% | Qty="10 Nos" | Rate=800.00 | Amount=8000.00
- Row 5: "20 Sediment cartridge Filter Jumbo" | HSN=8421 | GST=18% | Qty="10 Nos" | Rate=900.00 | Amount=9000.00
- Total row + Handwritten annotation → SKIP handwriting
- Footer totals: Taxable=29250.00, SGST=2632.50, CGST=2632.50, IGST=0.00, Grand Total=34515.00
CORRECT EXTRACTION (partial): line_items count=5, grand_total_taxable=29250.00, grand_total_cgst=2632.50, grand_total_sgst=2632.50, grand_total_final=34515.00

#### Example 10: POS Thermal Utility Bill / Diagnostic Money Receipt (Fast Net Billing / Lifecare / Broadband Point type)
Document: UTILITY SERVICE BILL / DIAGNOSTIC MONEY RECEIPT with columns Item | Qty | Rate | Amount
Footer has:
- Sub Total: 31,491.60  → grand_total_taxable: 31491.60
- Discount: 3,149.16    → total_discount: 3149.16
- VAT (7.5%): 2,125.68  → grand_total_sgst: 2125.68 (or total VAT)
- Rounding: -0.36
- NET PAYABLE: 30,467.76 → grand_total_final: 30467.76
Rule for Net Payable formula: Net Payable = Sub Total - Discount + VAT + Rounding
(31491.60 - 3149.16 + 2125.68 - 0.36 = 30467.76 ✓)
CORRECT EXTRACTION: grand_total_taxable=31491.60, total_discount=3149.16, grand_total_sgst=2125.68, grand_total_final=30467.76

#### Example 11: Corporate B2B Service Bills (DEBIT NOTE, WORK COMPLETION BILL, BILL OF SERVICES, PROCUREMENT SUPPORT BILL)
Document types may use non-standard column titles for Quantity, Rate, and Amount:
- Qty column headers: "NOS.", "Measurement", "UNITS", "No.", "Qty"  → extract into "qty"
- Rate column headers: "UNIT VALUE", "Rate", "CHARGE", "Charge Rate", "Unit Price"  → extract into "rate"
- Amount column headers: "DEBIT AMOUNT", "Bill Amount", "VALUE", "Amount"  → extract into "amount"
- Vendor label variations: "From", "Contractor Details", "Maintenance Vendor / Issued By", "Procurement Agent", "Service Platform"
- Buyer label variations: "To", "Employer / Client", "Site / Issued To", "Principal / Buyer", "Subscriber"
- Footer total variations: "Total Payable", "Amount To Be Paid", "Total Bill", "Net Payable", "Payable Balance"
CORRECT EXTRACTION RULE: Map all quantity variations to "qty", rate variations to "rate", and amount variations to "amount".
Example: {{"description": "Networking support chrg supply and configuration", "qty": 6.0, "rate": 2982.00, "amount": 17892.00}}




### STRUCTURED OUTPUT JSON SCHEMA (Requirement 2):
Return ONLY valid JSON matching this exact structure:
{{
  "header": {{
    "vendor_name": "string or null - the seller/vendor/supplier company name",
    "vendor_gstin": "string or null - vendor's GSTIN number",
    "customer_name": "string or null - the buyer/customer name",
    "customer_gstin": "string or null - customer's GSTIN number",
    "document_no": "string or null - invoice/quotation/PO number",
    "document_date": "string or null - YYYY-MM-DD",
    "grand_total_taxable": "number or null - printed subtotal/gross before discount/tax",
    "total_discount": "number or null - total discount",
    "grand_total_cgst": "number or null - cgst tax",
    "grand_total_sgst": "number or null - sgst/vat tax",
    "grand_total_final": "number or null - final net total payable",
    "payment_terms": "string or null",
    "currency": "string - default INR",
    "computed_subtotal": 0.0,
    "printed_subtotal": 0.0,
    "subtotal_reconciled": false
  }},
  "line_items": [
    {{
      "line_no": 1,
      "item_code": "string or null - product/catalog code",
      "description": "string - clean description (MUST NOT start with quantity digits)",
      "qty": 0.0,
      "uom": "string or null",
      "rate": 0.0,
      "amount": 0.0,
      "discount_pct": 0.0,
      "discount_amount": 0.0,
      "cgst_pct": 0.0,
      "sgst_pct": 0.0,
      "needs_review": false,
      "review_reason": "string or null - explanation on mismatch"
    }}
  ]
}}

--- RAW OCR TEXT (AS SECONDARY FALLBACK SIGNAL) ---
{ocr_text}
--- END OCR TEXT ---

### ADDITIONAL FEW-SHOT EXAMPLES — MERGED QTY+TOTAL COLUMN (Mushak-6.3 / Bangladesh retail invoices):

Some document types (e.g. Mushak-6.3, Bangladesh VAT retail invoices) print the Qty and Total columns
with no whitespace separator between them. The OCR will merge them into a single token.

Pattern: the merged cell looks like one long number `X.YY Z.ZZ` or `X.YYZZ.ZZ`
Rule: split at the first `.` followed by exactly 2 digits that is followed IMMEDIATELY by more digits
(indicating the total's integer part has been glued on):

#### Example 3: Mushak-6.3 — merged Qty+Total (Negative/Avoid example)
- OCR raw text for Qty+Total columns together: "6.00383.04"
- This means Qty=6.00, Total=383.04  (unit_price=63.84, so 6 × 63.84 = 383.04 ✓)
- WRONG EXTRACTION: {{"qty": 6.00383, "rate": 63.84, "amount": 0.04}}
- CORRECT EXTRACTION: {{"qty": 6.00, "description": "Soybean Oil 1L", "rate": 63.84, "amount": 383.04}}

#### Example 4: Mushak-6.3 — merged Qty+Total with leading digit absorbed
- OCR raw text: "7.QQ439.85" (Q is OCR artefact for 0, so real string is "7.002439.85" with leading "2" dropped)
- The unit price is 348.55, so 7 × 348.55 = 2439.85
- CORRECT EXTRACTION: {{"qty": 7.00, "description": "Indian Spinach", "rate": 348.55, "amount": 2439.85}}
- How to detect: when qty × unit_price ≠ printed_total, try multiplying by 10 — if that matches, a leading digit was dropped from the total.

#### Example 5: Mushak-6.3 — another merged case
- OCR raw text: "8.QQ111.20" (= 8.001111.20, leading "1" of 1111.20 dropped)
- unit_price=138.90, so 8 × 138.90 = 1111.20
- CORRECT EXTRACTION: {{"qty": 8.00, "description": "Miniket Rice 5kg", "rate": 138.90, "amount": 1111.20}}

IMPORTANT: For all documents with this pattern:
1. Parse the Qty column independently.
2. Parse the Total column independently (it may have had its leading digit dropped if it starts with 1, 2, etc.)
3. ALWAYS verify: qty × unit_price ≈ total (within 0.05 tolerance). If not, try: (total + leading_digit*10^len(total)) / qty.

Extract the structured data as JSON:"""



def build_extraction_prompt(ocr_text: str) -> str:
    """Construct the LLM prompt with the raw OCR text embedded and dynamic learned few-shots.

    Args:
        ocr_text: Raw OCR text from the document.

    Returns:
        Complete prompt string ready to send to the LLM.
    """
    # Retrieve dynamic few-shot examples from user corrections & learned memory
    dynamic_context = ""
    try:
        from app.learning.memory_store import get_relevant_few_shots
        learned_shots = get_relevant_few_shots(ocr_text)
        if learned_shots:
            dynamic_context = "\n\n### ACTIVE USER MEMORY (VERIFIED TEMPLATES FROM PAST CORRECTIONS):\n"
            for shot in learned_shots:
                v_name = shot.get("vendor_name") or "Verified Document"
                dynamic_context += f"- Vendor: '{v_name}' (Type: {shot.get('document_type', '')})\n"
                for item in shot.get("sample_items", []):
                    desc = item.get("description")
                    qty = item.get("qty")
                    rate = item.get("rate")
                    amt = item.get("amount")
                    hsn = item.get("hsn_code")
                    uom = item.get("uom")
                    dynamic_context += f"  * Line: \"{desc}\" | Qty: {qty} {uom} | Rate: {rate} | Amount: {amt} | HSN: {hsn}\n"
    except Exception as e:
        logger.debug(f"Dynamic few-shot retrieval skipped: {e}")

    # Truncate extremely long texts to stay within model context window
    max_chars = 12000
    if len(ocr_text) > max_chars:
        ocr_text = ocr_text[:max_chars] + "\n... [truncated]"

    formatted_prompt = EXTRACTION_PROMPT_TEMPLATE.format(ocr_text=ocr_text)
    if dynamic_context:
        formatted_prompt = dynamic_context + "\n" + formatted_prompt

    return formatted_prompt



# ── LLM Communication ────────────────────────────────────────────────────────

def is_ollama_available(model: str) -> bool:
    """Check if Ollama is running and has the specified model."""
    import urllib.request
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in body.get("models", [])]
                if any(model.lower() in m.lower() for m in models):
                    return True
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["ollama", "show", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False



def call_ollama(prompt: str, model: str, timeout: int, images: Optional[List[str]] = None) -> str:
    """Call an Ollama model via HTTP JSON API with optional visual image inputs."""
    import urllib.request

    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False
        }
        if images:
            payload["images"] = images

        req_data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=req_data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_json = json.loads(response.read().decode("utf-8"))
            output = res_json.get("response", "")
            if output.strip():
                return output
            raise RuntimeError("Ollama returned empty response")
    except Exception as http_err:
        if "timed out" in str(http_err).lower() or "timeout" in str(http_err).lower():
            raise RuntimeError(f"Ollama call timed out after {timeout}s")
        logger.warning(f"Ollama HTTP JSON API call failed ({http_err}), falling back to CLI subprocess.")

    # CLI subprocess fallback (does not support images)
    process = subprocess.Popen(
        ["ollama", "run", model],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        output, error = process.communicate(input=prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise RuntimeError(f"Ollama call timed out after {timeout}s")

    if process.returncode != 0:
        raise RuntimeError(f"Ollama returned non-zero exit code: {error}")
    if not output.strip():
        raise RuntimeError("Ollama returned empty response")
    return output


def call_llm_for_extraction(ocr_text: str, images: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Call the LLM/VLM to extract structured data.

    Tries the primary model first (llama3), then falls back to the
    secondary model (olmocr2). Returns None if all attempts fail.

    Args:
        ocr_text: Raw OCR text from the document.
        images: Optional list of base64-encoded image strings.

    Returns:
        Parsed JSON dict with 'header' and 'line_items' keys, or None on failure.
    """
    prompt = build_extraction_prompt(ocr_text)

    models_to_try = [AI_EXTRACTION_MODEL]
    if AI_EXTRACTION_FALLBACK_MODEL != AI_EXTRACTION_MODEL:
        models_to_try.append(AI_EXTRACTION_FALLBACK_MODEL)

    for model in models_to_try:
        if not is_ollama_available(model):
            logger.warning(f"Ollama model '{model}' not available, skipping.")
            continue

        logger.info(f"Calling Ollama '{model}' for AI extraction...")
        try:
            # Only send images to multimodal-capable models or if images is provided
            # Note: olmocr2 is specifically visual
            send_imgs = images if ("olmocr" in model or "llava" in model or "minicpm" in model) else None
            raw_response = call_ollama(prompt, model, AI_EXTRACTION_TIMEOUT, images=send_imgs)
            parsed = parse_llm_response(raw_response)
            if parsed is not None:
                is_valid, err_reason = validate_extracted_json(parsed)
                if is_valid:
                    return parsed
                else:
                    logger.warning(f"Extracted JSON failed schema validation: {err_reason}. Retrying without images...")
                    if send_imgs:
                        raw_response_retry = call_ollama(prompt, model, AI_EXTRACTION_TIMEOUT, images=None)
                        parsed_retry = parse_llm_response(raw_response_retry)
                        if parsed_retry is not None:
                            is_valid_retry, _ = validate_extracted_json(parsed_retry)
                            if is_valid_retry:
                                return parsed_retry
            else:
                logger.warning(f"Model '{model}' returned unparseable response, trying next.")
        except Exception as e:
            logger.warning(f"Ollama '{model}' call failed: {e}")

    logger.error("All LLM extraction attempts failed.")
    return None


# ── Response Parsing ──────────────────────────────────────────────────────────

def parse_llm_response(raw_response: str) -> Optional[Dict[str, Any]]:
    """Parse the LLM's raw text response into a structured dict.

    Handles markdown code fences, leading/trailing text, and partial/flat JSON structures.
    """
    text = raw_response.strip()

    # Strip markdown code fences
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```\s*$', '', text)
    text = text.strip()

    # Try direct parse
    result = _try_parse_json(text)
    if result is not None:
        return result

    # Try regex match for outermost JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        result = _try_parse_json(match.group(0))
        if result is not None:
            return result

    logger.warning("Could not parse JSON from LLM response.")
    return None


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to parse text as JSON and validate / normalize required keys."""
    try:
        data = json.loads(text)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            data = data[0]

        if isinstance(data, dict):
            # Case 1: Standard nested format {"header": {...}, "line_items": [...]}
            if "header" in data and any(k in data for k in ["line_items", "items", "products", "lines"]):
                items = data.get("line_items") or data.get("items") or data.get("products") or data.get("lines") or []
                return {"header": data.get("header", {}), "line_items": items}

            # Case 2: Flat format where header fields and line_items are at top-level
            line_item_keys = [k for k in ["line_items", "items", "products", "table_items", "lines"] if k in data]
            if line_item_keys:
                key = line_item_keys[0]
                items = data[key] if isinstance(data[key], list) else []
                header = {k: v for k, v in data.items() if k != key}
                return {"header": header, "line_items": items}
    except (json.JSONDecodeError, ValueError):
        pass
    return None


# ── Merged-Column Pattern Handler (Mushak-6.3 / Bangladesh retail) ────────────

def split_merged_qty_total(raw_qty_total: str, unit_price: Decimal) -> tuple[Decimal, Decimal]:
    """Deterministically split a merged Qty+Total OCR token into (qty, total).

    In Mushak-6.3 Bangladesh retail invoices, the Qty and Total columns are
    printed without any whitespace separator, causing OCR to produce tokens like:
        "6.00383.04"   →  qty=6.00, total=383.04  (6 × 63.84 = 383.04 ✓)
        "7.002439.85"  →  qty=7.00, total=2439.85
        "8.001111.20"  →  qty=8.00, total=1111.20

    Additionally, when the merged total has a leading digit that gets absorbed by
    the "N.00" qty decimal segment, the OCR result may drop it:
        "7.QQ439.85" (where QQ=00) → actual is qty=7, total=2439.85

    Strategy:
    1. Try every possible split point M.NN | rest, where M.NN looks like a qty
       (integer.2-decimal-places), and validate: M.NN × unit_price ≈ rest.
    2. If step 1 fails and unit_price > 0, try recovering the dropped leading
       digit of total by prepending 1-9 and repeating the check.
    3. If nothing resolves, fall back to returning the raw string parsed as total
       with qty=1.

    Args:
        raw_qty_total: The merged OCR string containing both qty and total.
        unit_price: The unit price for arithmetic cross-validation.

    Returns:
        Tuple of (qty, total) as Decimal values.
    """
    # Normalise: strip commas/spaces
    raw = re.sub(r"[,\s]", "", raw_qty_total)
    # Replace OCR noise characters Q/O/q/o with 0 when they appear between digits OR after a dot
    # (handles cases like "7.QQ439.85" where the dot precedes QQ, not a digit)
    raw = re.sub(r"[QqOo]", "0", raw)
    # Strip any remaining non-numeric/non-dot chars
    raw = re.sub(r"[^0-9.]", "", raw)

    # Find all decimal points
    dot_positions = [i for i, c in enumerate(raw) if c == "."]

    if len(dot_positions) >= 2:
        # Try each first-dot as the qty/total boundary
        for dot_idx in dot_positions[:-1]:
            # qty candidate: everything up to 2 chars after this dot
            qty_end = dot_idx + 3  # e.g. "6.00" = 4 chars, dot at 1 so end=4
            if qty_end > len(raw):
                continue
            qty_str = raw[:qty_end]
            total_str = raw[qty_end:]
            if not total_str:
                continue
            try:
                qty_val = Decimal(qty_str)
                total_val = Decimal(total_str)
            except Exception:
                continue

            if qty_val <= 0 or total_val <= 0:
                continue

            # Primary check: qty × unit_price ≈ total
            if unit_price > 0:
                expected = (qty_val * unit_price).quantize(Decimal("0.01"))
                if abs(expected - total_val) <= Decimal("0.10"):
                    return qty_val, total_val

                # Secondary check: leading digit was dropped from total — try prepending 1-9
                for leading in range(1, 10):
                    total_candidate = Decimal(f"{leading}{total_str}")
                    # Re-compute expected with qty_val (not re-using previous expected)
                    expected2 = (qty_val * unit_price).quantize(Decimal("0.01"))
                    if abs(expected2 - total_candidate) <= Decimal("0.10"):
                        return qty_val, total_candidate


            else:
                # No unit price: accept first valid split where qty looks like a small integer
                if qty_val < 10000 and total_val > qty_val:
                    return qty_val, total_val

    # No usable split found — return entire string as total with qty=1
    try:
        return Decimal("1.00"), Decimal(raw.replace(",", ""))
    except Exception:
        return Decimal("1.00"), Decimal("0.00")



def _to_decimal(val: Any) -> Decimal:
    """Safely convert a value to Decimal."""
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


# ── Indian GST Tax Invoice helpers ────────────────────────────────────────────

# Known UOM tokens that may appear embedded in the qty cell of Indian invoices
_KNOWN_UOMS = frozenset([
    "nos", "no", "pcs", "pc", "l", "ltr", "ltrs", "litre", "litres",
    "kg", "kgs", "gm", "gms", "g", "ml", "mtr", "mtrs", "m",
    "box", "boxes", "set", "sets", "roll", "rolls", "bag", "bags",
    "sqft", "sqm", "rft", "unit", "units", "pair", "pairs", "can", "cans",
])


def split_qty_uom(raw_qty: Any) -> tuple[Decimal, str]:
    """Split a combined qty+UOM cell (e.g. '10 L', '5 Nos') into (qty, uom).

    Indian tax invoices frequently print quantity and unit of measure in the
    same table cell without a dedicated UOM column. Examples:
        '10 L'   → (Decimal('10.00'), 'L')
        '5 Nos'  → (Decimal('5.00'), 'Nos')
        '10 Nos' → (Decimal('10.00'), 'Nos')
        100      → (Decimal('100.00'), '')   # already a number, no UOM

    Args:
        raw_qty: Raw qty value from the LLM (string or number).

    Returns:
        Tuple of (qty as Decimal, uom as str).
    """
    if raw_qty is None:
        return Decimal("0.00"), ""

    raw = str(raw_qty).strip()

    # If it's a pure number already, just parse it
    try:
        return Decimal(raw).quantize(Decimal("0.01")), ""
    except (InvalidOperation, ValueError):
        pass

    # Try "number uom" pattern
    parts = raw.split(None, 1)   # split on first whitespace
    if len(parts) == 2:
        qty_str, uom_str = parts
        if uom_str.lower() in _KNOWN_UOMS or uom_str.isalpha():
            try:
                qty_val = Decimal(qty_str.replace(",", "")).quantize(Decimal("0.01"))
                return qty_val, uom_str
            except (InvalidOperation, ValueError):
                pass

    # Fallback: try to parse whatever numeric portion is present
    num_match = re.match(r"^([\d,]+\.?\d*)", raw)
    if num_match:
        try:
            qty_val = Decimal(num_match.group(1).replace(",", "")).quantize(Decimal("0.01"))
            remainder = raw[num_match.end():].strip()
            return qty_val, remainder
        except (InvalidOperation, ValueError):
            pass

    return Decimal("0.00"), raw


def filter_handwritten_rows(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove handwritten annotation pseudo-rows that OCR incorrectly treats as line items.

    In scanned Indian GST invoices, handwritten stamps or annotations
    (e.g. approval marks, 'above items' notes, delivery dates) occasionally
    get interpreted by OCR as an additional table row. These rows have:
    - No HSN code (empty / null)
    - No numeric rate
    - No numeric amount (or amount=0)
    - Description contains non-product handwritten text patterns

    Args:
        items: Raw list of line item dicts from LLM.

    Returns:
        Filtered list with handwritten rows removed.
    """
    # Pattern: handwritten annotation rows typically contain these tokens
    _handwriting_indicators = re.compile(
        r"\b(above|items?|rcd|rcvd|received|inward|sign|date|time|sr\.?\s*no|"
        r"serial|checked|verified|approved|authority|stamp|chq|ref|delivery)\b",
        re.IGNORECASE
    )

    cleaned = []
    for item in items:
        rate = _to_decimal(item.get("rate"))
        amount = _to_decimal(item.get("amount"))
        hsn = str(item.get("hsn_code") or "").strip()
        desc = str(item.get("description") or "").strip()

        # Keep if it has real financials
        if rate > Decimal("0.00") or amount > Decimal("0.00"):
            cleaned.append(item)
            continue

        # Drop if no financials AND description looks handwritten/annotation-like
        if _handwriting_indicators.search(desc):
            logger.info(f"Filtered handwritten annotation row: '{desc}'")
            continue

        # Drop if description is very short and has no numeric content at all
        if len(desc) < 4 and not any(c.isdigit() for c in desc):
            logger.info(f"Filtered empty/noise row: '{desc}'")
            continue

        cleaned.append(item)

    return cleaned




def validate_and_reconcile(
    header: Dict[str, Any], items: List[Dict[str, Any]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Post-LLM arithmetic validation and reconciliation.

    Ensures qty × rate = amount for each line item, and that header totals
    are consistent with the sum of line items.

    Args:
        header: Raw header dict from LLM.
        items: Raw line items list from LLM.

    Returns:
        Tuple of (cleaned_header, cleaned_items).
    """
    cleaned_items = []
    line_no = 1

    # ── Apply learned memory corrections (vendor catalog & verified items) ───
    try:
        from app.learning.memory_store import apply_learned_memory_corrections
        header, items = apply_learned_memory_corrections(header, items)
    except Exception as e:
        logger.debug(f"Learned memory correction skipped: {e}")

    # ── Pre-processing: remove handwritten annotation pseudo-rows ────────────
    items = filter_handwritten_rows(items)


    for item in items:
        # ── Split embedded UOM from qty field (Indian GST invoice style) ────
        raw_qty_val = item.get("qty")
        if isinstance(raw_qty_val, str) and not raw_qty_val.replace(".", "").replace(",", "").isdigit():
            parsed_qty, parsed_uom = split_qty_uom(raw_qty_val)
            if parsed_uom and not item.get("uom"):
                item = dict(item)   # copy to avoid mutating shared dict
                item["qty"] = float(parsed_qty)
                item["uom"] = parsed_uom

        qty = _to_decimal(item.get("qty"))
        rate = _to_decimal(item.get("rate"))
        amount = _to_decimal(item.get("amount"))


        # Column swap detection (e.g. rate put in qty column or amount put in rate column)
        # Guard: skip swap when _raw_qty_total is provided — merged-token recovery will handle it.
        has_merged_token = bool(item.get("_raw_qty_total", ""))
        if not has_merged_token:
            if rate > amount and amount > Decimal("0.00"):
                # Only swap if swap would give a consistent qty × new_rate ≈ new_amount
                swapped_ok = qty > 0 and abs((qty * amount) - rate) <= Decimal("0.50")
                if swapped_ok:
                    rate, amount = amount, rate
            if qty > amount and amount > Decimal("0.00") and qty > Decimal("100.00"):
                qty, amount = amount, qty


        desc = (item.get("description") or "").strip()
        # Self-correction: check if description starts with a number N such that N * rate == amount
        import re
        desc_match = re.match(r"^(\d+)\s+(.+)$", desc)
        if desc_match:
            n_val = Decimal(desc_match.group(1))
            rem_desc = desc_match.group(2)
            if rate > 0 and amount > 0:
                if abs((n_val * rate) - amount) <= Decimal("0.05"):
                    qty = n_val
                    desc = rem_desc
            elif rate > 0 and qty <= 0:
                qty = n_val
                desc = rem_desc

        # Arithmetic reconciliation: qty × rate = amount
        if qty > 0 and rate > 0:
            expected = (qty * rate).quantize(Decimal("0.01"))
            if amount == Decimal("0.00"):
                amount = expected
            elif abs(expected - amount) > Decimal("0.05"):
                # ── Mushak-6.3 merged Qty+Total recovery ──────────────────────
                # If qty looks abnormally large (e.g. 6.00383 from "6.00383.04")
                # or if qty × rate is wildly off, attempt split recovery.
                raw_qty_str = str(item.get("qty", ""))
                raw_amt_str = str(item.get("amount", ""))

                # Build merged candidate:
                # LLM split "6.00383.04" into qty="6.00383", amount="0.04"
                # To reconstruct, we need "6.00383.04"
                # Strategy: qty_str + "." + decimal_part_of_amount
                merged_candidate = None
                if "." in raw_qty_str:
                    # Get just the decimal part of the amount (after the leading "0.")
                    # "0.04" → "04", then reconstruct qty_str + "." + "04" = "6.00383.04"
                    amt_parts = raw_amt_str.split(".")
                    if len(amt_parts) == 2:
                        merged_candidate = raw_qty_str + "." + amt_parts[1]

                # Also try with the explicit _raw_qty_total annotation from item if available
                raw_merged = item.get("_raw_qty_total", "")
                for candidate in filter(None, [raw_merged, merged_candidate]):
                    if candidate.count(".") >= 2:
                        split_qty, split_total = split_merged_qty_total(candidate, rate)
                        if split_qty > 0 and split_total > 0:
                            check = (split_qty * rate).quantize(Decimal("0.01"))
                            if abs(check - split_total) <= Decimal("0.10"):
                                qty = split_qty
                                amount = split_total
                                break


                # If still mismatched: if amount / rate is a clean whole number infer correct qty
                expected2 = (qty * rate).quantize(Decimal("0.01"))
                if abs(expected2 - amount) > Decimal("0.05"):
                    if rate > 0 and (amount / rate) == (amount / rate).to_integral_value():
                        qty = (amount / rate).quantize(Decimal("0.01"))
                    else:
                        amount = expected2

        elif amount > 0 and rate > 0 and qty == 0:
            qty = (amount / rate).quantize(Decimal("0.01"))
        elif amount > 0 and qty > 0 and rate == 0:
            rate = (amount / qty).quantize(Decimal("0.01"))

        cgst_pct = _to_decimal(item.get("cgst_pct"))
        sgst_pct = _to_decimal(item.get("sgst_pct"))
        cgst_amount = (amount * cgst_pct / Decimal("100")).quantize(Decimal("0.01")) if cgst_pct > 0 else Decimal("0.00")
        sgst_amount = (amount * sgst_pct / Decimal("100")).quantize(Decimal("0.01")) if sgst_pct > 0 else Decimal("0.00")

        discount_pct = _to_decimal(item.get("discount_pct"))
        discount_amount = _to_decimal(item.get("discount_amount"))
        if discount_amount == Decimal("0.00") and discount_pct > Decimal("0.00"):
            discount_amount = (amount * discount_pct / Decimal("100")).quantize(Decimal("0.01"))
        elif discount_pct == Decimal("0.00") and discount_amount > Decimal("0.00") and amount > Decimal("0.00"):
            discount_pct = (discount_amount / amount * Decimal("100")).quantize(Decimal("0.01"))

        taxable_amount = amount - discount_amount if amount >= discount_amount else amount

        cleaned_items.append({
            "line_no": line_no,
            "item_code": item.get("item_code") or f"ITEM-{line_no}",
            "description": desc,
            "hsn_code": item.get("hsn_code") or "",
            "brand": "",
            "uom": item.get("uom") or "Nos",
            "packing": "",
            "qty": qty if qty > 0 else Decimal("1.00"),
            "rate": rate,
            "gross_amount": amount,
            "discount_pct": discount_pct,
            "discount_amount": discount_amount,
            "taxable_amount": taxable_amount,
            "cgst_pct": cgst_pct,
            "cgst_amount": cgst_amount,
            "sgst_pct": sgst_pct,
            "sgst_amount": sgst_amount,
            "final_value": taxable_amount + cgst_amount + sgst_amount,
            "status_eta": "In Stock",
            "item_date": item.get("item_date"),
        })
        line_no += 1

    # Reconcile header totals from line items if missing
    taxable_sum = sum(i["taxable_amount"] for i in cleaned_items)
    cgst_sum = sum(i["cgst_amount"] for i in cleaned_items)
    sgst_sum = sum(i["sgst_amount"] for i in cleaned_items)

    h_taxable = _to_decimal(header.get("grand_total_taxable"))
    h_cgst = _to_decimal(header.get("grand_total_cgst"))
    h_sgst = _to_decimal(header.get("grand_total_sgst"))
    h_final = _to_decimal(header.get("grand_total_final"))

    # If header totals are zero/missing, compute from items
    if h_taxable == Decimal("0.00") and taxable_sum > 0:
        header["grand_total_taxable"] = taxable_sum
    if h_cgst == Decimal("0.00") and cgst_sum > 0:
        header["grand_total_cgst"] = cgst_sum
    if h_sgst == Decimal("0.00") and sgst_sum > 0:
        header["grand_total_sgst"] = sgst_sum
    if h_final == Decimal("0.00"):
        header["grand_total_final"] = (
            _to_decimal(header.get("grand_total_taxable", taxable_sum))
            + _to_decimal(header.get("grand_total_cgst", cgst_sum))
            + _to_decimal(header.get("grand_total_sgst", sgst_sum))
        )

    return header, cleaned_items


# ── Main Entry Point ──────────────────────────────────────────────────────────

def _encode_image_to_base64(img) -> str:
    """Encode PIL or numpy image into base64 JPEG string."""
    from PIL import Image
    import base64
    from io import BytesIO
    from pathlib import Path
    
    buffered = BytesIO()
    if hasattr(img, "shape"): # numpy array
        pil_img = Image.fromarray(img)
    elif isinstance(img, Image.Image):
        pil_img = img
    elif isinstance(img, (str, Path)):
        pil_img = Image.open(img)
    else:
        pil_img = img
        
    pil_img.convert("RGB").save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def ai_extract_document(
    ocr_text: str, source_file: str, images: Optional[List[Any]] = None
) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """AI/VLM-powered universal document extraction.

    Sends raw OCR text and optional visual images to local Ollama VLM/LLM.
    The response is then validated and reconciled for arithmetic consistency.

    Args:
        ocr_text: Raw OCR text from the document.
        source_file: Name of the source file for metadata.
        images: Optional list of PIL/numpy page images.

    Returns:
        Tuple of (quotation_dict, line_items) ready for DB persistence,
        or None if AI extraction is disabled or fails entirely.
    """
    if not AI_EXTRACTION_ENABLED:
        logger.info("AI extraction is disabled via settings.")
        return None

    if not ocr_text or len(ocr_text.strip()) < 20:
        logger.warning("OCR text too short for AI extraction, skipping.")
        return None

    base64_imgs = None
    if images:
        try:
            base64_imgs = [_encode_image_to_base64(img) for img in images]
        except Exception as e:
            logger.warning(f"Failed to encode images for VLM: {e}")

    parsed = call_llm_for_extraction(ocr_text, images=base64_imgs)
    if parsed is None:
        return None

    raw_header = parsed.get("header", {})
    raw_items = parsed.get("line_items", [])

    if not raw_items:
        logger.warning("AI extraction returned zero line items.")
        return None

    header, items = validate_and_reconcile(raw_header, raw_items)


    # Build quotation_dict compatible with save_quotation_to_db
    from app.quotation_extraction.classifier import classify_document_text
    doc_type, confidence, reasoning = classify_document_text(ocr_text)

    quotation_dict = {
        "vendor_name": header.get("vendor_name"),
        "vendor_gstin": header.get("vendor_gstin"),
        "customer_name": header.get("customer_name"),
        "customer_gstin": header.get("customer_gstin"),
        "quotation_no": header.get("document_no"),
        "quotation_date": _parse_date_str(header.get("document_date")),
        "validity_date": None,
        "payment_terms": header.get("payment_terms"),
        "currency": header.get("currency", "INR"),
        "enquiry_ref": None,
        "enquiry_date": None,
        "grand_total_taxable": _to_decimal(header.get("grand_total_taxable")),
        "grand_total_cgst": _to_decimal(header.get("grand_total_cgst")),
        "grand_total_sgst": _to_decimal(header.get("grand_total_sgst")),
        "grand_total_final": _to_decimal(header.get("grand_total_final")),
        "grand_total_words": None,
        "source_file": source_file,
        "document_type": doc_type,
        "document_no": header.get("document_no"),
        "document_date": _parse_date_str(header.get("document_date")),
        "classification_confidence": confidence,
        "classification_reasoning": reasoning,
        "extraction_status": "ok" if items else "needs_review",
    }

    from app.quotation_extraction.validator import validate_row_arithmetic, validate_quotation_totals
    items = [validate_row_arithmetic(item) for item in items]
    quotation_dict = validate_quotation_totals(quotation_dict, items)

    return quotation_dict, items


def _parse_date_str(date_str: Optional[str]):
    """Parse a YYYY-MM-DD date string into a date object, capping future OCR misreads at 2026."""
    if not date_str:
        return None
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y"):
        try:
            d = datetime.strptime(date_str.strip(), fmt).date()
            if d.year > 2026:
                d = d.replace(year=2026)
            return d
        except ValueError:
            continue
    return None
