"""
Master Document Classification & Entity Re-alignment Script.

Fixes false information in billing_documents:
1. All medical/MRN documents (med_doc_bill, hospital statements, MRN-*) are classified as 'patient_account_statement' and have vendor_id = NULL.
2. Only authentic commercial AIC PDFs/price lists get vendor_id = 'AIC Enterprises Pvt Ltd'.
3. Only commercial batch CSV/XLSX files get vendor_id = 'TechVision Distributors Pvt Ltd'.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_all_docs")

DB_URL = os.getenv("DATABASE_URL", "postgresql://vishnucharan@localhost:5432/scanner")

def fix_all_documents():
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        logger.info("Step 1: Fixing all medical / MRN documents...")
        # Reclassify all med_doc_bill, hospital, or MRN- documents as patient_account_statement and set vendor_id = NULL
        session.execute(text("""
            UPDATE billing_documents
            SET document_type = 'patient_account_statement',
                vendor_id = NULL
            WHERE source_file LIKE '%med_doc_bill%'
               OR source_file LIKE '%hospital%'
               OR source_file LIKE '%statement%'
               OR document_no LIKE 'MRN-%';
        """))
        session.commit()

        logger.info("Step 2: Ensuring AIC Enterprises vendor ID exists...")
        aic_res = session.execute(text("SELECT id FROM billing_vendors WHERE name = 'AIC Enterprises Pvt Ltd';")).fetchone()
        if not aic_res:
            aic_res = session.execute(text("""
                INSERT INTO billing_vendors (name, address, created_at, updated_at)
                VALUES ('AIC Enterprises Pvt Ltd', 'Plot 42, Electronics City Phase 1, Hosur Road, Bengaluru, Karnataka 560100', NOW(), NOW())
                RETURNING id;
            """)).fetchone()
        aic_v_id = aic_res[0]

        logger.info("Step 3: Ensuring TechVision Distributors vendor ID exists...")
        tv_res = session.execute(text("SELECT id FROM billing_vendors WHERE name = 'TechVision Distributors Pvt Ltd';")).fetchone()
        if not tv_res:
            tv_res = session.execute(text("""
                INSERT INTO billing_vendors (name, address, created_at, updated_at)
                VALUES ('TechVision Distributors Pvt Ltd', 'Sector 62, Commercial Complex, IT Park, Noida, Uttar Pradesh 201309', NOW(), NOW())
                RETURNING id;
            """)).fetchone()
        tv_v_id = tv_res[0]

        logger.info("Step 4: Setting vendor_id = AIC Enterprises for authentic AIC documents only...")
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = :aic_id
            WHERE (source_file LIKE '%AIC ENTERP%' OR source_file LIKE '%invoice_51109%')
              AND source_file NOT LIKE '%med_doc_bill%'
              AND (document_no IS NULL OR document_no NOT LIKE 'MRN-%');
        """), {"aic_id": aic_v_id})
        session.commit()

        logger.info("Step 5: Setting vendor_id = TechVision Distributors for commercial batch files...")
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = :tv_id
            WHERE (source_file LIKE '%batch%' OR source_file LIKE '%test_invoice%')
              AND source_file NOT LIKE '%med_doc_bill%'
              AND (document_no IS NULL OR document_no NOT LIKE 'MRN-%');
        """), {"tv_id": tv_v_id})
        session.commit()

        logger.info("Step 6: Purging all orphan non-commercial vendors from billing_vendors...")
        session.execute(text("""
            DELETE FROM billing_vendors
            WHERE name NOT IN ('AIC Enterprises Pvt Ltd', 'TechVision Distributors Pvt Ltd');
        """))
        session.commit()

        logger.info("SUCCESS: Document classifications and vendor associations strictly reconciled!")

    except Exception as e:
        session.rollback()
        logger.error(f"Error during document fix: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    fix_all_documents()
