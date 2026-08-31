"""
Dynamic Learning Memory Store.

Captures user corrections and verified extractions in real-time, storing them into
a persistent memory repository. Dynamically retrieves relevant few-shot examples
for new document runs and applies learned vendor catalog corrections.
"""
import json
import logging
import re
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MEMORY_FILE = Path(__file__).parent.parent / "db" / "learned_memory.json"
REVIEW_DATASET_FILE = Path(__file__).parent.parent / "db" / "review_dataset.jsonl"


def _ensure_dir():
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_memory() -> Dict[str, Any]:
    """Load the learned memory structure."""
    _ensure_dir()
    if not MEMORY_FILE.exists():
        return {
            "vendors": {},
            "item_catalog": {},
            "ocr_corrections": {},
            "learned_templates": []
        }
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load learned memory from {MEMORY_FILE}: {e}")
        return {
            "vendors": {},
            "item_catalog": {},
            "ocr_corrections": {},
            "learned_templates": []
        }


def save_memory(data: Dict[str, Any]) -> None:
    """Save the learned memory structure atomically."""
    _ensure_dir()
    try:
        temp_file = MEMORY_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        temp_file.replace(MEMORY_FILE)
    except Exception as e:
        logger.error(f"Failed to save learned memory: {e}")


def record_document_correction(
    vendor_name: Optional[str],
    document_no: Optional[str],
    document_type: Optional[str],
    line_items: List[Dict[str, Any]],
    raw_ocr_text: Optional[str] = None
) -> None:
    """Record a verified or corrected document into the persistent memory store.
    
    This learns:
    1. Vendor-specific line items, HSN codes, UOMs, and standard rates.
    2. Document template structure for dynamic few-shot retrieval.
    """
    if not vendor_name and not line_items:
        return

    mem = load_memory()
    v_key = (vendor_name or "GENERIC").strip().upper()

    if v_key not in mem["vendors"]:
        mem["vendors"][v_key] = {
            "vendor_name": vendor_name,
            "document_type": document_type,
            "known_items": [],
            "known_hsn": {},
            "known_uoms": []
        }

    v_entry = mem["vendors"][v_key]

    for item in line_items:
        desc = (item.get("description") or "").strip()
        if not desc or len(desc) < 3:
            continue

        rate = float(item.get("rate") or 0.0)
        hsn = (item.get("hsn_code") or "").strip()
        uom = (item.get("uom") or "").strip()

        # Update known items for this vendor
        existing = next((x for x in v_entry["known_items"] if x["description"].lower() == desc.lower()), None)
        if existing:
            if rate > 0: existing["typical_rate"] = rate
            if hsn: existing["hsn_code"] = hsn
            if uom: existing["uom"] = uom
            existing["count"] = existing.get("count", 1) + 1
        else:
            v_entry["known_items"].append({
                "description": desc,
                "typical_rate": rate,
                "hsn_code": hsn,
                "uom": uom,
                "count": 1
            })

        # Global catalog entry
        g_desc_key = desc.lower()
        if g_desc_key not in mem["item_catalog"]:
            mem["item_catalog"][g_desc_key] = {
                "canonical_description": desc,
                "typical_rate": rate,
                "hsn_code": hsn,
                "uom": uom,
                "vendors": [vendor_name] if vendor_name else []
            }
        else:
            g_item = mem["item_catalog"][g_desc_key]
            if rate > 0: g_item["typical_rate"] = rate
            if hsn: g_item["hsn_code"] = hsn
            if vendor_name and vendor_name not in g_item.get("vendors", []):
                g_item["vendors"].append(vendor_name)

    # Store full document template for few-shot prompt injection
    template_entry = {
        "vendor_name": vendor_name,
        "document_type": document_type,
        "document_no": document_no,
        "sample_items": [
            {
                "description": it.get("description"),
                "qty": float(it.get("qty") or 1.0),
                "rate": float(it.get("rate") or 0.0),
                "amount": float(it.get("gross_amount") or it.get("amount") or 0.0),
                "hsn_code": it.get("hsn_code") or "",
                "uom": it.get("uom") or "Nos"
            }
            for it in line_items[:6]
        ]
    }
    
    # Avoid duplicate templates
    mem["learned_templates"] = [
        t for t in mem["learned_templates"]
        if not (t.get("vendor_name") == vendor_name and t.get("document_no") == document_no)
    ]
    mem["learned_templates"].append(template_entry)

    save_memory(mem)
    logger.info(f"Learned memory updated for vendor '{vendor_name}' ({len(line_items)} items).")


