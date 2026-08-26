"""
Schema Mapping Agent — renames normalised field names to actual database column names
using a YAML config. Unmapped fields go into an 'extras' dict so no data is silently lost.
"""

import logging
from pathlib import Path
from typing import Any

import yaml

from app.config.settings import FIELD_MAPPINGS_PATH
from app.schema_mapping.exceptions import SchemaMappingError, MappingNotFoundError

logger = logging.getLogger(__name__)

_mappings_cache: dict | None = None

def _load_all_mappings() -> dict:
    global _mappings_cache
    if _mappings_cache is not None:
        return _mappings_cache
        
    try:
        with open(FIELD_MAPPINGS_PATH, "r", encoding="utf-8") as f:
            _mappings_cache = yaml.safe_load(f) or {}
    except Exception as e:
        raise SchemaMappingError(f"Failed to load schema mappings: {e}") from e
        
    return _mappings_cache

def load_mapping(document_type: str) -> dict[str, str]:
    mappings = _load_all_mappings()
    if document_type not in mappings:
        raise MappingNotFoundError(f"No mapping found for document type: {document_type}")
    return mappings[document_type]

def _normalize_key(key: str) -> str:
    return " ".join(key.lower().split())

def map_fields(normalized_row: dict, document_type: str) -> dict:
    try:
        mapping = load_mapping(document_type)
    except MappingNotFoundError:
        logger.warning(f"Mapping not found for '{document_type}'. All fields will go to extras.")
        mapping = {}
        
    lookup = {_normalize_key(k): v for k, v in mapping.items()}
    
    result = {"extras": {}}
    mapped_count = 0
    unmapped_count = 0
    
    for key, value in normalized_row.items():
        if key == "_normalization_warnings":
            result["_normalization_warnings"] = value
            continue
            
        normalized_k = _normalize_key(key)
        if normalized_k in lookup:
            result[lookup[normalized_k]] = value
            mapped_count += 1
        else:
            # Fallback to Learning Agent for abbreviations, aliases, and partial matches
            try:
                from app.learning.agent import resolve_alias
                match = resolve_alias(normalized_k)
                if match and match.similarity_score >= 0.75:
                    result[match.canonical_name] = value
                    mapped_count += 1
                else:
                    result["extras"][key] = value
                    unmapped_count += 1
            except Exception:
                result["extras"][key] = value
                unmapped_count += 1
            
    logger.debug(f"Mapped fields: {mapped_count}, Unmapped fields: {unmapped_count}")
    return result

def map_document(document_id: str, normalized_rows: list[dict], document_type: str) -> list[dict]:
    mapped_rows = [map_fields(row, document_type) for row in normalized_rows]
    logger.info(f"Document {document_id} ({document_type}): Mapped {len(mapped_rows)} rows")
    return mapped_rows

def add_mapping_rule(document_type: str, source_field: str, target_column: str) -> None:
    global _mappings_cache
    try:
        if Path(FIELD_MAPPINGS_PATH).exists():
            with open(FIELD_MAPPINGS_PATH, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
        else:
            yaml_data = {}
            
        yaml_data.setdefault(document_type, {})[source_field] = target_column
        
        with open(FIELD_MAPPINGS_PATH, "w", encoding="utf-8") as f:
            yaml.dump(yaml_data, f, allow_unicode=True, default_flow_style=False)
            
        _mappings_cache = None
        logger.info(f"Added mapping rule for {document_type}: {source_field} -> {target_column}")
    except Exception as e:
        raise SchemaMappingError(f"Failed to write mapping rule: {e}") from e
