import pytest
from pathlib import Path
import yaml
from app.schema_mapping.agent import load_mapping, map_fields, map_document, add_mapping_rule
from app.schema_mapping.exceptions import MappingNotFoundError, SchemaMappingError

def test_load_mapping_invoice():
    mapping = load_mapping('invoice')
    assert isinstance(mapping, dict)
    assert 'invoice_number' in mapping.values()

def test_load_mapping_unknown_type():
    with pytest.raises(MappingNotFoundError):
        load_mapping('nonexistent_xyz')

def test_map_fields_all_matched():
    row = {'invoice #': 'INV-001', 'bill to': 'ACME', 'total due': '500.00', '_normalization_warnings': []}
    res = map_fields(row, 'invoice')
    assert 'invoice_number' in res
    assert 'customer_name' in res
    assert 'total_amount' in res
    assert res['extras'] == {}
    assert res['_normalization_warnings'] == []

def test_map_fields_unmapped_to_extras():
    row = {'mystery_field': 'value'}
    res = map_fields(row, 'invoice')
    assert 'mystery_field' in res['extras']
    assert res['extras']['mystery_field'] == 'value'

def test_map_fields_case_insensitive():
    row = {'Invoice #': '123'}
    res = map_fields(row, 'invoice')
    assert 'invoice_number' in res

def test_map_fields_whitespace_tolerant():
    row = {'  invoice  #  ': '123'}
    res = map_fields(row, 'invoice')
    assert 'invoice_number' in res

def test_map_fields_preserves_warnings():
    row = {'_normalization_warnings': ['bad field']}
    res = map_fields(row, 'invoice')
    assert res['_normalization_warnings'] == ['bad field']

def test_add_mapping_rule(tmp_path, monkeypatch):
    import app.schema_mapping.agent as agent_module
    
    test_yaml = tmp_path / "test_mappings.yaml"
    initial_data = {'invoice': {'test field': 'test_col'}}
    with open(test_yaml, "w") as f:
        yaml.dump(initial_data, f)
        
    monkeypatch.setattr(agent_module, "FIELD_MAPPINGS_PATH", str(test_yaml))
    agent_module._mappings_cache = None
    
    add_mapping_rule('invoice', 'ref no', 'reference_number')
    
    with open(test_yaml, "r") as f:
        data = yaml.safe_load(f)
    assert data['invoice']['ref no'] == 'reference_number'
    
    mapping = load_mapping('invoice')
    assert mapping['ref no'] == 'reference_number'

def test_map_document_multiple_rows():
    rows = [{'Invoice #': '1'}, {'Invoice #': '2'}, {'Invoice #': '3'}]
    res = map_document('doc1', rows, 'invoice')
    assert len(res) == 3
