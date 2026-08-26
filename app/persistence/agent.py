"""
Persistence Agent — the single boundary layer for all database reads and writes. No other agent should import SQLAlchemy or sqlite3 directly.
"""
import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, update, func, desc

from app.persistence.database import get_db_session, init_db
from app.persistence.models import (
    RawDocument, Invoice, Resume, GenericRecord, Quarantine, ProcessingLog, ProcessingQueue, LearnedAlias
)
from app.persistence.exceptions import PersistenceError, UnsupportedDocumentTypeError

logger = logging.getLogger(__name__)


from app.persistence.db import (
    save_vendor, list_vendors, get_vendor_by_id,
    save_document, save_document_fields, get_document_with_fields,
    list_documents, link_vendor_to_document, migrate_legacy_data
)


def save_raw_document(document_id: str, file_hash: str, filename: str, file_type: str, document_type: str | None, raw_data: Any | None) -> None:
    if isinstance(raw_data, (dict, list)):
        raw_data_str = json.dumps(raw_data)
    else:
        raw_data_str = str(raw_data) if raw_data else None

    # Save to legacy RawDocument table
    with get_db_session() as session:
        doc = session.get(RawDocument, document_id)
        if doc is None:
            stmt = select(RawDocument).where(RawDocument.file_hash == file_hash)
            doc = session.execute(stmt).scalar_one_or_none()
        
        if doc is not None and doc.document_id != document_id:
            old_id = doc.document_id
            session.query(Invoice).filter(Invoice.document_id == old_id).delete()
            session.query(Resume).filter(Resume.document_id == old_id).delete()
            session.query(GenericRecord).filter(GenericRecord.document_id == old_id).delete()
            session.query(Quarantine).filter(Quarantine.document_id == old_id).delete()
            session.query(ProcessingLog).filter(ProcessingLog.document_id == old_id).delete()
            session.query(ProcessingQueue).filter(ProcessingQueue.document_id == old_id).delete()
            from app.persistence.models import Document as EAVDocument
            session.query(EAVDocument).filter(EAVDocument.document_id == old_id).delete()
            session.delete(doc)
            session.flush()
            doc = None

        if doc is None:
            doc = RawDocument(
                document_id=document_id,
                file_hash=file_hash,
                original_filename=filename,
                file_type=file_type,
                document_type=document_type,
                raw_extracted_json=raw_data_str
            )
            session.add(doc)
        else:
            doc.original_filename = filename
            doc.file_type = file_type
            doc.document_type = document_type
            doc.raw_extracted_json = raw_data_str


    # Save to new EAV documents table
    save_document(
        document_id=document_id,
        file_hash=file_hash,
        filename=filename,
        file_type=file_type,
        document_type=document_type,
        status="stored",
        raw_text=raw_data_str,
    )


def _serialize_complex_types(record: dict[str, Any]) -> dict[str, Any]:
    serialized = {}
    for k, v in record.items():
        if isinstance(v, (dict, list)):
            serialized[k] = json.dumps(v)
        else:
            serialized[k] = v
    return serialized


def save_record(document_id: str, document_type: str, record: dict[str, Any]) -> None:
    with get_db_session() as session:
        serialized_record = _serialize_complex_types(record)
        
        if document_type in ('invoice', 'quotation'):
            model = Invoice
            serialized_record['document_id'] = document_id
            valid_keys = {col.name for col in model.__table__.columns}
            filtered = {k: v for k, v in serialized_record.items() if k in valid_keys}
            
            stmt = select(model).where(model.document_id == document_id)
            existing = session.execute(stmt).scalar_one_or_none()
            
            if existing:
                for k, v in filtered.items():
                    setattr(existing, k, v)
            else:
                new_record = model(**filtered)
                session.add(new_record)
        elif document_type == 'resume':
            model = Resume
            serialized_record['document_id'] = document_id
            valid_keys = {col.name for col in model.__table__.columns}
            filtered = {k: v for k, v in serialized_record.items() if k in valid_keys}
            
            stmt = select(model).where(model.document_id == document_id)
            existing = session.execute(stmt).scalar_one_or_none()
            
            if existing:
                for k, v in filtered.items():
                    setattr(existing, k, v)
            else:
                new_record = model(**filtered)
                session.add(new_record)
        else:
            import json as _json
            session.add(GenericRecord(
                document_id=document_id,
                document_type=document_type,
                record_json=_json.dumps(serialized_record),
            ))

    # Also save to new EAV document_fields table
    save_document_fields(document_id, record)



