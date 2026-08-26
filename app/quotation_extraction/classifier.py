import logging
import re
import json
from decimal import Decimal
from typing import Dict, Any, Tuple
from app.config.settings import OPENAI_API_KEY, OLLAMA_MODEL

logger = logging.getLogger(__name__)


def classify_document_text(text: str) -> Tuple[str, Decimal, str]:
    """Classify the document type from first page raw text using heuristics and LLM fallback.
    
    Returns:
        Tuple[document_type, confidence, reasoning]
    """
    if not text:
        return 'quotation', Decimal('0.500'), 'Empty text fallback to quotation'

    normalized = " ".join(text.lower().split())

    # Patient Account Statement / Hospital Bill
    if any(k in normalized for k in ["patient account statement", "patient statement", "account statement", "medical statement", "hospital statement", "patient amount due", "total billed charges"]):
        return 'patient_account_statement', Decimal('1.000'), 'Found "Patient Account Statement" heading'

    # Proforma Invoice
    if "proforma invoice" in normalized or "pro-forma invoice" in normalized or "pi no." in normalized or "proforma" in normalized:
        return 'invoice_proforma', Decimal('1.000'), 'Found "Proforma Invoice" heading'
    
    # Purchase Order
    if "purchase order" in normalized or "po no" in normalized or "po number" in normalized or "lpo no" in normalized:
        return 'purchase_order', Decimal('1.000'), 'Found "Purchase Order" heading'

    # Tax Invoice
    if "tax invoice" in normalized or "retail invoice" in normalized or "bill of supply" in normalized or "commercial invoice" in normalized:
        return 'invoice_final', Decimal('1.000'), 'Found "Tax Invoice" heading'

    # Quotation
    if "quotation" in normalized or "quote" in normalized or "validity" in normalized or "enq. ref" in normalized:
        return 'quotation', Decimal('0.950'), 'Found Quotation-specific header terms ("Quotation" / "Validity" / "Enq. Ref")'

    # Generic Invoice
    if "invoice no" in normalized or "invoice date" in normalized or "bill no" in normalized or "tax id" in normalized:
        return 'invoice_final', Decimal('0.900'), 'Found invoice number and date fields'

    # If heuristics are ambiguous, fall back to LLM classifier
    logger.info("Heuristics ambiguous. Invoking LLM for document classification.")
    return classify_with_llm(text)


def classify_with_llm(text: str) -> Tuple[str, Decimal, str]:
    """Fallback LLM classification using OpenAI (if key is set) or local Ollama."""
    prompt = f"""You are a document classification assistant. Analyze the following document text and classify it into one of these five categories:
- purchase_order (if it is a Purchase Order issued by the customer confirming an order)
- quotation (if it is a price offer/proposal from the vendor containing validity or enquiry fields)
- invoice_proforma (if it is a proforma/advance invoice issued before goods or payment)
- invoice_final (if it is a final GST tax invoice with an invoice number and no quotation/validity terms)
- patient_account_statement (if it is a patient account statement, hospital bill, or medical statement)

Return ONLY a valid JSON object in this format:
{{
  "document_type": "purchase_order" | "quotation" | "invoice_proforma" | "invoice_final" | "patient_account_statement",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<brief explanation>"
}}

Document text:
\"\"\"
{text[:2000]}
\"\"\"
"""
    raw_response = ""
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            raw_response = completion.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI classification failed: {e}. Falling back to Ollama.")

    if not raw_response:
        try:
            import subprocess
            process = subprocess.Popen(
                ["ollama", "run", OLLAMA_MODEL],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            raw_response, err = process.communicate(input=prompt, timeout=60)
            if process.returncode != 0:
                raise RuntimeError(err or "Ollama classification execution failed")
        except Exception as e:
            logger.error(f"Ollama classification failed: {e}. Defaulting to quotation.")
            return 'quotation', Decimal('0.500'), f'LLM classification failed: {e}. Defaulted to quotation.'

    try:
        # Clean JSON fences if any
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        
        parsed = json.loads(cleaned, strict=False)
        doc_type = parsed.get("document_type", "quotation")
        if doc_type not in ('purchase_order', 'quotation', 'invoice_proforma', 'invoice_final', 'patient_account_statement'):
            doc_type = 'quotation'
        confidence = Decimal(str(round(float(parsed.get("confidence", 0.8)), 3)))
        reasoning = parsed.get("reasoning", "LLM classified")
        return doc_type, confidence, reasoning
    except Exception as e:
        logger.error(f"Failed to parse LLM classification response: {e}")
        return 'quotation', Decimal('0.500'), f'Failed to parse LLM response: {e}'
