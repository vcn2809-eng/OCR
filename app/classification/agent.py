"""
Classification Agent — determines document type (invoice, resume, etc.) using keyword
heuristics first, falling back to an LLM call only when confidence is below threshold.
The LLM call is isolated in classify_with_llm() so it can be swapped or mocked easily.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import yaml
import openpyxl

from app.config import settings
from app.classification.exceptions import ClassificationError, LLMClassificationError
from app.classification.models import ClassificationResult

logger = logging.getLogger(__name__)

_rules_cache: dict | None = None

def load_classification_rules() -> dict:
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache
    
    rules_path = settings.CLASSIFICATION_RULES_PATH
    if not rules_path.exists():
        raise ClassificationError(f"Classification rules not found at {rules_path}")
    
    try:
        with open(rules_path, 'r') as f:
            rules = yaml.safe_load(f)
        if not rules:
            raise ClassificationError("Rules file is empty or malformed.")
        _rules_cache = rules
        return rules
    except Exception as e:
        raise ClassificationError(f"Failed to load rules: {e}")

def classify_with_heuristics(text_sample: str) -> ClassificationResult:
    text_sample_lower = text_sample.lower()
    rules = load_classification_rules()
    
    winner = 'generic'
    winner_score = 0.0
    
    for doc_type, config in rules.items():
        if doc_type == 'generic':
            continue
        
        keywords = config.get('keywords', [])
        threshold = config.get('threshold', 0.0)
        
        if not keywords:
            continue
            
        count = sum(1 for kw in keywords if kw.lower() in text_sample_lower)
        score = count / len(keywords)
        
        if score >= threshold and score > winner_score:
            winner = doc_type
            winner_score = score
            
    if winner == 'generic':
        result = ClassificationResult('generic', 0.0, 'heuristic')
    else:
        result = ClassificationResult(winner, winner_score, 'heuristic')
        
    logger.info(f"Heuristic classification result: {result.document_type} with confidence {result.confidence}")
    return result

def classify_with_llm(text_sample: str) -> ClassificationResult:
    if not settings.OPENAI_API_KEY:
        raise LLMClassificationError('No OpenAI API key configured')
        
    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    'role': 'system', 
                    'content': 'You are a document classifier. Classify the document into exactly one of: invoice, resume, financial_statement, purchase_order, generic. Reply with JSON only: {"document_type": "<type>", "confidence": <0-1>}'
                },
                {
                    'role': 'user', 
                    'content': text_sample[:2000]
                }
            ]
        )
        content = response.choices[0].message.content
        if not content:
            raise LLMClassificationError("Empty response from LLM")
            
        data = json.loads(content)
        result = ClassificationResult(
            document_type=data.get('document_type', 'generic'),
            confidence=float(data.get('confidence', 0.0)),
            method='llm_fallback'
        )
        logger.info(f"LLM classification result: {result.document_type} with confidence {result.confidence}")
        return result
    except Exception as e:
        raise LLMClassificationError(f"LLM classification failed: {e}")

def classify_excel(file_path: Path) -> ClassificationResult:
    try:
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet = wb.active
        text_parts = []
        if sheet.title:
            text_parts.append(sheet.title)
            
        for row_idx, row in enumerate(sheet.iter_rows(values_only=True)):
            if row_idx >= 3:
                break
            row_vals = [str(cell) for cell in row if cell is not None]
            text_parts.extend(row_vals)
            
        text_sample = ' '.join(text_parts)
        
        result = classify_with_heuristics(text_sample)
        if result.confidence < settings.CLASSIFICATION_CONFIDENCE_THRESHOLD and settings.OPENAI_API_KEY:
            try:
                llm_result = classify_with_llm(text_sample)
                return llm_result
            except LLMClassificationError as e:
                logger.warning(f"LLM fallback failed: {e}")
                return result
                
        return result
    except Exception as e:
        logger.warning(f"Failed to read excel file {file_path}: {e}")
        return ClassificationResult('generic', 0.0, 'heuristic')

def classify_document(document_id: str, file_path: Path, file_type: str, text_sample: str = '') -> ClassificationResult:
    if file_type == 'pdf':
        result = classify_with_heuristics(text_sample)
        if result.confidence < settings.CLASSIFICATION_CONFIDENCE_THRESHOLD and settings.OPENAI_API_KEY:
            try:
                result = classify_with_llm(text_sample)
            except LLMClassificationError as e:
                logger.warning(f"LLM fallback failed: {e}")
    elif file_type in ('xlsx', 'xls'):
        result = classify_excel(file_path)
    elif file_type == 'csv':
        result = ClassificationResult('generic', 0.5, 'heuristic')
    else:
        result = ClassificationResult('generic', 0.0, 'heuristic')
        
    logger.info(f"Document {document_id} ({file_type}) classified as {result.document_type} with confidence {result.confidence} via {result.method}")
    return result
