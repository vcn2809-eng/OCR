import pytest
from unittest.mock import patch, MagicMock, call
from app.orchestrator.agent import process_document, process_queue, retry_failed_document
from app.orchestrator.models import PipelineStage, ProcessingOutcome
from app.orchestrator.exceptions import DocumentNotFoundError

@patch('app.orchestrator.agent._persist')
def test_process_document_not_found(mock_persist):
    # Mock empty queue
    mock_persist.return_value.get_next_queued_documents.return_value = []
    
    with pytest.raises(DocumentNotFoundError):
        process_document('doc_missing')


@patch('app.orchestrator.agent._persist')
@patch('app.orchestrator.agent._classify')
@patch('app.preprocessing.agent.pdf_to_page_images', create=True)
@patch('app.preprocessing.agent.preprocess_page', create=True)
@patch('app.ocr.agent.run_ocr_on_document', create=True)
@patch('app.table_detection.agent.extract_tables_from_page', create=True)
@patch('app.normalization.agent.normalize_document', create=True)
@patch('app.schema_mapping.agent.map_document', create=True)
@patch('app.validation.agent.validate_document', create=True)
def test_process_document_full_success(
    mock_validate, mock_map, mock_normalize, mock_extract, mock_ocr,
    mock_preprocess, mock_pdf_to_images, mock_classify, mock_persist
):
    mock_persist.return_value.get_next_queued_documents.return_value = [
        {'document_id': 'doc1', 'file_path': '/tmp/test.pdf', 'file_hash': 'abc', 'file_type': 'pdf', 'status': 'queued'}
    ]
    import numpy as np
    mock_pdf_to_images.return_value = [np.zeros((100, 100, 3), dtype=np.uint8)]
    mock_preprocess.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    
    mock_ocr_result = MagicMock()
    mock_ocr_result.full_text = 'invoice total due'
    mock_ocr_result.words = []
    mock_ocr_result.page_confidence = 0.8
    mock_ocr_result.page_number = 0
    mock_ocr.return_value = [mock_ocr_result]
    
    mock_classify_result = MagicMock()
    mock_classify_result.document_type = 'invoice'
    mock_classify_result.confidence = 0.9
    mock_classify.return_value.classify_document.return_value = mock_classify_result
    
    mock_extract.return_value = []
    mock_normalize.return_value = [{}]
    mock_map.return_value = [{}]
    mock_validate.return_value = [('accept', {})]
    
    outcome = process_document('doc1')
    
    assert outcome.success is True
    assert outcome.final_stage == PipelineStage.DONE
    assert outcome.accepted_count == 1
    assert outcome.quarantined_count == 0


@patch('app.orchestrator.agent._persist')
@patch('app.orchestrator.agent._classify')
@patch('app.preprocessing.agent.pdf_to_page_images', create=True)
@patch('app.preprocessing.agent.preprocess_page', create=True)
@patch('app.ocr.agent.run_ocr_on_document', create=True)
def test_process_document_ocr_fails(
    mock_ocr, mock_preprocess, mock_pdf_to_images, mock_classify, mock_persist
):
    mock_persist.return_value.get_next_queued_documents.return_value = [
        {'document_id': 'doc2', 'file_path': '/tmp/test2.pdf', 'file_hash': 'def', 'file_type': 'pdf', 'status': 'queued'}
    ]
    import numpy as np
    mock_pdf_to_images.return_value = [np.zeros((100, 100, 3), dtype=np.uint8)]
    mock_preprocess.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
    
    mock_ocr.side_effect = Exception("OCRFailureError")
    
    outcome = process_document('doc2')
    
    assert outcome.success is False
    assert outcome.final_stage == PipelineStage.FAILED


@patch('app.orchestrator.agent._persist')
@patch('app.orchestrator.agent.process_document')
def test_process_queue_calls_each_doc(mock_process_doc, mock_persist):
    mock_persist.return_value.get_next_queued_documents.return_value = [
        {'document_id': 'doc1'},
        {'document_id': 'doc2'}
    ]
    
    mock_process_doc.return_value = ProcessingOutcome('doc', PipelineStage.DONE, True)
    
    outcomes = process_queue(batch_size=2)
    
    assert len(outcomes) == 2
    assert mock_process_doc.call_count == 2
    mock_process_doc.assert_has_calls([call('doc1'), call('doc2')])


@patch('app.orchestrator.agent._get_last_completed_stage')
@patch('app.orchestrator.agent.process_document')
def test_retry_failed_document(mock_process_doc, mock_get_last_stage):
    mock_get_last_stage.return_value = PipelineStage.CLASSIFIED
    mock_process_doc.return_value = ProcessingOutcome('doc1', PipelineStage.DONE, True)
    
    outcome = retry_failed_document('doc1')
    
    mock_process_doc.assert_called_once_with('doc1')
    assert outcome.success is True


@patch('app.orchestrator.agent._persist')
@patch('app.orchestrator.agent.process_document')
def test_process_queue_logs_summary(mock_process_doc, mock_persist, caplog):
    import logging
    mock_persist.return_value.get_next_queued_documents.return_value = [
        {'document_id': 'doc1'},
        {'document_id': 'doc2'}
    ]
    
    mock_process_doc.side_effect = [
        ProcessingOutcome('doc1', PipelineStage.DONE, True),
        ProcessingOutcome('doc2', PipelineStage.FAILED, False)
    ]
    
    with caplog.at_level(logging.INFO, logger='app.orchestrator.agent'):
        process_queue(batch_size=2)
    
    assert "Batch complete" in caplog.text
