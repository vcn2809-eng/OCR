CATEGORIES = [
    "Laboratory Reagents",
    "Glassware",
    "Consumables",
    "Instrumentation",
    "Chemicals",
    "Filters",
    "Safety Equipment",
    "Other"
]


def bill_category_prompt(description_text: str) -> str:
    category_list = ", ".join(CATEGORIES)
    return f"""Classify this item description into one of these categories exactly:
{category_list}

Description: {description_text}

Respond with only one category name and nothing else.
"""
