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
    """Read modern .xlsx file into a 2D grid using openpyxl, selecting the sheet with the most content."""
    rows = []
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        best_sheet = wb.active
        max_non_empty = 0
        for sheetname in wb.sheetnames:
            s = wb[sheetname]
            count = sum(1 for row in s.iter_rows(values_only=True) if any(c is not None for c in row))
            if count > max_non_empty:
                max_non_empty = count
                best_sheet = s

        for row in best_sheet.iter_rows(values_only=True):
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

    # Check if any cell contains an embedded JSON quotation payload (e.g. synthetic batch CSVs)
    import json
    json_results = []
    for r_idx, row in enumerate(raw_rows):
        if not row:
            continue
        for cell in row:
            if cell is None:
                continue
            cell_str = str(cell).strip()
            if ('"invoice_no"' in cell_str or '"quotation_no"' in cell_str or '"items"' in cell_str) and '{' in cell_str:
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
                            "vendor_address": seller.get("address"),
                            "customer_name": client.get("name"),
                            "customer_gstin": client.get("tax_id"),
                            "customer_address": client.get("address"),
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

    # ── Step 1: Scan Top Rows for Document Metadata ────────────────────────────
    top_cells = []
    for r in raw_rows[:15]:
        for c in r:
            if c is not None and str(c).strip():
                top_cells.append(str(c).strip())
    top_text = "\n".join(top_cells)

    quotation_dict = {
        "vendor_name": None,
        "vendor_gstin": None,
        "vendor_address": None,
        "customer_name": None,
        "customer_gstin": None,
        "customer_address": None,
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

    # GSTIN
    gst_m = re.search(r"(?i)GST(?:IN)?\s*[\:\;\=\s]*([A-Za-z0-9]{15})", top_text)
    if gst_m:
        quotation_dict["vendor_gstin"] = gst_m.group(1).upper()

    # Quotation / Invoice No & Date
    q_m = re.search(r"(?i)(?:Qt\s*No|Quotation\s*No|Invoice\s*No|Doc\s*No)\s*[\:\;\#\=\s]*([A-Za-z0-9\-\/]+)", top_text)
    if q_m:
        quotation_dict["quotation_no"] = q_m.group(1).strip()

    d_m = re.search(r"(?i)Date\s*[\:\;\=\s]*([0-9]{1,2}[\.\/\-][0-9]{1,2}[\.\/\-][0-9]{2,4})", top_text)
    if d_m:
        quotation_dict["quotation_date"] = parse_date(d_m.group(1).strip())

    # Vendor Name & Address
    for cell_str in top_cells:
        if any(k in cell_str.upper() for k in ["SCIENTIFIC", "CHEMICALS", "PHARMA", "ENTERPRISES", "SERVICES", "PVT", "LTD", "INDUSTRIES", "LAB"]):
            if not quotation_dict["vendor_name"] and not cell_str.startswith(("DEALERS", "EAST POINT", "TO", "GSTIN", "QUOTATION")):
                quotation_dict["vendor_name"] = cell_str.split("\n")[0].strip()
        if "DEALERS IN" in cell_str or "#" in cell_str:
            if not quotation_dict["vendor_address"]:
                quotation_dict["vendor_address"] = cell_str.replace("\n", ", ").strip()

    # Customer Name & Address
    for cell_str in top_cells:
        if any(k in cell_str.upper() for k in ["COLLEGE", "HOSPITAL", "PHARMACY", "UNIVERSITY", "INSTITUTE", "LLP", "CORP"]):
            lines = [l.strip() for l in cell_str.split("\n") if l.strip()]
            if lines:
                if not quotation_dict["customer_name"]:
                    quotation_dict["customer_name"] = lines[0]
                    if len(lines) > 1:
                        quotation_dict["customer_address"] = ", ".join(lines[1:])

    # ── Step 2: Multi-Tier Header Table Detection ──────────────────────────────
    header_start_idx = -1
    for r_idx, row in enumerate(raw_rows):
        row_str = " ".join([str(c or "").lower() for c in row if c is not None])
        if any(k in row_str for k in ["sl #", "sl.no", "sl no", "s.no", "sno", "item no", "line no"]):
            header_start_idx = r_idx
            break
        if any(d in row_str for d in ["item description", "particulars"]) and any(q in row_str for q in ["qty", "quantity", "rate", "price", "amount"]):
            header_start_idx = r_idx
            break

    if header_start_idx == -1:
        header_start_idx = 0


    combined_headers: Dict[int, List[str]] = {}
    last_header_idx = header_start_idx

    for r_idx in range(header_start_idx, min(header_start_idx + 4, len(raw_rows))):
        row = raw_rows[r_idx]
        if row and row[0] is not None and str(row[0]).strip().isdigit() and int(str(row[0]).strip()) == 1:
            break
        last_header_idx = r_idx
        for c_idx in range(len(row)):
            val = row[c_idx]
            if val is not None:
                c_str = str(val).strip().replace("\n", " ")
                if c_str:
                    if c_idx not in combined_headers:
                        combined_headers[c_idx] = []
                    combined_headers[c_idx].append(c_str)

    col_map: Dict[int, str] = {}
    for c_idx, parts in combined_headers.items():
        h_str = " ".join(parts).lower()
        if any(k in h_str for k in ["sl #", "s.no", "sno", "sl no", "line"]):
            col_map[c_idx] = "line_no"
        elif any(k in h_str for k in ["item description", "description", "particulars", "product", "details"]):
            col_map[c_idx] = "description"
        elif "brand" in h_str:
            col_map[c_idx] = "brand"
        elif any(k in h_str for k in ["uom", "unit"]):
            col_map[c_idx] = "uom"
        elif any(k in h_str for k in ["selling price", "unit price", "net price", "rate"]):
            col_map[c_idx] = "rate"
        elif any(k in h_str for k in ["sub total", "gross", "gross amount"]):
            col_map[c_idx] = "gross_amount"
        elif any(k in h_str for k in ["discount %", "disc %", "disc%"]):
            col_map[c_idx] = "discount_pct"
        elif any(k in h_str for k in ["discount amount", "disc amt"]) or (h_str == "amount" and c_idx == 8):
            col_map[c_idx] = "discount_amount"
        elif any(k in h_str for k in ["after discount", "taxable", "taxable amount"]):
            col_map[c_idx] = "taxable_amount"
        elif any(k in h_str for k in ["gst %", "tax %", "vat %"]):
            col_map[c_idx] = "gst_pct"
        elif any(k in h_str for k in ["amount (rs.) b", "gst amount", "tax amount", "vat amount"]):
            col_map[c_idx] = "gst_amount"
        elif any(k in h_str for k in ["amount (rs.) a+b", "final", "total", "net value", "grand total"]):
            col_map[c_idx] = "final_value"

    # Auto-detect Quantity column if unmapped
    if "qty" not in col_map.values():
        for c_idx in range(len(raw_rows[0])):
            if c_idx not in col_map:
                sample_vals = [raw_rows[r][c_idx] for r in range(last_header_idx + 1, min(last_header_idx + 10, len(raw_rows))) if len(raw_rows[r]) > c_idx]
                if any(isinstance(v, (int, float)) and v > 0 for v in sample_vals):
                    col_map[c_idx] = "qty"
                    break

    # ── Step 3: Extract Line Items ─────────────────────────────────────────────
    line_items = []
    auto_line_no = 1

    for r_idx in range(last_header_idx + 1, len(raw_rows)):
        row = raw_rows[r_idx]
        if not row or not any(c is not None for c in row):
            continue

        row_str = " ".join([str(c) for c in row if c is not None])
        if "grand total" in row_str.lower() or "total amount" in row_str.lower():
            continue

        s_no = row[0]
        desc = row[1] if len(row) > 1 else None
        if s_no is None and (desc is None or str(desc).strip() == ""):
            continue
        if str(s_no).strip().lower() in ["lab", "sl #", "s.no", "total", ""]:
            continue

        item_dict: Dict[str, Any] = {}
        for c_idx, field in col_map.items():
            if c_idx < len(row):
                item_dict[field] = row[c_idx]

        l_no = auto_line_no
        if item_dict.get("line_no") is not None:
            try:
                l_no = int(str(item_dict["line_no"]).replace("#", "").replace(".", "").strip())
            except ValueError:
                l_no = auto_line_no

        auto_line_no = l_no + 1

        desc_str = str(item_dict.get("description") or "").strip()
        brand_str = str(item_dict.get("brand") or "").strip()
        uom_str = str(item_dict.get("uom") or "Nos").strip()

        qty = to_decimal(item_dict.get("qty"))
        if qty == Decimal("0.00"):
            qty = Decimal("1.00")
        rate = to_decimal(item_dict.get("rate"))
        gross = to_decimal(item_dict.get("gross_amount"))
        if gross == Decimal("0.00") and rate > Decimal("0.00"):
            gross = rate * qty

        disc_pct_raw = to_decimal(item_dict.get("discount_pct"))
        disc_pct = disc_pct_raw * Decimal("100.00") if (Decimal("0.00") < disc_pct_raw < Decimal("1.00")) else disc_pct_raw
        disc_amt = to_decimal(item_dict.get("discount_amount"))
        if disc_amt == Decimal("0.00") and disc_pct > Decimal("0.00"):
            disc_amt = (gross * disc_pct) / Decimal("100.00")

        taxable = to_decimal(item_dict.get("taxable_amount"))
        if taxable == Decimal("0.00") and gross > Decimal("0.00"):
            taxable = gross - disc_amt

        gst_pct_raw = to_decimal(item_dict.get("gst_pct"))
        gst_pct = gst_pct_raw * Decimal("100.00") if (Decimal("0.00") < gst_pct_raw < Decimal("1.00")) else gst_pct_raw
        half_gst = gst_pct / Decimal("2.00")

        gst_amt = to_decimal(item_dict.get("gst_amount"))
        if gst_amt == Decimal("0.00") and gst_pct > Decimal("0.00"):
            gst_amt = (taxable * gst_pct) / Decimal("100.00")
        half_tax_amt = gst_amt / Decimal("2.00")

        final_val = to_decimal(item_dict.get("final_value"))
        if final_val == Decimal("0.00") and taxable > Decimal("0.00"):
            final_val = taxable + gst_amt

        item = {
            "line_no": l_no,
            "item_code": f"ITEM-{l_no}",
            "description": desc_str,
            "hsn_code": "",
            "brand": brand_str,
            "uom": uom_str or "Nos",
            "packing": "",
            "qty": qty,
            "rate": rate,
            "gross_amount": gross,
            "discount_pct": disc_pct,
            "discount_amount": disc_amt,
            "taxable_amount": taxable,
            "cgst_pct": half_gst,
            "cgst_amount": half_tax_amt,
            "sgst_pct": half_gst,
            "sgst_amount": half_tax_amt,
            "final_value": final_val,
            "status_eta": "In Stock",
        }
        line_items.append(validate_row_arithmetic(item))

    # Calculate grand total from line items if not extracted
    if quotation_dict["grand_total_final"] == Decimal("0.00") and line_items:
        quotation_dict["grand_total_final"] = sum(to_decimal(i.get("final_value") or 0) for i in line_items)
        quotation_dict["grand_total_taxable"] = sum(to_decimal(i.get("taxable_amount") or 0) for i in line_items)
        quotation_dict["grand_total_cgst"] = sum(to_decimal(i.get("cgst_amount") or 0) for i in line_items)
        quotation_dict["grand_total_sgst"] = sum(to_decimal(i.get("sgst_amount") or 0) for i in line_items)

    # Classify document
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

