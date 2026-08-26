"""
Learning Agent — discovers, stores, and resolves field name aliases, abbreviations,
misspellings, and partial values.

Persists learned mappings in PostgreSQL so they carry forward across document runs,
and provides fuzzy and partial string extraction.
"""
from difflib import SequenceMatcher
import logging
import re
from typing import Any, Optional

from app.learning.exceptions import LearningError, InvalidAliasError, AliasNotFoundError
from app.learning.models import AliasMapping, MatchResult

logger = logging.getLogger(__name__)

# Built-in base dictionary of common industry abbreviations and aliases
DEFAULT_ALIASES: dict[str, tuple[str, str]] = {
    "mtrl": ("materials", "header"),
    "mat": ("materials", "header"),
    "materials": ("materials", "header"),
    "qty": ("quantity", "header"),
    "qnty": ("quantity", "header"),
    "desc": ("description", "header"),
    "descripon": ("description", "header"),
    "inv": ("invoice_number", "header"),
    "inv #": ("invoice_number", "header"),
    "inv no": ("invoice_number", "header"),
    "invoice #": ("invoice_number", "header"),
    "amt": ("amount", "header"),
    "gross amt": ("gross_amount", "header"),
    "tot": ("total", "header"),
    "disc": ("discount", "header"),
    "disc%": ("discount_percentage", "header"),
    "taxable": ("taxable_amount", "header"),
    "cust": ("customer_name", "header"),
    "client": ("customer_name", "header"),
    "vendor": ("vendor_name", "header"),
    "seller": ("vendor_name", "header"),
    "po": ("purchase_order_number", "header"),
    "po #": ("purchase_order_number", "header"),
    "po number": ("purchase_order_number", "header"),
    "soluon": ("solution", "term"),
    "extrapure": ("extra_pure", "term"),
}

# In-memory dynamic cache (populated from database on demand)
_in_memory_aliases: dict[str, tuple[str, str, float, int]] = {}
_is_cache_initialized: bool = False


def _get_persistence():
    try:
        from app.persistence import agent as persistence_agent
        return persistence_agent
    except Exception as exc:
        logger.debug("Persistence agent not accessible: %s", exc)
        return None


def _ensure_cache_loaded() -> None:
    """Load learned aliases from the database into the in-memory cache."""
    global _in_memory_aliases, _is_cache_initialized
    if _is_cache_initialized:
        return

    _in_memory_aliases.clear()

    # 1. Load built-in defaults
    for alias, (canonical, category) in DEFAULT_ALIASES.items():
        _in_memory_aliases[alias.lower()] = (canonical.lower(), category, 1.0, 1)

    # 2. Load from DB if available
    persistence = _get_persistence()
    if persistence:
        try:
            db_aliases = persistence.get_learned_aliases()
            for item in db_aliases:
                _in_memory_aliases[item["alias"].lower()] = (
                    item["canonical_name"].lower(),
                    item.get("category", "header"),
                    item.get("confidence", 1.0),
                    item.get("occurrence_count", 1),
                )
            logger.info("Loaded %d learned aliases from database", len(db_aliases))
        except Exception as exc:
            logger.warning("Could not load learned aliases from database: %s", exc)

    _is_cache_initialized = True


def _clean_key(text: str) -> str:
    """Normalize input text: lowercase, strip, collapse multiple spaces."""
    cleaned = text.strip().lower()
    return re.sub(r"\s+", " ", cleaned)


def _is_abbreviation(alias: str, canonical: str) -> bool:
    """Check if alias is an abbreviation of canonical (e.g. mtrl -> materials, qty -> quantity)."""
    if len(alias) >= len(canonical):
        return False

    # Check if prefix match (e.g. mat -> materials, desc -> description)
    if canonical.startswith(alias):
        return True

    # Check subsequence match (e.g. mtrl -> m-a-t-e-r-i-a-l-s)
    it = iter(canonical)
    return all(char in it for char in alias)


