import logging
import re
import hashlib
from pathlib import Path
from difflib import SequenceMatcher
from typing import Dict, Any, List, Optional, Union
from app.persistence.database import get_db_session, init_db
from app.persistence.models import BillingDocument, BillingDocumentLineItem, BillingVendor, BillingCustomer
from app.quotation_extraction.exceptions import QuotationLoaderError

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Lowercase and remove non-alphanumeric characters for clean string comparison."""
    if not name:
        return ""
    n = name.lower()
    n = re.sub(r'\b(pvt|ltd|private|limited|co|corp|inc)\b', '', n)
    return re.sub(r'[^a-z0-9]', '', n)


def is_fuzzy_match(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """Fuzzy match two names using SequenceMatcher similarity."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    return SequenceMatcher(None, n1, n2).ratio() >= threshold


def compute_file_sha256(file_path: Union[str, Path]) -> Optional[str]:
    """Compute SHA-256 binary hash of a file for exact duplicate checking."""
    try:
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            return None
        hasher = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.warning(f"Could not compute SHA-256 for '{file_path}': {e}")
        return None


def find_intricate_duplicate(
    session, 
    quotation_dict: Dict[str, Any], 
    line_items: List[Dict[str, Any]], 
    file_hash: Optional[str] = None
) -> Optional[BillingDocument]:
    """Intricately check if a document with identical content/values already exists in DB.
    
    Checks across multiple layers:
    1. Binary Content Hash (SHA-256)
    2. Document Number & Financial Amounts (grand_total_final, document_date, taxable)
    3. Intricate Line Item Values (count, item_code, rate, qty, final_value, description)
    """
    doc_no = quotation_dict.get("document_no") or quotation_dict.get("quotation_no")
    doc_type = quotation_dict.get("document_type", "quotation")
    new_grand_total = quotation_dict.get("grand_total_final")
    new_date = quotation_dict.get("document_date") or quotation_dict.get("quotation_date")

    # 1. SHA-256 File Hash Match
    if file_hash:
        doc_by_hash = session.query(BillingDocument).filter(BillingDocument.source_file == str(file_hash)).first()
        if doc_by_hash:
            logger.info(f"Duplicate match found via SHA-256 binary hash: Doc ID #{doc_by_hash.id}")
            return doc_by_hash

    # 2. Search candidates by document_no or grand_total_final
    candidates = []
    if doc_no:
        candidates = session.query(BillingDocument).filter(
            BillingDocument.document_no == str(doc_no),
            BillingDocument.document_type == str(doc_type)
        ).all()

    if not candidates and new_grand_total:
        try:
            gt_val = float(new_grand_total)
            all_docs = session.query(BillingDocument).all()
            for d in all_docs:
                if d.grand_total_final is not None and abs(float(d.grand_total_final) - gt_val) < 0.5:
                    candidates.append(d)
        except (ValueError, TypeError):
            pass

    for candidate in candidates:
        header_match = True

        # Compare Grand Total Amount
        if new_grand_total is not None and candidate.grand_total_final is not None:
            try:
                if abs(float(new_grand_total) - float(candidate.grand_total_final)) > 0.5:
                    header_match = False
            except (ValueError, TypeError):
                pass

        # Compare Document Date
        if new_date and candidate.document_date:
            if str(new_date) != str(candidate.document_date):
                header_match = False

        if not header_match:
            continue

        # 3. Intricate Line Items Comparison
        existing_items = candidate.line_items
        if len(line_items) > 0 and len(existing_items) > 0:
            if len(line_items) != len(existing_items):
                continue

            matched_count = 0
            for new_item in line_items:
                new_code = (new_item.get("item_code") or "").strip().lower()
                new_desc = (new_item.get("description") or "").strip().lower()
                
                try:
                    new_qty = float(new_item.get("qty") or 0)
                    new_rate = float(new_item.get("rate") or 0)
                    new_val = float(new_item.get("final_value") or 0)
                except (ValueError, TypeError):
                    new_qty, new_rate, new_val = 0, 0, 0

                # Look for matching line in candidate document
                found_match = False
                for ex_item in existing_items:
                    ex_code = (ex_item.item_code or "").strip().lower()
                    ex_desc = (ex_item.description or "").strip().lower()
                    try:
                        ex_qty = float(ex_item.qty or 0)
                        ex_rate = float(ex_item.rate or 0)
                        ex_val = float(ex_item.final_value or 0)
                    except (ValueError, TypeError):
                        ex_qty, ex_rate, ex_val = 0, 0, 0

                    code_match = (new_code and new_code == ex_code)
                    desc_match = (new_desc and is_fuzzy_match(new_desc, ex_desc, threshold=0.85))
                    vals_match = (abs(new_qty - ex_qty) < 0.01 and abs(new_rate - ex_rate) < 0.5 and abs(new_val - ex_val) < 0.5)

                    if (code_match or desc_match) and vals_match:
                        found_match = True
                        break

                if found_match:
                    matched_count += 1

            if matched_count == len(line_items):
                logger.info(f"Intricate duplicate match confirmed for candidate Doc ID #{candidate.id} ({matched_count}/{len(line_items)} line items matched)")
                return candidate
        elif doc_no and header_match:
            logger.info(f"Intricate header match confirmed for candidate Doc ID #{candidate.id}")
            return candidate

    return None


