import logging
import re
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
import pdfplumber
import pdf2image
import pytesseract
from app.quotation_extraction.validator import to_decimal, validate_row_arithmetic, validate_quotation_totals
from app.quotation_extraction.exceptions import QuotationParsingError

logger = logging.getLogger(__name__)


def parse_date(date_str: str) -> Optional[date]:
    """Parse dates in various formats (e.g. 15-Jun-2026, 02/02/2024, 15-07-2026)."""
    if not date_str:
        return None
    cleaned = date_str.strip()
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    # Try generic parser
    try:
        from dateutil.parser import parse
        return parse(cleaned, dayfirst=True).date()
    except Exception:
        logger.warning(f"Could not parse date string: '{date_str}'")
        return None


def clean_text_layer(text: str) -> str:
    """Clean CID character map issues and stray newlines."""
    if not text:
        return ""
    cleaned = text.replace("(cid:415)", "ti").replace("(cid:425)", "tt")
    return cleaned.strip()


def extract_header_from_text(text: str) -> Dict[str, Any]:
    """Fallback metadata extractor using full page text layer."""
    header_data: Dict[str, Any] = {
        "vendor_name": None,
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
    }
    if not text:
        return header_data

    # Document / Invoice / Quotation / PO / Guarantor / MRN No
    doc_no_match = re.search(r"(?i)(?:Invoice|Quotation|PO|Purchase\s*Order|Doc|Guarantor\s*No|MRN)\s*(?:no|number|\.)?\s*:\s*([A-Z0-9\-\/]+)", text)
    if doc_no_match:
        header_data["quotation_no"] = doc_no_match.group(1).strip()

    # Date of Issue / Invoice Date / Quotation Date / Statement Date
    date_match = re.search(r"(?i)(?:Date\s*of\s*issue|Invoice\s*date|Quotation\s*date|Statement\s*date|PO\s*date|Date)\s*:\s*([0-9A-Za-z\/\-]+)", text)
    if date_match:
        header_data["quotation_date"] = parse_date(date_match.group(1).strip())

    # Patient / Customer Name
    patient_match = re.search(r"(?i)(?:Patient\s*Name|Patient|Customer\s*Name|Customer|Client|Bill\s*To)\s*:\s*([A-Za-z\s]+?)(?:\s+Primary|\s+Date|\n|$)", text)
    if patient_match:
        header_data["customer_name"] = patient_match.group(1).strip()

    # Vendor (Seller) and Customer (Client)
    if "Seller:" in text and "Client:" in text:
        seller_pos = text.find("Seller:")
        client_pos = text.find("Client:")
        items_pos = text.find("ITEMS") if "ITEMS" in text else len(text)
        
        seller_block = text[seller_pos:client_pos]
        client_block = text[client_pos:items_pos]

        s_lines = [l.strip() for l in seller_block.split("\n") if l.strip()]
        for line in s_lines:
            if any(k in line.upper() for k in ["PVT LTD", "LTD", "LIMITED", "DISTRIBUTORS", "ENTERPRISES", "SUPPLIERS", "INC", "CORP", "HOSPITAL", "CLINIC", "HEALTH", "MEDICAL"]):
                header_data["vendor_name"] = line
                break

        c_lines = [l.strip() for l in client_block.split("\n") if l.strip()]
        for line in c_lines:
            if any(k in line.upper() for k in ["ELECTRONICS", "HUB", "COLLEGE", "HOSPITAL", "PHARMACY", "PVT", "LTD", "CORP"]):
                if not header_data["customer_name"]:
                    header_data["customer_name"] = line
                break

        v_gst = re.search(r"(?:GSTIN|Tax\s*Id)\s*:\s*([A-Z0-9]+)", seller_block)
        if v_gst:
            header_data["vendor_gstin"] = v_gst.group(1).strip()

        c_gst = re.search(r"(?:GSTIN|Tax\s*Id)\s*:\s*([A-Z0-9\-]+)", client_block)
        if c_gst:
            header_data["customer_gstin"] = c_gst.group(1).strip()
    else:
        # Check side-by-side Seller: Client: layout
        if "Seller:" in text and "Client:" in text:
            sc_match = re.search(r"Seller:\s*Client:\s*\n([^\n]+)", text)
            if sc_match:
                combined = sc_match.group(1).strip()
                m = re.match(r"^(.+?\b(?:Pvt\s+Ltd|Ltd|Limited|Enterprises|Suppliers|Distributors)\b)\s+(.+)$", combined, re.IGNORECASE)
                if m:
                    header_data["vendor_name"] = m.group(1).strip()
                    header_data["customer_name"] = m.group(2).strip()

        if not header_data["vendor_name"]:
            seller_match = re.search(r"(?i)Seller\s*:\s*\n?([^\n]+)", text)
            if seller_match:
                header_data["vendor_name"] = seller_match.group(1).strip()
            else:
                for line in text.split("\n")[:12]:
                    line_clean = line.strip()
                    if any(k in line_clean.upper() for k in ["PVT LTD", "LTD", "LIMITED", "DISTRIBUTORS", "ENTERPRISES", "SUPPLIERS", "HOSPITAL", "CLINIC", "HEALTHCARE", "MEDICAL", "COLLEGE", "INSTITUTE", "LAB", "DIAGNOSTICS"]):
                        header_data["vendor_name"] = line_clean
                        break

        vendor_gst_match = re.search(r"(?i)(?:GSTIN|Tax\s*Id)\s*:\s*([A-Z0-9]+)", text)
        if vendor_gst_match:
            header_data["vendor_gstin"] = vendor_gst_match.group(1).strip()

        if not header_data["customer_name"]:
            client_match = re.search(r"(?i)(?:Client|Customer|Bill\s*To)\s*:\s*\n?([^\n]+)", text)
            if client_match:
                header_data["customer_name"] = client_match.group(1).strip()

        client_tax_match = re.search(r"(?i)Client[\s\S]*?(?:Tax\s*Id|GSTIN)\s*:\s*([A-Z0-9\-]+)", text)
        if client_tax_match:
            header_data["customer_gstin"] = client_tax_match.group(1).strip()

    return header_data


