"""
Orchestrator Agent — drives documents through the complete processing pipeline stage by
stage. This is the ONLY module that imports from all other agents. It is the single
entry point for any external caller (API endpoint, CLI, scheduled job) to run the pipeline.
"""

import json
import logging
from pathlib import Path
from statistics import mean
from typing import Optional

from app.orchestrator.exceptions import OrchestratorError, DocumentNotFoundError
from app.orchestrator.models import PipelineStage, ProcessingOutcome

logger = logging.getLogger(__name__)


def _persist():
    from app.persistence import agent as _a
    return _a


def _classify():
    from app.classification import agent as _a
    return _a


def _get_last_completed_stage(document_id: str) -> Optional[PipelineStage]:
    """Get the last successfully completed pipeline stage for a document."""
    status_history = _persist().get_processing_status(document_id)
    # Find the last row where status == 'success'
    for row in reversed(status_history):
        if row.get('status') == 'success':
            try:
                return PipelineStage(row.get('stage'))
            except ValueError:
                continue
    return None


def process_document(document_id: str) -> ProcessingOutcome:
    """Run the full processing pipeline for a single document."""
    column_types = {}
    
    def _handle_failure(stage: PipelineStage, exc: Exception) -> ProcessingOutcome:
        error_msg = str(exc)
        logger.error(f"Error in {stage.value} for {document_id}: {error_msg}", exc_info=True)
        _persist().log_stage(document_id, stage, 'error', error_msg)
        _persist().update_queue_status(document_id, 'failed')
        return ProcessingOutcome(document_id, PipelineStage.FAILED, False, error_msg)

    # a) LOAD DOCUMENT
    get_q_fn = getattr(_persist(), 'get_queue_item', None)
    doc_info = None
    if callable(get_q_fn):
        res = get_q_fn(document_id)
        if isinstance(res, dict):
            doc_info = res
    if not doc_info:
        docs = _persist().get_next_queued_documents(batch_size=100)
        doc_info = next((d for d in docs if d.get('document_id') == document_id), None)
    
    if not doc_info:
        raise DocumentNotFoundError(f"Document {document_id} not found in the processing queue.")
    
    file_type = doc_info['file_type']
    file_path = doc_info['file_path']
    _persist().update_queue_status(document_id, 'processing')
    _persist().log_stage(document_id, PipelineStage.QUEUED, 'success', 'Processing started')

    # b) CLASSIFICATION STAGE
    document_type = None
    try:
        text_sample = ''
        if file_type == 'pdf':
            from app.preprocessing.agent import pdf_to_page_images, preprocess_page
            from app.ocr.agent import run_ocr_on_document
            # Fast scan: convert ONLY page 1 for classification
            pages = pdf_to_page_images(Path(file_path), first_page=1, last_page=1)
            if pages:
                cleaned = [preprocess_page(pages[0], document_id)]
                ocr_results = run_ocr_on_document(document_id, cleaned)
                text_sample = ocr_results[0].full_text if ocr_results else ''
                
        result = _classify().classify_document(document_id, Path(file_path), file_type, text_sample)
        document_type = result.document_type
        
        _persist().update_queue_status(document_id, 'processing', document_type, result.confidence)
        _persist().log_stage(document_id, PipelineStage.CLASSIFIED, 'success', f'{document_type} ({result.confidence:.2f})')
    except Exception as e:
        return _handle_failure(PipelineStage.CLASSIFIED, e)

    # c) EXTRACTION STAGE
    raw_rows = []
    avg_ocr_confidence = None
    try:
        if file_type == 'pdf':
            from concurrent.futures import ThreadPoolExecutor
            from app.preprocessing.agent import pdf_to_page_images, preprocess_page
            from app.ocr.agent import run_ocr_on_document, get_document_text
            from app.table_detection.agent import extract_tables_from_page
            
            pages = pdf_to_page_images(Path(file_path))

            def _process_page_worker(item):
                page_num, page_img = item
                cleaned = preprocess_page(page_img, document_id)
                ocr_res = run_ocr_on_document(document_id, [cleaned])[0]
                tables = extract_tables_from_page(document_id, page_num, cleaned, ocr_res)
                p_rows = []
                for table in tables:
                    for row in table[1:]:
                        p_rows.append({f'col_{i}': cell for i, cell in enumerate(row)})
                return page_num, cleaned, ocr_res, p_rows

            with ThreadPoolExecutor(max_workers=min(8, max(1, len(pages)))) as executor:
                page_results = list(executor.map(_process_page_worker, enumerate(pages)))

            page_results.sort(key=lambda x: x[0])
            cleaned_pages = [r[1] for r in page_results]
            ocr_results = [r[2] for r in page_results]
            for r in page_results:
                raw_rows.extend(r[3])

            avg_ocr_confidence = mean([r.page_confidence for r in ocr_results]) if ocr_results else 0.0

            if not raw_rows:
                full_text = get_document_text(ocr_results)
                raw_rows = [{'text': line} for line in full_text.split('\n') if line.strip()]
                
            raw_data = {'rows': raw_rows, 'file_type': 'pdf', 'ocr_text': get_document_text(ocr_results)}
            
        elif file_type in ('xlsx', 'xls', 'csv'):
            from app.excel_extraction.agent import extract_excel_document, infer_column_types
            sheets = extract_excel_document(document_id, Path(file_path))
            for sheet_name, rows in sheets.items():
                raw_rows.extend(rows)
                if rows:
                    column_types.update(infer_column_types(rows))
            raw_data = {'rows': raw_rows, 'file_type': file_type, 'sheets': list(sheets.keys())}
        else:
            raw_data = {'rows': [], 'file_type': file_type}

        _persist().save_raw_document(
            document_id, doc_info['file_hash'], Path(file_path).name, file_type, document_type, raw_data
        )
        _persist().log_stage(document_id, PipelineStage.EXTRACTED, 'success', f'{len(raw_rows)} rows')
    except Exception as e:
        return _handle_failure(PipelineStage.EXTRACTED, e)

    # d) NORMALIZATION STAGE
    try:
        from app.normalization.agent import normalize_document
        normalized_rows = normalize_document(document_id, raw_rows, column_types)
        _persist().log_stage(document_id, PipelineStage.NORMALIZED, 'success')
    except Exception as e:
        return _handle_failure(PipelineStage.NORMALIZED, e)

    # e) SCHEMA MAPPING STAGE
    try:
        from app.schema_mapping.agent import map_document
        mapped_rows = map_document(document_id, normalized_rows, document_type)
        _persist().log_stage(document_id, PipelineStage.MAPPED, 'success')
    except Exception as e:
        return _handle_failure(PipelineStage.MAPPED, e)

    # f) VALIDATION + PERSISTENCE STAGE
    try:
        from app.validation.agent import validate_document
        results = validate_document(document_id, mapped_rows, document_type, avg_ocr_confidence)
        
        accepted = 0
        quarantined = 0
        for routing, record_or_q in results:
            if routing == 'accept':
                record_dict = record_or_q if isinstance(record_or_q, dict) else (
                    record_or_q.model_dump() if hasattr(record_or_q, 'model_dump') else dict(record_or_q)
                )
                _persist().save_record(document_id, document_type, record_dict)
                accepted += 1
            else:
                _persist().save_to_quarantine(
                    document_id, 
                    document_type, 
                    record_or_q.get('record', {}), 
                    record_or_q.get('reasons', [])
                )
                quarantined += 1
                
        _persist().log_stage(document_id, PipelineStage.VALIDATED, 'success')
        
        final_stage = PipelineStage.DONE if accepted > 0 else PipelineStage.QUARANTINED
        _persist().log_stage(document_id, final_stage, 'success')
        _persist().update_queue_status(document_id, 'done')
        
        return ProcessingOutcome(
            document_id=document_id, 
            final_stage=final_stage, 
            success=True, 
            accepted_count=accepted, 
            quarantined_count=quarantined
        )
    except Exception as e:
        return _handle_failure(PipelineStage.VALIDATED, e)


def retry_failed_document(document_id: str) -> ProcessingOutcome:
    """Retry processing a failed document from scratch."""
    last_stage = _get_last_completed_stage(document_id)
    if not last_stage or last_stage == PipelineStage.QUEUED:
        logger.info(f"Retrying document {document_id} from scratch (no significant past progress).")
    else:
        logger.info(f"Retrying from after {last_stage.value} for document {document_id}")
    
    logger.info(f"Initiating retry for {document_id}")
    return process_document(document_id)


def process_queue(batch_size: int = 10) -> list[ProcessingOutcome]:
    """Process a batch of documents from the queue."""
    docs = _persist().get_next_queued_documents(batch_size)
    outcomes = []
    
    for doc in docs:
        outcome = process_document(doc['document_id'])
        outcomes.append(outcome)
        
    success = sum(1 for o in outcomes if o.success and o.final_stage == PipelineStage.DONE)
    quarantined = sum(1 for o in outcomes if o.final_stage == PipelineStage.QUARANTINED)
    failed = sum(1 for o in outcomes if o.final_stage == PipelineStage.FAILED)
    
    logger.info('Batch complete: %d succeeded, %d quarantined, %d failed', success, quarantined, failed)
    
    return outcomes
