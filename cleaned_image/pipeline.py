import re
import logging
from ai1 import get_json_from_prompt
from ai2 import get_category_from_ollama
from db import init_db, save_quotation_to_db

logger = logging.getLogger(__name__)


def process_quotation_text(raw_pdf_text: str) -> dict:
    """
    Complete end-to-end multi-agent pipeline:
    Agent 1: Extraction -> Agent 2: Categorization -> Agent 3: DB Storage
    """
    init_db()

    # Chunker logic: Split the raw text by page dividers or fixed length
    dividers = list(re.finditer(r'--- Text from .*? ---|--- Page Break ---|\f', raw_pdf_text))
    
    chunks = []
    if len(dividers) > 1:
        # Split by dividers
        parts = re.split(r'--- Text from .*? ---|--- Page Break ---|\f', raw_pdf_text)
        for p in parts:
            if p.strip():
                chunks.append(p.strip())
    else:
        # No dividers, chunk by lines
        lines = raw_pdf_text.split('\n')
        chunk_size_lines = 100
        for i in range(0, len(lines), chunk_size_lines):
            chunk = '\n'.join(lines[i:i+chunk_size_lines])
            if chunk.strip():
                chunks.append(chunk.strip())

    chunks_results = []
    for chunk in chunks:
        try:
            res = get_json_from_prompt(chunk)
            if res:
                chunks_results.append(res)
        except Exception as e:
            logger.error(f"Chunk extraction failed: {e}")
            continue

    # Merge results
    merged = {
        "quotation_number": "",
        "quotation_date": "",
        "customer_details": {},
        "vendor_details": {},
        "line_items": [],
        "grand_total": 0.0
    }
    
    for res in chunks_results:
        if not merged["quotation_number"] and res.get("quotation_number"):
            merged["quotation_number"] = res["quotation_number"]
        if not merged["quotation_date"] and res.get("quotation_date"):
            merged["quotation_date"] = res["quotation_date"]
        if not merged["customer_details"] and res.get("customer_details"):
            merged["customer_details"] = res["customer_details"]
        if not merged["vendor_details"] and res.get("vendor_details"):
            merged["vendor_details"] = res["vendor_details"]
            
        items = res.get("line_items", [])
        if isinstance(items, list):
            merged["line_items"].extend(items)

    # Estimate expected rows based on input text length (roughly 3 lines per row)
    expected_rows_estimate = max(1, len(raw_pdf_text.split('\n')) // 3)
    extracted_rows_count = len(merged["line_items"])
    logger.info(f"expected ~{expected_rows_estimate} rows based on input size, extracted {extracted_rows_count} rows")

    # Run categorization on all line items
    for item in merged["line_items"]:
        desc = item.get("description", "")
        category = get_category_from_ollama(desc)
        item["category"] = category

    save_quotation_to_db(merged)
    return merged
