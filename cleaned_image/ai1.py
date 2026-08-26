import json
import re
import subprocess

from prompt1 import data_conversion


def _sanitize_json_text(raw_json_text: str) -> str:
    """Coerce Ollama model output into strict JSON syntax by removing newline control characters inside quoted strings."""
    in_string = False
    escaped = False
    out = []

    for ch in raw_json_text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                in_string = False
                out.append(ch)
            elif ch in ("\n", "\r"):
                out.append(" ")
            else:
                out.append(ch)
        else:
            if ch == '"':
                in_string = True
            out.append(ch)

    return "".join(out)


def get_json_from_prompt(raw_invoice_text: str) -> dict:
    """Send raw OCR text to Ollama and return a parsed JSON dictionary."""
    prompt_str = data_conversion(raw_invoice_text)
    model_name = "richardyoung/olmocr2:7b-q8"

    process = subprocess.Popen(
        ["ollama", "run", model_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output, error = process.communicate(input=prompt_str)

    if process.returncode != 0 or error:
        raise RuntimeError(f"Ollama execution error: {error}")

    clean_output = output.strip()
    clean_output = re.sub(r"^```(?:json)?\s*", "", clean_output, flags=re.MULTILINE)
    clean_output = re.sub(r"\s*```$", "", clean_output, flags=re.MULTILINE)

    match = re.search(r"\{.*\}", clean_output, re.DOTALL)
    if match:
        clean_output = match.group(0)

    trimmed = clean_output.strip()
    if not (trimmed.endswith("}") or trimmed.endswith("]")):
        raise ValueError("Model response is truncated or incomplete JSON")

    try:
        return json.loads(clean_output)
    except json.JSONDecodeError as e:
        sanitized_output = _sanitize_json_text(clean_output)
        try:
            return json.loads(sanitized_output)
        except json.JSONDecodeError as fallback_error:
            print(f"Failed to parse JSON string: {fallback_error}")
            print("Raw output was:", output)
            print("Sanitized candidate was:", sanitized_output)
            return {}


if __name__ == "__main__":
    sample_pdf_text = """
    QUOTATION No.: 470114429 Date: 15-June-2026
    Kind Attention: Dr. Tathagata Dey (tathagata.dey@eastpoint.ac.in)
    To: East Point College of Pharmacy, M G Charitable Trust, Bidarahalli, Bengaluru-560049

    Item 1:
    Code: 88639-500GM
    Description: 2,4-Dinitrophenylhydrazine extrapure AR, 99%-500GM - 29280090
    Brand: SRL | UOM: 500GM | Packing: 1 Each | Qty: 1 | Rate: 3800.00
    Gross Amt: 3800.00 | Disc%: 25.00 | Discount Amount: 950.00 | Taxable: 2850.00
    CGST%: 9 (256.50) | SGST%: 9 (256.50) | Final Value: 3,363.00 | ETA: 7-10 Days

    Grand Total: INR 381656.00
    """

    extracted_json = get_json_from_prompt(sample_pdf_text)
    print("Successfully extracted JSON object:")
    print(json.dumps(extracted_json, indent=2))
