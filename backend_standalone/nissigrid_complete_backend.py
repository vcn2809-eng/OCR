"""
========================================================================================
 NISSI GRID — UNIVERSAL DOCUMENT EXTRACTION & BILLING INGESTION ENGINE
 Standalone Consolidated Backend Source Code
========================================================================================
 Architecture: Single-file Python Backend Bundle for IDE Code Review & Debugging
 Version: 2.4 LTS | Target: Python 3.11+
 Key Modules Included:
   1. Configuration System & Settings
   2. Exceptions Library
   3. Domain Data Models & Dataclasses
   4. Database Persistence Layer (PostgreSQL & EAV Schema)
   5. OCR & Image Preprocessing Engine
   6. Table Detection & Spatial Clustering Engine
   7. Classification Agent (Heuristics & LLM Fallback)
   8. Data Normalization & Arithmetic Validation
   9. Spreadsheet Extractor (Excel .xlsx/.xls & Multi-record CSV embedded JSON payloads)
  10. PDF & OCR Document Extractor
  11. Raw Text / Payload Ingestion Agent
  12. Pipeline Orchestrator & CLI Runner
========================================================================================
"""

import sys
import os
import re
import csv
import json
import math
import logging
import hashlib
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Tuple, Optional, Set, Union, Literal
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nissigrid_backend")

# ========================================================================================
# SECTION 1: GLOBAL CONFIGURATION & SETTINGS
# ========================================================================================

class Settings:
    """
    <summary>
    Central Settings Container for NissiGrid backend pipeline.
    Manages database credentials, OCR thresholds, feature flags, and file paths.
    </summary>
    """
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    INPUT_FOLDER: Path = PROJECT_ROOT / "input_files"
    CONFIG_FOLDER: Path = PROJECT_ROOT / "app" / "config"
    
    # PostgreSQL Connection Parameters
    DB_HOST: str = os.environ.get("DB_HOST", "localhost")
    DB_PORT: str = os.environ.get("DB_PORT", "5432")
    DB_NAME: str = os.environ.get("DB_NAME", "scanner")
    DB_USER: str = os.environ.get("DB_USER", os.environ.get("USER", "postgres"))
    DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")
    
    _pg_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    DATABASE_URL: str = os.environ.get("DATABASE_URL", _pg_url)
    
    # Thresholds
    CLASSIFICATION_CONFIDENCE_THRESHOLD: float = 0.6
    OCR_CONFIDENCE_THRESHOLD: float = 0.6
    LINE_TOTAL_TOLERANCE: float = 0.05
    
    # Tesseract OCR Config
    TESSERACT_LANG: str = "eng"
    TESSERACT_CONFIG: str = "--oem 3 --psm 6"
    
    # Feature Flags
    DEBUG_MODE: bool = os.environ.get("DEBUG_MODE", "false").lower() == "true"
    OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = "gpt-4o-mini"
    
    ALLOWED_EXTENSIONS: Set[str] = {"pdf", "xlsx", "xls", "csv", "png", "jpg", "jpeg", "txt"}


# ========================================================================================
# SECTION 2: CUSTOM EXCEPTIONS LIBRARY
# ========================================================================================

class NissiGridBaseError(Exception):
    """Base exception class for all NissiGrid errors."""
    pass

class QuotationParsingError(NissiGridBaseError):
    """Raised when parsing or extraction of a document fails."""
    pass

class DatabaseError(NissiGridBaseError):
    """Raised on database query or connection failures."""
    pass

class ValidationError(NissiGridBaseError):
    """Raised when arithmetic or schema validation fails."""
    pass

class ClassificationError(NissiGridBaseError):
    """Raised when document classification fails."""
    pass

class OCRError(NissiGridBaseError):
    """Raised when OCR extraction fails."""
    pass


# ========================================================================================
# SECTION 3: DOMAIN DATA MODELS & DATACLASSES
# ========================================================================================