def save_to_quarantine(document_id: str, document_type: str, record: dict[str, Any], reasons: list[str]) -> None:
    with get_db_session() as session:
        q = Quarantine(
            document_id=document_id,
            document_type=document_type,
            record_json=json.dumps(record),
            reasons=json.dumps(reasons)
        )
        session.add(q)


def log_stage(document_id: str, stage: Any, status: str, message: str = '') -> None:
    stage_str = stage.value if hasattr(stage, 'value') else str(stage)
    stage_str = stage_str.replace('PipelineStage.', '')
    with get_db_session() as session:
        log_entry = ProcessingLog(
            document_id=document_id,
            stage=stage_str,
            status=status,
            message=message
        )
        session.add(log_entry)


def get_processing_status(document_id: str) -> list[dict[str, Any]]:
    with get_db_session() as session:
        stmt = select(ProcessingLog).where(ProcessingLog.document_id == document_id).order_by(ProcessingLog.timestamp.asc())
        logs = session.execute(stmt).scalars().all()
        return [
            {
                "id": log.id,
                "document_id": log.document_id,
                "stage": log.stage,
                "status": log.status,
                "message": log.message,
                "timestamp": log.timestamp.isoformat()
            }
            for log in logs
        ]


def get_document_record(document_id: str) -> dict[str, Any] | None:
    with get_db_session() as session:
        raw_doc = session.get(RawDocument, document_id)
        if not raw_doc or not raw_doc.document_type:
            return None
            
        doc_type = raw_doc.document_type
        if doc_type == 'invoice':
            model = Invoice
            stmt = select(model).where(model.document_id == document_id)
            record = session.execute(stmt).scalar_one_or_none()
            if record:
                result = {col.name: getattr(record, col.name) for col in record.__table__.columns}
                for k, v in result.items():
                    if hasattr(v, 'isoformat'):
                        result[k] = v.isoformat()
                return result
        elif doc_type == 'resume':
            model = Resume
            stmt = select(model).where(model.document_id == document_id)
            record = session.execute(stmt).scalar_one_or_none()
            if record:
                result = {col.name: getattr(record, col.name) for col in record.__table__.columns}
                for k, v in result.items():
                    if hasattr(v, 'isoformat'):
                        result[k] = v.isoformat()
                return result
        
        # Generic or other document types
        stmt = select(GenericRecord).where(GenericRecord.document_id == document_id)
        g_rec = session.execute(stmt).scalars().first()
        if g_rec and g_rec.record_json:
            try:
                return json.loads(g_rec.record_json)
            except Exception:
                pass
                
        if raw_doc.raw_extracted_json:
            try:
                raw_data = json.loads(raw_doc.raw_extracted_json)
                if isinstance(raw_data, dict):
                    return raw_data
            except Exception:
                pass

        return None


def get_raw_document(document_id: str) -> dict[str, Any] | None:
    with get_db_session() as session:
        doc = session.get(RawDocument, document_id)
        if doc:
            result = {col.name: getattr(doc, col.name) for col in doc.__table__.columns}
            if result.get("uploaded_at"):
                result["uploaded_at"] = result["uploaded_at"].isoformat()
            return result
        return None


def get_all_documents(page: int = 1, page_size: int = 20) -> tuple[list[dict[str, Any]], int]:
    offset = (page - 1) * page_size
    with get_db_session() as session:
        total_stmt = select(func.count()).select_from(RawDocument)
        total = session.execute(total_stmt).scalar() or 0

        stmt = select(RawDocument).order_by(desc(RawDocument.uploaded_at)).limit(page_size).offset(offset)
        docs = session.execute(stmt).scalars().all()
        
        results = []
        for doc in docs:
            doc_dict = {col.name: getattr(doc, col.name) for col in doc.__table__.columns}
            if doc_dict.get("uploaded_at"):
                doc_dict["uploaded_at"] = doc_dict["uploaded_at"].isoformat()
                
            # Get latest processing log stage
            log_stmt = select(ProcessingLog).where(ProcessingLog.document_id == doc.document_id).order_by(desc(ProcessingLog.timestamp)).limit(1)
            latest_log = session.execute(log_stmt).scalar_one_or_none()
            
            doc_dict["latest_stage"] = latest_log.stage if latest_log else None
            doc_dict["current_stage"] = latest_log.stage if latest_log else None
            doc_dict["latest_status"] = latest_log.status if latest_log else None
            results.append(doc_dict)
            
        return results, total


