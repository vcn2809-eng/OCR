import logging
from decimal import Decimal
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def to_decimal(val: Any) -> Decimal:
    """Safely convert any value to Decimal, default to 0.00."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    if isinstance(val, Decimal):
        return val
    cleaned = str(val).strip().replace(",", "").replace("%", "")
    if not cleaned or cleaned.lower() in ("-", "n/a", "none"):
        return Decimal("0.00")
    try:
        return Decimal(cleaned)
    except Exception:
        logger.warning(f"Could not convert '{val}' to Decimal, defaulting to 0.00")
        return Decimal("0.00")


def validate_row_arithmetic(item: Dict[str, Any]) -> Dict[str, Any]:
    """Verify arithmetic constraints for a single line item, inferring missing values."""
    needs_review = False
    reasons = []

    qty = to_decimal(item.get("qty"))
    if qty == Decimal("0.00"):
        qty = Decimal("1.00")
        item["qty"] = qty

    rate = to_decimal(item.get("rate"))
    gross = to_decimal(item.get("gross_amount"))
    disc_pct = to_decimal(item.get("discount_pct"))
    disc_amt = to_decimal(item.get("discount_amount"))
    taxable = to_decimal(item.get("taxable_amount"))
    cgst_pct = to_decimal(item.get("cgst_pct"))
    cgst_amt = to_decimal(item.get("cgst_amount"))
    sgst_pct = to_decimal(item.get("sgst_pct"))
    sgst_amt = to_decimal(item.get("sgst_amount"))
    final_val = to_decimal(item.get("final_value"))

    # Auto-infer missing arithmetic fields
    if rate > Decimal("0.00") and gross == Decimal("0.00"):
        gross = rate * qty
    if gross > Decimal("0.00") and rate == Decimal("0.00"):
        rate = gross / qty

    if disc_pct > Decimal("0.00") and disc_amt == Decimal("0.00"):
        disc_amt = (gross * disc_pct) / Decimal("100.00")

    if gross > Decimal("0.00") and taxable == Decimal("0.00"):
        taxable = gross - disc_amt
    if taxable == Decimal("0.00") and final_val > Decimal("0.00"):
        taxable = final_val

    if cgst_pct > Decimal("0.00") and cgst_amt == Decimal("0.00"):
        cgst_amt = (taxable * cgst_pct) / Decimal("100.00")
    if sgst_pct > Decimal("0.00") and sgst_amt == Decimal("0.00"):
        sgst_amt = (taxable * sgst_pct) / Decimal("100.00")

    if final_val == Decimal("0.00") and taxable > Decimal("0.00"):
        final_val = taxable + cgst_amt + sgst_amt
    if final_val > Decimal("0.00") and gross == Decimal("0.00"):
        gross = final_val
        rate = final_val / qty

    item["qty"] = qty
    item["rate"] = rate
    item["gross_amount"] = gross
    item["discount_pct"] = disc_pct
    item["discount_amount"] = disc_amt
    item["taxable_amount"] = taxable
    item["cgst_pct"] = cgst_pct
    item["cgst_amount"] = cgst_amt
    item["sgst_pct"] = sgst_pct
    item["sgst_amount"] = sgst_amt
    item["final_value"] = final_val

    # 1. Gross Amount = Rate * Qty
    expected_gross = rate * qty
    if abs(gross - expected_gross) > Decimal("0.05"):
        needs_review = True
        reasons.append(f"Gross Amount mismatch: calculated {expected_gross}, got {gross}")

    # 2. Final Value = Taxable Amount + CGST Amount + SGST Amount
    expected_final = taxable + cgst_amt + sgst_amt
    if abs(final_val - expected_final) > Decimal("0.05"):
        needs_review = True
        reasons.append(f"Final Value mismatch: calculated {expected_final}, got {final_val}")

    item["needs_review"] = needs_review
    item["review_reason"] = "; ".join(reasons) if reasons else None
    return item


def validate_quotation_totals(quotation: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reconcile printed grand totals with the sum of line items."""
    sum_taxable = sum(to_decimal(item.get("taxable_amount")) for item in items)
    sum_cgst = sum(to_decimal(item.get("cgst_amount")) for item in items)
    sum_sgst = sum(to_decimal(item.get("sgst_amount")) for item in items)
    sum_final = sum(to_decimal(item.get("final_value")) for item in items)

    grand_taxable = to_decimal(quotation.get("grand_total_taxable"))
    grand_cgst = to_decimal(quotation.get("grand_total_cgst"))
    grand_sgst = to_decimal(quotation.get("grand_total_sgst"))
    grand_final = to_decimal(quotation.get("grand_total_final"))

    discount = to_decimal(quotation.get("total_discount"))

    # Auto-correct header totals if OCR extracted a wildly inaccurate value (e.g. 2,025,000.00 vs real 29,250.00)
    if sum_taxable > Decimal("0.00"):
        if grand_taxable == Decimal("0.00") or (grand_taxable > sum_taxable * Decimal("2.5")):
            logger.warning(f"Header grand_total_taxable ({grand_taxable}) severely mismatched line items sum ({sum_taxable}). Auto-correcting to {sum_taxable}.")
            quotation["grand_total_taxable"] = sum_taxable
            grand_taxable = sum_taxable

    expected_final = (sum_taxable + grand_cgst + grand_sgst - discount) if sum_taxable > Decimal("0.00") else sum_final
    if expected_final > Decimal("0.00"):
        if grand_final == Decimal("0.00") or (grand_final > expected_final * Decimal("2.5")):
            logger.warning(f"Header grand_total_final ({grand_final}) severely mismatched expected final ({expected_final}). Auto-correcting to {expected_final}.")
            quotation["grand_total_final"] = expected_final
            grand_final = expected_final


    status = "ok"
    reasons = []

    if abs(sum_taxable - grand_taxable) > Decimal("1.00"):
        status = "needs_review"
        reasons.append(f"Taxable total mismatch: sum of items {sum_taxable}, grand total {grand_taxable}")
    if abs(sum_cgst - grand_cgst) > Decimal("1.00"):
        status = "needs_review"
        reasons.append(f"CGST total mismatch: sum of items {sum_cgst}, grand total {grand_cgst}")
    if abs(sum_sgst - grand_sgst) > Decimal("1.00"):
        status = "needs_review"
        reasons.append(f"SGST total mismatch: sum of items {sum_sgst}, grand total {grand_sgst}")

    final_diff = abs(sum_final - grand_final)
    final_diff_with_discount = abs(sum_final - discount - grand_final)
    if final_diff > Decimal("2.00") and final_diff_with_discount > Decimal("2.00") and status != "needs_review":
        status = "needs_review"
        reasons.append(f"Final total mismatch: sum of items {sum_final}, grand total {grand_final} (discount: {discount})")

    # Double check if any individual row needs review
    if any(item.get("needs_review") for item in items):
        status = "needs_review"
        reasons.append("One or more line items failed validation")


    quotation["extraction_status"] = status
    if status == "needs_review":
        quotation["review_reason"] = "; ".join(reasons)
    else:
        quotation["review_reason"] = None

    return quotation