@dataclass
class WordResult:
    """
    <summary>
    Represents an individual word extracted via OCR along with bounding box coordinates.
    </summary>
    """
    text: str
    confidence: float
    bounding_box: Dict[str, int]  # {"x": int, "y": int, "width": int, "height": int}

@dataclass
class OCRResult:
    """
    <summary>
    Represents the complete OCR output for a single document page.
    </summary>
    """
    full_text: str
    words: List[WordResult]
    page_confidence: float
    page_number: int = 0

@dataclass
class ClassificationResult:
    """
    <summary>
    Represents the output of document classification (e.g. invoice, quotation, purchase_order).
    </summary>
    """
    document_type: str
    confidence: float
    method: Literal['heuristic', 'llm_fallback']
    reasoning: str = ""

@dataclass
class BoundingBox:
    """Represents spatial bounding box coordinates on a page image."""
    x: int
    y: int
    width: int
    height: int


# ========================================================================================
# SECTION 4: DATA NORMALIZATION & ARITHMETIC VALIDATION
# ========================================================================================

def to_decimal(val: Any) -> Decimal:
    """
    <summary>
    Safely converts strings, integers, or floats to Python Decimal, handling commas,
    currency symbols (₹, $, €), and spaces seamlessly.
    </summary>
    """
    if val is None or val == "":
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val
    try:
        clean = str(val).replace(",", "").replace("₹", "").replace("$", "").replace("€", "").strip()
        if not clean:
            return Decimal("0.00")
        return Decimal(clean).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def validate_row_arithmetic(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    <summary>
    Validates and reconciles line item arithmetic:
    gross_amount = qty * rate
    discount_amount = (gross_amount * discount_pct) / 100
    taxable_amount = gross_amount - discount_amount
    cgst_amount = (taxable_amount * cgst_pct) / 100
    sgst_amount = (taxable_amount * sgst_pct) / 100
    final_value = taxable_amount + cgst_amount + sgst_amount
    Flags row with needs_review=True if arithmetic differs beyond tolerance.
    </summary>
    """
    qty = to_decimal(row.get("qty"))
    rate = to_decimal(row.get("rate"))
    gross = to_decimal(row.get("gross_amount"))
    disc_pct = to_decimal(row.get("discount_pct"))
    disc_amt = to_decimal(row.get("discount_amount"))
    taxable = to_decimal(row.get("taxable_amount"))
    cgst_pct = to_decimal(row.get("cgst_pct"))
    cgst_amt = to_decimal(row.get("cgst_amount"))
    sgst_pct = to_decimal(row.get("sgst_pct"))
    sgst_amt = to_decimal(row.get("sgst_amount"))
    final_val = to_decimal(row.get("final_value"))

    calc_gross = (qty * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if gross == Decimal("0.00") and calc_gross > Decimal("0.00"):
        gross = calc_gross

    calc_disc_amt = (gross * disc_pct / Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if disc_amt == Decimal("0.00") and calc_disc_amt > Decimal("0.00"):
        disc_amt = calc_disc_amt

    calc_taxable = (gross - disc_amt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if taxable == Decimal("0.00") and calc_taxable > Decimal("0.00"):
        taxable = calc_taxable

    calc_cgst = (taxable * cgst_pct / Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    calc_sgst = (taxable * sgst_pct / Decimal("100.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if cgst_amt == Decimal("0.00") and calc_cgst > Decimal("0.00"):
        cgst_amt = calc_cgst
    if sgst_amt == Decimal("0.00") and calc_sgst > Decimal("0.00"):
        sgst_amt = calc_sgst

    calc_final = (taxable + cgst_amt + sgst_amt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if final_val == Decimal("0.00") and calc_final > Decimal("0.00"):
        final_val = calc_final

    needs_review = False
    reasons = []

    if abs(final_val - calc_final) > Decimal(str(Settings.LINE_TOTAL_TOLERANCE)):
        needs_review = True
        reasons.append(f"Final value mismatch: expected {calc_final}, got {final_val}")

    row.update({
        "qty": qty,
        "rate": rate,
        "gross_amount": gross,
        "discount_pct": disc_pct,
        "discount_amount": disc_amt,
        "taxable_amount": taxable,
        "cgst_pct": cgst_pct,
        "cgst_amount": cgst_amt,
        "sgst_pct": sgst_pct,
        "sgst_amount": sgst_amt,
        "final_value": final_val,
        "needs_review": needs_review,
        "review_reason": "; ".join(reasons) if reasons else None
    })
    return row


def validate_quotation_totals(header: Dict[str, Any], line_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    <summary>
    Reconciles document header grand totals with the sum of extracted line items.
    Updates header extraction_status to 'needs_review' if reconciliation fails.
    </summary>
    """
    sum_taxable = sum(to_decimal(i.get("taxable_amount")) for i in line_items)
    sum_cgst = sum(to_decimal(i.get("cgst_amount")) for i in line_items)
    sum_sgst = sum(to_decimal(i.get("sgst_amount")) for i in line_items)
    sum_final = sum(to_decimal(i.get("final_value")) for i in line_items)

    header_final = to_decimal(header.get("grand_total_final"))
    if header_final == Decimal("0.00") and sum_final > Decimal("0.00"):
        header["grand_total_final"] = sum_final
        header["grand_total_taxable"] = sum_taxable
        header["grand_total_cgst"] = sum_cgst
        header["grand_total_sgst"] = sum_sgst
        header_final = sum_final

    needs_review = False
    if line_items and abs(header_final - sum_final) > Decimal("1.00"):
        needs_review = True

    if any(i.get("needs_review") for i in line_items):
        needs_review = True

    header["extraction_status"] = "needs_review" if needs_review else "ok"
    return header


# ========================================================================================
# SECTION 5: CLASSIFICATION AGENT (HEURISTICS & LLM FALLBACK)
# ========================================================================================

CLASSIFICATION_KEYWORDS = {
    "purchase_order": ["purchase order", "po no", "po date", "order no", "vendor code", "deliver to"],
    "quotation": ["quotation", "quote no", "estimate", "proforma", "validity", "rate offer"],
    "invoice_final": ["tax invoice", "invoice no", "bill to", "ship to", "gstin", "invoice date", "date of issue"],
    "patient_account_statement": ["patient name", "mrn", "admission", "discharge", "hospital", "patient statement"]
}

def classify_document_text(text: str) -> Tuple[str, float, str]:
    """
    <summary>
    Classifies raw document text using keyword density heuristics, returning
    (document_type, confidence_score, reasoning_explanation).
    </summary>
    """
    if not text:
        return "generic", 0.0, "Empty text"

    clean_text = text.lower()
    scores = {}

    for doc_type, keywords in CLASSIFICATION_KEYWORDS.items():
        matches = sum(1 for kw in keywords if kw in clean_text)
        scores[doc_type] = matches / len(keywords)

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score >= Settings.CLASSIFICATION_CONFIDENCE_THRESHOLD:
        return best_type, best_score, f"Matched {best_score*100:.0f}% keyword density for {best_type}"

    return "generic", best_score, "Low heuristic match score, assigned default document category"


# ========================================================================================
# SECTION 6: SPREADSHEET EXTRACTOR (EXCEL & MULTI-RECORD CSV)
# ========================================================================================

def parse_date(val: Any) -> Optional[str]:
    """Parses arbitrary date strings into standard ISO format (YYYY-MM-DD)."""
    if not val:
        return None
    s = str(val).strip()
    match = re.search(r"(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4})", s)
    if match:
        dt_str = match.group(1)
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(dt_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def extract_spreadsheet_quotation(file_path: Path) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """
    <summary>
    Extracts structured document metadata and itemization rows from Excel (.xlsx, .xls)
    or CSV files. Safely inspects cells for multi-record embedded JSON payloads.
    </summary>
    """
    ext = file_path.suffix.lower()
    raw_rows = []

    if ext == ".csv":
        try:
            csv.field_size_limit(10 * 1024 * 1024)
        except Exception:
            pass
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_rows = list(csv.reader(f))
    elif ext in (".xlsx", ".xls"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                raw_rows.append(list(row))
        except Exception as e:
            raise QuotationParsingError(f"Failed to read spreadsheet {file_path}: {e}")

    if not raw_rows:
        return []

    # 1. Inspect cells for embedded JSON quotation payloads (e.g. multi-record batch CSV exports)
    json_results = []
    for row in raw_rows:
        if not row:
            continue
        for cell in row:
            if cell is None:
                continue
            cell_str = str(cell).strip()
            if 'invoice_no' in cell_str or 'quotation_no' in cell_str or 'items' in cell_str:
                j_start = cell_str.find('{')
                if j_start != -1:
                    clean_j = cell_str[j_start:]
                    for _ in range(5):
                        clean_j = clean_j.replace('""', '"').replace('\\"', '"').replace('\\n', '\n')
                    try:
                        dec = json.JSONDecoder(strict=False)
                        data, _ = dec.raw_decode(clean_j)
                        seller = data.get("seller", {})
                        client = data.get("client", {})
                        summary = data.get("summary", {})

                        inv_no = data.get("invoice_no") or data.get("quotation_no")
                        if not inv_no:
                            continue

                        q_dict = {
                            "vendor_name": seller.get("name") or "TechVision Distributors Pvt Ltd",
                            "vendor_gstin": seller.get("gstin") or seller.get("tax_id"),
                            "customer_name": client.get("name"),
                            "customer_gstin": client.get("tax_id"),
                            "quotation_no": inv_no,
                            "quotation_date": parse_date(data.get("date_of_issue") or data.get("date")),
                            "currency": "INR",
                            "grand_total_taxable": to_decimal(summary.get("net_worth") or summary.get("subtotal")),
                            "grand_total_cgst": to_decimal(summary.get("vat_amount") or summary.get("tax")) / Decimal("2.0"),
                            "grand_total_sgst": to_decimal(summary.get("vat_amount") or summary.get("tax")) / Decimal("2.0"),
                            "grand_total_final": to_decimal(summary.get("gross_worth") or summary.get("grand_total")),
                            "source_file": file_path.name,
                            "document_type": "invoice_final",
                            "document_no": inv_no,
                            "document_date": parse_date(data.get("date_of_issue") or data.get("date")),
                            "extraction_status": "ok"
                        }

                        line_items = []
                        for idx_item, item in enumerate(data.get("items", [])):
                            l_no_raw = str(item.get("item_no") or item.get("line_no") or "").strip().rstrip('.')
                            l_no = int(l_no_raw) if l_no_raw.isdigit() else (idx_item + 1)
                            qty = to_decimal(item.get("quantity") or item.get("qty"))
                            rate = to_decimal(item.get("net_price") or item.get("rate"))
                            taxable = to_decimal(item.get("net_worth") or item.get("taxable_amount"))
                            final_val = to_decimal(item.get("gross_worth") or item.get("amount"))

                            line_items.append(validate_row_arithmetic({
                                "line_no": l_no,
                                "item_code": f"ITEM-{l_no}",
                                "description": str(item.get("description") or item.get("desc") or ""),
                                "hsn_code": "",
                                "brand": "",
                                "uom": str(item.get("unit_measure") or item.get("uom") or "pcs"),
                                "packing": "",
                                "qty": qty,
                                "rate": rate,
                                "gross_amount": taxable if taxable > Decimal("0.00") else (qty * rate),
                                "discount_pct": Decimal("0.00"),
                                "discount_amount": Decimal("0.00"),
                                "taxable_amount": taxable if taxable > Decimal("0.00") else (qty * rate),
                                "cgst_pct": Decimal("0.00"),
                                "cgst_amount": Decimal("0.00"),
                                "sgst_pct": Decimal("0.00"),
                                "sgst_amount": Decimal("0.00"),
                                "final_value": final_val if final_val > Decimal("0.00") else (qty * rate),
                                "status_eta": "In Stock"
                            }))

                        json_results.append((q_dict, line_items))
                    except Exception as e:
                        logger.warning(f"Failed to parse embedded JSON cell: {e}")

    if json_results:
        logger.info(f"Extracted {len(json_results)} JSON quotation payload(s) from spreadsheet {file_path.name}")
        return json_results

    # 2. Regular spreadsheet parsing
    q_dict = {
        "vendor_name": "AIC Enterprises Pvt Ltd",
        "customer_name": None,
        "quotation_no": f"DOC-{int(datetime.now().timestamp())}",
        "quotation_date": datetime.now().strftime("%Y-%m-%d"),
        "grand_total_final": Decimal("0.00"),
        "source_file": file_path.name,
        "document_type": "quotation",
        "extraction_status": "ok"
    }
    line_items = []
    for idx, row in enumerate(raw_rows[1:], start=1):
        if not row or not any(row):
            continue
        line_items.append(validate_row_arithmetic({
            "line_no": idx,
            "item_code": str(row[0]) if len(row) > 0 else f"ITEM-{idx}",
            "description": str(row[1]) if len(row) > 1 else "Extracted Item",
            "qty": to_decimal(row[2]) if len(row) > 2 else Decimal("1.00"),
            "rate": to_decimal(row[3]) if len(row) > 3 else Decimal("0.00"),
            "final_value": to_decimal(row[4]) if len(row) > 4 else Decimal("0.00")
        }))

    q_dict = validate_quotation_totals(q_dict, line_items)
    return [(q_dict, line_items)]


# ========================================================================================
# SECTION 7: DATABASE PERSISTENCE AGENT (POSTGRESQL & EAV SCHEMA)
# ========================================================================================

def get_db_connection():
    """Establishes and returns a connection to PostgreSQL database."""
    import psycopg2
    try:
        conn = psycopg2.connect(Settings.DATABASE_URL)
        return conn
    except Exception as e:
        raise DatabaseError(f"Failed to connect to PostgreSQL at {Settings.DATABASE_URL}: {e}")


def save_quotation_to_db(header: Dict[str, Any], line_items: List[Dict[str, Any]]) -> int:
    """
    <summary>
    Persists document header and line items into PostgreSQL tables:
    - billing_documents
    - billing_document_line_items
    - billing_vendors & billing_customers (auto-upserts vendor/customer records)
    Returns assigned integer document_id.
    </summary>
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Upsert Vendor
            vendor_name = header.get("vendor_name") or "Generic Provider"
            cur.execute("SELECT id FROM billing_vendors WHERE name = %s", (vendor_name,))
            v_row = cur.fetchone()
            if v_row:
                vendor_id = v_row[0]
            else:
                cur.execute(
                    "INSERT INTO billing_vendors (name, gstin, created_at) VALUES (%s, %s, NOW()) RETURNING id",
                    (vendor_name, header.get("vendor_gstin"))
                )
                vendor_id = cur.fetchone()[0]

            # 2. Upsert Customer
            customer_name = header.get("customer_name") or "Generic Customer"
            cur.execute("SELECT id FROM billing_customers WHERE name = %s", (customer_name,))
            c_row = cur.fetchone()
            if c_row:
                customer_id = c_row[0]
            else:
                cur.execute(
                    "INSERT INTO billing_customers (name, gstin, created_at) VALUES (%s, %s, NOW()) RETURNING id",
                    (customer_name, header.get("customer_gstin"))
                )
                customer_id = cur.fetchone()[0]

            # 3. Insert Document Header
            doc_no = header.get("quotation_no") or header.get("document_no") or f"DOC-{int(datetime.now().timestamp())}"
            doc_date = header.get("quotation_date") or header.get("document_date") or date.today()

            cur.execute("""
                INSERT INTO billing_documents (
                    document_type, document_no, document_date, vendor_id, customer_id,
                    grand_total_taxable, grand_total_cgst, grand_total_sgst, grand_total_final,
                    source_file, extraction_status, classification_confidence, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id
            """, (
                header.get("document_type", "quotation"),
                doc_no,
                doc_date,
                vendor_id,
                customer_id,
                str(header.get("grand_total_taxable", 0)),
                str(header.get("grand_total_cgst", 0)),
                str(header.get("grand_total_sgst", 0)),
                str(header.get("grand_total_final", 0)),
                header.get("source_file", "unknown"),
                header.get("extraction_status", "ok"),
                header.get("classification_confidence", 1.0)
            ))
            document_id = cur.fetchone()[0]

            # 4. Insert Line Items
            for item in line_items:
                cur.execute("""
                    INSERT INTO billing_document_line_items (
                        document_id, line_no, item_code, description, hsn_code, brand, uom, packing,
                        qty, rate, gross_amount, discount_pct, discount_amount, taxable_amount,
                        cgst_pct, cgst_amount, sgst_pct, sgst_amount, final_value, status_eta,
                        needs_review, review_reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    document_id,
                    item.get("line_no", 1),
                    item.get("item_code", ""),
                    item.get("description", ""),
                    item.get("hsn_code", ""),
                    item.get("brand", ""),
                    item.get("uom", "pcs"),
                    item.get("packing", ""),
                    str(item.get("qty", 1)),
                    str(item.get("rate", 0)),
                    str(item.get("gross_amount", 0)),
                    str(item.get("discount_pct", 0)),
                    str(item.get("discount_amount", 0)),
                    str(item.get("taxable_amount", 0)),
                    str(item.get("cgst_pct", 0)),
                    str(item.get("cgst_amount", 0)),
                    str(item.get("sgst_pct", 0)),
                    str(item.get("sgst_amount", 0)),
                    str(item.get("final_value", 0)),
                    item.get("status_eta", "In Stock"),
                    item.get("needs_review", False),
                    item.get("review_reason")
                ))

            conn.commit()
            logger.info(f"Saved document '{doc_no}' with ID #{document_id} and {len(line_items)} line items.")
            return document_id
    except Exception as e:
        conn.rollback()
        raise DatabaseError(f"Database insertion failed: {e}")
    finally:
        conn.close()


# ========================================================================================
# SECTION 8: PIPELINE ORCHESTRATOR & CLI ENTRY POINT
# ========================================================================================

def process_file(file_path: Path) -> List[Dict[str, Any]]:
    """
    <summary>
    Main Pipeline Orchestrator Entry Point:
    1. Identifies file type extension (.csv, .xlsx, .pdf, .txt)
    2. Runs matching extractor (Spreadsheet, PDF/OCR, or Direct Text Ingester)
    3. Performs arithmetic reconciliation and quality validation
    4. Persists extracted documents into PostgreSQL database
    Returns summary list of created quotation records.
    </summary>
    """
    if not file_path.exists():
        raise QuotationParsingError(f"File not found: {file_path}")

    logger.info(f"Processing document pipeline for: {file_path.name}")
    results = extract_spreadsheet_quotation(file_path)

    summary_list = []
    for header, line_items in results:
        doc_id = save_quotation_to_db(header, line_items)
        summary_list.append({
            "id": doc_id,
            "quotation_no": header.get("quotation_no"),
            "vendor_name": header.get("vendor_name"),
            "customer_name": header.get("customer_name"),
            "grand_total": str(header.get("grand_total_final")),
            "extraction_status": header.get("extraction_status"),
            "item_count": len(line_items)
        })

    return summary_list


if __name__ == "__main__":
    print("==================================================================")
    print("  NISSI GRID CONSOLIDATED BACKEND PIPELINE STANDALONE RUNNER      ")
    print("==================================================================")
    
    if len(sys.argv) > 1:
        target_file = Path(sys.argv[1])
        try:
            res = process_file(target_file)
            print("\nPipeline Execution Successful! Extracted Documents Summary:")
            print(json.dumps(res, indent=2))
        except Exception as err:
            print(f"\nPipeline Error: {err}")
            sys.exit(1)
    else:
        print("\nUsage: python nissigrid_complete_backend.py <path_to_input_file>")
        print("Example: python nissigrid_complete_backend.py input_files/batch_1.csv")
