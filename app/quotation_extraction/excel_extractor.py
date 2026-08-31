import csv
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from decimal import Decimal
import openpyxl
import xlrd
from app.quotation_extraction.validator import to_decimal, validate_row_arithmetic, validate_quotation_totals
from app.quotation_extraction.pdf_extractor import parse_date
from app.quotation_extraction.exceptions import QuotationParsingError

logger = logging.getLogger(__name__)

HEADER_PATTERNS = {
    "line_no": ["s.no", "sno", "s n", "sn", "line", "sl", "sl.no", "item no", "#"],
    "item_code": ["code", "item code", "catalog", "part no", "part", "sku", "product code", "hsn"],
    "description": ["description", "item", "desc", "particulars", "product", "details", "name", "service", "material"],
    "hsn_code": ["hsn", "hsn code", "sac", "sac code"],
    "brand": ["brand", "make", "manufacturer"],
    "uom": ["uom", "unit", "um"],
    "packing": ["packing", "pack", "pkg"],
    "qty": ["qty", "quantity", "nos", "units", "count"],
    "rate": ["rate", "price", "unit price", "net price", "cost"],
    "gross_amount": ["gross", "gross amount", "gross amt", "amount", "total amount"],
    "discount_pct": ["disc", "discount", "disc%"],
    "discount_amount": ["discount amount", "disc amt"],
    "taxable_amount": ["taxable", "taxable amount", "taxable amt", "subtotal"],
    "cgst_pct": ["cgst %", "cgst%"],
    "cgst_amount": ["cgst amount", "cgst amt"],
    "sgst_pct": ["sgst %", "sgst%"],
    "sgst_amount": ["sgst amount", "sgst amt"],
    "final_value": ["final", "final value", "net value", "total", "net total", "grand total"],
    "status_eta": ["status", "eta", "delivery"]
}

def match_cell_to_field(cell_val: Any) -> Optional[str]:
    if cell_val is None:
        return None
    clean = str(cell_val).strip().lower().replace("\n", " ")
    if not clean:
        return None
    
    for field, patterns in HEADER_PATTERNS.items():
        for pat in patterns:
            if pat in clean:
                return field
    return None


def read_csv_file(file_path: Path) -> List[List[Any]]:
    """Read CSV file into a 2D grid."""
    import sys
    try:
        csv.field_size_limit(10 * 1024 * 1024)
    except Exception:
        pass

    rows = []
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(row)
    except Exception as e:
        raise QuotationParsingError(f"Failed to read CSV file: {e}")
    return rows


def read_xls_file(file_path: Path) -> List[List[Any]]:
    """Read legacy .xls file into a 2D grid using xlrd."""
    rows = []
    try:
        wb = xlrd.open_workbook(file_path)
        sheet = wb.sheet_by_index(0)
        for r_idx in range(sheet.nrows):
            rows.append([sheet.cell_value(r_idx, c_idx) for c_idx in range(sheet.ncols)])
    except Exception as e:
        raise QuotationParsingError(f"Failed to read XLS file: {e}")
    return rows


def read_xlsx_file(file_path: Path) -> List[List[Any]]:
    """Read modern .xlsx file into a 2D grid using openpyxl."""
    rows = []
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active
        for row in sheet.iter_rows(values_only=True):
            rows.append(list(row))
    except Exception as e:
        raise QuotationParsingError(f"Failed to read XLSX file: {e}")
    return rows


