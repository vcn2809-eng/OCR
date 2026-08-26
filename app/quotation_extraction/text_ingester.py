import sys
import os
import re
import json
import logging
from decimal import Decimal
from pathlib import Path
from app.quotation_extraction.loader import save_quotation_to_db
from app.quotation_extraction.pdf_extractor import parse_date
from app.quotation_extraction.validator import to_decimal
from app.quotation_extraction.classifier import classify_document_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("text_ingester")

def ingest_text_content(text_content: str) -> list:
    ingested_quotations = []
    
    # 1. Check if text contains invoice_51109 or similar CSV structure
    chunks = re.split(r'invoice_\d+', text_content)
    if len(chunks) > 1:
        seen_nos = set()
        for c in chunks[1:]:
            j_no = c.find('invoice_no')
            if j_no == -1:
                j_no = c.find('quotation_no')
            if j_no == -1:
                continue
            
            j_start = c.rfind('{', 0, j_no)
            if j_start == -1:
                continue

            raw_j = c[j_start:]
            clean_j = re.sub(r'\\+n', '\n', raw_j)
            clean_j = re.sub(r'\\+"', '"', clean_j)
            clean_j = clean_j.replace('""', '"')

            try:
                dec = json.JSONDecoder(strict=False)
                data, _ = dec.raw_decode(clean_j)
                inv_no = data.get('invoice_no') or data.get('quotation_no')
                if not inv_no or inv_no in seen_nos:
                    continue
                
                seen_nos.add(inv_no)
                seller = data.get('seller', {})
                client = data.get('client', {})
                summary = data.get('summary', {})

                quotation_dict = {
                    'vendor_name': seller.get('name') or 'TechVision Distributors Pvt Ltd',
                    'vendor_gstin': seller.get('gstin') or seller.get('tax_id'),
                    'customer_name': client.get('name'),
                    'customer_gstin': client.get('tax_id'),
                    'quotation_no': inv_no,
                    'quotation_date': parse_date(data.get('date_of_issue') or data.get('date')),
                    'grand_total_taxable': to_decimal(summary.get('net_worth') or summary.get('subtotal')),
                    'grand_total_cgst': to_decimal(summary.get('vat_amount') or summary.get('tax')) / Decimal('2.0'),
                    'grand_total_sgst': to_decimal(summary.get('vat_amount') or summary.get('tax')) / Decimal('2.0'),
                    'grand_total_final': to_decimal(summary.get('gross_worth') or summary.get('grand_total')),
                    'source_file': f"text_import_{inv_no}.txt",
                    'document_type': 'invoice_final',
                    'extraction_status': 'ok'
                }

                line_items = []
                for item in data.get('items', []):
                    l_no_raw = str(item.get('item_no') or item.get('line_no') or '').strip().rstrip('.')
                    l_no = int(l_no_raw) if l_no_raw.isdigit() else (len(line_items) + 1)
                    qty = to_decimal(item.get('quantity') or item.get('qty'))
                    rate = to_decimal(item.get('net_price') or item.get('rate'))
                    taxable = to_decimal(item.get('net_worth') or item.get('taxable_amount'))
                    final_val = to_decimal(item.get('gross_worth') or item.get('amount'))
                    vat_str = str(item.get('vat_pct') or item.get('tax_pct') or '0').replace('%', '').strip()
                    vat_pct = to_decimal(vat_str)
                    half_vat = vat_pct / Decimal('2.0')
                    vat_amt = (taxable * vat_pct) / Decimal('100.00')
                    half_vat_amt = vat_amt / Decimal('2.0')

                    line_items.append({
                        'line_no': l_no,
                        'item_code': f'ITEM-{l_no}',
                        'description': str(item.get('description') or item.get('desc') or ''),
                        'hsn_code': '',
                        'brand': '',
                        'uom': str(item.get('unit_measure') or item.get('uom') or 'pcs'),
                        'packing': '',
                        'qty': qty,
                        'rate': rate,
                        'gross_amount': taxable if taxable > Decimal('0.00') else (qty * rate),
                        'discount_pct': Decimal('0.00'),
                        'discount_amount': Decimal('0.00'),
                        'taxable_amount': taxable if taxable > Decimal('0.00') else (qty * rate),
                        'cgst_pct': half_vat,
                        'cgst_amount': half_vat_amt,
                        'sgst_pct': half_vat,
                        'sgst_amount': half_vat_amt,
                        'final_value': final_val if final_val > Decimal('0.00') else (qty * rate),
                        'status_eta': 'In Stock'
                    })

                doc_id = save_quotation_to_db(quotation_dict, line_items)
                ingested_quotations.append({
                    'id': doc_id,
                    'quotation_no': inv_no,
                    'document_type': quotation_dict['document_type'],
                    'vendor_name': quotation_dict['vendor_name'],
                    'customer_name': quotation_dict['customer_name'],
                    'extraction_status': quotation_dict['extraction_status']
                })
            except Exception as e:
                logger.warning(f"Failed to parse chunk: {e}")

    # 2. If no chunk JSON was extracted, treat as raw OCR or statement text
    if not ingested_quotations:
        from app.quotation_extraction.pdf_extractor import extract_header_from_text, parse_ocr_totals, parse_ocr_line_items
        doc_type, confidence, reasoning = classify_document_text(text_content)
        header_data = extract_header_from_text(text_content)
        totals_data = parse_ocr_totals(text_content)
        line_items = parse_ocr_line_items(text_content)

        quotation_dict = {
            **header_data,
            **totals_data,
            "grand_total_words": None,
            "source_file": "text_input.txt",
            "document_type": doc_type,
            "document_no": header_data.get("quotation_no"),
            "document_date": header_data.get("quotation_date"),
            "classification_confidence": confidence,
            "classification_reasoning": reasoning,
            "extraction_status": "ok" if line_items else "needs_review"
        }

        doc_id = save_quotation_to_db(quotation_dict, line_items)
        ingested_quotations.append({
            'id': doc_id,
            'quotation_no': quotation_dict['document_no'],
            'document_type': doc_type,
            'vendor_name': quotation_dict['vendor_name'],
            'customer_name': quotation_dict['customer_name'],
            'extraction_status': quotation_dict['extraction_status']
        })

    return ingested_quotations


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No input text file provided"}))
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(json.dumps({"status": "error", "message": f"File not found: {file_path}"}))
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    results = ingest_text_content(text)
    output = {"status": "success", "quotations": results}
    print(f"JSON_OUTPUT:{json.dumps(output)}")


if __name__ == "__main__":
    main()
