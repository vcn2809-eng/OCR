import json

JSON_SCHEMA = {
    "quotation_number": "string",
    "quotation_date": "string",
    "customer_details": {
        "name": "string",
        "kind_attention": "string",
        "email": "string"
    },
    "vendor_details": {
        "name": "string",
        "gstin": "string",
        "pan": "string"
    },
    "line_items": [
        {
            "sl_no": "integer",
            "code": "string",
            "description": "string",
            "brand": "string",
            "uom": "string",
            "quantity": "integer",
            "rate": "number",
            "gross_amount": "number",
            "discount_percent": "number",
            "discount_amount": "number",
            "taxable_amount": "number",
            "cgst_percent": "number",
            "cgst_amount": "number",
            "sgst_percent": "number",
            "sgst_amount": "number",
            "final_value": "number",
            "eta": "string"
        }
    ],
    "grand_total": "number"
}


def data_conversion(raw_text: str) -> str:
    """Build structured prompt for extraction from raw OCR text."""
    schema_text = json.dumps(JSON_SCHEMA, indent=2)
    return (
        "You are a quotation extraction assistant.\n\n"
        "Return ONLY valid JSON. Do not explain anything.\n\n"
        "Extract fields from the following OCR text and populate the JSON structure below.\n\n"
        "Expected JSON schema:\n"
        f"{schema_text}\n\n"
        "Rules:\n"
        "- Use only information that exists in the OCR text.\n"
        "- Do not invent missing fields.\n"
        "- Preserve order where possible.\n"
        "- The output must be one JSON object with keys exactly matching the schema.\n"
        "- If some fields are missing, use empty strings, null, or omit them only where the schema allows.\n"
        "- If a field's value is unknown, keep it as empty string or 0.\n\n"
        "OCR TEXT:\n"
        "\"\"\"\n"
        f"{raw_text}\n"
        "\"\"\"\n"
    )