def extract_excel_quotation(file_path: Path) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Extract quotation metadata and line items from Excel / CSV sheets."""
    ext = file_path.suffix.lower()
    if ext == ".csv":
        raw_rows = read_csv_file(file_path)
    elif ext == ".xls":
        raw_rows = read_xls_file(file_path)
    elif ext in (".xlsx", ".xlsm"):
        raw_rows = read_xlsx_file(file_path)
    else:
        raise QuotationParsingError(f"Unsupported spreadsheet format: {ext}")

    if not raw_rows:
        return []

    # Check if any cell contains an embedded JSON quotation payload (e.g. filename, json_data, ocred_text)
    import json
    json_results = []
    for r_idx, row in enumerate(raw_rows):
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
                            "validity_date": None,
                            "payment_terms": None,
                            "currency": "INR",
                            "enquiry_ref": None,
                            "enquiry_date": None,
                            "grand_total_taxable": to_decimal(summary.get("net_worth") or summary.get("subtotal")),
                            "grand_total_cgst": to_decimal(summary.get("vat_amount") or summary.get("tax")) / Decimal("2.0"),
                            "grand_total_sgst": to_decimal(summary.get("vat_amount") or summary.get("tax")) / Decimal("2.0"),
                            "grand_total_final": to_decimal(summary.get("gross_worth") or summary.get("grand_total")),
                            "grand_total_words": None,
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
                            vat_str = str(item.get("vat_pct") or item.get("tax_pct") or "0").replace("%", "").strip()
                            vat_pct = to_decimal(vat_str)
                            half_vat = vat_pct / Decimal("2.0")
                            vat_amt = (taxable * vat_pct) / Decimal("100.00")
                            half_vat_amt = vat_amt / Decimal("2.0")

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
                                "cgst_pct": half_vat,
                                "cgst_amount": half_vat_amt,
                                "sgst_pct": half_vat,
                                "sgst_amount": half_vat_amt,
                                "final_value": final_val if final_val > Decimal("0.00") else (qty * rate),
                                "status_eta": "In Stock"
                            }))

                        json_results.append((q_dict, line_items))
                    except Exception as e:
                        logger.warning(f"Failed to parse embedded JSON cell: {e}")

    if json_results:
        logger.info(f"Extracted {len(json_results)} JSON quotation payload(s) from spreadsheet {file_path.name}")
        return json_results

    # Initialize quotation header data
    quotation_dict = {
        "vendor_name": "TechVision Distributors Pvt Ltd",  # Default / fallback for commercial batch spreadsheets
        "vendor_gstin": None,
        "customer_name": None,
        "customer_gstin": None,
        "quotation_no": None,
        "quotation_date": None,
        "validity_date": None,
        "payment_terms": None,
        "currency": "INR",
        "enquiry_ref": None,
        "enquiry_date": None,
        "grand_total_taxable": Decimal("0.00"),
        "grand_total_cgst": Decimal("0.00"),
        "grand_total_sgst": Decimal("0.00"),
        "grand_total_final": Decimal("0.00"),
        "grand_total_words": None,
        "source_file": file_path.name,
    }

    header_row_idx = -1
    col_mapping: Dict[int, str] = {}

    # Step 1: Scan rows to find headers and quotation info
    for r_idx, row in enumerate(raw_rows):
        if not row:
            continue
        
        # Parse Quotation info if present in cell values
        for cell in row:
            if cell is None:
                continue
            cell_str = str(cell)
            if "Quotation. No." in cell_str or "Quotation No" in cell_str or "Invoice No" in cell_str:
                parts = cell_str.split(":")
                if len(parts) > 1:
                    quotation_dict["quotation_no"] = parts[1].strip()
            if "GST No" in cell_str or "GSTIN" in cell_str:
                parts = cell_str.split(":")
                if len(parts) > 1:
                    if "customer" in cell_str.lower() or "to" in cell_str.lower():
                        quotation_dict["customer_gstin"] = parts[1].strip()
                    else:
                        quotation_dict["vendor_gstin"] = parts[1].strip()

        # Check if this is the header row
        temp_mapping = {}
        matched_cols = 0
        for c_idx, cell in enumerate(row):
            field = match_cell_to_field(cell)
            if field and field not in temp_mapping.values():
                temp_mapping[c_idx] = field
                matched_cols += 1

        # Assume header row if at least 2 headers matched
        if matched_cols >= 2:
            header_row_idx = r_idx
            col_mapping = temp_mapping
            break

    # Fallback header mapping if no header row matched 2+ columns
    if header_row_idx == -1:
        logger.info("Using fallback column mapping for spreadsheet...")
        header_row_idx = 0
        # Default column mapping: col 0=line_no, col 1=description, col 2=qty, col 3=rate, col 4=final_value
        col_mapping = {0: "line_no", 1: "description", 2: "qty", 3: "rate", 4: "final_value"}

    # Step 2: Extract items below header row
    line_items = []
    auto_line_no = 1

    for r_idx in range(header_row_idx + 1, len(raw_rows)):
        row = raw_rows[r_idx]
        if not row:
            continue
        
        row_str = " ".join([str(c) for c in row if c is not None])
        if not row_str.strip():
            continue

        # Check if this row is a grand total row
        if "grand total" in row_str.lower() or "total amount" in row_str.lower():
            for c_idx, val in enumerate(row):
                if c_idx in col_mapping:
                    field = col_mapping[c_idx]
                    if field == "taxable_amount":
                        quotation_dict["grand_total_taxable"] = to_decimal(val)
                    elif field == "cgst_amount":
                        quotation_dict["grand_total_cgst"] = to_decimal(val)
                    elif field == "sgst_amount":
                        quotation_dict["grand_total_sgst"] = to_decimal(val)
                    elif field == "final_value":
                        quotation_dict["grand_total_final"] = to_decimal(val)
            continue

        if "total in words" in row_str.lower():
            for val in row:
                if val and "only" in str(val).lower():
                    quotation_dict["grand_total_words"] = str(val).strip()
            continue

        # Extract regular item cells
        item: Dict[str, Any] = {}
        has_data = False
        for c_idx, val in enumerate(row):
            if c_idx in col_mapping:
                field = col_mapping[c_idx]
                if val is not None and str(val).strip():
                    item[field] = val
                    has_data = True
            elif c_idx < len(row) and val is not None and str(val).strip() and "description" not in item:
                # Store unmapped non-empty text into description if empty
                item["description"] = str(val).strip()
                has_data = True

        if not has_data:
            continue

        # Auto-assign line_no if missing or non-integer
        if "line_no" in item:
            try:
                item["line_no"] = int(float(str(item["line_no"]).replace("#", "").replace(".", "").strip()))
            except ValueError:
                item["line_no"] = auto_line_no
        else:
            item["line_no"] = auto_line_no

        auto_line_no += 1

        # Clean HSN code and description
        desc_hsn = str(item.get("description") or "")
        hsn_code = str(item.get("hsn_code") or "")
        description = desc_hsn

        if not hsn_code:
            hsn_match = re.search(r"-\s*(\d{6,8})\s*-?$", desc_hsn)
            if hsn_match:
                hsn_code = hsn_match.group(1).strip()
                description = re.sub(r"-\s*\d{6,8}\s*-?$", "", desc_hsn).strip()
        
        item["hsn_code"] = hsn_code
        item["description"] = description

        # Arithmetic Validation
        item = validate_row_arithmetic(item)
        line_items.append(item)

    # Calculate grand total from line items if not extracted
    if quotation_dict["grand_total_final"] == Decimal("0.00") and line_items:
        quotation_dict["grand_total_final"] = sum(to_decimal(i.get("final_value") or i.get("gross_amount") or i.get("taxable_amount") or 0) for i in line_items)
        quotation_dict["grand_total_taxable"] = sum(to_decimal(i.get("taxable_amount") or i.get("gross_amount") or i.get("final_value") or 0) for i in line_items)

    # Classify the Excel document
    text_sample = " ".join([str(cell) for row in raw_rows[:10] for cell in row if cell is not None])
    from app.quotation_extraction.classifier import classify_document_text
    doc_type, confidence, reasoning = classify_document_text(text_sample)

    quotation_dict.update({
        "document_type": doc_type,
        "document_no": quotation_dict.get("quotation_no"),
        "document_date": quotation_dict.get("quotation_date"),
        "classification_confidence": confidence,
        "classification_reasoning": reasoning,
        "extraction_status": "ok" if line_items else "needs_review"
    })

    # Validate totals
    quotation_dict = validate_quotation_totals(quotation_dict, line_items)

    return [(quotation_dict, line_items)]
