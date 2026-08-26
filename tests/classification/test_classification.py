import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import openpyxl

from app.classification.agent import (
    classify_with_heuristics, classify_with_llm, classify_excel, classify_document,
    load_classification_rules, _rules_cache
)
from app.classification.models import ClassificationResult
from app.classification.exceptions import ClassificationError, LLMClassificationError

@pytest.fixture(autouse=True)
def clear_rules_cache():
    import app.classification.agent
    app.classification.agent._rules_cache = None
    yield
    app.classification.agent._rules_cache = None

def test_classify_clear_invoice_text():
    text = "Here is the invoice for the services. Bill To: John Doe. Total Due is 500. Payment Terms: net 30."
    result = classify_with_heuristics(text)
    assert result.document_type == 'invoice'
    assert result.confidence >= 0.2
    assert result.method == 'heuristic'

def test_classify_clear_resume_text():
    text = "Work experience: 10 years. Education: BSc Computer Science. Skills: Python, Java."
    result = classify_with_heuristics(text)
    assert result.document_type == 'resume'
    assert result.confidence >= 0.3
    assert result.method == 'heuristic'

def test_classify_ambiguous_text():
    text = "hello world nothing relevant"
    result = classify_with_heuristics(text)
    assert result.document_type == 'generic'
    assert result.confidence == 0.0
    assert result.method == 'heuristic'

def test_classify_with_llm_mocked(monkeypatch):
    monkeypatch.setattr('app.classification.agent.settings.OPENAI_API_KEY', 'fake_key')
    monkeypatch.setattr('app.classification.agent.settings.OPENAI_MODEL', 'gpt-4o-mini')
    
    # openai.OpenAI is imported lazily inside classify_with_llm, so patch at source
    with patch('openai.OpenAI') as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '{"document_type":"invoice","confidence":0.95}'
        mock_client.chat.completions.create.return_value = mock_response
        
        result = classify_with_llm("some text")
        
        assert result.document_type == 'invoice'
        assert result.confidence == 0.95
        assert result.method == 'llm_fallback'

def test_classify_llm_no_api_key(monkeypatch):
    monkeypatch.setattr('app.classification.agent.settings.OPENAI_API_KEY', '')
    with pytest.raises(LLMClassificationError, match="No OpenAI API key configured"):
        classify_with_llm("test text")

def test_classify_excel_invoice_headers(tmp_path):
    excel_path = tmp_path / "test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Invoice #", "Bill To", "Total Due"])
    wb.save(excel_path)
    
    with patch('app.classification.agent.settings') as mock_settings:
        mock_settings.CLASSIFICATION_RULES_PATH = Path("/Users/vishnucharan/nissigrid/app/config/classification_rules.yaml")
        mock_settings.CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.6
        mock_settings.OPENAI_API_KEY = "" # ensure no LLM fallback
        
        result = classify_excel(excel_path)
        assert result.document_type == 'invoice'
        assert result.confidence > 0.0
        assert result.method == 'heuristic'

def test_classify_document_pdf_heuristic():
    import app.classification.agent
    app.classification.agent._rules_cache = None
    text = "Here is the invoice. Bill To: Jane. Total Due 100. Payment Terms: net 30. Subtotal: 90."
    with patch('app.classification.agent.settings') as mock_settings:
        mock_settings.CLASSIFICATION_RULES_PATH = Path("/Users/vishnucharan/nissigrid/app/config/classification_rules.yaml")
        mock_settings.CLASSIFICATION_CONFIDENCE_THRESHOLD = 0.1 # Very low so it won't fallback
        mock_settings.OPENAI_API_KEY = ""
        
        result = classify_document("doc123", Path("fake.pdf"), "pdf", text)
        assert result.document_type == 'invoice'
        assert result.method == 'heuristic'

def test_classify_document_csv_returns_generic():
    result = classify_document("doc123", Path("fake.csv"), "csv", "")
    assert result.document_type == 'generic'
    assert result.confidence == 0.5
    assert result.method == 'heuristic'
