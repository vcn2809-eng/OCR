"""
API Layer — thin FastAPI wrapper exposing the PDF/Excel scanner pipeline to a future frontend.
Contains NO business logic; all calls delegate to Orchestrator or Persistence agents.

TODO: Add authentication/authorisation before exposing this publicly.
TODO: Restrict CORS allow_origins to the actual frontend domain once known.
"""
from typing import Any
import json
import logging
from pathlib import Path
from uuid import uuid4

from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.api.models import (
    DocumentList, DocumentListItem, DocumentRecord, DocumentStatus,
    HealthResponse, QuarantineItem, QuarantineList,
    QuarantineResolveRequest, QuarantineResolveResponse, UploadResponse,
    LearnAliasRequest, LearnAliasResponse, AliasListResponse, AliasItem,
    VendorCreateRequest, VendorCreateResponse, VendorListItem, VendorDetailResponse,
)

from app.config.settings import INPUT_FOLDER

logger = logging.getLogger(__name__)

app = FastAPI(
    title='PDF/Excel Scanner API',
    version='1.0.0',
    description='Backend pipeline for ingesting and extracting structured data from PDF and Excel files.',
)

# TODO: Restrict allow_origins to the actual frontend domain before public deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


@app.on_event('startup')
async def startup_event() -> None:
    """Initialise the database and ensure the input folder exists on startup."""
    from app.persistence.database import init_db
    init_db()
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    logger.info('API started. DB initialised. Input folder: %s', INPUT_FOLDER)


