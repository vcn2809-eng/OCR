import logging
import sys
from pathlib import Path
from decimal import Decimal
from typing import List, Dict, Any, Tuple
from app.quotation_extraction.pdf_extractor import extract_pdf_quotation, extract_image_quotation
from app.quotation_extraction.excel_extractor import extract_excel_quotation
from app.quotation_extraction.loader import save_quotation_to_db

# Configure logger to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("quotation_runner")


def run_pipeline(file_path: Path) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """Runs the extraction pipeline based on file type."""
    if not file_path.exists():
        logger.error(f"Target file not found: {file_path}")
        sys.exit(1)

    logger.info(f"Starting ingestion pipeline for file: {file_path}")
    
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_pdf_quotation(file_path)
    elif ext in (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"):
        return extract_image_quotation(file_path)
    elif ext in (".xlsx", ".xls", ".csv"):
        return extract_excel_quotation(file_path)
    else:
        logger.error(f"Unsupported file type: {ext}")
        sys.exit(1)


def verify_reconciliation(quotation: Dict[str, Any], items: List[Dict[str, Any]], expected_totals: Dict[str, Decimal]) -> bool:
    """Verifies that the extracted totals match the expected totals within tolerance."""
    logger.info(f"Reconciling Quotation {quotation.get('quotation_no')}...")

    taxable = Decimal(str(quotation.get("grand_total_taxable", 0.0)))
    cgst = Decimal(str(quotation.get("grand_total_cgst", 0.0)))
    sgst = Decimal(str(quotation.get("grand_total_sgst", 0.0)))
    final = Decimal(str(quotation.get("grand_total_final", 0.0)))

    logger.info(f"Extracted Grand Totals: Taxable={taxable}, CGST={cgst}, SGST={sgst}, Final={final}")
    logger.info(f"Expected Grand Totals:  Taxable={expected_totals['taxable']}, CGST={expected_totals['cgst']}, SGST={expected_totals['sgst']}, Final={expected_totals['final']}")

    success = True
    for key, field, value in [
        ("taxable", "grand_total_taxable", taxable),
        ("cgst", "grand_total_cgst", cgst),
        ("sgst", "grand_total_sgst", sgst),
        ("final", "grand_total_final", final)
    ]:
        diff = abs(value - expected_totals[key])
        # tolerance for grand totals is 1.0 due to integer rounding on final values
        tolerance = Decimal("1.00") if key == "final" else Decimal("0.05")
        if diff > tolerance:
            logger.error(f"Reconciliation error on field '{field}': difference is {diff} (tolerance {tolerance})")
            success = False

    if success:
        logger.info(f"Quotation {quotation.get('quotation_no')} RECONCILED SUCCESSFULLY!")
    else:
        logger.error(f"Quotation {quotation.get('quotation_no')} RECONCILIATION FAILED!")
        
    return success


def main():
    import json
    
    # Check if a file path is provided via command line arguments
    if len(sys.argv) > 1:
        target_path = Path(sys.argv[1])
    else:
        # Fallback to the sample PDF in the workspace
        target_path = Path("./input_files/d92c764f-3b4f-463d-b131-d2071fa5d2cc_AIC ENTERP Price list.pdf")
        if not target_path.exists():
            target_path = Path("./bill_image/AIC ENTERP Price list.pdf")
            
    if not target_path.exists():
        logger.error(f"Could not locate target file: {target_path}")
        print(json.dumps({"status": "error", "message": f"File not found: {target_path}"}))
        sys.exit(1)

    try:
        results = run_pipeline(target_path)
    except Exception as e:
        logger.error(f"Ingestion pipeline failed: {e}", exc_info=True)
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)

    logger.info(f"Extraction completed. Found {len(results)} separate quotation(s) in PDF.")

    expected_q1 = {
        "taxable": Decimal("324537.45"),
        "cgst": Decimal("28559.51"),
        "sgst": Decimal("28559.51"),
        "final": Decimal("381656.00"),
    }

    expected_q2 = {
        "taxable": Decimal("188994.85"),
        "cgst": Decimal("15492.14"),
        "sgst": Decimal("15492.14"),
        "final": Decimal("219979.00"),
    }

    expected_q3 = {
        "taxable": Decimal("225655.50"),
        "cgst": Decimal("18504.57"),
        "sgst": Decimal("18504.57"),
        "final": Decimal("262665.00"),
    }

    expected_map = {
        "470114429": expected_q1,
        "470114596": expected_q2,
        "470114575": expected_q3
    }

    output_data = []

    for idx, (quotation, items) in enumerate(results):
        q_no = quotation.get("quotation_no")
        logger.info(f"\n==================================================")
        logger.info(f"PROCESSING QUOTATION {idx+1}/{len(results)} (No: {q_no})")
        logger.info(f"==================================================")
        
        # Verify reconciliation against expectations if it's one of the three known quotations
        if q_no in expected_map:
            verify_reconciliation(quotation, items, expected_map[q_no])

        # Save to database with duplicate checking
        try:
            save_res = save_quotation_to_db(quotation, items, file_path=str(target_path))
            db_id = save_res.get("id") if isinstance(save_res, dict) else save_res
            is_dup = save_res.get("is_duplicate", False) if isinstance(save_res, dict) else False
            msg = save_res.get("message") if isinstance(save_res, dict) else ""

            logger.info(f"Saved quotation result for {q_no}: ID {db_id} (is_duplicate: {is_dup})")
            output_data.append({
                "id": db_id,
                "is_duplicate": is_dup,
                "quotation_no": q_no,
                "extraction_status": quotation.get("extraction_status", "ok"),
                "vendor_name": quotation.get("vendor_name"),
                "customer_name": quotation.get("customer_name"),
                "message": msg
            })
        except Exception as e:
            logger.error(f"Failed to save quotation {q_no} to database: {e}")

    # Print clean JSON of the results for the calling process to capture
    print("JSON_OUTPUT:" + json.dumps({"status": "success", "quotations": output_data}))
    sys.exit(0)


if __name__ == "__main__":
    main()
