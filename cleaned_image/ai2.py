import re
import subprocess

from prompt2 import bill_category_prompt


def get_category_from_ollama(description_text: str) -> str:
    """Allows each line-item description to be classified by a local Ollama model."""
    prompt_str = bill_category_prompt(description_text)
    model_name = "richardyoung/olmocr2:7b-q8"

    process = subprocess.Popen(
        ["ollama", "run", model_name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    output, error = process.communicate(input=prompt_str)

    if process.returncode != 0 or error or not output.strip():
        return "UNCATEGORIZED_LLM_ERROR"

    clean_category = output.strip()
    clean_category = re.sub(r'["\'\.\,]', '', clean_category)

    lines = clean_category.split("\n")
    final_category = lines[0].strip() if lines else "Others"

    return final_category if final_category else "Others"


if __name__ == "__main__":
    sample_descriptions = [
        "Acetone Extrapure, 99%-500ML-29141100-",
        "Sulphuric Acid 90% For Synthesis-2500ML - 28070010-",
        "Bromocresol Green Solution-125ML-29349990-",
        "Agar Powder Regular Grade For Bacteriology-500GM - 13023100-",
        "Sodium Chloride ACS, 99.9%-500GM- 25010090-",
    ]

    print("Categorization Results:")
    print("-" * 50)
    for desc in sample_descriptions:
        cat = get_category_from_ollama(desc)
        print(f"Item: {desc}\n  --> Category: {cat}\n")
