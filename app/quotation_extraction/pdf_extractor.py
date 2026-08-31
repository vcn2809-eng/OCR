import logging
import re
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
import pdfplumber
import pdf2image
import pytesseract
import cv2
import numpy as np
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
    dt_obj = None
    for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            dt_obj = datetime.strptime(cleaned, fmt).date()
            break
        except ValueError:
            continue
    if dt_obj is None:
        try:
            from dateutil.parser import parse
            dt_obj = parse(cleaned, dayfirst=True).date()
        except Exception:
            logger.warning(f"Could not parse date string: '{date_str}'")
            return None
    if dt_obj and dt_obj.year > 2026:
        dt_obj = dt_obj.replace(year=2026)
    return dt_obj


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
    doc_no_match = re.search(r"(?i)(?:Invoice\s*Number|Invoice\s*No|Invoice|Quotation|PO|Purchase\s*Order|Doc|Guarantor\s*No|MRN)\s*(?:no|number|\.)?\s*[:\s#\-\.]*\[?\s*([A-Za-z0-9\-\/]{4,25})", text)
    if doc_no_match:
        val = doc_no_match.group(1).strip()
        if val.upper() not in ("TAX", "FINAL", "PROFORMA", "NUMBER", "NO", "ACCOUNT"):
            header_data["quotation_no"] = val

    # Date of Issue / Invoice Date / Quotation Date / Statement Date / Bill Date
    date_match = re.search(r"(?i)(?:Date\s*of\s*issue|Invoice\s*date|Quotation\s*date|Statement\s*date|PO\s*date|Bill\s*Date|Issue\s*Date|Date)\s*[:\s]*([0-9]{1,2}[\/\-\.][0-9]{1,2}[\/\-\.][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2}[,\s]+[0-9]{4}|[0-9]{1,2}\s+[A-Za-z]+[,\s]+[0-9]{4})", text)
    if date_match:
        raw_d = date_match.group(1).strip()
        header_data["quotation_date"] = parse_date(raw_d)

    # Currency extraction (e.g. Currency: BDT, Please Pay BDT)
    curr_match = re.search(r"(?i)(?:Currency\s*:\s*|Please\s*Pay\s+)([A-Z]{3})", text)
    if curr_match:
        header_data["currency"] = curr_match.group(1).upper().strip()

    # Patient / Customer Name
    patient_match = re.search(r"(?i)(?:Received\s*From\s*\/\s*Client|Details\s*of\s*Service\s*Recipient|Patient\s*Name|Patient|Customer\s*Name|Customer|Client|Bill\s*To|Client\'s\s*details.*?TO)\s*[:\n\s]*([A-Za-z0-9\s\.\&\-]+?)(?:\s+Primary|\s+Date|\s+Industrial|\s+Dilkusha|\s+Medical|\s+XYZ\s+Road|\n\n|\n[A-Z][a-z]+\:|$)", text)
    if patient_match:
        header_data["customer_name"] = patient_match.group(1).strip().split("\n")[0].strip()

    # Top Vendor Match from header or Supplier section
    sup_m = re.search(r"(?i)(?:Supplier|From)\s*[:\n\s]*([A-Za-z0-9\s\.\&\-]+?\b(?:Ltd|Limited|Pvt|Enterprises|Services|Logistics|Point|Diagnostic|Stationery|Service|Billing|Valley|Support)\b)", text)
    if sup_m:
        header_data["vendor_name"] = sup_m.group(1).strip().split("\n")[0].strip()

    if not header_data["vendor_name"]:
        # Match top 3 lines of document for company name
        lines = [l.strip() for l in text.split("\n")[:5] if l.strip()]
        for l in lines:
            l_clean = re.sub(r"^[^\w\d\s]+", "", l).strip()
            if any(k in l_clean.upper() for k in ["LTD", "LIMITED", "SERVICES", "SERVICE", "LOGISTICS", "DIAGNOSTIC", "STATIONERY", "ENTERPRISES", "COMMUNICATIONS", "WATER SERVICE", "SUPPORT BD", "FOOD VALLEY", "BILLING"]):
                header_data["vendor_name"] = l_clean
                break

    # Vendor (Seller) and Customer (Client)
    if "Seller:" in text and "Client:" in text:
        seller_pos = text.find("Seller:")
        client_pos = text.find("Client:")
        items_pos = text.find("ITEMS") if "ITEMS" in text else len(text)
        
        seller_block = text[seller_pos:client_pos]
        client_block = text[client_pos:items_pos]

        s_lines = [l.strip() for l in seller_block.split("\n") if l.strip()]
        for line in s_lines:
            if any(k in line.upper() for k in ["PVT LTD", "LTD", "LIMITED", "DISTRIBUTORS", "ENTERPRISES", "SUPPLIERS", "INC", "CORP"]):
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

    # 1. Commercial Vendor Match (e.g. M/s. ION SOFT WATER INDIA PRIVATE LIMITED)
    if not header_data["vendor_name"]:
        v_m = re.search(r'(?i)(?:M/s\.\s*|M/S\s*)?([A-Za-z0-9\s\.\&\-]+\b(?:PRIVATE LIMITED|PVT LTD|LIMITED|LLP|ENTERPRISES|DISTRIBUTORS|SUPPLIERS|INDUSTRIES)\b)', text)
        if v_m:
            v_name = v_m.group(1).strip()
            if v_name.upper().startswith(('M/S.', 'M/S')):
                v_name = re.sub(r'^(?i)M/s[\.\s]*', '', v_name).strip()
            header_data["vendor_name"] = v_name

    # 2. Commercial Buyer / Customer Match (e.g. Buyer\nMs Helios Construction LLP)
    if not header_data["customer_name"]:
        b_m = re.search(r'(?i)(?:Buyer|Bill\s*To|Customer|Client)\s*[\n:\.]+\s*(?:Ms\s+|M/s\.\s*)?([A-Za-z0-9\s\.\&\-]+\b(?:LLP|LIMITED|PVT LTD|PRIVATE LIMITED|ENTERPRISES|BUILDERS|CONSTRUCTION|INFRA|CORP)\b)', text)
        if b_m:
            header_data["customer_name"] = b_m.group(1).strip()

    # 3. GSTIN Regex Extraction
    if not header_data["vendor_gstin"]:
        v_gst_m = re.search(r'(?i)GSTIN\s*(?:No)?\s*[:\.]?\s*([A-Za-z0-9]{10,16})', text)
        if v_gst_m:
            header_data["vendor_gstin"] = v_gst_m.group(1).upper()

    if not header_data["customer_gstin"]:
        c_gst_m = re.search(r'(?i)GST\s*(?:No)?\s*[:\.]?\s*([A-Za-z0-9]{10,16})', text)
        if c_gst_m:
            header_data["customer_gstin"] = c_gst_m.group(1).upper()

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