def learn_alias(
    alias: str,
    canonical_name: str,
    category: str = "header",
    confidence: float = 1.0,
) -> AliasMapping:
    """Register and persist a new alias -> canonical_name mapping.

    Learned mappings are saved to PostgreSQL and carried forward automatically.
    """
    clean_alias = _clean_key(alias)
    clean_canonical = _clean_key(canonical_name)

    if not clean_alias or not clean_canonical:
        raise InvalidAliasError("Alias and canonical_name must be non-empty strings.")

    _ensure_cache_loaded()

    # Update memory cache
    existing = _in_memory_aliases.get(clean_alias)
    count = (existing[3] + 1) if existing else 1
    _in_memory_aliases[clean_alias] = (clean_canonical, category, confidence, count)

    # Persist to database if available
    persistence = _get_persistence()
    if persistence:
        try:
            persistence.save_learned_alias(clean_alias, clean_canonical, category, confidence)
            logger.info("Learned alias '%s' -> '%s' saved to database", clean_alias, clean_canonical)
        except Exception as exc:
            logger.warning("Failed to persist alias '%s' to DB: %s", clean_alias, exc)

    return AliasMapping(
        alias=clean_alias,
        canonical_name=clean_canonical,
        category=category,
        confidence=confidence,
        occurrence_count=count,
    )


def resolve_alias(
    text: str,
    category: Optional[str] = None,
    threshold: float = 0.75,
) -> Optional[MatchResult]:
    """Resolve a raw field name or term to its canonical name.

    Search order:
      1. Exact match against learned & built-in dictionary
      2. Known abbreviation / prefix match
      3. Fuzzy string matching (SequenceMatcher ratio >= threshold)
    """
    if not text or not text.strip():
        return None

    clean_text = _clean_key(text)
    _ensure_cache_loaded()

    # 1. Exact match
    if clean_text in _in_memory_aliases:
        canonical, cat, conf, _ = _in_memory_aliases[clean_text]
        if category is None or cat == category:
            return MatchResult(
                original_text=text,
                canonical_name=canonical,
                match_type="exact" if clean_text == canonical else "alias",
                similarity_score=conf,
                category=cat,
                start_index=0,
                end_index=len(text),
            )

    # 2. Abbreviation / Prefix match
    best_abbr: Optional[tuple[str, str, float]] = None
    for alias_key, (canonical, cat, conf, _) in _in_memory_aliases.items():
        if category and cat != category:
            continue
        if _is_abbreviation(clean_text, canonical) or _is_abbreviation(clean_text, alias_key):
            score = len(clean_text) / float(len(canonical))
            if best_abbr is None or score > best_abbr[2]:
                best_abbr = (canonical, cat, max(0.8, score))

    if best_abbr:
        return MatchResult(
            original_text=text,
            canonical_name=best_abbr[0],
            match_type="abbreviation",
            similarity_score=best_abbr[2],
            category=best_abbr[1],
            start_index=0,
            end_index=len(text),
        )

    # 3. Fuzzy match against all known aliases and canonical names
    best_fuzzy: Optional[tuple[str, str, float]] = None
    for alias_key, (canonical, cat, conf, _) in _in_memory_aliases.items():
        if category and cat != category:
            continue

        ratio_alias = SequenceMatcher(None, clean_text, alias_key).ratio()
        ratio_canonical = SequenceMatcher(None, clean_text, canonical).ratio()
        max_ratio = max(ratio_alias, ratio_canonical)

        if max_ratio >= threshold:
            if best_fuzzy is None or max_ratio > best_fuzzy[2]:
                best_fuzzy = (canonical, cat, max_ratio)

    if best_fuzzy:
        return MatchResult(
            original_text=text,
            canonical_name=best_fuzzy[0],
            match_type="fuzzy",
            similarity_score=best_fuzzy[2],
            category=best_fuzzy[1],
            start_index=0,
            end_index=len(text),
        )

    return None