def delete_document(document_id: str) -> bool:
    """Delete all records associated with a document_id across all tables."""
    from app.persistence.models import Document as EAVDocument
    deleted_any = False
    with get_db_session() as session:
        session.query(Invoice).filter(Invoice.document_id == document_id).delete()
        session.query(Resume).filter(Resume.document_id == document_id).delete()
        session.query(GenericRecord).filter(GenericRecord.document_id == document_id).delete()
        session.query(Quarantine).filter(Quarantine.document_id == document_id).delete()
        session.query(ProcessingLog).filter(ProcessingLog.document_id == document_id).delete()
        session.query(ProcessingQueue).filter(ProcessingQueue.document_id == document_id).delete()
        
        doc = session.get(RawDocument, document_id)
        if doc:
            session.delete(doc)
            deleted_any = True

        eav_doc = session.get(EAVDocument, document_id)
        if eav_doc:
            session.delete(eav_doc)
            deleted_any = True

        return deleted_any



def get_quarantine_items(page: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
    offset = (page - 1) * page_size
    with get_db_session() as session:
        stmt = select(Quarantine).where(Quarantine.reviewed == False).order_by(desc(Quarantine.flagged_at)).limit(page_size).offset(offset)
        items = session.execute(stmt).scalars().all()
        
        return [
            {
                "id": item.id,
                "document_id": item.document_id,
                "document_type": item.document_type,
                "record_json": item.record_json,
                "reasons": item.reasons,
                "flagged_at": item.flagged_at.isoformat(),
                "reviewed": item.reviewed
            }
            for item in items
        ]


def resolve_quarantine_item(quarantine_id: int, corrected_record: dict[str, Any] | None = None) -> None:
    with get_db_session() as session:
        item = session.get(Quarantine, quarantine_id)
        if not item:
            raise RecordNotFoundError(f"Quarantine item {quarantine_id} not found.")

        item.reviewed = True

        if corrected_record is not None:
            document_type = item.document_type
            document_id = item.document_id
            serialized = _serialize_complex_types(corrected_record)

            if document_type in ('invoice', 'quotation'):
                model = Invoice
                serialized['document_id'] = document_id
                valid_keys = {col.name for col in model.__table__.columns}
                filtered = {k: v for k, v in serialized.items() if k in valid_keys}
                stmt = select(model).where(model.document_id == document_id)
                existing = session.execute(stmt).scalar_one_or_none()
                if existing:
                    for k, v in filtered.items():
                        setattr(existing, k, v)
                else:
                    session.add(model(**filtered))

            elif document_type == 'resume':
                model = Resume
                serialized['document_id'] = document_id
                valid_keys = {col.name for col in model.__table__.columns}
                filtered = {k: v for k, v in serialized.items() if k in valid_keys}
                stmt = select(model).where(model.document_id == document_id)
                existing = session.execute(stmt).scalar_one_or_none()
                if existing:
                    for k, v in filtered.items():
                        setattr(existing, k, v)
                else:
                    session.add(model(**filtered))

            else:
                # Generic / unknown type — store as JSON in generic_records
                import json as _json
                session.add(GenericRecord(
                    document_id=document_id,
                    document_type=document_type,
                    record_json=_json.dumps(corrected_record),
                ))


def bulk_dismiss_quarantine(document_id: str | None = None) -> int:
    """Mark all unreviewed quarantine items as dismissed (reviewed=True).

    If document_id is given, only items for that document are dismissed.
    Returns the count of items dismissed.
    """
    with get_db_session() as session:
        stmt = select(Quarantine).where(Quarantine.reviewed == False)
        if document_id:
            stmt = stmt.where(Quarantine.document_id == document_id)
        items = session.execute(stmt).scalars().all()
        for item in items:
            item.reviewed = True
        return len(items)


def hash_exists_in_raw_documents(file_hash: str) -> bool:
    with get_db_session() as session:
        stmt = select(RawDocument.document_id).where(RawDocument.file_hash == file_hash).limit(1)
        result = session.execute(stmt).scalar_one_or_none()
        return result is not None


def hash_exists_in_queue(file_hash: str) -> bool:
    with get_db_session() as session:
        stmt = select(ProcessingQueue.document_id).where(ProcessingQueue.file_hash == file_hash).limit(1)
        result = session.execute(stmt).scalar_one_or_none()
        return result is not None


def enqueue_document(document_id: str, file_path: str, file_hash: str, file_type: str) -> None:
    with get_db_session() as session:
        item = ProcessingQueue(
            document_id=document_id,
            file_path=file_path,
            file_hash=file_hash,
            file_type=file_type,
            status='queued'
        )
        session.add(item)


def get_next_queued_documents(batch_size: int = 10) -> list[dict[str, Any]]:
    with get_db_session() as session:
        stmt = select(ProcessingQueue).where(ProcessingQueue.status == 'queued').order_by(ProcessingQueue.created_at.asc()).limit(batch_size)
        items = session.execute(stmt).scalars().all()
        
        return [
            {
                "document_id": item.document_id,
                "file_path": item.file_path,
                "file_hash": item.file_hash,
                "file_type": item.file_type,
                "status": item.status,
                "document_type": item.document_type,
                "classification_confidence": item.classification_confidence,
                "created_at": item.created_at.isoformat() if item.created_at else None
            }
            for item in items
        ]


def get_queue_item(document_id: str) -> dict[str, Any] | None:
    with get_db_session() as session:
        item = session.get(ProcessingQueue, document_id)
        if item:
            return {
                "document_id": item.document_id,
                "file_path": item.file_path,
                "file_hash": item.file_hash,
                "file_type": item.file_type,
                "status": item.status,
                "document_type": item.document_type,
                "classification_confidence": item.classification_confidence,
                "created_at": item.created_at.isoformat() if item.created_at else None
            }
        return None


def update_queue_status(document_id: str, status: str, document_type: str | None = None, classification_confidence: float | None = None) -> None:
    with get_db_session() as session:
        item = session.get(ProcessingQueue, document_id)
        if item:
            item.status = status
            if document_type is not None:
                item.document_type = document_type
            if classification_confidence is not None:
                item.classification_confidence = classification_confidence


def save_learned_alias(alias: str, canonical_name: str, category: str = 'header', confidence: float = 1.0) -> dict[str, Any]:
    """Insert or update a learned alias mapping in the database."""
    clean_alias = alias.strip().lower()
    clean_canonical = canonical_name.strip().lower()

    with get_db_session() as session:
        stmt = select(LearnedAlias).where(LearnedAlias.alias == clean_alias)
        existing = session.execute(stmt).scalar_one_or_none()

        if existing:
            existing.canonical_name = clean_canonical
            existing.category = category
            existing.confidence = confidence
            existing.occurrence_count += 1
            rec = existing
        else:
            rec = LearnedAlias(
                alias=clean_alias,
                canonical_name=clean_canonical,
                category=category,
                confidence=confidence,
                occurrence_count=1
            )
            session.add(rec)
            session.flush()

        return {
            "id": rec.id,
            "alias": rec.alias,
            "canonical_name": rec.canonical_name,
            "category": rec.category,
            "confidence": rec.confidence,
            "occurrence_count": rec.occurrence_count
        }


def get_learned_aliases(category: str | None = None) -> list[dict[str, Any]]:
    """Retrieve all learned alias records, optionally filtered by category."""
    with get_db_session() as session:
        stmt = select(LearnedAlias)
        if category:
            stmt = stmt.where(LearnedAlias.category == category)
        items = session.execute(stmt.order_by(desc(LearnedAlias.occurrence_count))).scalars().all()

        return [
            {
                "id": item.id,
                "alias": item.alias,
                "canonical_name": item.canonical_name,
                "category": item.category,
                "confidence": item.confidence,
                "occurrence_count": item.occurrence_count
            }
            for item in items
        ]


def delete_learned_alias(alias: str) -> bool:
    """Delete a learned alias from the database by name."""
    clean_alias = alias.strip().lower()
    with get_db_session() as session:
        stmt = select(LearnedAlias).where(LearnedAlias.alias == clean_alias)
        item = session.execute(stmt).scalar_one_or_none()
        if item:
            session.delete(item)
            return True
        return False