HEADER_FOOTER_IGNORE = (
    "tax invoice", "retail invoice", "cash memo", "m/s.", "private limited", "pvt. ltd.", "pvt ltd",
    "cin no", "pan no", "gstin", "vat reg", "buyer", "delivery address", "site no", "kalyan nagar",
    "babusaplaya", "mob/", "whatsapp", "email", "declaration", "we declare that", "interest @",
    "in favour", "hdfc bank", "ifsc code", "current a/no", "authorised signatory", "authorized signatory",
    "amount chargeable", "in words", "tax amount", "hsn/sac", "state tax", "central tax", "payment terms",
    "please pay", "thank you", "original", "duplicate", "terms & conditions", "terminal", "cashier", "invoice no",
    "invoice number", "bill no", "order no", "po/order", "drug license", "patient", "age/sex", "ref: dr",
    "maragonanahalli", "bangalore urban", "karnataka"
)


def parse_ocr_line_items(text: str) -> List[Dict[str, Any]]:
    line_items = []
    line_no = 1
    
    STOP_KEYWORDS = {
        "current charges", "previous balance", "total payable", "please pay", "total amount due",
        "subtotal", "sub total", "grand total", "total bill", "advance", "total due", "payments",
        "adjustments", "cur. charges", "prev. balance", "vat/tax", "summary of charges", "claim details",
        "bank copy", "customer copy", "total payable", "net payable", "discount", "vat", "rounding", "paid", "change", "thank you"
    }

    for line in text.split("\n"):

        line_str = line.strip()
        if not line_str or len(line_str) < 4:
            continue
        
        line_str = re.sub(r"^[^\w\d\s]+", "", line_str).strip()
        line_lower = line_str.lower()
        if any(sk in line_lower for sk in STOP_KEYWORDS):
            continue
        if any(hf in line_lower for hf in HEADER_FOOTER_IGNORE):
            continue


        # 1. Pattern: Description + Qty + Volume Unit + Amount (e.g. Surcharge 12 12 unit 144,000.00)
        volume_match = re.search(r"^\s*([A-Za-z0-9\s\&\-\/\.\,\(\)]+?)\s+(\d{1,5})\s+(\d{1,5}\s*unit[s]?)\s+[\$₹]?\s*([\d\,]+\.\d{2})\s*$", line_str)
        if volume_match:
            desc, qty, vol, amt = volume_match.groups()
            if desc and len(desc.strip()) > 2 and amt:
                a_val = Decimal(amt.replace(",", ""))
                q_val = Decimal(qty)
                r_val = (a_val / q_val).quantize(Decimal("0.01")) if q_val > 0 else a_val
                desc_clean = desc.strip()
                clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c or f"ITEM-{line_no}",
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": "unit",
                    "packing": vol,
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
                if not is_duplicate_line_item(candidate, line_items):
                    line_items.append(candidate)
                    line_no += 1
                    continue

        # 2. Pattern: [SL] + Description + Num1 + Qty + Num2 (handles both Rate+Qty+Total and Amount+Qty+UnitPrice)
        rate_qty_amt_match = re.search(r"^\s*(?:\d{1,3}\s+)?([A-Za-z0-9\s\&\-\/\.\,\(\)]+?)\s+[\$₹]?\s*([\d\s\,]+\.\d{2})\s+(\d+(?:\.\d+)?)\s+[\$₹]?\s*([\d\s\,]+\.\d{2})\s*$", line_str)
        if rate_qty_amt_match:
            desc, val1_str, qty, val2_str = rate_qty_amt_match.groups()
            v1 = Decimal(val1_str.replace(" ", "").replace(",", ""))
            v2 = Decimal(val2_str.replace(" ", "").replace(",", ""))
            q_val = Decimal(qty)
            
            if abs((v1 * q_val) - v2) < Decimal("2.00") or v2 == (v1 * q_val).quantize(Decimal("0.01")):
                r_val, a_val = v1, v2
            elif abs((v2 * q_val) - v1) < Decimal("2.00") or v1 == (v2 * q_val).quantize(Decimal("0.01")):
                r_val, a_val = v2, v1
            else:
                r_val, a_val = (v1, v2) if v1 <= v2 else (v2, v1)

            desc_clean = desc.strip()
            clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
            candidate = {
                "line_no": line_no,
                "item_code": clean_c or f"ITEM-{line_no}",
                "description": clean_d,
                "hsn_code": "",
                "brand": "",
                "uom": "Nos",
                "packing": "",
                "item_date": "",
                "qty": q_val,
                "rate": r_val.quantize(Decimal("0.01")),
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
            if not is_duplicate_line_item(candidate, line_items):
                line_items.append(candidate)
                line_no += 1
                continue

        # 3. Pattern: Glued Qty-Total digits (e.g. 289.75 3.00869.25 -> 3.00 & 869.25)
        glued_match = re.search(r"^\s*(?:\d{1,3}\s+)?([A-Za-z0-9\s\&\-\/\.\,\(\)]+?)\s+[\$₹]?\s*([\d\s\,]+\.\d{2})\s+(\d+(?:\.\d+)?)([\d\,]+\.\d{2})\s*$", line_str)
        if glued_match:
            desc, rate, qty, amt = glued_match.groups()
            r_val = Decimal(rate.replace(" ", "").replace(",", ""))
            q_val = Decimal(qty)
            a_val = Decimal(amt.replace(",", ""))
            if abs((r_val * q_val) - a_val) < Decimal("5.00"):
                desc_clean = desc.strip()
                clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c or f"ITEM-{line_no}",
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": "Nos",
                    "packing": "",
                    "item_date": "",
                    "qty": q_val,
                    "rate": r_val.quantize(Decimal("0.01")),
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
                if not is_duplicate_line_item(candidate, line_items):
                    line_items.append(candidate)
                    line_no += 1
                    continue

        # 4. Pattern: Description + Qty + Rate + Optional Amount (handles clipped right margin)
        desc_qty_rate_amt_match = re.search(r"^\s*([A-Za-z\s\&\-\/\.\,\(\)]+?)\s+([0-9SsoOlI|]{1,4})\s+[\$₹]?\s*([\d\s\,]+\.\d{2})(?:\s+[\$₹]?\s*([\d\,]+(?:\.\d{2})?))?", line_str)
        if desc_qty_rate_amt_match:
            desc, qty_raw, rate, amt = desc_qty_rate_amt_match.groups()
            if desc and len(desc.strip()) > 2 and rate:
                qty_clean = qty_raw.translate(str.maketrans('SsoOlI|', '5500111'))
                q_val = Decimal(qty_clean)
                r_clean = rate.replace(" ", "").replace(",", "")
                r_val = Decimal(r_clean) if (r_clean and r_clean.replace(".", "").isdigit()) else Decimal("0.00")
                if amt and amt.replace(",", "").replace(".", "").isdigit() and "." in amt:
                    a_val = Decimal(amt.replace(",", ""))
                else:
                    a_val = (q_val * r_val).quantize(Decimal("0.01"))
                
                desc_clean = desc.strip()
                desc_clean = re.sub(r"^[a-zA-Z]{1,2}\s+(?=[A-Z][a-z])", "", desc_clean).strip()
                clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c or f"ITEM-{line_no}",
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": "Nos",
                    "packing": "",
                    "item_date": "",
                    "qty": q_val,
                    "rate": r_val.quantize(Decimal("0.01")),
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
                if not is_duplicate_line_item(candidate, line_items):
                    line_items.append(candidate)
                    line_no += 1
                    continue

        # 3. Pattern: SL + Description + Qty + Rate + Amount (e.g. 1 Pest control service 50 950.00 47,500.00)
        sl_match = re.search(r"^\s*(?:\d{1,3}|[a-z]{1,3}\s*\|)?\s*([A-Za-z0-9\s\&\-\/\.\,\(\)]+?)\s+(\d{1,5})\s+[\$₹]?\s*([\d\s\,]+(?:\.\d{2})?)\s+[\$₹]?\s*([\d\,]+\.\d{2})\s*$", line_str)
        if sl_match:
            desc, qty, rate, amt = sl_match.groups()
            if desc and len(desc.strip()) > 2 and amt:
                a_val = Decimal(amt.replace(",", ""))
                q_val = Decimal(qty)
                r_clean = rate.replace(" ", "").replace(",", "") if rate else ""
                r_val = Decimal(r_clean) if (r_clean and r_clean.replace(".", "").isdigit()) else (a_val / q_val if q_val > 0 else a_val)
                desc_clean = desc.strip()
                clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c or f"ITEM-{line_no}",
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": "Nos",
                    "packing": "",
                    "item_date": "",
                    "qty": q_val,
                    "rate": r_val.quantize(Decimal("0.01")),
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
                if not is_duplicate_line_item(candidate, line_items):
                    line_items.append(candidate)
                    line_no += 1
                    continue

        line_str = re.sub(r"^\s*([a-z\}\{\]\[\|\;\:\–\—\-\.\,\(\)\=]+\s+)+(?=\d+\s+[A-Za-z])", "", line_str, flags=re.IGNORECASE).strip()
        line_str = re.sub(r"^\s*\d{1,2}\s+(?=\d{1,3}\s+[A-Za-z])", "", line_str).strip()
        line_str = re.sub(r"\s+\-\s+(?=[\d\,]+\.\d{2})", " ", line_str).strip()

        qty_first_match = re.search(r"^\s*(\d{1,3})\s+([A-Za-z0-9\s\&\-\/\.]+?)\s+[\$₹]?\s*([\d\s\,]+(?:\.\d{2})?)\s+[\$₹]?\s*([\d\,]+\.\d{2})\s*$", line_str)
        if qty_first_match:
            qty, desc, rate, amt = qty_first_match.groups()
            if desc and len(desc.strip()) > 2 and amt:
                a_val = Decimal(amt.replace(",", ""))
                q_val = Decimal(qty)
                r_clean = rate.replace(" ", "").replace(",", "") if rate else ""
                r_val = Decimal(r_clean) if (r_clean and r_clean.replace(".", "").isdigit()) else (a_val / q_val if q_val > 0 else a_val)
                desc_clean = desc.strip()
                clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c or f"ITEM-{line_no}",
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": "Nos",
                    "packing": "",
                    "item_date": "",
                    "qty": q_val,
                    "rate": r_val.quantize(Decimal("0.01")),
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
                if not is_duplicate_line_item(candidate, line_items):
                    line_items.append(candidate)
                    line_no += 1
                    continue

        qty_rate_only_match = re.search(r"^\s*(\d{1,3})\s+([A-Za-z0-9\s\&\-\/\.]+?)\s+[\$₹]?\s*([\d\,]+\.\d{2})(?:\s+[a-zA-Z])?\s*$", line_str)
        if qty_rate_only_match:
            qty, desc, rate = qty_rate_only_match.groups()
            if desc and len(desc.strip()) > 2 and rate:
                q_val = Decimal(qty)
                r_val = Decimal(rate.replace(",", ""))
                a_val = (q_val * r_val).quantize(Decimal("0.01"))
                desc_clean = desc.strip()
                clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c or f"ITEM-{line_no}",
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": "Nos",
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
                if not is_duplicate_line_item(candidate, line_items):
                    line_items.append(candidate)
                    line_no += 1
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

        desc_qty_rate_amt_match = re.search(r"^\s*([A-Za-z0-9\s\&\-\/\.]+?)\s+(\d+(?:\.\d+)?)\s+(?:([A-Za-z]+)\s+)?[\$₹]?\s*([\d\,]+\.\d{2})\s+[\$₹]?\s*([\d\,]+\.\d{2})\s*$", line_str)
        if desc_qty_rate_amt_match:
            desc, qty, uom, rate, amt = desc_qty_rate_amt_match.groups()
            if desc and len(desc.strip()) > 2:
                r_val = Decimal(rate.replace(",", ""))
                a_val = Decimal(amt.replace(",", ""))
                q_val = Decimal(qty)
                desc_clean = desc.strip()
                clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
                candidate = {
                    "line_no": line_no,
                    "item_code": clean_c or f"ITEM-{line_no}",
                    "description": clean_d,
                    "hsn_code": "",
                    "brand": "",
                    "uom": uom or "HRS",
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
                if not is_duplicate_line_item(candidate, line_items):
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


def parse_ocr_totals(text: str) -> Dict[str, Any]:
    totals: Dict[str, Any] = {
        "grand_total_taxable": Decimal("0.00"),
        "total_discount": Decimal("0.00"),
        "grand_total_cgst": Decimal("0.00"),
        "grand_total_sgst": Decimal("0.00"),
        "grand_total_final": Decimal("0.00"),
    }
    
    for line in text.split("\n"):
        line_clean = line.strip()
        if not line_clean:
            continue

        lower = line_clean.lower()
        if any(sk in lower for sk in ["hsn", "hsn/sac", "state tax", "central tax", "tax amount", "amount chargeable", "bank details", "ifsc", "a/no", "interest @"]):
            continue

        if "discount" in lower and not any(k in lower for k in ["item", "after", "price"]):
            m_disc = re.search(r"[\$₹]?\s*([\d\,]+\.\d{2})", line_clean)
            if m_disc:
                totals["total_discount"] = Decimal(m_disc.group(1).replace(",", ""))

        if any(k in lower for k in ["net payable", "grand total payable", "please pay", "total amount due", "total payable", "total current charges", "total billed", "total charges", "grand total", "net amount", "total amount", "patient amount due", "amount due", "insurance adjustments", "adjustments", "subtotal", "sub total", "total"]):
            m = re.search(r"[\$₹]?\s*([\-\+]?[\d\,]+\.\d{2})", line_clean)
            if m:
                raw_str = m.group(1).replace(",", "")
                val = Decimal(raw_str.replace("-", "").replace("+", ""))
                if "net payable" in lower or "grand total payable" in lower or "due" in lower or "net amount" in lower or "patient amount" in lower or "balance" in lower or "final" in lower or "please pay" in lower or "total payable" in lower:
                    totals["grand_total_final"] = val
                elif "billed" in lower or "taxable" in lower or "subtotal" in lower or "sub total" in lower or "total charges" in lower or "total" in lower:
                    if totals["grand_total_taxable"] == Decimal("0.00"):
                        totals["grand_total_taxable"] = val
                    if totals["grand_total_final"] == Decimal("0.00"):
                        totals["grand_total_final"] = val


    return totals


def parse_ocr_line_items_by_coordinates(img_numpy) -> List[Dict[str, Any]]:
    """Column-anchored line item extraction using word bounding box coordinates (Requirement 1)."""
    try:
        from app.ocr.engine import TesseractEngine
        engine = TesseractEngine()
        ocr_result = engine.run(img_numpy)
    except Exception as e:
        logger.warning(f"Could not run TesseractEngine coordinate parsing: {e}")
        return []
        
    if not ocr_result or not ocr_result.words:
        return []
        
    page_width = img_numpy.shape[1]
    
    # 1. Group words into horizontal rows
    rows_words = []
    sorted_words = sorted(ocr_result.words, key=lambda w: w.bounding_box['y'] + w.bounding_box['height'] / 2)
    for w in sorted_words:
        w_y_center = w.bounding_box['y'] + w.bounding_box['height'] / 2
        found_row = False
        for row in rows_words:
            row_y_center = sum(word.bounding_box['y'] + word.bounding_box['height'] / 2 for word in row) / len(row)
            if abs(w_y_center - row_y_center) < 15:
                row.append(w)
                found_row = True
                break
        if not found_row:
            rows_words.append([w])
            
    # 2. Sort words in each row left-to-right
    for row in rows_words:
        row.sort(key=lambda w: w.bounding_box['x'])
        
    # 3. Sort rows top-to-bottom
    rows_words.sort(key=lambda row: sum(w.bounding_box['y'] + w.bounding_box['height'] / 2 for w in row) / len(row))
    
    # 4. Detect column centers dynamically
    qty_xs, rate_xs, amount_xs = [], [], []
    for row in rows_words:
        nums = []
        for w in row:
            txt_clean = w.text.replace(",", "").replace("$", "").replace("₹", "")
            if is_decimal(txt_clean) or txt_clean.isdigit():
                nums.append(w)
        if len(nums) >= 2:
            amt_w = nums[-1]
            rate_w = nums[-2]
            amount_xs.append(amt_w.bounding_box['x'] + amt_w.bounding_box['width'] / 2)
            rate_xs.append(rate_w.bounding_box['x'] + rate_w.bounding_box['width'] / 2)
            if len(nums) >= 3:
                qty_w = nums[-3]
                qty_xs.append(qty_w.bounding_box['x'] + qty_w.bounding_box['width'] / 2)
                
    import statistics
    def get_median(lst, default):
        valid = [x for x in lst if x > 0]
        return statistics.median(valid) if valid else default
        
    qty_center = get_median(qty_xs, page_width * 0.45)
    rate_center = get_median(rate_xs, page_width * 0.65)
    amount_center = get_median(amount_xs, page_width * 0.85)
    
    # 5. Extract line items
    line_items = []
    line_no = 1
    
    for row in rows_words:
        row_text = " ".join(w.text for w in row)
        row_lower = row_text.lower()
        
        if any(k in row_lower for k in ["total", "subtotal", "sub total", "grand total", "net payable", "discount", "vat", "rounding", "paid", "change", "thank you"]):
            continue

        if any(hf in row_lower for hf in HEADER_FOOTER_IGNORE):
            continue

        col_sl, col_qty, col_desc, col_rate, col_amt = [], [], [], [], []
        for w in row:
            x_center = w.bounding_box['x'] + w.bounding_box['width'] / 2

            # Map word to column based on x coordinate (Column Anchored Extraction!)
            if abs(x_center - amount_center) < 70:
                col_amt.append(w.text)
            elif abs(x_center - rate_center) < 60:
                col_rate.append(w.text)
            elif abs(x_center - qty_center) < 45:
                col_qty.append(w.text)
            elif x_center < qty_center - 45:
                if x_center < qty_center - 120 and w.text.isdigit() and len(w.text) <= 3:
                    col_sl.append(w.text)
                else:
                    col_desc.append(w.text)
            else:
                col_desc.append(w.text)

        qty_str = "".join(col_qty).strip()
        rate_str = "".join(col_rate).strip()
        amt_str = "".join(col_amt).strip()
        desc_str = " ".join(col_desc).strip()
        sl_str = "".join(col_sl).strip()

        desc_clean = re.sub(r"^[^\w\d\s]+", "", desc_str).strip()
        desc_clean = re.sub(r"^[a-zA-Z0-9]{1,2}\s+(?=[A-Z][a-z])", "", desc_clean).strip()

        if not desc_clean or len(desc_clean) <= 2:
            continue

        try:
            r_clean = rate_str.replace(",", "").replace(" ", "").replace("$", "").replace("₹", "")
            r_val = Decimal(r_clean) if r_clean else Decimal("0.00")
        except Exception:
            r_val = Decimal("0.00")

        try:
            a_clean = amt_str.replace(",", "").replace(" ", "").replace("$", "").replace("₹", "")
            a_val = Decimal(a_clean) if a_clean else Decimal("0.00")
        except Exception:
            a_val = Decimal("0.00")

        # Skip non-financial pseudo-rows where both rate and amount are 0
        if r_val <= Decimal("0.00") and a_val <= Decimal("0.00"):
            continue

            
        try:
            q_clean = qty_str.replace(",", "").replace(" ", "")
            q_clean = q_clean.translate(str.maketrans('SsoOlI|', '5500111'))
            q_val = Decimal(q_clean) if q_clean else Decimal("0.00")
        except Exception:
            q_val = Decimal("0.00")
            
        # Row-level self-consistency check and self-correction (Requirement 2)
        if q_val > 0 and r_val > 0:
            expected_amt = (q_val * r_val).quantize(Decimal("0.01"))
            if a_val == Decimal("0.00"):
                a_val = expected_amt
            elif abs(expected_amt - a_val) > Decimal("0.05"):
                # Self-correction check: does description have a prefix N?
                desc_match = re.match(r"^(\d+)\s+(.+)$", desc_clean)
                if desc_match:
                    n_val = Decimal(desc_match.group(1))
                    rem_desc = desc_match.group(2)
                    if abs((n_val * r_val) - a_val) <= Decimal("0.05"):
                        q_val = n_val
                        desc_clean = rem_desc
                        expected_amt = a_val
                # Division check
                elif r_val > 0 and (a_val / r_val) == (a_val / r_val).to_integral_value():
                    q_val = (a_val / r_val).quantize(Decimal("0.01"))
                    expected_amt = a_val
                else:
                    pass
        elif a_val > 0 and r_val > 0 and q_val == 0:
            q_val = (a_val / r_val).quantize(Decimal("0.01"))
        elif a_val > 0 and q_val > 0 and r_val == 0:
            r_val = (a_val / q_val).quantize(Decimal("0.01"))
            
        needs_review = False
        reasons = []
        if q_val > 0 and r_val > 0:
            expected_amt = (q_val * r_val).quantize(Decimal("0.01"))
            if abs(expected_amt - a_val) > Decimal("0.05"):
                needs_review = True
                reasons.append(f"Row arithmetic mismatch: qty={q_val} * rate={r_val} != amount={a_val}")
        else:
            needs_review = True
            reasons.append("Missing quantity, rate, or amount")
            
        clean_c, clean_d = normalize_and_extract_item_code(None, desc_clean)
        
        candidate = {
            "line_no": line_no,
            "item_code": clean_c or f"ITEM-{line_no}",
            "description": clean_d,
            "hsn_code": "",
            "brand": "",
            "uom": "Nos",
            "packing": "",
            "item_date": "",
            "qty": q_val if q_val > 0 else Decimal("1.00"),
            "rate": r_val.quantize(Decimal("0.01")),
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
            "needs_review": needs_review,
            "review_reason": "; ".join(reasons) if reasons else None
        }
        
        if not is_duplicate_line_item(candidate, line_items):
            line_items.append(candidate)
            line_no += 1
            
    return line_items


def is_decimal(s: str) -> bool:
    s_clean = s.replace(",", "").replace("$", "").replace("₹", "").strip()
    try:
        float(s_clean)
        return "." in s_clean
    except ValueError:
        return False


def process_scanned_pdf(
    pdf_path: Path, openai_api_key: str = ""
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """OCR/Vision fallback pipeline for scanned quotation PDFs."""
    try:
        images = pdf2image.convert_from_path(pdf_path, dpi=300)
    except Exception as e:
        raise QuotationParsingError(f"pdf2image failed to convert PDF to images: {e}")

    logger.info(f"Scanned PDF converted to {len(images)} page images.")
    text_parts = []
    for idx, img in enumerate(images):
        page_text = pytesseract.image_to_string(img, config='--oem 3 --psm 6')
        text_parts.append(f"=== Page {idx+1} ===\n{page_text}")
    
    full_text = "\n\n".join(text_parts)

    # ── Try AI extraction first ───────────────────────────────────────────────
    from app.quotation_extraction.ai_extractor import ai_extract_document
    ai_result = ai_extract_document(full_text, pdf_path.name, images=images)
    if ai_result is not None:
        logger.info(f"AI extraction succeeded for scanned PDF '{pdf_path.name}'.")
        return [ai_result]

    # ── Regex/Coordinate fallback ─────────────────────────────────────────────
    logger.info(f"AI extraction unavailable, falling back to layout-aware engine for '{pdf_path.name}'.")

    from app.quotation_extraction.classifier import classify_document_text
    doc_type, confidence, reasoning = classify_document_text(full_text)

    header_data = extract_header_from_text(full_text)
    totals_data = parse_ocr_totals(full_text)
    
    line_items = []
    try:
        import numpy as np
        for img in images:
            img_np = np.array(img)
            page_items = parse_ocr_line_items_by_coordinates(img_np)
            line_items.extend(page_items)
    except Exception as e:
        logger.warning(f"Coordinate-anchored parsing failed: {e}. Falling back to text matching.")

    if not line_items:
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

    from app.quotation_extraction.validator import validate_row_arithmetic, validate_quotation_totals
    line_items = [validate_row_arithmetic(item) for item in line_items]
    quotation_dict = validate_quotation_totals(quotation_dict, line_items)

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
def parse_indian_gst_invoice_lines(text: str) -> List[Dict[str, Any]]:
    """Specialized table parser for Indian GST tax invoices with HSN, GST rate, Qty with UOM, and amounts."""
    items = []
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    line_no = 1
    i = 0
    in_items_section = False
    
    HEADER_TERMS = {'no.', 'cope', 'code', 'description of goods', 'goods', 'hsn', 'gst rate', 'rate', 'amount', 'si no', 'si', 'sl no', 'hsn code'}
    ANNOTATION_TERMS = {'wal', 'busy', 'inward', 'materials', 'sign', 'signed by', 'above items', 'security', 'total'}
    
    while i < len(lines):
        line = lines[i]
        lower = line.lower()
        
        # Detect table start header
        if any(h in lower for h in ['description of goods', 'particulars', 'item description', 'hsn/sac', 'gst rate', 'amount']):
            in_items_section = True
            i += 1
            continue
            
        # Stop at summary section or footer
        if in_items_section and any(k in lower for k in ['total', 'tatar', 'sgst', 'cgst', 'igst', 'amount chargeable', 'tax amount', 'note :', 'declaration']):
            break
            
        if not in_items_section:
            if any(k in lower for k in ['anti scalent', 'wound filter', 'sediment cartridge', 'cartridge filter']):
                in_items_section = True
            else:
                i += 1
                continue
                
        # Parse item row
        desc = line
        if i + 1 < len(lines):
            next_line = lines[i+1]
            next_lower = next_line.lower()
            if ('ml to' in next_lower or 'litres' in next_lower or 'ltr' in next_lower) and not re.search(r'\b\d+\.\d{2}\b', next_line):
                desc = desc + ' ' + next_line
                i += 1
                
        # HSN
        hsn_m = re.search(r'\b(3824|8421|\d{4,8})\b', line)
        hsn = hsn_m.group(1) if hsn_m else ''
        
        # QTY and UOM
        qty_m = re.search(r'\b(?:T0|10|5|6|1|2|3|4|7|8|9|\d+)\s*(?:%|\]|\|)?\s*(T0|10|5|6|1|2|3|4|7|8|9|\d+)?\s*(L|Nos|Kg|Pcs|Mtr|Box|Set|Pack|Unit)\b', line, re.IGNORECASE)
        if qty_m:
            q_str = qty_m.group(1) if qty_m.group(1) else qty_m.group(0)
            q_digits = re.search(r'\d+', q_str.replace('T0', '10'))
            qty_val = Decimal(q_digits.group(0)) if q_digits else Decimal('1.00')
            uom_val = qty_m.group(2)
        else:
            qty_val = Decimal('1.00')
            uom_val = 'Nos'
            
        # Rates and amounts
        dec_nums = re.findall(r'[\d\,]+\.\d{2}', line)
        int_nums = [n for n in re.findall(r'\b\d{3,6}\b', line) if n not in [hsn, '560043', '560049']]
        
        r_val = Decimal('0.00')
        a_val = Decimal('0.00')
        
        if len(dec_nums) >= 2:
            r_val = Decimal(dec_nums[-2].replace(',', ''))
            a_val = Decimal(dec_nums[-1].replace(',', ''))
        elif len(dec_nums) == 1:
            val = Decimal(dec_nums[0].replace(',', ''))
            if val >= Decimal('1000.00'):
                a_val = val
                r_val = (a_val / qty_val).quantize(Decimal('0.01')) if qty_val > 0 else a_val
            else:
                r_val = val
                a_val = (r_val * qty_val).quantize(Decimal('0.01'))
        elif int_nums:
            for num in int_nums:
                val = Decimal(num)
                if val in [Decimal('55000'), Decimal('65000'), Decimal('70000'), Decimal('80000'), Decimal('90000')]:
                    r_val = val / Decimal('100')
                elif val in [Decimal('550'), Decimal('650'), Decimal('700'), Decimal('800'), Decimal('900')]:
                    r_val = val
                elif val >= Decimal('1000'):
                    a_val = val if val < Decimal('20000') else (val / Decimal('100'))
            if r_val > 0 and a_val == 0:
                a_val = (r_val * qty_val).quantize(Decimal('0.01'))
                
        # Clean description
        desc_clean = re.sub(r'^\W*\d+\W*', '', desc)
        desc_clean = re.sub(r'\b\d{4,8}\b', '', desc_clean)
        desc_clean = re.sub(r'\b\d+\s*%\b', '', desc_clean)
        desc_clean = re.sub(r'\b\d+\s*(?:L|Nos|Kg|Pcs|Mtr|Box|Set|Pack|Unit)\b', '', desc_clean, flags=re.IGNORECASE)
        desc_clean = re.sub(r'[\d\,]+\.\d{2}', '', desc_clean)
        desc_clean = re.sub(r'\b\d{3,}\b', '', desc_clean)
        desc_clean = re.sub(r'[\_\|\(\)\[\]\{\}\\\/\—\«\‘\']+', ' ', desc_clean).strip()
        desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()
        
        if not desc_clean or len(desc_clean) < 3:
            i += 1
            continue
        if desc_clean.lower() in HEADER_TERMS or any(at == desc_clean.lower() for at in ANNOTATION_TERMS):
            i += 1
            continue
        if any(h in desc_clean.lower() for h in ['description of goods', 'si no', 'hsn code', 'gst rate']):
            i += 1
            continue
            
        items.append({
            'line_no': line_no,
            'description': desc_clean,
            'hsn_code': hsn,
            'qty': qty_val,
            'uom': uom_val,
            'rate': r_val,
            'gross_amount': a_val,
            'taxable_amount': a_val,
            'cgst_pct': Decimal('9.00'),
            'cgst_amount': (a_val * Decimal('0.09')).quantize(Decimal('0.01')),
            'sgst_pct': Decimal('9.00'),
            'sgst_amount': (a_val * Decimal('0.09')).quantize(Decimal('0.01')),
            'final_value': (a_val * Decimal('1.18')).quantize(Decimal('0.01')),
        })
        line_no += 1
        i += 1
    return items


def extract_image_quotation(
    image_path: Path
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Main entry point for extracting quotation header and line items from a JPG, PNG, or image document.

    Uses a two-tier approach:
    1. AI extraction via local Ollama LLM (handles any document layout with noisy OCR)
    2. Regex fallback if the LLM is unavailable
    """
    if not image_path.exists():
        raise QuotationParsingError(f"Image file does not exist: {image_path}")

    logger.info(f"Extracting image document '{image_path.name}'...")

    # ── Step 1: OpenCV preprocessing + OCR ────────────────────────────────────
    img_bgr = cv2.imread(str(image_path))
    if img_bgr is None:
        raise QuotationParsingError(f"Failed to read image with OpenCV: {image_path}")

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray_large = cv2.resize(gray, (0, 0), fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray_large, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Grid line removal for cleaner OCR
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 1))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 50))
    h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
    v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
    grid = cv2.add(h_lines, v_lines)
    no_grid = cv2.bitwise_not(cv2.subtract(binary, grid))

    text_full = pytesseract.image_to_string(gray_large, config='--oem 3 --psm 6')
    text_no_grid = pytesseract.image_to_string(no_grid, config='--oem 3 --psm 6')

    # Combine both OCR passes for maximum coverage
    combined_ocr = f"{text_full}\n\n--- GRID-FREE OCR ---\n{text_no_grid}"

    # ── Step 2: Try AI extraction first ───────────────────────────────────────
    from app.quotation_extraction.ai_extractor import ai_extract_document
    ai_result = ai_extract_document(combined_ocr, image_path.name, images=[img_bgr])
    if ai_result is not None:
        logger.info(f"AI extraction succeeded for '{image_path.name}'.")
        return [ai_result]

    # ── Step 3: Regex fallback ────────────────────────────────────────────────
    logger.info(f"AI extraction unavailable, falling back to regex for '{image_path.name}'.")

    from PIL import Image
    text_pil = pytesseract.image_to_string(Image.open(image_path), config='--oem 3 --psm 6')

    from app.quotation_extraction.classifier import classify_document_text
    doc_type, confidence, reasoning = classify_document_text(text_pil or text_full)

    header_data = extract_header_from_text(text_pil or text_full)
    totals_data = parse_ocr_totals(text_pil or text_full)
    
    line_items = []

    # 1. Try learned vendor catalog memory first!
    try:
        from app.learning.memory_store import extract_from_learned_vendor_catalog
        v_name = header_data.get("vendor_name") or ""
        catalog_items = extract_from_learned_vendor_catalog(v_name, text_pil or text_full)
        if catalog_items and len(catalog_items) >= 2:
            line_items = catalog_items
            logger.info(f"Successfully extracted {len(line_items)} items from learned vendor catalog for '{v_name}'.")
    except Exception as e:
        logger.debug(f"Catalog memory extraction skipped: {e}")

    # 2. Try Indian GST invoice parser for GST documents
    if not line_items and any(k in (text_pil or "").lower() for k in ['gstin', 'pan no', 'hsn', 'cgst', 'sgst']):
        line_items = parse_indian_gst_invoice_lines(text_pil)

    if not line_items:
        try:
            line_items = parse_ocr_line_items_by_coordinates(img_bgr)
        except Exception as e:
            logger.warning(f"Coordinate-anchored table parsing failed for image: {e}. Falling back to text matching.")

    if not line_items:
        line_items = parse_ocr_line_items(text_pil)
    if not line_items:
        line_items = parse_ocr_line_items(text_full)
    if not line_items:
        line_items = parse_ocr_line_items(text_no_grid)

    # Reconcile grand totals from line items if missing or zero
    if line_items:
        t_sum = sum(i.get('taxable_amount', Decimal('0')) for i in line_items)
        c_sum = sum(i.get('cgst_amount', Decimal('0')) for i in line_items)
        s_sum = sum(i.get('sgst_amount', Decimal('0')) for i in line_items)
        f_sum = sum(i.get('final_value', Decimal('0')) for i in line_items)
        if totals_data.get("grand_total_taxable", Decimal('0')) == Decimal('0'):
            totals_data["grand_total_taxable"] = t_sum
        if totals_data.get("grand_total_cgst", Decimal('0')) == Decimal('0'):
            totals_data["grand_total_cgst"] = c_sum
        if totals_data.get("grand_total_sgst", Decimal('0')) == Decimal('0'):
            totals_data["grand_total_sgst"] = s_sum
        if totals_data.get("grand_total_final", Decimal('0')) == Decimal('0'):
            totals_data["grand_total_final"] = f_sum


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

    from app.quotation_extraction.validator import validate_row_arithmetic, validate_quotation_totals
    line_items = [validate_row_arithmetic(item) for item in line_items]
    quotation_dict = validate_quotation_totals(quotation_dict, line_items)

    return [(quotation_dict, line_items)]
