import logging
import re
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from app.persistence.models import BillingDocument, BillingDocumentLineItem, BillingVendor, BillingCustomer, SearchAlias, LearnedAlias

logger = logging.getLogger(__name__)

SEED_ALIASES = [
    {"alias": "mtrl", "canonical": "material"},
    {"alias": "qty", "canonical": "quantity"},
    {"alias": "amt", "canonical": "amount"},
    {"alias": "ext", "canonical": "extrapure"},
    {"alias": "extrap", "canonical": "extrapure"},
    {"alias": "chem", "canonical": "chemical"},
    {"alias": "pkg", "canonical": "packing"},
    {"alias": "soln", "canonical": "solution"},
    {"alias": "sol", "canonical": "solution"},
    {"alias": "pur", "canonical": "pure"},
    {"alias": "ar", "canonical": "analytical reagent"},
    {"alias": "pc", "canonical": "piece"},
    {"alias": "ea", "canonical": "each"},
    {"alias": "spec", "canonical": "specification"},
    {"alias": "mfg", "canonical": "manufacturing"},
    {"alias": "exp", "canonical": "expiry"},
    {"alias": "temp", "canonical": "temperature"},
    {"alias": "std", "canonical": "standard"}
]


def seed_search_aliases(session: Session) -> None:
    """Seed the search_aliases table with common lab/chemical supply abbreviations."""
    existing_count = session.query(SearchAlias).filter(SearchAlias.source == 'seed').count()
    if existing_count > 0:
        return

    logger.info("Seeding search_aliases table with domain-specific shorthand aliases...")
    for entry in SEED_ALIASES:
        alias_record = SearchAlias(
            alias=entry["alias"],
            canonical=entry["canonical"],
            scope="global",
            source="seed",
            confidence=Decimal("1.000")
        )
        session.add(alias_record)
    session.flush()


def expand_query(session: Session, query_string: str) -> List[List[str]]:
    """Tokenize the query string and expand each token using its configured aliases.
    
    Returns:
        List of lists, where each sublist contains the token and its synonym alternatives.
    """
    if not query_string:
        return []

    # Ensure aliases are seeded
    seed_search_aliases(session)

    tokens = [t.strip().lower() for t in query_string.split() if t.strip()]
    expanded = []

    for token in tokens:
        alternatives = {token}
        # Look up aliases matching this token
        aliases = session.query(SearchAlias).filter(SearchAlias.alias == token).all()
        for a in aliases:
            alternatives.add(a.canonical.lower())

        # Reverse lookup (if user searches canonical, match shorthand too)
        reverses = session.query(SearchAlias).filter(SearchAlias.canonical == token).all()
        for r in reverses:
            alternatives.add(r.alias.lower())

        expanded.append(list(alternatives))

    return expanded


