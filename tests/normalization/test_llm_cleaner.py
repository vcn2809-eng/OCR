import json
from unittest.mock import patch, MagicMock
import pytest
from app.normalization.llm_cleaner import map_llm_keys, clean_rows_with_llm, is_ollama_available


def test_map_llm_keys_success():
    llm_row = {
        "item_code": "88639-500GM",
        "description": "2,4-Dinitrophenylhydrazi",
        "brand": "SRL",
        "pack": "5OOGM",
        "qty": "1",
        "rate": "3800.00",
        "disc": "25.00/",
        "taxable": "2850.00",
        "final_value": "3,363.00",
    }

    mapped = map_llm_keys(llm_row)

    # Standard canonical schema keys
    assert mapped["Item Code"] == "88639-500GM"
    assert mapped["Description"] == "2,4-Dinitrophenylhydrazi"
    assert mapped["Brand"] == "SRL"
    assert mapped["Packing"] == "5OOGM"
    assert mapped["Qty"] == "1"
    assert mapped["Rate"] == "3800.00"
    assert mapped["Disc %"] == "25.00/"
    assert mapped["Taxable"] == "2850.00"
    assert mapped["Final Value"] == "3,363.00"

    # col_X keys for UI compatibility
    assert mapped["col_1"] == "88639-500GM"
    assert mapped["col_47"] == "2,4-Dinitrophenylhydrazi"
    assert mapped["col_48"] == "SRL"
    assert mapped["col_66"] == "5OOGM"
    assert mapped["col_71"] == "1"
    assert mapped["col_14"] == "3800.00"
    assert mapped["col_24"] == "25.00/"
    assert mapped["col_26"] == "2850.00"
    assert mapped["col_35"] == "3,363.00"

    assert mapped["_normalization_warnings"] == []


@patch("app.normalization.llm_cleaner.is_ollama_available", return_value=False)
def test_clean_rows_with_llm_offline_fallback(mock_avail):
    rows = [
        {"col_1": "88639-500GM", "col_14": "3800.00"},
        {"col_1": "19661-500Gms", "col_14": "4260.00"},
    ]
    column_types = {"col_14": "currency"}

    res = clean_rows_with_llm(rows, column_types)

    # Should run regular normalization
    assert len(res) == 2
    assert res[0]["col_1"] == "88639-500GM"
    assert res[0]["col_14"] == "3800.00"  # normalized to decimal string by standard normalizer
    assert res[1]["col_14"] == "4260.00"


@patch("app.normalization.llm_cleaner.is_ollama_available", return_value=True)
@patch("app.normalization.llm_cleaner.call_ollama")
def test_clean_rows_with_llm_success(mock_call, mock_avail):
    rows = [
        {"col_1": "88639-500GM", "col_14": "3800.00", "col_48": "SRL"},
    ]
    column_types = {}

    mock_response = json.dumps([
        {
            "Item Code": "88639-500GM",
            "Description": "2,4-Dinitrophenylhydrazi",
            "Brand": "SRL",
            "Packing": "500GM",
            "Qty": "1",
            "Rate": "3800.00",
            "Disc %": "25.00",
            "Taxable": "2850.00",
            "Final Value": "3363.00",
        }
    ])
    mock_call.return_value = mock_response

    res = clean_rows_with_llm(rows, column_types)

    assert len(res) == 1
    assert res[0]["Item Code"] == "88639-500GM"
    assert res[0]["Brand"] == "SRL"
    assert res[0]["Packing"] == "500GM"
    assert res[0]["col_48"] == "SRL"
    assert res[0]["col_66"] == "500GM"


@patch("app.normalization.llm_cleaner.is_ollama_available", return_value=True)
@patch("app.normalization.llm_cleaner.call_ollama", side_effect=Exception("Ollama busy"))
def test_clean_rows_with_llm_error_fallback(mock_call, mock_avail):
    rows = [
        {"col_1": "88639-500GM", "col_14": "3800.00"},
    ]
    column_types = {"col_14": "currency"}

    res = clean_rows_with_llm(rows, column_types)

    # Should fall back to standard normalizer
    assert len(res) == 1
    assert res[0]["col_1"] == "88639-500GM"
    assert res[0]["col_14"] == "3800.00"
