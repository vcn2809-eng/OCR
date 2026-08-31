"""
Script to remove Hospital vendors and clear vendor_id on patient account statements.
Strictly keeps commercial vendors only; leaves non-commercial documents with blank vendor.
"""

import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("remove_hospital_vendors")

DB_URL = os.getenv("DATABASE_URL", "postgresql://vishnucharan@localhost:5432/scanner")

def remove_hospitals():
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Step 1: Set vendor_id = NULL for all patient_account_statement documents
        logger.info("Step 1: Setting vendor_id = NULL for all patient_account_statement documents...")
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = NULL
            WHERE document_type = 'patient_account_statement';
        """))
        session.commit()

        # Step 2: Set vendor_id = NULL for any documents linked to hospital vendor entities
        logger.info("Step 2: Clearing vendor_id for documents linked to hospital entities...")
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = NULL
            WHERE vendor_id IN (
                SELECT id FROM billing_vendors
                WHERE name LIKE '%Hospital%'
                   OR name LIKE '%College%'
                   OR name LIKE '%Clinic%'
                   OR name LIKE '%Institute%'
                   OR name LIKE '05/%'
                   OR name LIKE '0270%'
            );
        """))
        session.commit()

        # Step 3: Remove hospital vendor records from billing_vendors table
        logger.info("Step 3: Removing non-commercial hospital vendor records from billing_vendors...")
        session.execute(text("""
            DELETE FROM billing_vendors
            WHERE name LIKE '%Hospital%'
               OR name LIKE '%College%'
               OR name LIKE '%Clinic%'
               OR name LIKE '%Institute%'
               OR name LIKE '05/%'
               OR name LIKE '0270%';
        """))
        session.commit()

        logger.info("SUCCESS: All hospital vendor associations removed. Non-commercial documents left with blank vendor!")

    except Exception as e:
        session.rollback()
        logger.error(f"Error removing hospital vendors: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    remove_hospitals()