def search_billing_documents(session: Session, query_str: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Perform alias-aware search over documents and line items with filters.
    
    Filters can contain: vendor_id, customer_id, document_type, start_date, end_date.
    """
    expanded_tokens = expand_query(session, query_str)
    
    query = session.query(BillingDocument).outerjoin(BillingVendor).outerjoin(BillingCustomer)

    # 1. Apply search keyword matches (AND of each query token's expanded alternatives)
    if expanded_tokens:
        for alternatives in expanded_tokens:
            token_conditions = []
            for alt in alternatives:
                pattern = f"%{alt}%"
                token_conditions.append(
                    or_(
                        BillingDocument.document_no.ilike(pattern),
                        BillingDocument.source_file.ilike(pattern),
                        BillingVendor.name.ilike(pattern),
                        BillingCustomer.name.ilike(pattern),
                        BillingDocument.line_items.any(
                            or_(
                                BillingDocumentLineItem.description.ilike(pattern),
                                BillingDocumentLineItem.item_code.ilike(pattern),
                                BillingDocumentLineItem.brand.ilike(pattern),
                                BillingDocumentLineItem.hsn_code.ilike(pattern)
                            )
                        )
                    )
                )
            query = query.filter(or_(*token_conditions))

    # 2. Apply filters
    if filters.get("vendor_id"):
        query = query.filter(BillingDocument.vendor_id == int(filters["vendor_id"]))
    if filters.get("customer_id"):
        query = query.filter(BillingDocument.customer_id == int(filters["customer_id"]))
    if filters.get("document_type"):
        query = query.filter(BillingDocument.document_type == filters["document_type"])
    if filters.get("start_date"):
        query = query.filter(BillingDocument.document_date >= filters["start_date"])
    if filters.get("end_date"):
        query = query.filter(BillingDocument.document_date <= filters["end_date"])

    # Order by date descending
    query = query.order_by(BillingDocument.document_date.desc(), BillingDocument.id.desc())
    
    docs = query.all()
    results = []
    for d in docs:
        results.append({
            "id": d.id,
            "document_type": d.document_type,
            "document_no": d.document_no,
            "document_date": d.document_date.isoformat() if d.document_date else None,
            "vendor_name": d.vendor.name if d.vendor else None,
            "customer_name": d.customer.name if d.customer else None,
            "grand_total_final": str(d.grand_total_final),
            "extraction_status": d.extraction_status,
            "classification_confidence": str(d.classification_confidence) if d.classification_confidence else None
        })
    return results


def suggest_alias(session: Session, query_str: str) -> Optional[Dict[str, str]]:
    """If search returns 0 results, find a close term in the database vocabulary to suggest."""
    if not query_str:
        return None

    tokens = [t.strip().lower() for t in query_str.split() if t.strip()]
    if not tokens:
        return None

    # Get unique words in document line item descriptions (our vocabulary)
    # Simple word tokenizer
    desc_words = set()
    items = session.query(BillingDocumentLineItem.description).all()
    for item in items:
        if item[0]:
            words = re.findall(r'\b[a-zA-Z]{3,}\b', item[0].lower())
            desc_words.update(words)

    from difflib import get_close_matches
    # For each token, if it has no matches, check if we have a close match in the vocabulary
    for token in tokens:
        # If token is already an alias or canonical, skip it
        alias_exists = session.query(SearchAlias).filter(
            or_(SearchAlias.alias == token, SearchAlias.canonical == token)
        ).first()
        if alias_exists:
            continue

        matches = get_close_matches(token, list(desc_words), n=1, cutoff=0.75)
        if matches:
            return {
                "alias": token,
                "suggested_canonical": matches[0]
            }
    return None


def record_feedback(session: Session, alias: str, canonical: str, accepted: bool) -> bool:
    """Track feedback on alias suggestions and promote to SearchAlias on 3 confirmations."""
    if not accepted or not alias or not canonical:
        return False

    alias = alias.strip().lower()
    canonical = canonical.strip().lower()

    # Check if this alias already exists in SearchAlias
    existing = session.query(SearchAlias).filter(
        SearchAlias.alias == alias,
        SearchAlias.canonical == canonical
    ).first()
    if existing:
        return True

    # Retrieve or create learned alias record
    la = session.query(LearnedAlias).filter(
        LearnedAlias.alias == alias,
        LearnedAlias.canonical_name == canonical
    ).first()

    if not la:
        la = LearnedAlias(
            alias=alias,
            canonical_name=canonical,
            category="global",
            occurrence_count=1
        )
        session.add(la)
        session.flush()
    else:
        la.occurrence_count += 1
        session.flush()

    logger.info(f"Learned alias feedback recorded for '{alias}' -> '{canonical}'. Occurrences: {la.occurrence_count}")

    # Promote to search_aliases if confirmed 3 or more times
    if la.occurrence_count >= 3:
        new_alias = SearchAlias(
            alias=alias,
            canonical=canonical,
            scope="global",
            source="learned",
            confidence=Decimal("0.900")
        )
        session.add(new_alias)
        session.delete(la)  # Clean up learned alias record
        session.flush()
        logger.info(f"Promoted learned alias '{alias}' -> '{canonical}' to SearchAlias.")
        return True

    return False