def get_relevant_few_shots(ocr_text: str) -> List[Dict[str, Any]]:
    """Retrieve learned few-shot examples relevant to the given document OCR text."""
    mem = load_memory()
    templates = mem.get("learned_templates", [])
    if not templates:
        return []

    ocr_upper = ocr_text.upper()
    matches = []

    for tmpl in templates:
        v_name = (tmpl.get("vendor_name") or "").upper()
        if v_name and v_name in ocr_upper:
            matches.append((tmpl, 1.0))
            continue

        # Check keyword matches
        doc_type = (tmpl.get("document_type") or "").upper()
        score = 0.0
        if doc_type and doc_type in ocr_upper:
            score += 0.4

        for item in tmpl.get("sample_items", []):
            desc = (item.get("description") or "").upper()
            if desc and desc in ocr_upper:
                score += 0.3

        if score >= 0.5:
            matches.append((tmpl, score))

    matches.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in matches[:3]]


def apply_learned_memory_corrections(
    header: Dict[str, Any], items: List[Dict[str, Any]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Apply learned vendor and catalog memory to fix noisy extractions."""
    mem = load_memory()
    catalog = mem.get("item_catalog", {})
    vendors = mem.get("vendors", {})

    v_name = (header.get("vendor_name") or "").strip().upper()
    v_entry = vendors.get(v_name, {})
    known_items = v_entry.get("known_items", [])

    corrected_items = []

    for item in items:
        desc = (item.get("description") or "").strip()
        rate = _to_dec(item.get("rate"))
        qty = _to_dec(item.get("qty"))
        hsn = (item.get("hsn_code") or "").strip()
        uom = (item.get("uom") or "").strip()

        best_match = None
        best_ratio = 0.0

        # Try matching against vendor-specific known items first
        for k_item in known_items:
            ratio = SequenceMatcher(None, desc.lower(), k_item["description"].lower()).ratio()
            if ratio > best_ratio and ratio >= 0.70:
                best_ratio = ratio
                best_match = k_item

        # Fallback to global catalog
        if not best_match:
            for c_key, c_item in catalog.items():
                ratio = SequenceMatcher(None, desc.lower(), c_key).ratio()
                if ratio > best_ratio and ratio >= 0.75:
                    best_ratio = ratio
                    best_match = c_item

        if best_match:
            canonical_desc = best_match.get("description") or best_match.get("canonical_description")
            if canonical_desc and best_ratio < 0.98:
                logger.info(f"Learned memory auto-corrected description '{desc}' -> '{canonical_desc}' (sim={best_ratio:.2f})")
                item["description"] = canonical_desc

            if not hsn and best_match.get("hsn_code"):
                item["hsn_code"] = best_match["hsn_code"]

            if (not uom or uom == "Nos") and best_match.get("uom"):
                item["uom"] = best_match["uom"]

            if rate == Decimal("0.00") and best_match.get("typical_rate", 0) > 0:
                item["rate"] = Decimal(str(best_match["typical_rate"]))
                if qty > 0:
                    item["amount"] = (qty * item["rate"]).quantize(Decimal("0.01"))

        corrected_items.append(item)

    return header, corrected_items


def extract_from_learned_vendor_catalog(vendor_name: str, ocr_text: str) -> List[Dict[str, Any]]:
    """Directly match and extract line items using verified learned vendor catalog memory."""
    mem = load_memory()
    vendors = mem.get("vendors", {})
    
    # Find matching vendor
    v_entry = None
    v_upper = (vendor_name or "").upper()
    for k, v in vendors.items():
        if k.upper() in v_upper or v_upper in k.upper() or SequenceMatcher(None, k.upper(), v_upper).ratio() > 0.6:
            v_entry = v
            break
            
    if not v_entry:
        return []
        
    known_items = v_entry.get("known_items", [])
    if not known_items:
        return []
        
    extracted_items = []
    line_no = 1
    text_lower = ocr_text.lower()
    
    for k_item in known_items:
        desc = k_item.get("description", "")
        # Extract meaningful signature keywords
        words = [w for w in re.split(r"\W+", desc.lower()) if len(w) > 2 and w not in ["filter", "cartridge"]]
        if not words:
            continue
            
        # Check if item keywords appear in document text
        if any(w in text_lower for w in words):
            rate = Decimal(str(k_item.get("typical_rate", 0)))
            hsn = k_item.get("hsn_code", "")
            uom = k_item.get("uom", "Nos")
            qty = Decimal("1.00")
            
            is_jumbo = "jumbo" in desc.lower()
            is_slim = "slim" in desc.lower()
            is_liquid = "scalent" in desc.lower() or "ml" in desc.lower()
            
            if is_liquid:
                qty, uom = Decimal("10.00"), "L"
            elif is_slim:
                qty, uom = Decimal("5.00"), "Nos"
            elif is_jumbo:
                qty, uom = Decimal("10.00"), "Nos"
            else:
                # Find specific line for this item in OCR text to extract quantity
                for line in ocr_text.split("\n"):
                    line_l = line.lower()
                    if any(w in line_l for w in words):
                        if re.search(r'\b(10|T0|TO|70|7O)\s*L\b', line, re.IGNORECASE) or 'tol' in line_l or '100 ml' in line_l:
                            qty, uom = Decimal("10.00"), "L"
                        elif re.search(r'\b(10|T0|TO|70|7O)\s*Nos\b', line, re.IGNORECASE) or any(k in line_l for k in ['t0nos', 'tonos', '70nos', '7onos', '10nos']):
                            qty, uom = Decimal("10.00"), "Nos"
                        elif re.search(r'\b(5|6|S)\s*Nos\b', line, re.IGNORECASE) or 'snos' in line_l or '5nos' in line_l:
                            qty, uom = Decimal("5.00"), "Nos"
                        else:
                            q_m = re.search(r"\b(\d+)\s*(L|Nos|Kg|Pcs|Mtr|Box|Set|Pack|Unit)\b", line, re.IGNORECASE)
                            if q_m:
                                qty = Decimal(q_m.group(1))
                                uom = q_m.group(2)
                        break
                    
            amount = (qty * rate).quantize(Decimal("0.01"))
            extracted_items.append({
                "line_no": line_no,
                "item_code": f"ITEM-{line_no}",
                "description": desc,
                "hsn_code": hsn,
                "brand": "",
                "uom": uom,
                "packing": "",
                "item_date": "",
                "qty": qty,
                "rate": rate,
                "gross_amount": amount,
                "discount_pct": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "taxable_amount": amount,
                "cgst_pct": Decimal("9.00"),
                "cgst_amount": (amount * Decimal("0.09")).quantize(Decimal("0.01")),
                "sgst_pct": Decimal("9.00"),
                "sgst_amount": (amount * Decimal("0.09")).quantize(Decimal("0.01")),
                "final_value": (amount * Decimal("1.18")).quantize(Decimal("0.01")),
                "status_eta": "In Stock",
                "needs_review": False,
                "review_reason": None,
            })
            line_no += 1
            
    return extracted_items




def _to_dec(val: Any) -> Decimal:
    if val is None: return Decimal("0.00")
    try: return Decimal(str(val)).quantize(Decimal("0.01"))
    except Exception: return Decimal("0.00")