def extract_partial_values(
    text: str,
    candidates: Optional[list[str]] = None,
    threshold: float = 0.70,
) -> list[MatchResult]:
    """Extract partial matches and sub-strings from a raw line of text.

    Finds embedded abbreviations (e.g. 'mtrl', 'qty') or candidate names within messy OCR strings.
    """
    if not text or not text.strip():
        return []

    _ensure_cache_loaded()
    results: list[MatchResult] = []
    seen_spans: set[tuple[int, int]] = set()

    # Collect target candidates: provided list + all learned canonicals & aliases
    target_map: dict[str, str] = {}  # token -> canonical
    if candidates:
        for c in candidates:
            target_map[_clean_key(c)] = _clean_key(c)

    for alias, (canonical, cat, _, _) in _in_memory_aliases.items():
        target_map[alias] = canonical
        target_map[canonical] = canonical

    # Tokenize input text with positions
    tokens_with_spans = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"\S+", text)]

    for token, start, end in tokens_with_spans:
        clean_tok = _clean_key(token)
        if len(clean_tok) < 2:
            continue

        # Check exact or alias match for token
        match = resolve_alias(clean_tok, threshold=threshold)
        if match:
            match.original_text = token
            match.start_index = start
            match.end_index = end
            if (start, end) not in seen_spans:
                results.append(match)
                seen_spans.add((start, end))
            continue

        # Check candidate partial matching
        for target, canonical in target_map.items():
            if _is_abbreviation(clean_tok, target):
                res = MatchResult(
                    original_text=token,
                    canonical_name=canonical,
                    match_type="partial",
                    similarity_score=len(clean_tok) / float(len(target)),
                    category="header",
                    start_index=start,
                    end_index=end,
                )
                if (start, end) not in seen_spans:
                    results.append(res)
                    seen_spans.add((start, end))
                break

    return results


def learn_from_document(
    raw_fields: list[str],
    mapped_record: dict[str, Any],
    document_type: str = "generic",
) -> int:
    """Analyze extractions from a document to discover and persist new field aliases.

    Compares unmapped raw field names with mapped target schema columns to learn
    aliases automatically for future document runs.
    """
    learned_count = 0

    for raw_key in raw_fields:
        clean_raw = _clean_key(raw_key)
        if not clean_raw:
            continue

        # Check if raw_key mapped to any non-extras column
        for mapped_col, val in mapped_record.items():
            if mapped_col == "extras":
                continue
            clean_col = _clean_key(mapped_col)

            # If raw key partially matches target column name but isn't exact, learn it
            if clean_raw != clean_col and _is_abbreviation(clean_raw, clean_col):
                learn_alias(clean_raw, clean_col, category="header", confidence=0.9)
                learned_count += 1
                logger.info("Auto-learned alias from document: '%s' -> '%s'", clean_raw, clean_col)

    return learned_count


def get_all_learned_aliases(category: Optional[str] = None) -> list[dict[str, Any]]:
    """Return all stored learned aliases."""
    _ensure_cache_loaded()
    results = []
    for alias, (canonical, cat, conf, count) in _in_memory_aliases.items():
        if category is None or cat == category:
            results.append(
                {
                    "alias": alias,
                    "canonical_name": canonical,
                    "category": cat,
                    "confidence": conf,
                    "occurrence_count": count,
                }
            )
    return results


def bulk_learn_aliases(
    alias_pairs: list[tuple[str, str]],
    category: str = "header",
) -> int:
    """Bulk register multiple (alias, canonical_name) pairs."""
    count = 0
    for alias, canonical in alias_pairs:
        try:
            learn_alias(alias, canonical, category=category)
            count += 1
        except LearningError as exc:
            logger.warning("Failed to learn pair (%s, %s): %s", alias, canonical, exc)
    return count