def extract_header_fields(first_page_table: List[List[Any]], first_page_text: str = "") -> Dict[str, Any]:
    """Extract vendor, customer, and quotation details from table or text layer."""
    header_data = extract_header_from_text(first_page_text)

    if not first_page_table or len(first_page_table) < 2:
        return header_data

    # Overlay specific table fields if in AIC Enterprises 2-row table format
    vendor_block = clean_text_layer(first_page_table[0][0] or "")
    if "AIC ENTERPRISES" in vendor_block:
        header_data["vendor_name"] = "AIC Enterprises Pvt Ltd"
    elif not header_data["vendor_name"]:
        lines = [l.strip() for l in vendor_block.split("\n") if l.strip()]
        for line in lines:
            if "PVT" in line.upper() or "LTD" in line.upper() or "LIMITED" in line.upper():
                header_data["vendor_name"] = line
                break

    gst_match = re.search(r"GSTNo\.\s*:\s*([A-Z0-9]+)", vendor_block)
    if gst_match:
        header_data["vendor_gstin"] = gst_match.group(1).strip()

    if len(first_page_table) >= 2 and first_page_table[1]:
        customer_block = clean_text_layer(first_page_table[1][0] or "")
        quotation_block = clean_text_layer(first_page_table[1][11] or "") if len(first_page_table[1]) > 11 else ""

        cust_lines = [l.strip() for l in customer_block.split("\n") if l.strip()]
        name_candidates = []
        for line in cust_lines:
            if line.startswith("To ,") or "GST Catagery" in line or "GST Category" in line or "Department :" in line:
                continue
            if "GST No" in line:
                g_parts = line.split(":")
                if len(g_parts) > 1:
                    header_data["customer_gstin"] = g_parts[1].strip()
                continue
            if any(k in line for k in ["Kind Attention", "Kind A", "E-mail Id", "Email", "Enq. Ref", "Enq.Date"]):
                continue
            if any(c.isalpha() for c in line):
                name_candidates.append(line)

        if name_candidates:
            header_data["customer_name"] = name_candidates[0]

        for line in cust_lines:
            if "Enq. Ref.No" in line or "Enq. Ref" in line:
                header_data["enquiry_ref"] = line.split(":", 1)[1].strip()
            elif "Enq.Date" in line:
                enq_date_str = line.split(":", 1)[1].strip()
                header_data["enquiry_date"] = parse_date(enq_date_str)

        quote_lines = [l.strip() for l in quotation_block.split("\n") if l.strip()]
        for line in quote_lines:
            if "Quotation. No." in line or "Quotation No" in line or "Quota" in line:
                header_data["quotation_no"] = line.split(":", 1)[1].strip()
            elif "Payment Terms" in line:
                header_data["payment_terms"] = line.split(":", 1)[1].strip()
            elif "Currency" in line:
                header_data["currency"] = line.split(":", 1)[1].strip()
            elif "Validity" in line:
                v_date_str = line.split(":", 1)[1].strip()
                header_data["validity_date"] = parse_date(v_date_str)
            elif "Quotation. Date" in line or "Date" in line:
                d_parts = line.split(":")
                if len(d_parts) > 1:
                    header_data["quotation_date"] = parse_date(d_parts[1].strip())

    if not header_data["quotation_date"] and header_data["enquiry_date"]:
        header_data["quotation_date"] = header_data["enquiry_date"]

    return header_data