def get_or_create_vendor(session, name: Optional[str], gstin: Optional[str], address: Optional[str] = None) -> Optional[int]:
    """Retrieve existing vendor by GSTIN or fuzzy name matching, or create a new one with registered address."""
    if not name:
        return None

    vendor = None
    if gstin:
        vendor = session.query(BillingVendor).filter(BillingVendor.gstin == gstin).first()

    if not vendor:
        all_vendors = session.query(BillingVendor).all()
        for v in all_vendors:
            if is_fuzzy_match(v.name, name):
                vendor = v
                break

    if vendor:
        if address and not vendor.address:
            vendor.address = address
            session.flush()
        return vendor.id

    new_vendor = BillingVendor(name=name, gstin=gstin, address=address)
    session.add(new_vendor)
    session.flush()
    logger.info(f"Created new BillingVendor: '{name}' (ID: {new_vendor.id})")
    return new_vendor.id


def get_or_create_customer(session, name: Optional[str], gstin: Optional[str], address: Optional[str] = None) -> Optional[int]:
    """Retrieve existing customer by GSTIN or fuzzy name matching, or create a new one with registered address."""
    if not name:
        return None

    customer = None
    if gstin:
        customer = session.query(BillingCustomer).filter(BillingCustomer.gstin == gstin).first()

    if not customer:
        all_customers = session.query(BillingCustomer).all()
        for c in all_customers:
            if is_fuzzy_match(c.name, name):
                customer = c
                break

    if customer:
        if address and not customer.address:
            customer.address = address
            session.flush()
        return customer.id

    new_customer = BillingCustomer(name=name, gstin=gstin, address=address)
    session.add(new_customer)
    session.flush()
    logger.info(f"Created new BillingCustomer: '{name}' (ID: {new_customer.id})")
    return new_customer.id


