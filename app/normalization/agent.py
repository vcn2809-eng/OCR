"""
Normalization Agent — standardises raw extracted field values into consistent Python types
(date, Decimal, float, str). Logs warnings for unparseable values rather than crashing.
Fields that fail normalisation are kept with their raw value and flagged in
'_normalization_warnings'.
"""
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional

import yaml
from dateutil import parser as dateutil_parser
from dateutil.parser import ParserError

from app.config.settings import OCR_CORRECTIONS_PATH
from app.normalization.exceptions import NormalizationError

logger = logging.getLogger(__name__)

_corrections_cache: dict | None = None


def load_ocr_corrections() -> dict:
    """Read OCR_CORRECTIONS_PATH YAML and cache the results."""
    global _corrections_cache
    if _corrections_cache is not None:
        return _corrections_cache

    try:
        path = Path(OCR_CORRECTIONS_PATH)
        if not path.exists():
            logger.warning(f"OCR corrections file not found at {path}")
            _corrections_cache = {'corrections': {}, 'patterns': {}}
            return _corrections_cache

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        _corrections_cache = {
            'corrections': data.get('corrections', {}),
            'patterns': data.get('patterns', {})
        }
    except Exception as e:
        logger.warning(f"Error loading OCR corrections: {e}")
        _corrections_cache = {'corrections': {}, 'patterns': {}}
        
    return _corrections_cache