def extract_grand_totals(all_page_tables: List[List[List[Any]]]) -> Dict[str, Any]:
    """Extract printed grand total values and words from page tables."""
    totals_data = {
        "grand_total_taxable": Decimal("0.00"),
        "grand_total_cgst": Decimal("0.00"),
        "grand_total_sgst": Decimal("0.00"),
        "grand_total_final": Decimal("0.00"),
        "grand_total_words": None,
    }

    if not all_page_tables:
        return totals_data

    for tables in reversed(all_page_tables):
        for table in tables:
            for row in table:
                if not row or not row[0]:
                    continue
                row_str = " ".join([clean_text_layer(str(c or "")) for c in row])
                if "Grand Total" in row_str or "Total" in row_str:
                    if "Grand Total :" in row_str:
                        words_part = re.sub(r"(?i)Grand Total\s*:\s*(?:INR)?", "", row_str).strip()
                        totals_data["grand_total_words"] = words_part

                    numeric_tokens = []
                    for cell in row:
                        if cell is not None:
                            for token in str(cell).split():
                                clean_tok = token.replace("INR", "").replace(",", "").strip()
                                clean_test = clean_tok.replace("-", "").replace(".", "", 1)
                                if clean_test.isdigit():
                                    try:
                                        numeric_tokens.append(Decimal(clean_tok))
                                    except Exception:
                                        pass

                    if len(numeric_tokens) == 4:
                        totals_data["grand_total_taxable"] = numeric_tokens[0]
                        totals_data["grand_total_cgst"] = numeric_tokens[1]
                        totals_data["grand_total_sgst"] = numeric_tokens[2]
                        totals_data["grand_total_final"] = numeric_tokens[3]
                    elif len(numeric_tokens) == 3:
                        totals_data["grand_total_taxable"] = numeric_tokens[0]
                        totals_data["grand_total_cgst"] = numeric_tokens[1] / Decimal("2.0")
                        totals_data["grand_total_sgst"] = numeric_tokens[1] / Decimal("2.0")
                        totals_data["grand_total_final"] = numeric_tokens[2]

    return totals_data


def parse_generic_table_row(row: List[Any], headers: List[str]) -> Optional[Dict[str, Any]]:
    """Parse a generic table row into a structured line item dictionary."""
    if not row or len(row) < 3:
        return None
    
    s_no_str = str(row[0] or "").strip().rstrip('.')
    if not s_no_str.isdigit():
        return None
    line_no = int(s_no_str)

    header_map = {}
    for idx, h in enumerate(headers):
        h_clean = str(h or "").lower().replace('\n', ' ').strip()
        header_map[h_clean] = idx

    def get_col_val(key_substrings):
        for h, idx in header_map.items():
            if any(k in h for k in key_substrings):
                if idx < len(row):
                    return row[idx]
        return None

    desc_raw = get_col_val(["description", "item", "particulars"]) or (row[1] if len(row) > 1 else "")
    description = clean_text_layer(str(desc_raw or ""))

    qty_raw = get_col_val(["qty", "quantity"]) or (row[2] if len(row) > 2 else "1.00")
    qty = to_decimal(qty_raw)

    uom_raw = get_col_val(["um", "uom", "unit"]) or (row[3] if len(row) > 3 else "")
    uom = clean_text_layer(str(uom_raw or ""))

    rate_raw = get_col_val(["net price", "rate", "price", "unit price"]) or (row[4] if len(row) > 4 else "0.00")
    rate = to_decimal(rate_raw)

    gross_raw = get_col_val(["net worth", "gross", "gross worth", "amount", "total"]) or (row[5] if len(row) > 5 else "0.00")
    gross_amount = to_decimal(gross_raw)

    tax_pct_raw = get_col_val(["vat %", "vat", "tax %", "cgst %"]) or (row[6] if len(row) > 6 else "0.00")
    tax_pct = to_decimal(tax_pct_raw)

    final_raw = get_col_val(["gross worth", "final", "total worth", "final value"]) or (row[7] if len(row) > 7 else "0.00")
    final_value = to_decimal(final_raw)

    if rate == Decimal("0.00") and qty > Decimal("0.00") and gross_amount > Decimal("0.00"):
        rate = gross_amount / qty
    if gross_amount == Decimal("0.00") and rate > Decimal("0.00") and qty > Decimal("0.00"):
        gross_amount = rate * qty
    if final_value == Decimal("0.00") and gross_amount > Decimal("0.00"):
        tax_amt = (gross_amount * tax_pct) / Decimal("100.00")
        final_value = gross_amount + tax_amt

    tax_amt = (gross_amount * tax_pct) / Decimal("100.00")
    half_tax_pct = tax_pct / Decimal("2.00")
    half_tax_amt = tax_amt / Decimal("2.00")

    return {
        "line_no": line_no,
        "item_code": description.split()[0] if description else "",
        "description": description,
        "hsn_code": "",
        "brand": "",
        "uom": uom,
        "packing": "",
        "qty": qty,
        "rate": rate,
        "gross_amount": gross_amount,
        "discount_pct": Decimal("0.00"),
        "discount_amount": Decimal("0.00"),
        "taxable_amount": gross_amount,
        "cgst_pct": half_tax_pct,
        "cgst_amount": half_tax_amt,
        "sgst_pct": half_tax_pct,
        "sgst_amount": half_tax_amt,
        "final_value": final_value,
        "status_eta": "In Stock",
    }


