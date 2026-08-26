import pytest
from datetime import date
from decimal import Decimal
from app.normalization.agent import (
    clean_text, normalize_date, normalize_currency, normalize_number, normalize_row
)


def test_normalize_date_iso():
    assert normalize_date('2024-01-15') == date(2024, 1, 15)


def test_normalize_date_us_format():
    assert normalize_date('01/15/2024') == date(2024, 1, 15)


def test_normalize_date_written():
    assert normalize_date('January 15, 2024') == date(2024, 1, 15)


def test_normalize_date_invalid():
    assert normalize_date('not a date') is None


def test_normalize_date_empty():
    assert normalize_date('') is None


def test_normalize_date_na():
    assert normalize_date('n/a') is None


def test_normalize_currency_usd():
    assert normalize_currency('$1,234.56') == Decimal('1234.56')


def test_normalize_currency_euro_symbol():
    assert normalize_currency('€500.00') == Decimal('500.00')


def test_normalize_currency_invalid():
    assert normalize_currency('not money') is None


def test_normalize_number_with_commas():
    assert normalize_number('1,234,567.89') == 1234567.89


def test_normalize_number_invalid():
    assert normalize_number('abc') is None


def test_clean_text_strips_whitespace():
    assert clean_text('  hello   world  ') == 'hello world'


def test_clean_text_none_input():
    assert clean_text(None) == ''


def test_normalize_row_mixed_types():
    row = {
        'invoice_date': '01/15/2024',
        'total_amount': '$500.00',
        'invoice_number': 'INV-001',
        'quantity': '5'
    }
    column_types = {
        'invoice_date': 'date',
        'total_amount': 'currency',
        'invoice_number': 'text',
        'quantity': 'number'
    }
    
    result = normalize_row(row, column_types)
    
    assert result['invoice_date'] == '2024-01-15'
    assert result['total_amount'] == '500.00'
    assert result['invoice_number'] == 'INV-001'
    assert result['quantity'] == 5.0
    assert result['_normalization_warnings'] == []


def test_normalize_row_bad_field_kept_with_warning():
    row = {
        'invoice_date': 'NOT A DATE',
        'total_amount': '$100.00'
    }
    column_types = {
        'invoice_date': 'date',
        'total_amount': 'currency'
    }
    
    result = normalize_row(row, column_types)
    
    assert result['invoice_date'] == 'NOT A DATE'
    assert result['total_amount'] == '100.00'
    assert len(result['_normalization_warnings']) > 0
    assert any('invoice_date' in w for w in result['_normalization_warnings'])


def test_normalize_row_unknown_field_defaults_to_text():
    row = {'mystery': 'hello world  '}
    
    result = normalize_row(row, {})
    
    assert result['mystery'] == 'hello world'
