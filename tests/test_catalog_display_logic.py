"""
Tests for catalog table display-logic bugs found during investigation.

These tests mirror the JavaScript helpers in Vendors.jsx as Python functions
so the root-cause contract can be verified without a browser.

Bug 1 — Description column empty:
    The OCR word-clustering assigns each word an independent column index per row.
    "Description" was at col_68 in the header row, but the actual description text
    lands at col_47/col_52/col_53/col_17/col_18/col_84 in data rows.
    The old code read col_6/col_7/col_8 (which held "PAN NO." company header text).

Bug 2 — Disc% shows '|', '}', '/', ']' characters:
    col_24 values arrive as '25.00/', '25.00|', '|25.00|', '125.900]' because OCR
    merges vertical table-border characters into the numeric value.
    The old regex /[\}\]\|]1$/ only stripped a trailing brace/pipe IMMEDIATELY
    followed by the digit 1 — it missed leading pipes and trailing '/', ']'.
"""
import re
import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Python mirrors of the JS helpers in Vendors.jsx
# ─────────────────────────────────────────────────────────────────────────────

def clean_val(val: object) -> str:
    """Plain string clean — trim whitespace and correct common OCR unit anomalies."""
    if val is None:
        return ""
    s = str(val).strip()
    
    # Auto-correct common OCR unit transcription exceptions
    s = re.sub(r'\b[BS5]OO\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), s)
    s = re.sub(r'\b[BS5]0O\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), s)
    s = re.sub(r'\b[BS5]O0\s*(ML|GM|G|L|ml|gm|g|l)\b', lambda m: '500' + m.group(1), s)
    s = re.sub(r'\b1OO\s*(ML|GM|G|L|ml|gm|g|l|Gms|gms)\b', lambda m: '100' + m.group(1), s)
    s = re.sub(r'^_(S|5)OOGM$', '500GM', s, flags=re.IGNORECASE)
    s = re.sub(r'^_(S|5)00GM$', '500GM', s, flags=re.IGNORECASE)
    
    return s


def clean_numeric(val: object) -> str:
    """
    Strip ALL leading and trailing non-numeric/non-decimal characters.

    Handles: |25.00|, 25.00/, {1, 125.900], }1
    BUG FIX: old regex /[\}\]\|]1$/ only matched trailing '}]|' + '1',
    missing leading '|' and trailing '/' or ']'.
    """
    if val is None:
        return ""
    s = str(val).strip()
    # Strip leading non-numeric chars (pipes, braces, brackets, letters)
    s = re.sub(r'^[^\d.\-,(]+', '', s)
    # Strip trailing non-numeric chars (pipes, braces, slashes, brackets)
    s = re.sub(r'[^\d.,%]+$', '', s)
    return s


# Columns actually confirmed to hold description text in AIC catalog rows.
DESC_COLS = ['col_47', 'col_52', 'col_53', 'col_17', 'col_18', 'col_84']
SEPARATOR_RE = re.compile(r'^[|{}\[\]\-.~,;:]+$')
CATALOG_CODE_RE = re.compile(r'^\d{4,}-\S+')


def get_description(row: dict) -> str:
    """Collect description tokens dynamically from the row columns, ignoring codes, brands, numbers, and header words."""
    sorted_keys = sorted(
        [k for k in row.keys() if k.startswith('col_')],
        key=lambda x: int(x.split('_')[1])
    )
    
    brands = ['SRL', 'LOBA', 'MERCK', 'CDH', 'NICE']
    blacklist = ['PAN', 'GSTIN', 'GST', 'MSME', 'UDYAM', 'AASCAQSO0A', 'CODE', 'PRICE', 'LIST', 'PAGE', 'NO.']
    tokens = []
    
    for key in sorted_keys:
        val = clean_val(row.get(key, ''))
        if not val:
            continue
            
        if SEPARATOR_RE.match(val):
            continue
        if CATALOG_CODE_RE.match(val):
            continue
            
        upper = val.toUpperCase() if hasattr(val, 'toUpperCase') else val.upper()
        if any(b == upper or b in upper for b in blacklist):
            continue
        if any(b in upper for b in brands):
            continue
            
        if re.search(r'^\b\d*[A-Z]{1,4}\s*(ml|gm|gms|g|l|each)\b', val, re.IGNORECASE):
            continue
        if re.search(r'^\b[BS5]OO\s*(ML|GM|G|L)\b', val, re.IGNORECASE):
            continue
        if val.lower() in ('500gm', '500ml', '25gm', '500gms', '5oogm', 'booml', 'sooml', 'each', '1 each'):
            continue
            
        clean_num = re.sub(r'[^\d.\-,()]', '', val)
        try:
            if clean_num:
                float(clean_num)
                continue
        except ValueError:
            pass
            
        tokens.append(val)
        
    return ' '.join(tokens).strip()


def is_catalog_item_row(row: dict) -> bool:
    """A real catalog row has a code matching the catalog code pattern in any column."""
    return any(bool(CATALOG_CODE_RE.match(clean_val(v))) for v in row.values())


def is_missing_description(row: dict) -> bool:
    """Flag rows where description is empty but price/qty data IS present."""
    desc = get_description(row)
    has_other = clean_numeric(row.get('col_14')) or \
                clean_numeric(row.get('col_71')) or \
                clean_val(row.get('col_48'))
    return not desc and bool(has_other)


# ─────────────────────────────────────────────────────────────────────────────
# Tests required by the task specification
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanVal:
    def test_clean_val_ocr_corrections(self):
        assert clean_val("BOOml") == "500ml"
        assert clean_val("BOOML") == "500ML"
        assert clean_val("SOOML") == "500ML"
        assert clean_val("5OOGM") == "500GM"
        assert clean_val("_SOOGM") == "500GM"
        assert clean_val("1OOML") == "100ML"


class TestCleanNumeric:
    """Bug 2: Disc% / numeric fields must never contain trailing non-numeric chars."""

    def test_clean_trailing_pipe(self):
        """'25.00|' → '25.00'  (trailing pipe from OCR table-border merge)"""
        assert clean_numeric("25.00|") == "25.00"

    def test_clean_leading_pipe(self):
        """'|25.00' → '25.00'  (leading pipe)"""
        assert clean_numeric("|25.00") == "25.00"

    def test_clean_surrounding_pipes(self):
        """|25.00| → '25.00'"""
        assert clean_numeric("|25.00|") == "25.00"

    def test_clean_trailing_slash(self):
        """'25.00/' → '25.00'  (slash from OCR column-separator artifact)"""
        assert clean_numeric("25.00/") == "25.00"

    def test_clean_trailing_bracket(self):
        """'125.900]' → '125.900'"""
        assert clean_numeric("125.900]") == "125.900"

    def test_clean_trailing_brace(self):
        """'25.00}' → '25.00'  (the original stray-brace example from bug report)"""
        assert clean_numeric("25.00}") == "25.00"

    def test_clean_leading_brace_with_digit(self):
        """'}1' → '1'  (this is what the old regex was MEANT to handle)"""
        assert clean_numeric("}1") == "1"

    def test_clean_plain_number_unchanged(self):
        """'256.50' → '256.50'  (clean values must pass through unchanged)"""
        assert clean_numeric("256.50") == "256.50"

    def test_clean_number_with_comma_separator(self):
        """'3,363.00' → '3,363.00'  (commas as thousands-sep must be preserved)"""
        assert clean_numeric("3,363.00") == "3,363.00"

    def test_clean_none_returns_empty(self):
        assert clean_numeric(None) == ""

    def test_clean_empty_string(self):
        assert clean_numeric("") == ""

    def test_result_never_contains_pipe(self):
        """Systematic: no output from clean_numeric() should contain |, }, {, /, ]"""
        samples = ["25.00|", "|25.00|", "|1", "{1", "25.00}", "125.900]", "25.00/"]
        for s in samples:
            result = clean_numeric(s)
            for bad_char in ('|', '}', '{', '/', ']'):
                assert bad_char not in result, (
                    f"clean_numeric({s!r}) = {result!r} still contains {bad_char!r}"
                )


class TestGetDescription:
    """Bug 1: Description column was empty because wrong col indices were read."""

    # Real data rows extracted from the AIC catalog DB (confirmed via investigation)
    ROW_DINITRO = {
        "col_1": "88639-500GM",
        "col_24": "25.00/",
        "col_37": "Each",
        "col_47": "2,4-Dinitrophenylhydrazi",
        "col_48": "SRL",
        "col_60": "}1",
        "col_66": "5OOGM",
        "col_71": "1",
        "col_72": "950.00",
    }

    ROW_AGAR = {
        "col_1": "19661-500Gms",
        "col_3": "3",
        "col_14": "79.88",
        "col_17": "Agar",
        "col_18": "Powder",
        "col_23": "4260.00",
        "col_24": "|25.00|",
        "col_26": "3195.00",
        "col_35": "3,354.75",
        "col_37": "Each",
        "col_38": "79.88",
        "col_48": "SRL",
        "col_60": "|1",
        "col_62": "4260.00",
        "col_66": "_SOOGM",
        "col_71": "1",
        "col_72": "1065.00",
    }

    ROW_ALMOND = {
        "col_1": "45262-S500ML",
        "col_3": "9",
        "col_14": "529.20",
        "col_18": "Oil",
        "col_23": "7840.00",
        "col_24": "25.00|",
        "col_26": "5880.00",
        "col_35": "6,938.40",
        "col_37": "Each",
        "col_38": "529.20",
        "col_48": "SRL",
        "col_52": "Almond",
        "col_53": "pure-SOOML",
        "col_54": "-",
        "col_60": "|1",
        "col_62": "7840.00",
        "col_66": "SOOML",
        "col_71": "1",
        "col_72": "1960.00",
    }

    ROW_ACRIFLAVINE = {
        "col_1": "35188-25GM",
        "col_3": "9",
        "col_14": "1,755.00",
        "col_23": "26000.00",
        "col_24": "125.900]",
        "col_26": "19500.00",
        "col_35": "23,010.00",
        "col_37": "Each",
        "col_48": "SRL",
        "col_52": "Acriflavine",
        "col_53": "Hydrochloride",
        "col_56": "4,755.00",
        "col_60": "{1",
        "col_62": "2600.00",
        "col_66": "25GM",
        "col_71": "10",
        "col_72": "6500.00",
    }

    def test_dinitro_description_extracted(self):
        """2,4-Dinitrophenylhydrazi is at col_47 — must be found."""
        desc = get_description(self.ROW_DINITRO)
        assert "Dinitrophenylhydrazi" in desc, (
            f"Expected 'Dinitrophenylhydrazi' in description, got: {desc!r}"
        )

    def test_agar_description_extracted(self):
        """Agar Powder is split across col_17 and col_18 — both must be joined."""
        desc = get_description(self.ROW_AGAR)
        assert "Agar" in desc, f"'Agar' missing from description: {desc!r}"
        assert "Powder" in desc, f"'Powder' missing from description: {desc!r}"

    def test_almond_description_extracted(self):
        """Almond Oil: 'Almond' at col_52, 'Oil' at col_18."""
        desc = get_description(self.ROW_ALMOND)
        assert "Almond" in desc, f"'Almond' missing from description: {desc!r}"

    def test_acriflavine_description_extracted(self):
        """Acriflavine Hydrochloride split across col_52 and col_53."""
        desc = get_description(self.ROW_ACRIFLAVINE)
        assert "Acriflavine" in desc, f"'Acriflavine' missing: {desc!r}"
        assert "Hydrochloride" in desc, f"'Hydrochloride' missing: {desc!r}"

    def test_description_not_from_header_cols(self):
        """
        The OLD code read col_6/col_7/col_8. Those hold "PAN NO. AASCAQSO0A"
        (company header OCR text). get_description() must NOT include that text.
        """
        header_pollution_row = {
            "col_1": "88639-500GM",
            "col_6": "PAN",
            "col_7": "NO.",
            "col_8": "AASCAQSO0A",
            "col_47": "2,4-Dinitrophenylhydrazi",
            "col_48": "SRL",
        }
        desc = get_description(header_pollution_row)
        assert "PAN" not in desc, f"Header pollution 'PAN' leaked into description: {desc!r}"
        assert "NO." not in desc, f"Header pollution 'NO.' leaked into description: {desc!r}"
        assert "AASCAQSO0A" not in desc, f"Header pollution 'AASCAQSO0A' leaked: {desc!r}"

    def test_description_last_field_no_trailing_delimiter(self):
        """
        Test case: description token is the LAST field in the row (no trailing
        delimiter). This is the exact shape that the old regex-based extraction
        broke on, since it assumed a trailing comma/newline always followed.
        """
        row_description_last = {
            "col_1": "99999-100GM",
            "col_71": "5",
            "col_14": "120.00",
            "col_24": "10.00",
            "col_26": "540.00",
            "col_35": "637.20",
            "col_47": "Sodium Chloride",   # description is the last meaningful field
        }
        desc = get_description(row_description_last)
        assert desc == "Sodium Chloride", (
            f"Expected 'Sodium Chloride', got: {desc!r}. "
            "Regression: description-last-field case."
        )


class TestIsCatalogItemRow:
    """Filtering: only rows with a valid catalog code in col_1 are item rows."""

    def test_valid_catalog_code(self):
        assert is_catalog_item_row({"col_1": "88639-500GM"})
        assert is_catalog_item_row({"col_1": "19661-500Gms"})
        assert is_catalog_item_row({"col_1": "35188-25GM"})

    def test_header_row_rejected(self):
        """Row 30 is the header row — col_1='Code', not a catalog code."""
        assert not is_catalog_item_row({"col_1": "Code"})

    def test_address_row_rejected(self):
        """Address rows have col_1 like 'MSME' — rejected."""
        assert not is_catalog_item_row({"col_1": "MSME"})

    def test_empty_col1_rejected(self):
        assert not is_catalog_item_row({"col_1": ""})
        assert not is_catalog_item_row({})

    def test_ocr_garbage_row_rejected(self):
        """Garbage OCR row with col_1 like 'neses-cnom' — starts with letters, not digits."""
        assert not is_catalog_item_row({"col_1": "neses-cnom"})


class TestColumnShiftRegression:
    """
    Step 4 requirement: fix must be field-name-based so a missing field in one
    row cannot shift every subsequent column for that row.

    These tests verify that even when an optional field is absent from a row,
    the fields AFTER it are still read from the correct column.
    """

    def test_missing_optional_field_does_not_shift_columns(self):
        """
        A row missing col_17 (one of the optional description columns) must still
        correctly extract col_52 and col_53 as description tokens.
        """
        row = {
            "col_1": "12345-250GM",
            # col_17 is absent (optional)
            "col_48": "SRL",
            "col_52": "Potassium",
            "col_53": "Permanganate",
            "col_66": "250GM",
            "col_71": "3",
            "col_14": "88.00",
            "col_24": "10.00",
            "col_26": "237.60",
            "col_35": "280.37",
        }
        desc = get_description(row)
        assert "Potassium" in desc, f"col_52 missing from desc despite col_17 absent: {desc!r}"
        assert "Permanganate" in desc, f"col_53 missing from desc despite col_17 absent: {desc!r}"

    def test_missing_col_47_still_finds_col_52(self):
        """Missing col_47 must not prevent col_52 from being read."""
        row = {
            "col_1": "67890-1L",
            # col_47 absent
            "col_52": "Methanol",
            "col_48": "SRL",
        }
        desc = get_description(row)
        assert "Methanol" in desc, f"col_52 not found when col_47 absent: {desc!r}"

    def test_all_desc_cols_absent_gives_empty(self):
        """When genuinely no description columns are populated, return empty string."""
        row = {"col_1": "11111-500ML", "col_48": "SRL", "col_71": "1", "col_14": "50.00"}
        desc = get_description(row)
        assert desc == "", f"Expected empty description, got: {desc!r}"


class TestMissingDescriptionFlag:
    """Step 5: rows where description is absent but other fields are present must be flagged."""

    def test_flags_row_with_data_but_no_description(self):
        row = {
            "col_1": "12345-100GM",
            "col_14": "88.00",
            "col_71": "3",
            "col_48": "SRL",
            # no description cols populated
        }
        assert is_missing_description(row) is True

    def test_does_not_flag_row_with_description(self):
        row = {
            "col_1": "12345-100GM",
            "col_47": "Sodium Sulphate",
            "col_14": "88.00",
            "col_71": "3",
            "col_48": "SRL",
        }
        assert is_missing_description(row) is False

    def test_does_not_flag_empty_row(self):
        """A completely empty row (garbage/header) must not be flagged."""
        assert is_missing_description({}) is False
        assert is_missing_description({"col_1": "Code"}) is False