def parse_line_item_row(row: List[Any], num_cols: int) -> Optional[Dict[str, Any]]:
    """Parse a single raw table row into quotation line item dict."""
    if not row or not row[0]:
        return None

    # Identify S.No / line number
    s_no_str = str(row[0]).strip().rstrip('.')
    if not s_no_str.isdigit():
        return None
    line_no = int(s_no_str)

    item_code = clean_text_layer(row[1]) if row[1] else ""
    desc_hsn = clean_text_layer(row[2]) if row[2] else ""
    brand = clean_text_layer(row[3]) if row[3] else ""

    # Parse Description and HSN
    hsn_code = ""
    description = desc_hsn
    hsn_match = re.search(r"-\s*(\d{6,8})\s*-?$", desc_hsn)
    if hsn_match:
        hsn_code = hsn_match.group(1).strip()
        description = re.sub(r"-\s*\d{6,8}\s*-?$", "", desc_hsn).strip()

    # Columns 4 and 5 are Packing and UOM in cells (swapped)
    packing = clean_text_layer(row[4]) if len(row) > 4 and row[4] else ""
    uom = clean_text_layer(row[5]) if len(row) > 5 and row[5] else ""

    qty = to_decimal(row[6]) if len(row) > 6 else Decimal("0.00")
    rate = to_decimal(row[7]) if len(row) > 7 else Decimal("0.00")
    gross_amount = to_decimal(row[8]) if len(row) > 8 else Decimal("0.00")
    discount_pct = to_decimal(row[9]) if len(row) > 9 else Decimal("0.00")
    discount_amount = to_decimal(row[10]) if len(row) > 10 else Decimal("0.00")

    status_eta = clean_text_layer(row[-1]) if row[-1] else ""
    status_eta = " ".join(status_eta.split())

    middle_cells = row[11:-1] if len(row) > 12 else []
    raw_tokens = []
    for cell in middle_cells:
        if cell is not None:
            raw_tokens.extend(str(cell).split())

    tokens = []
    i = 0
    while i < len(raw_tokens):
        t = raw_tokens[i].replace(",", "")
        if i + 1 < len(raw_tokens):
            next_t = raw_tokens[i+1].replace(",", "")
            if "." in t:
                parts = t.split(".")
                if len(parts) == 2 and len(parts[1]) == 1 and len(next_t) == 1 and next_t.isdigit():
                    t = t + next_t
                    i += 1
        tokens.append(t)
        i += 1

    numeric_tokens = []
    for t in tokens:
        t_clean = t.replace("-", "").replace(".", "", 1)
        if t_clean.isdigit():
            numeric_tokens.append(Decimal(t))

    taxable_amount = Decimal("0.00")
    cgst_pct = Decimal("0.00")
    cgst_amount = Decimal("0.00")
    sgst_pct = Decimal("0.00")
    sgst_amount = Decimal("0.00")
    final_value = Decimal("0.00")

    if len(numeric_tokens) == 6:
        taxable_amount = numeric_tokens[0]
        cgst_pct = numeric_tokens[1]
        cgst_amount = numeric_tokens[2]
        sgst_pct = numeric_tokens[3]
        sgst_amount = numeric_tokens[4]
        final_value = numeric_tokens[5]
    elif len(numeric_tokens) >= 5:
        taxable_amount = to_decimal(row[11]) if len(row) > 11 else Decimal("0.00")
        cgst_pct = to_decimal(row[12]) if len(row) > 12 else Decimal("0.00")
        cgst_amount = to_decimal(row[13]) if len(row) > 13 else Decimal("0.00")
        if num_cols == 17 and len(row) > 15:
            sgst_col_str = str(row[14] or "")
            parts = sgst_col_str.split()
            if len(parts) >= 2:
                sgst_amount = to_decimal(parts[-1])
                sgst_pct = to_decimal(parts[-2])
            final_value = to_decimal(row[15])
        elif len(row) > 16:
            sgst_pct = to_decimal(row[14])
            sgst_amount = to_decimal(row[15])
            final_value = to_decimal(row[16])

    if taxable_amount == Decimal("0.00") and final_value != Decimal("0.00"):
        expected_taxable = gross_amount - discount_amount
        if expected_taxable > 0:
            taxable_amount = expected_taxable

    item_dict = {
        "line_no": line_no,
        "item_code": item_code,
        "description": description,
        "hsn_code": hsn_code,
        "brand": brand,
        "uom": uom,
        "packing": packing,
        "qty": qty,
        "rate": rate,
        "gross_amount": gross_amount,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "taxable_amount": taxable_amount,
        "cgst_pct": cgst_pct,
        "cgst_amount": cgst_amount,
        "sgst_pct": sgst_pct,
        "sgst_amount": sgst_amount,
        "final_value": final_value,
        "status_eta": status_eta,
    }

    return item_dict


