import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# We need to mock init_db before importing app to avoid DB creation during tests
with patch('app.persistence.database.init_db', return_value=None):
    from app.api.main import app

client = TestClient(app, raise_server_exceptions=False)

def test_health_endpoint():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'

@patch('app.ingestion.agent.compute_file_hash', return_value='abc123')
@patch('app.ingestion.agent.detect_true_file_type', return_value='pdf')
@patch('app.ingestion.agent.enqueue_file', return_value='doc-uuid-001')
@patch('app.orchestrator.agent.process_document', return_value=None)
def test_upload_pdf_success(mock_process, mock_enqueue, mock_detect, mock_hash):
    response = client.post(
        '/documents/upload',
        files={'file': ('test.pdf', b'%PDF-1.4', 'application/pdf')}
    )
    assert response.status_code == 200
    assert response.json()['document_id'] == 'doc-uuid-001'

@patch('app.ingestion.agent.compute_file_hash', return_value='abc')
@patch('app.ingestion.agent.detect_true_file_type', return_value='unknown')
def test_upload_unsupported_type(mock_detect, mock_hash):
    response = client.post(
        '/documents/upload',
        files={'file': ('test.exe', b'EXE-DATA', 'application/x-msdownload')}
    )
    assert response.status_code == 400

@patch('app.persistence.agent.get_processing_status', return_value=[{'stage': 'CLASSIFIED', 'status': 'success', 'message': '', 'timestamp': '2024-01-01'}])
def test_get_status_found(mock_get_status):
    response = client.get('/documents/doc-123/status')
    assert response.status_code == 200
    assert response.json()['current_stage'] == 'CLASSIFIED'

@patch('app.persistence.agent.get_processing_status', return_value=[])
def test_get_status_not_found(mock_get_status):
    response = client.get('/documents/nonexistent/status')
    assert response.status_code == 404

@patch('app.persistence.db.get_document_with_fields', return_value={'document_id': 'doc-123', 'status': 'done', 'fields': {'invoice_number': 'INV-001'}})
def test_get_document_done(mock_get_doc):
    response = client.get('/documents/doc-123')
    assert response.status_code == 200
    assert response.json()['status'] == 'done'
    assert response.json()['fields'] is not None

@patch('app.persistence.db.get_document_with_fields', return_value={'document_id': 'doc-123', 'status': 'processing', 'fields': {}})
def test_get_document_processing(mock_get_doc):
    response = client.get('/documents/doc-123')
    assert response.status_code == 200
    assert response.json()['status'] == 'processing'

@patch('app.persistence.db.list_documents', return_value=[{'document_id': 'doc1', 'original_filename': 'test.pdf', 'file_type': 'pdf', 'document_type': 'invoice', 'uploaded_at': '2024-01-01', 'status': 'stored'}])
@patch('app.persistence.database.get_db_session')
def test_list_documents(mock_get_db_session, mock_list_docs):
    mock_session = MagicMock()
    mock_session.execute.return_value.scalar.return_value = 1
    mock_get_db_session.return_value.__enter__.return_value = mock_session

    response = client.get('/documents?page=1&page_size=10')
    assert response.status_code == 200
    assert len(response.json()['items']) == 1




@patch('app.persistence.agent.get_quarantine_items', return_value=[{'id': 1, 'document_id': 'doc1', 'document_type': 'invoice', 'record_json': '{"invoice_number": "INV-001"}', 'reasons': '["low confidence"]', 'flagged_at': '2024-01-01', 'reviewed': False}])
def test_get_quarantine(mock_get_quarantine):
    response = client.get('/quarantine')
    assert response.status_code == 200
    assert len(response.json()['items']) == 1
    assert response.json()['items'][0]['reasons'] == ['low confidence']

@patch('app.persistence.agent.resolve_quarantine_item', return_value=None)
def test_resolve_quarantine_accept(mock_resolve):
    response = client.post(
        '/quarantine/1/resolve',
        json={'action': 'accept', 'corrected_record': {'invoice_number': 'INV-001'}}
    )
    assert response.status_code == 200
    assert response.json()['action'] == 'accept'

def test_resolve_quarantine_invalid_action():
    response = client.post(
        '/quarantine/1/resolve',
        json={'action': 'fly_away'}
    )
    assert response.status_code == 400

def test_resolve_quarantine_accept_without_record():
    response = client.post(
        '/quarantine/1/resolve',
        json={'action': 'accept'}
    )
    assert response.status_code == 422


def test_learn_alias_endpoint():
    with patch('app.learning.agent.learn_alias') as mock_learn:
        from app.learning.models import AliasMapping
        mock_learn.return_value = AliasMapping(alias='mtrl', canonical_name='materials', category='header')
        
        response = client.post(
            '/aliases/learn',
            json={'alias': 'mtrl', 'canonical_name': 'materials'}
        )
        assert response.status_code == 200
        assert response.json()['alias'] == 'mtrl'
        assert response.json()['canonical_name'] == 'materials'


def test_list_aliases_endpoint():
    with patch('app.learning.agent.get_all_learned_aliases') as mock_get:
        mock_get.return_value = [
            {'alias': 'mtrl', 'canonical_name': 'materials', 'category': 'header', 'confidence': 1.0, 'occurrence_count': 1}
        ]
        
        response = client.get('/aliases')
        assert response.status_code == 200
        assert response.json()['total'] == 1
        assert response.json()['items'][0]['alias'] == 'mtrl'


def test_get_document_rows_endpoint():
    class MockGenericRecord:
        def __init__(self, id, doc_id, record_json):
            self.id = id
            self.document_id = doc_id
            self.record_json = record_json

    rec1 = MockGenericRecord(1, "doc-123", '{"extras": {"col_1": "88639-500GM", "col_47": "2,4-Dinitrophenylhydrazi"}}')
    rec2 = MockGenericRecord(2, "doc-123", '{"extras": {"col_1": "19661-500Gms", "col_47": "Agar Powder"}}')

    with patch('app.persistence.database.get_db_session') as mock_get_db_session:
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = [rec1, rec2]

        mock_session.query.return_value = mock_query
        mock_session.get_bind.return_value.dialect.name = 'sqlite'
        mock_get_db_session.return_value.__enter__.return_value = mock_session

        # Simple get rows
        response = client.get('/documents/doc-123/rows')
        assert response.status_code == 200
        assert len(response.json()) == 2
        assert response.json()[0]['col_1'] == "88639-500GM"

        # Search query
        response = client.get('/documents/doc-123/rows?q=agar')
        assert response.status_code == 200

        # Search column
        response = client.get('/documents/doc-123/rows?q=agar&column=col_47')
        assert response.status_code == 200