def save_quotation_to_db(
    quotation_dict: Dict[str, Any], 
    line_items: List[Dict[str, Any]], 
    file_path: Optional[str] = None,
    allow_duplicate: bool = False
) -> Dict[str, Any]:
    """Save a single document and its line items to the SQL database.
    
    Checks if an identical document already exists by intricately matching all values
    (file SHA256 hash, document number, total financial amounts, and line item details).
    If a duplicate is found, skips insertion and returns duplicate info.
    """
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        raise QuotationLoaderError(f"Database initialization failed: {e}")

    file_hash = compute_file_sha256(file_path) if file_path else None

    try:
        with get_db_session() as session:
            doc_no = quotation_dict.get("document_no") or quotation_dict.get("quotation_no")
            doc_type = quotation_dict.get("document_type", "quotation")

            # Check for intricate duplicate
            if not allow_duplicate:
                existing_doc = find_intricate_duplicate(session, quotation_dict, line_items, file_hash)
                if existing_doc:
                    logger.warning(f"Intricate duplicate detected! Matches existing Document ID #{existing_doc.id}")
                    return {
                        "id": existing_doc.id,
                        "is_duplicate": True,
                        "document_no": existing_doc.document_no,
                        "message": f"Duplicate document detected! Matches existing Document #{existing_doc.id} with identical content and extracted values."
                    }

            # Resolve normalized Vendor and Customer with registered address
            vendor_id = get_or_create_vendor(
                session, 
                quotation_dict.get("vendor_name"), 
                quotation_dict.get("vendor_gstin"),
                quotation_dict.get("vendor_address")
            )
            customer_id = get_or_create_customer(
                session, 
                quotation_dict.get("customer_name"), 
                quotation_dict.get("customer_gstin"),
                quotation_dict.get("customer_address")
            )

            # Create new BillingDocument record
            doc = BillingDocument(
                document_type=doc_type,
                document_no=doc_no,
                document_date=quotation_dict.get("document_date") or quotation_dict.get("quotation_date"),
                classification_confidence=quotation_dict.get("classification_confidence"),
                classification_reasoning=quotation_dict.get("classification_reasoning"),
                vendor_id=vendor_id,
                customer_id=customer_id,
                validity_date=quotation_dict.get("validity_date"),
                payment_terms=quotation_dict.get("payment_terms"),
                currency=quotation_dict.get("currency") or 'INR',
                enquiry_ref=quotation_dict.get("enquiry_ref"),
                enquiry_date=quotation_dict.get("enquiry_date"),
                grand_total_taxable=quotation_dict.get("grand_total_taxable"),
                grand_total_cgst=quotation_dict.get("grand_total_cgst"),
                grand_total_sgst=quotation_dict.get("grand_total_sgst"),
                grand_total_final=quotation_dict.get("grand_total_final"),
                grand_total_words=quotation_dict.get("grand_total_words"),
                source_file=quotation_dict.get("source_file") or (file_path if isinstance(file_path, str) else None),
                extraction_status=quotation_dict.get("extraction_status"),
            )
            session.add(doc)
            session.flush()

            # Create BillingDocumentLineItem records
            for item in line_items:
                li = BillingDocumentLineItem(
                    document_id=doc.id,
                    line_no=item.get("line_no"),
                    item_code=item.get("item_code"),
                    description=item.get("description"),
                    hsn_code=item.get("hsn_code"),
                    brand=item.get("brand"),
                    uom=item.get("uom"),
                    packing=item.get("packing"),
                    qty=item.get("qty"),
                    rate=item.get("rate"),
                    gross_amount=item.get("gross_amount"),
                    discount_pct=item.get("discount_pct"),
                    discount_amount=item.get("discount_amount"),
                    taxable_amount=item.get("taxable_amount"),
                    cgst_pct=item.get("cgst_pct"),
                    cgst_amount=item.get("cgst_amount"),
                    sgst_pct=item.get("sgst_pct"),
                    sgst_amount=item.get("sgst_amount"),
                    final_value=item.get("final_value"),
                    item_date=item.get("item_date"),
                    status_eta=item.get("status_eta"),
                    needs_review=item.get("needs_review", False),
                    review_reason=item.get("review_reason"),
                )
                session.add(li)

            logger.info(f"Successfully loaded document '{doc_no}' ({doc_type}) with {len(line_items)} line items.")
            return {
                "id": doc.id,
                "is_duplicate": False,
                "document_no": doc.document_no,
                "message": "Saved successfully"
            }

    except Exception as e:
        logger.error(f"Error loading document to database: {e}", exc_info=True)
        raise QuotationLoaderError(f"Database load failed: {e}") from e