def process_text_pdf(pdf_path: Path) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Extract multiple quotations and line items from a text-based PDF using pdfplumber."""
    quotations_list = []
    
    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
        if num_pages == 0:
            return []

        # Group pages by quotation (or default to 1 group for non-AIC PDFs)
        quotation_groups: List[List[int]] = []
        current_group: List[int] = []

        for idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if "QUOTATION" in text and idx > 0:
                if current_group:
                    quotation_groups.append(current_group)
                    current_group = []
            current_group.append(idx)
        if current_group:
            quotation_groups.append(current_group)

        for group in quotation_groups:
            first_page_idx = group[0]
            first_page = pdf.pages[first_page_idx]
            first_page_text = first_page.extract_text() or ""
            first_page_tables = first_page.extract_tables() or []
            first_page_table = first_page_tables[0] if first_page_tables else []
            
            header_data = extract_header_fields(first_page_table, first_page_text)

            all_group_tables = [pdf.pages[i].extract_tables() for i in group if pdf.pages[i].extract_tables()]
            totals_data = extract_grand_totals(all_group_tables)

            from app.quotation_extraction.classifier import classify_document_text
            doc_type, confidence, reasoning = classify_document_text(first_page_text)

            quotation_dict = {
                **header_data,
                **totals_data,
                "source_file": pdf_path.name,
                "document_type": doc_type,
                "document_no": header_data.get("quotation_no"),
                "document_date": header_data.get("quotation_date") or header_data.get("enquiry_date"),
                "classification_confidence": confidence,
                "classification_reasoning": reasoning
            }

            line_items: List[Dict[str, Any]] = []
            for page_idx in group:
                page = pdf.pages[page_idx]
                tables = page.extract_tables()
                if not tables:
                    continue

                for table in tables:
                    if not table or len(table) < 1:
                        continue

                    # Check if table has a generic header row with items/description/qty
                    header_row_idx = -1
                    is_generic_items_table = False
                    for r_idx, row in enumerate(table):
                        row_cells_str = " ".join([str(c or "").lower() for c in row])
                        if ("no." in row_cells_str or "no" in row_cells_str or "item" in row_cells_str) and \
                           ("description" in row_cells_str or "qty" in row_cells_str or "net price" in row_cells_str or "worth" in row_cells_str):
                            header_row_idx = r_idx
                            is_generic_items_table = True
                            break

                    if is_generic_items_table and header_row_idx != -1:
                        headers = table[header_row_idx]
                        for row_idx in range(header_row_idx + 1, len(table)):
                            row = table[row_idx]
                            if not row:
                                continue
                            item = parse_generic_table_row(row, headers)
                            if item:
                                item = validate_row_arithmetic(item)
                                line_items.append(item)
                    else:
                        start_row = 4 if page_idx == first_page_idx else 2
                        num_cols = len(table[0]) if table else 18

                        for row_idx in range(start_row, len(table)):
                            row = table[row_idx]
                            if not row:
                                continue
                            row_str = clean_text_layer(str(row[0]))
                            if "Grand Total" in row_str or "Yours Sincerely" in row_str or "Remarks" in row_str:
                                continue
                            
                            item = parse_line_item_row(row, num_cols)
                            if item:
                                item = validate_row_arithmetic(item)
                                line_items.append(item)

            # Auto-calculate totals if totals_data was empty but line items exist
            if totals_data["grand_total_final"] == Decimal("0.00") and line_items:
                calc_taxable = sum(i["taxable_amount"] for i in line_items)
                calc_cgst = sum(i["cgst_amount"] for i in line_items)
                calc_sgst = sum(i["sgst_amount"] for i in line_items)
                calc_final = sum(i["final_value"] for i in line_items)

                quotation_dict["grand_total_taxable"] = calc_taxable
                quotation_dict["grand_total_cgst"] = calc_cgst
                quotation_dict["grand_total_sgst"] = calc_sgst
                quotation_dict["grand_total_final"] = calc_final

            quotation_dict = validate_quotation_totals(quotation_dict, line_items)
            quotations_list.append((quotation_dict, line_items))

    return quotations_list


def normalize_and_extract_item_code(raw_code: str, raw_desc: str) -> Tuple[str, str]:
    """
    Intelligently extracts, cleans, and isolates item codes (CPT, HSN, Part #, Catalog #)
    from raw OCR tokens and description strings, correcting common OCR digit misreads.
    """
    code = (raw_code or "").strip()
    desc = (raw_desc or "").strip()

    # 1. Check if description starts with a leading code pattern (e.g. "0270 Medical/Surgical Supplies" or "99213 Office Visit")
    if not code or len(code) <= 1:
        leading_code_match = re.match(r"^([A-Za-z0-9\-\/]{3,10})\s+[\-\:]?\s*(.+)$", desc)
        if leading_code_match:
            candidate_code = leading_code_match.group(1).strip()
            if re.search(r"\d", candidate_code) or len(candidate_code) in (4, 5, 6, 8):
                code = candidate_code
                desc = leading_code_match.group(2).strip()

    # 2. Check if code is embedded with hyphens/colons inside description (e.g. "Medical/Surgical Supplies (CPT: 0270)")
    if not code:
        embedded_match = re.search(r"(?:CPT|Code|HSN|Part\s*#?|Cat\s*#?)\s*[\:\-\s]\s*([A-Za-z0-9\-]{3,10})", desc, re.IGNORECASE)
        if embedded_match:
            code = embedded_match.group(1).strip()

    # 3. Clean and Normalize OCR Digit Misreads in Numeric Item Codes (e.g., CPT/HSN codes)
    if code:
        if len(code) in (4, 5, 6, 7, 8) and re.search(r"\d", code):
            cleaned_code = []
            for ch in code:
                if ch in ('O', 'o'):
                    cleaned_code.append('0')
                elif ch in ('I', 'l', '|'):
                    cleaned_code.append('1')
                elif ch in ('Z', 'z') and len(code) in (4, 5, 8):
                    cleaned_code.append('2')
                elif ch in ('S', 's') and len(code) in (4, 5, 8):
                    cleaned_code.append('5')
                elif ch in ('B') and len(code) in (4, 5, 8):
                    cleaned_code.append('8')
                else:
                    cleaned_code.append(ch)
            code = "".join(cleaned_code).upper()

    return code, desc


def is_duplicate_line_item(new_item: Dict[str, Any], existing_items: List[Dict[str, Any]]) -> bool:
    """
    Checks if a newly extracted line item is a duplicate or misread repeat of an already extracted line item.
    """
    new_desc = (new_item.get("description") or "").lower().strip()
    new_code = (new_item.get("item_code") or "").lower().strip()
    new_val = new_item.get("final_value") or new_item.get("gross_amount")

    for existing in existing_items:
        ex_desc = (existing.get("description") or "").lower().strip()
        ex_code = (existing.get("item_code") or "").lower().strip()
        ex_val = existing.get("final_value") or existing.get("gross_amount")

        if new_val != ex_val:
            continue

        # 1. Exact or normalized description match
        if new_desc and ex_desc and (new_desc == ex_desc or new_desc in ex_desc or ex_desc in new_desc):
            # Update existing item code if new code is longer/more specific
            if len(new_code) > len(ex_code) and (not ex_code or new_code.startswith(ex_code)):
                existing["item_code"] = new_item["item_code"]
            return True

        # 2. Code prefix match (e.g. 026 vs 0260)
        if new_code and ex_code:
            if new_code == ex_code or new_code.startswith(ex_code) or ex_code.startswith(new_code):
                if len(new_code) > len(ex_code):
                    existing["item_code"] = new_item["item_code"]
                return True

    return False


def parse_ocr_line_items(text: str) -> List[Dict[str, Any]]:
    line_items = []
    line_no = 1
    
    for line in text.split("\n"):
        line_str = line.strip()
        if not line_str:
            continue
        
        lower = line_str.lower()
        if any(k in lower for k in ["total", "subtotal", "billed", "adjustments", "amount due", "statement date", "group no", "npi:", "phone:", "address:"]):
            continue

        num_match = re.search(r"^\s*(\d{1,3})[\.\s]+([A-Za-z0-9\-\/]+)?\s+([A-Za-z0-9\s\,\-\(\)\/]+?)\s+(\d+(?:\.\d+)?)\s+(?:([A-Za-z]+)\s+)?[\$₹]?\s*([\d\,]+\.\d{2})\s+[\$₹]?\s*([\d\,]+\.\d{2})", line_str)
        if num_match:
            idx, code, desc, qty, uom, rate, amt = num_match.groups()
            l_no = int(idx) if idx and idx.isdigit() else line_no
            r_val = Decimal(rate.replace(",", ""))
            a_val = Decimal(amt.replace(",", ""))
            q_val = Decimal(qty) if qty else Decimal("1.00")
            desc_clean = desc.strip()
            
            clean_c, clean_d = normalize_and_extract_item_code(code, desc_clean)
            candidate = {
                "line_no": l_no,
                "item_code": clean_c,
                "description": clean_d,
                "hsn_code": "",
                "brand": "",
                "uom": uom or "Nos",
                "packing": "",
                "item_date": "",
                "qty": q_val,
                "rate": r_val,
                "gross_amount": a_val,
                "discount_pct": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "taxable_amount": a_val,
                "cgst_pct": Decimal("0.00"),
                "cgst_amount": Decimal("0.00"),
                "sgst_pct": Decimal("0.00"),
                "sgst_amount": Decimal("0.00"),
                "final_value": a_val,
                "status_eta": "In Stock",
            }

            if is_duplicate_line_item(candidate, line_items):
                continue

            line_items.append(candidate)
            line_no += 1
            continue

        date_code_match = re.search(r"(?:(\d{2}/\d{2}/\d{4})\s+)?([A-Za-z0-9\-]{3,8})?\s+([A-Za-z0-9\s\,\-\(\)\/]+?)\s+[\$₹]?\s*([\d\,]+\.\d{2})", line_str)
        if date_code_match:
            dt, code, desc, amt = date_code_match.groups()
            if desc and len(desc.strip()) > 2 and amt:
                val = Decimal(amt.replace(",", ""))
                desc_clean = desc.strip()
                
                clean_c, clean_d = normalize_and_extract_item_code(code, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c,
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": "",
                    "packing": "",
                    "item_date": dt.strip() if dt else "",
                    "qty": None,
                    "rate": None,
                    "gross_amount": val,
                    "discount_pct": Decimal("0.00"),
                    "discount_amount": Decimal("0.00"),
                    "taxable_amount": val,
                    "cgst_pct": Decimal("0.00"),
                    "cgst_amount": Decimal("0.00"),
                    "sgst_pct": Decimal("0.00"),
                    "sgst_amount": Decimal("0.00"),
                    "final_value": val,
                    "status_eta": "In Stock",
                }

                if is_duplicate_line_item(candidate, line_items):
                    continue

                line_items.append(candidate)
                line_no += 1

    return line_items


def parse_ocr_totals(text: str) -> Dict[str, Decimal]:
    totals = {
        "grand_total_taxable": Decimal("0.00"),
        "grand_total_cgst": Decimal("0.00"),
        "grand_total_sgst": Decimal("0.00"),
        "grand_total_final": Decimal("0.00"),
    }
    
    for line in text.split("\n"):
        line_clean = line.strip()
        if not line_clean:
            continue

        lower = line_clean.lower()
        if any(k in lower for k in ["total billed", "total charges", "grand total", "net amount", "total amount", "patient amount due", "amount due", "insurance adjustments", "adjustments"]):
            m = re.search(r"[\$₹]?\s*([\-\+]?[\d\,]+\.\d{2})", line_clean)
            if m:
                raw_str = m.group(1).replace(",", "")
                val = Decimal(raw_str.replace("-", "").replace("+", ""))
                if "due" in lower or "net amount" in lower or "patient amount" in lower or "balance" in lower:
                    totals["grand_total_final"] = val
                elif "billed" in lower or "taxable" in lower or "subtotal" in lower or "total charges" in lower:
                    totals["grand_total_taxable"] = val

    return totals


def process_scanned_pdf(
    pdf_path: Path, openai_api_key: str = ""
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """OCR/Vision fallback pipeline for scanned quotation PDFs."""
    try:
        images = pdf2image.convert_from_path(pdf_path)
    except Exception as e:
        raise QuotationParsingError(f"pdf2image failed to convert PDF to images: {e}")

    logger.info(f"Scanned PDF converted to {len(images)} page images.")
    text_parts = []
    for idx, img in enumerate(images):
        page_text = pytesseract.image_to_string(img)
        text_parts.append(f"=== Page {idx+1} ===\n{page_text}")
    
    full_text = "\n\n".join(text_parts)
    from app.quotation_extraction.classifier import classify_document_text
    doc_type, confidence, reasoning = classify_document_text(full_text)

    header_data = extract_header_from_text(full_text)
    totals_data = parse_ocr_totals(full_text)
    line_items = parse_ocr_line_items(full_text)

    quotation_dict = {
        **header_data,
        **totals_data,
        "grand_total_words": None,
        "source_file": pdf_path.name,
        "document_type": doc_type,
        "document_no": header_data.get("quotation_no"),
        "document_date": header_data.get("quotation_date"),
        "classification_confidence": confidence,
        "classification_reasoning": reasoning,
        "extraction_status": "ok" if line_items else "needs_review"
    }

    return [(quotation_dict, line_items)]


def extract_pdf_quotation(
    pdf_path: Path, force_ocr: bool = False
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Main entry point for extracting quotation header and line items from a PDF."""
    if not pdf_path.exists():
        raise QuotationParsingError(f"PDF file does not exist: {pdf_path}")

    if force_ocr:
        return process_scanned_pdf(pdf_path)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            has_text = False
            for page in pdf.pages:
                text = page.extract_text() or ""
                if len(text.strip()) > 30:
                    has_text = True
                    break
        
        if has_text:
            logger.info(f"Extracting '{pdf_path.name}' using text-layer PDF Plumber.")
            return process_text_pdf(pdf_path)
        else:
            logger.info(f"Extracting '{pdf_path.name}' using OCR fallback pipeline.")
            return process_scanned_pdf(pdf_path)

    except QuotationParsingError:
        raise
    except Exception as e:
        logger.error(f"pdfplumber failed on '{pdf_path.name}': {e}. Falling back to OCR.")
        try:
            return process_scanned_pdf(pdf_path)
        except Exception as ocr_err:
            raise QuotationParsingError(f"Both text-layer and OCR pipelines failed on {pdf_path.name}: {ocr_err}")


def extract_image_quotation(
    image_path: Path
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Main entry point for extracting quotation header and line items from a JPG, PNG, or image document."""
    if not image_path.exists():
        raise QuotationParsingError(f"Image file does not exist: {image_path}")

    logger.info(f"Extracting image document '{image_path.name}' using OCR pipeline...")

    try:
        from PIL import Image
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
    except Exception as e:
        raise QuotationParsingError(f"Failed to open image file {image_path.name}: {e}")

    full_text = ""
    try:
        full_text = clean_text_layer(pytesseract.image_to_string(img, config="--psm 6"))
        if len(full_text.strip()) < 20:
            full_text = clean_text_layer(pytesseract.image_to_string(img))
    except Exception as e:
        logger.warning(f"Pytesseract failed on image {image_path.name}: {e}")

    from app.quotation_extraction.classifier import classify_document_text
    doc_type, confidence, reasoning = classify_document_text(full_text)

    header_data = extract_header_from_text(full_text)
    totals_data = parse_ocr_totals(full_text)
    line_items = parse_ocr_line_items(full_text)

    quotation_dict = {
        **header_data,
        **totals_data,
        "grand_total_words": None,
        "source_file": image_path.name,
        "document_type": doc_type,
        "document_no": header_data.get("quotation_no"),
        "document_date": header_data.get("quotation_date"),
        "classification_confidence": confidence,
        "classification_reasoning": reasoning,
        "extraction_status": "ok" if line_items else "needs_review"
    }

    return [(quotation_dict, line_items)]
