"""
CLI script to sync user document edits & corrections from PostgreSQL into Learned Memory.
"""
import sys
import logging
from decimal import Decimal
import psycopg2
from app.config.settings import DATABASE_URL
from app.learning.memory_store import record_document_correction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_memory")


def sync_document_to_memory(document_id: int):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Get document & vendor info
    cur.execute("""
        SELECT d.id, d.document_no, d.document_type, v.name as vendor_name
        FROM billing_documents d
        LEFT JOIN vendors v ON d.vendor_id = v.id
        WHERE d.id = %s
    """, (document_id,))
    doc = cur.fetchone()
    if not doc:
        logger.warning(f"Document #{document_id} not found.")
        conn.close()
        return

    doc_id, doc_no, doc_type, vendor_name = doc

    # Get all line items for this document
    cur.execute("""
        SELECT description, qty, rate, gross_amount, hsn_code, uom
        FROM billing_document_line_items
        WHERE document_id = %s
        ORDER BY id
    """, (document_id,))
    rows = cur.fetchall()

    line_items = []
    for r in rows:
        line_items.append({
            "description": r[0] or "",
            "qty": float(r[1]) if r[1] is not None else 1.0,
            "rate": float(r[2]) if r[2] is not None else 0.0,
            "gross_amount": float(r[3]) if r[3] is not None else 0.0,
            "hsn_code": r[4] or "",
            "uom": r[5] or "Nos"
        })

    conn.close()

    record_document_correction(
        vendor_name=vendor_name,
        document_no=doc_no,
        document_type=doc_type,
        line_items=line_items
    )
    logger.info(f"Successfully synced Document #{document_id} ({vendor_name}) with {len(line_items)} items to learned memory.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        sync_document_to_memory(int(sys.argv[1]))
    else:
        logger.error("Usage: python -m app.learning.sync_memory <document_id>")