def clean_text(raw_value: Any) -> str:
    """Convert to string, strip whitespace, collapse internal spaces, apply corrections, and resolve OCR unit anomalies."""
    if raw_value is None:
        return ""
    if not isinstance(raw_value, str):
        raw_value = str(raw_value)
    
    cleaned = raw_value.strip()
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    
    # Auto-correct common OCR unit transcription exceptions
    cleaned = re.sub(r'\b[BS5]OO\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), cleaned)
    cleaned = re.sub(r'\b[BS5]0O\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), cleaned)
    cleaned = re.sub(r'\b[BS5]O0\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), cleaned)
    cleaned = re.sub(r'\b1OO\s*(ML|GM|G|L|ml|gm|g|l|Gms|gms)\b', lambda m: '100' + m.group(1), cleaned)
    cleaned = re.sub(r'^_(S|5)OOGM$', '500GM', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^_(S|5)00GM$', '500GM', cleaned, flags=re.IGNORECASE)

    corrections = load_ocr_corrections()
    patterns = corrections.get('patterns', {})
    
    for old, new in patterns.items():
        cleaned = cleaned.replace(old, new)
        
    return cleaned


def normalize_date(raw_value: str) -> Optional[date]:
    """Parse date from string."""
    cleaned = clean_text(raw_value)
    if not cleaned or cleaned.lower() in ('n/a', 'none', 'null', '-'):
        return None
        
    try:
        return dateutil_parser.parse(cleaned, fuzzy=True).date()
    except Exception as e:
        logger.warning(f"Failed to parse date from '{raw_value}': {e}")
        return None


def normalize_currency(raw_value: str) -> Optional[Decimal]:
    """Parse currency from string, handling negative parenthesis notation and thousands separators."""
    cleaned = clean_text(raw_value)
    if not cleaned or cleaned.lower() in ('n/a', 'none', '-'):
        return None
        
    # Remove currency symbols and words
    cleaned = re.sub(r'(?i)[\$£€¥₹]|usd|eur|gbp|inr', '', cleaned)
    
    # Handle parentheses for negative numbers
    match = re.match(r'^\s*\((.*)\)\s*$', cleaned)
    is_negative = False
    if match:
        cleaned = match.group(1)
        is_negative = True
        
    # Remove thousands separators (commas between digits)
    cleaned = re.sub(r'(\d),(\d)', r'\1\2', cleaned)
    cleaned = cleaned.strip()
    
    if is_negative:
        cleaned = f"-{cleaned}"
        
    try:
        return Decimal(cleaned)
    except Exception as e:
        logger.warning(f"Failed to parse currency from '{raw_value}': {e}")
        return None


def normalize_number(raw_value: str) -> Optional[float]:
    """Parse float from string."""
    cleaned = clean_text(raw_value)
    if not cleaned or cleaned.lower() in ('n/a', 'none', '-'):
        return None
        
    cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except Exception as e:
        logger.warning(f"Failed to parse number from '{raw_value}': {e}")
        return None


def normalize_row(raw_row: dict, column_types: dict[str, str]) -> dict:
    """Normalize a single row's fields based on column types."""
    normalized = {}
    warnings = []
    
    for key, value in raw_row.items():
        col_type = column_types.get(key, 'text')
        
        if col_type == 'date':
            result = normalize_date(value)
            if result is None:
                # Check if it was explicitly a null-like value vs a parsing failure
                cleaned = clean_text(value).lower()
                if cleaned and cleaned not in ('n/a', 'none', 'null', '-'):
                    warnings.append(f"Field '{key}' failed date normalisation for value '{value}'")
                    normalized[key] = value
                else:
                    normalized[key] = None
            else:
                normalized[key] = result.isoformat()
                
        elif col_type == 'currency':
            result = normalize_currency(value)
            if result is None:
                cleaned = clean_text(value).lower()
                if cleaned and cleaned not in ('n/a', 'none', '-'):
                    warnings.append(f"Field '{key}' failed currency normalisation for value '{value}'")
                    normalized[key] = value
                else:
                    normalized[key] = None
            else:
                normalized[key] = str(result)
                
        elif col_type == 'number':
            result = normalize_number(value)
            if result is None:
                cleaned = clean_text(value).lower()
                if cleaned and cleaned not in ('n/a', 'none', '-'):
                    warnings.append(f"Field '{key}' failed number normalisation for value '{value}'")
                    normalized[key] = value
                else:
                    normalized[key] = None
            else:
                normalized[key] = result
                
        else:
            normalized[key] = clean_text(value)
            
    normalized['_normalization_warnings'] = warnings
    return normalized


def normalize_document(document_id: str, rows: list[dict], column_types: dict[str, str]) -> list[dict]:
    """Normalize a batch of rows for a document, using LLM cleaner for catalog documents."""
    # Detect if it's a catalog document
    is_catalog_doc = False
    if rows:
        first_row_keys = list(rows[0].keys())
        has_col_keys = any(k.startswith('col_') for k in first_row_keys)
        if has_col_keys:
            # Let's check if any row matches catalog item row pattern
            catalog_code_re = re.compile(r'^\d{4,}-\S+')
            for row in rows:
                for v in row.values():
                    if v:
                        s = str(v).strip()
                        s = re.sub(r'\b[BS5]OO\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), s)
                        s = re.sub(r'\b[BS5]0O\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), s)
                        s = re.sub(r'\b[BS5]O0\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), s)
                        s = re.sub(r'\b1OO\s*(ML|GM|G|L|ml|gm|g|l|Gms|gms)\b', lambda m: '100' + m.group(1), s)
                        s = re.sub(r'^_(S|5)OOGM$', '500GM', s, flags=re.IGNORECASE)
                        s = re.sub(r'^_(S|5)00GM$', '500GM', s, flags=re.IGNORECASE)
                        if catalog_code_re.match(s):
                            is_catalog_doc = True
                            break
                if is_catalog_doc:
                    break

            # Also check if filename has price list or catalog
            if not is_catalog_doc:
                try:
                    from app.persistence.db import get_document_with_fields
                    doc = get_document_with_fields(document_id)
                    if doc:
                        filename = doc.get("original_filename", "").lower()
                        if "price list" in filename or "catalog" in filename or "price_list" in filename:
                            is_catalog_doc = True
                except Exception as e:
                    logger.warning(f"Error querying document info in normalizer: {e}")

    normalized_rows = []
    if is_catalog_doc:
        try:
            from app.normalization.llm_cleaner import clean_rows_with_llm
            normalized_rows = clean_rows_with_llm(rows, column_types)
        except Exception as e:
            logger.error(f"Failed to use LLM cleaner for document {document_id}: {e}. Falling back to standard normalizer.")
            normalized_rows = []

    # If not a catalog doc, or if LLM cleaner failed/returned empty list, use standard normalize_row
    if not normalized_rows:
        for row in rows:
            norm_row = normalize_row(row, column_types)
            normalized_rows.append(norm_row)

    has_warnings = False
    for norm_row in normalized_rows:
        if norm_row.get('_normalization_warnings'):
            has_warnings = True

    logger.info(f"Normalized {len(rows)} rows for document {document_id}")
    if has_warnings:
        logger.warning(f"Warnings encountered while normalizing document {document_id}")

    return normalized_rows