@app.get('/health', response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint for load balancers and uptime monitors."""
    return HealthResponse(status='ok', version='1.0.0')


@app.get('/stats')
async def get_stats() -> dict[str, Any]:
    """Return aggregated dashboard statistics: total_documents, by_type breakdown, quarantined_count, and recent_documents."""
    from app.persistence.database import get_db_session
    from app.persistence.models import Document, Quarantine
    from app.persistence.db import list_documents
    from sqlalchemy import select, func

    try:
        with get_db_session() as session:
            total = session.execute(select(func.count()).select_from(Document)).scalar() or 0
            quarantined_count = session.execute(
                select(func.count()).select_from(Quarantine).where(Quarantine.reviewed == False)
            ).scalar() or 0

            # Count by document_type
            by_type_rows = session.execute(
                select(Document.document_type, func.count()).group_by(Document.document_type)
            ).all()
            by_type = { (row[0] or 'generic'): row[1] for row in by_type_rows }
    except Exception as exc:
        logger.warning('Stats DB query failed: %s', exc)
        total, quarantined_count, by_type = 0, 0, {}

    try:
        recent = list_documents(limit=5)
    except Exception:
        recent = []

    return {
        'total_documents': total,
        'by_type': by_type,
        'quarantined_count': quarantined_count,
        'quarantine': quarantined_count,
        'processed': total - quarantined_count,
        'recent_documents': recent,
    }



@app.post('/aliases/resolve')
async def resolve_alias_endpoint(body: dict[str, str]) -> dict[str, Any]:
    """Resolve a raw field name or abbreviation to its canonical name using the Learning Agent."""
    from app.learning.agent import resolve_alias

    text = (body.get('text') or '').strip()
    if not text:
        raise HTTPException(status_code=422, detail='Field \'text\' is required.')

    result = resolve_alias(text)
    if result is None:
        return {
            'input': text,
            'canonical': text,
            'match_type': 'no_match',
            'confidence': 0.0,
            'category': None,
        }
    return {
        'input': text,
        'canonical': result.canonical_name,
        'match_type': result.match_type,
        'confidence': result.similarity_score,
        'category': result.category,
    }


@app.post('/documents/upload', response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadResponse:
    """Accept a file upload, enqueue it, and trigger pipeline processing in the background."""
    from app.ingestion.agent import compute_file_hash, detect_true_file_type, enqueue_file
    from app.orchestrator.agent import process_document

    try:
        # Save to input folder with UUID prefix to avoid collisions
        safe_name = f'{uuid4()}_{file.filename}'
        save_path = INPUT_FOLDER / safe_name
        contents = await file.read()
        save_path.write_bytes(contents)

        file_hash = compute_file_hash(save_path)
        file_type = detect_true_file_type(save_path)

        if file_type == 'unknown':
            save_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail='Unsupported file type detected.')

        document_id = enqueue_file(save_path, file_hash, file_type)
        background_tasks.add_task(process_document, document_id)

        return UploadResponse(
            document_id=document_id,
            filename=file.filename or safe_name,
            file_type=file_type,
            message='File uploaded and queued for processing.',
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error('Upload failed: %s', exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/documents/{document_id}/status', response_model=DocumentStatus)
async def get_document_status(document_id: str) -> DocumentStatus:
    """Return the current pipeline stage and all stage history for a document."""
    from app.persistence.agent import get_processing_status

    stages = get_processing_status(document_id)
    if not stages:
        raise HTTPException(status_code=404, detail='Document not found.')

    latest = stages[-1]
    return DocumentStatus(
        document_id=document_id,
        current_stage=latest.get('stage', ''),
        status=latest.get('status', ''),
        stages=stages,
        error_message=latest.get('message') if latest.get('status') == 'error' else None,
    )


@app.post('/documents/{document_id}/reprocess')
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Re-run the processing pipeline for a document in the background."""
    from app.orchestrator.agent import retry_failed_document
    background_tasks.add_task(retry_failed_document, document_id)
    return {'document_id': document_id, 'message': 'Document re-processing queued.'}


@app.get('/documents/{document_id}')
async def get_document(document_id: str) -> dict[str, Any]:
    """Return full document detail including reassembled EAV fields via get_document_with_fields()."""
    from app.persistence.db import get_document_with_fields
    from app.persistence.agent import get_processing_status

    doc_with_fields = get_document_with_fields(document_id)
    if not doc_with_fields:
        # Fallback to status check
        stages = get_processing_status(document_id)
        if not stages:
            raise HTTPException(status_code=404, detail='Document not found.')
        latest = stages[-1]
        return {
            'document_id': document_id,
            'status': latest.get('status', 'processing'),
            'current_stage': latest.get('stage', 'QUEUED'),
            'fields': {},
        }
    return doc_with_fields


@app.post('/documents/{document_id}/vendor')
async def link_vendor_endpoint(document_id: str, body: dict[str, str]) -> dict[str, Any]:
    """Link a vendor to a document."""
    from app.persistence.db import link_vendor_to_document
    vendor_id = (body.get('vendor_id') or '').strip()
    if not vendor_id:
        raise HTTPException(status_code=422, detail='vendor_id is required.')

    success = link_vendor_to_document(document_id, vendor_id)
    if not success:
        raise HTTPException(status_code=404, detail=f'Document {document_id} not found.')
    return {'document_id': document_id, 'vendor_id': vendor_id, 'message': 'Vendor linked successfully.'}


@app.get('/documents')
async def list_documents_endpoint(
    document_type: Optional[str] = Query(None),
    vendor_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    filename: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Paginated, filterable list of documents matching list_documents()."""
    from app.persistence.db import list_documents
    from app.persistence.database import get_db_session
    from app.persistence.models import Document
    from sqlalchemy import select, func

    offset = (page - 1) * page_size
    docs = list_documents(
        document_type=document_type if document_type and document_type != 'all' else None,
        vendor_id=vendor_id if vendor_id and vendor_id != 'all' else None,
        status=status if status and status != 'all' else None,
        limit=page_size,
        offset=offset,
    )

    # Filter by filename search box if provided
    if filename and filename.strip():
        fn_lower = filename.strip().lower()
        docs = [d for d in docs if fn_lower in d.get('original_filename', '').lower()]

    with get_db_session() as session:
        total = session.execute(select(func.count()).select_from(Document)).scalar() or len(docs)

    return {
        'items': docs,
        'total': total,
        'page': page,
        'page_size': page_size,
    }



@app.delete('/documents/{document_id}')
async def delete_document_endpoint(document_id: str) -> dict:
    """Delete a document and all its associated database records."""
    from app.persistence.agent import delete_document as _delete_doc
    success = _delete_doc(document_id)
    if not success:
        raise HTTPException(status_code=404, detail=f'Document {document_id} not found.')
    return {'document_id': document_id, 'message': f'Document {document_id} deleted successfully.'}


@app.get('/quarantine', response_model=QuarantineList)
async def list_quarantine(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> QuarantineList:
    """Paginated list of quarantined records awaiting human review."""
    from app.persistence.agent import get_quarantine_items

    raw_items = get_quarantine_items(page=page, page_size=page_size)
    items = []
    for item in raw_items:
        try:
            record = json.loads(item.get('record_json', '{}'))
            reasons = json.loads(item.get('reasons', '[]'))
        except (json.JSONDecodeError, TypeError):
            record = {}
            reasons = []
        items.append(QuarantineItem(
            id=item.get('id', 0),
            document_id=item.get('document_id', ''),
            document_type=item.get('document_type', ''),
            record=record,
            reasons=reasons,
            flagged_at=str(item.get('flagged_at', '')),
            reviewed=item.get('reviewed', False),
        ))
    return QuarantineList(items=items, total=len(items), page=page, page_size=page_size)


@app.post('/quarantine/{quarantine_id}/resolve', response_model=QuarantineResolveResponse)
async def resolve_quarantine(
    quarantine_id: int,
    body: QuarantineResolveRequest,
) -> QuarantineResolveResponse:
    """Accept (with optional correction) or dismiss a quarantined record."""
    from app.persistence.agent import resolve_quarantine_item

    if body.action not in ('accept', 'dismiss'):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid action '{body.action}'. Must be 'accept' or 'dismiss'.",
        )
    if body.action == 'accept' and body.corrected_record is None:
        raise HTTPException(
            status_code=422,
            detail="corrected_record is required when action is 'accept'.",
        )
    try:
        resolve_quarantine_item(
            quarantine_id,
            body.corrected_record if body.action == 'accept' else None,
        )
        return QuarantineResolveResponse(
            id=quarantine_id,
            action=body.action,
            message=f'Quarantine item {quarantine_id} {body.action}ed successfully.',
        )
    except Exception as exc:
        logger.error('Failed to resolve quarantine item %d: %s', quarantine_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post('/quarantine/bulk-dismiss')
async def bulk_dismiss_quarantine(
    document_id: Optional[str] = None,
) -> dict:
    """Dismiss all unreviewed quarantine items in one shot.

    Pass ?document_id=... to limit to a single document, or omit to dismiss everything.
    """
    from app.persistence.agent import bulk_dismiss_quarantine as _bulk_dismiss
    try:
        count = _bulk_dismiss(document_id=document_id)
        return {'dismissed': count, 'message': f'Dismissed {count} quarantine item(s).'}
    except Exception as exc:
        logger.error('Bulk dismiss failed: %s', exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get('/quarantine/{quarantine_id}', response_model=QuarantineItem)
async def get_quarantine_item(quarantine_id: int) -> QuarantineItem:
    """Fetch a single quarantine item by its integer ID."""
    from app.persistence.agent import get_quarantine_items
    from app.persistence.database import get_db_session
    from app.persistence.models import Quarantine
    import json
    with get_db_session() as session:
        item = session.get(Quarantine, quarantine_id)
        if not item:
            raise HTTPException(status_code=404, detail=f'Quarantine item {quarantine_id} not found.')
        try:
            record = json.loads(item.record_json or '{}')
            reasons = json.loads(item.reasons or '[]')
        except (json.JSONDecodeError, TypeError):
            record, reasons = {}, []
        return QuarantineItem(
            id=item.id,
            document_id=item.document_id,
            document_type=item.document_type,
            record=record,
            reasons=reasons,
            flagged_at=str(item.flagged_at),
            reviewed=item.reviewed,
        )


@app.post('/aliases/learn', response_model=LearnAliasResponse)
async def learn_new_alias(body: LearnAliasRequest) -> LearnAliasResponse:
    """Teach the Learning Agent a new alias or abbreviation mapping (e.g. mtrl -> materials).

    Mappings are stored in PostgreSQL and automatically carried forward to all future document extractions.
    """
    from app.learning.agent import learn_alias
    try:
        mapping = learn_alias(
            alias=body.alias,
            canonical_name=body.canonical_name,
            category=body.category,
            confidence=body.confidence,
        )
        return LearnAliasResponse(
            alias=mapping.alias,
            canonical_name=mapping.canonical_name,
            category=mapping.category,
            message=f"Successfully learned alias '{mapping.alias}' -> '{mapping.canonical_name}'.",
        )
    except Exception as exc:
        logger.error("Failed to learn alias '%s': %s", body.alias, exc)
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/aliases', response_model=AliasListResponse)
async def list_learned_aliases(category: Optional[str] = None) -> AliasListResponse:
    """Retrieve all learned alias mappings, optionally filtered by category."""
    from app.learning.agent import get_all_learned_aliases

    items_data = get_all_learned_aliases(category=category)
    items = [
        AliasItem(
            alias=item["alias"],
            canonical_name=item["canonical_name"],
            category=item["category"],
            confidence=item["confidence"],
            occurrence_count=item["occurrence_count"],
        )
        for item in items_data
    ]
    return AliasListResponse(items=items, total=len(items))


@app.get('/vendors', response_model=list[VendorListItem])
async def list_vendors_endpoint() -> list[VendorListItem]:
    """Retrieve a lightweight list of vendors (vendor_id and vendor_name), sorted alphabetically."""
    from app.persistence.db import list_vendors
    vendors = list_vendors()
    return [VendorListItem(vendor_id=v["vendor_id"], vendor_name=v["vendor_name"]) for v in vendors]


@app.get('/vendors/{vendor_id}', response_model=VendorDetailResponse)
async def get_vendor_endpoint(vendor_id: str) -> VendorDetailResponse:
    """Retrieve full details (name + address + timestamps) for a specific vendor."""
    from app.persistence.db import get_vendor_by_id
    vendor = get_vendor_by_id(vendor_id)
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found.")
    return VendorDetailResponse(
        vendor_id=vendor["vendor_id"],
        vendor_name=vendor["vendor_name"],
        address=vendor.get("address", ""),
        created_at=str(vendor.get("created_at", "")),
        updated_at=str(vendor.get("updated_at", "")),
    )


@app.post('/vendors', response_model=VendorCreateResponse)
async def create_vendor_endpoint(body: VendorCreateRequest) -> VendorCreateResponse:
    """Create a new vendor or update address if vendor_name already exists."""
    from app.persistence.db import save_vendor
    if not body.vendor_name or not body.vendor_name.strip():
        raise HTTPException(status_code=422, detail="vendor_name is required.")
    vendor_id = save_vendor(vendor_name=body.vendor_name, address=body.address or "")
    return VendorCreateResponse(vendor_id=vendor_id)


@app.get('/documents/{document_id}/rows')
async def get_document_rows(
    document_id: str,
    q: Optional[str] = Query(None, description="Free-text search query"),
    column: Optional[str] = Query(None, description="Column name to restrict search")
) -> list[dict[str, Any]]:
    """Return all extracted rows/records associated with a document_id, optionally filtered by search query."""
    from app.persistence.database import get_db_session
    from app.persistence.models import GenericRecord
    from sqlalchemy import func
    import json

    with get_db_session() as session:
        query = session.query(GenericRecord).filter(GenericRecord.document_id == document_id)
        
        if q and q.strip():
            search_val = f"%{q.strip().lower()}%"
            if column and column.strip():
                bind = session.get_bind()
                col_name = column.strip()
                from sqlalchemy import cast, JSON
                if bind.dialect.name == 'postgresql':
                    extras_str = func.json_extract_path_text(cast(GenericRecord.record_json, JSON), 'extras')
                    expr = func.json_extract_path_text(cast(extras_str, JSON), col_name)
                else:
                    extras_str = func.json_extract(GenericRecord.record_json, '$.extras')
                    expr = func.json_extract(extras_str, f'$.{col_name}')
                query = query.filter(func.lower(expr).like(search_val))
            else:
                query = query.filter(func.lower(GenericRecord.record_json).like(search_val))

        recs = query.order_by(GenericRecord.id.asc()).all()
        results = []
        for r in recs:
            try:
                data = json.loads(r.record_json)
                extras = data.get('extras', {})
                if isinstance(extras, str):
                    extras = json.loads(extras)
                results.append(extras)
            except Exception:
                continue
        return results


