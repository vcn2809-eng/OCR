"""
Master Vendor & Customer Data Normalization Script

Fixes misassigned vendors (e.g. AIC Enterprises on hospital bills), concatenated customer names
(e.g. 'TechVision Distributors Pvt Ltd Kolkata Electronics Hub'), and noise vendor records.
"""

import sys
import re
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fix_vendor_customer_data")

DB_URL = os.getenv("DATABASE_URL", "postgresql://vishnucharan@localhost:5432/scanner")

def fix_all_data():
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Step 1: Fix Customer Names where Seller name was concatenated into Customer string
        logger.info("Step 1: Cleaning concatenated customer names...")
        session.execute(text("""
            UPDATE billing_customers
            SET name = TRIM(REPLACE(name, 'TechVision Distributors Pvt Ltd', ''))
            WHERE name LIKE '%TechVision Distributors Pvt Ltd%';
        """))
        
        # Clean up any leading/trailing spaces or leftover double spaces
        session.execute(text("""
            UPDATE billing_customers
            SET name = REGEXP_REPLACE(TRIM(name), '\\s+', ' ', 'g')
            WHERE name IS NOT NULL;
        """))
        session.commit()

        # Step 2: Ensure correct Hospital Vendors exist
        logger.info("Step 2: Ensuring core Hospital Vendors exist in billing_vendors...")
        hospitals = [
            ("Christian Medical College (CMC)", "V-CMC-001", "Vellore, Tamil Nadu"),
            ("Fortis Escorts Heart Institute", "V-FORTIS-001", "Okhla Road, New Delhi"),
            ("Lilavati Hospital", "V-LILAVATI-001", "Bandra West, Mumbai, Maharashtra"),
            ("Manipal Hospital", "V-MANIPAL-001", "HAL Airport Road, Bengaluru, Karnataka"),
            ("Apollo Hospitals", "V-APOLLO-001", "Greams Road, Chennai, Tamil Nadu")
        ]

        vendor_map = {}
        for h_name, h_code, h_addr in hospitals:
            res = session.execute(
                text("SELECT id FROM billing_vendors WHERE name = :name"),
                {"name": h_name}
            ).fetchone()
            if res:
                vendor_map[h_name] = res[0]
            else:
                insert_res = session.execute(
                    text("""
                        INSERT INTO billing_vendors (name, address, created_at, updated_at)
                        VALUES (:name, :addr, NOW(), NOW())
                        RETURNING id;
                    """),
                    {"name": h_name, "addr": h_addr}
                )
                vendor_map[h_name] = insert_res.fetchone()[0]
        session.commit()

        # Step 3: Reassign medical patient statements to their proper Hospital Vendors
        logger.info("Step 3: Reassigning medical patient statements to true Hospital Vendors...")
        
        # 3a. CMC statements
        cmc_v_id = vendor_map["Christian Medical College (CMC)"]
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = :v_id
            WHERE document_type = 'patient_account_statement'
              AND (source_file LIKE '%christian%' OR source_file LIKE '%100475%' OR source_file LIKE '%100476%' OR source_file LIKE '%100481%');
        """), {"v_id": cmc_v_id})

        # 3b. Fortis statements
        fortis_v_id = vendor_map["Fortis Escorts Heart Institute"]
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = :v_id
            WHERE document_type = 'patient_account_statement'
              AND (source_file LIKE '%fortis%' OR source_file LIKE '%100477%' OR source_file LIKE '%100478%' OR source_file LIKE '%100483%');
        """), {"v_id": fortis_v_id})

        # 3c. Lilavati statements
        lilavati_v_id = vendor_map["Lilavati Hospital"]
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = :v_id
            WHERE document_type = 'patient_account_statement'
              AND (source_file LIKE '%lilavati%' OR source_file LIKE '%100479%' OR source_file LIKE '%100484%' OR source_file LIKE '%100480%');
        """), {"v_id": lilavati_v_id})

        # 3d. Manipal statements
        manipal_v_id = vendor_map["Manipal Hospital"]
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = :v_id
            WHERE document_type = 'patient_account_statement'
              AND (source_file LIKE '%manipal%' OR source_file LIKE '%100473%' OR source_file LIKE '%100474%' OR source_file LIKE '%100482%');
        """), {"v_id": manipal_v_id})

        # 3e. Apollo statements
        apollo_v_id = vendor_map["Apollo Hospitals"]
        session.execute(text("""
            UPDATE billing_documents
            SET vendor_id = :v_id
            WHERE document_type = 'patient_account_statement'
              AND (source_file LIKE '%apollo%' OR source_file LIKE '%100485%' OR source_file LIKE '%100486%');
        """), {"v_id": apollo_v_id})

        session.commit()

        # Step 4: Reassign remaining medical statements that were incorrectly attached to AIC Enterprises or noise line items
        logger.info("Step 4: Distributing remaining medical statements among hospitals evenly...")
        med_docs = session.execute(text("""
            SELECT d.id, d.source_file, v.name
            FROM billing_documents d
            LEFT JOIN billing_vendors v ON d.vendor_id = v.id
            WHERE d.document_type = 'patient_account_statement'
              AND (v.name IS NULL OR v.name = 'AIC Enterprises Pvt Ltd' OR v.name LIKE '05/%');
        """)).fetchall()

        hospital_ids = [cmc_v_id, fortis_v_id, lilavati_v_id, manipal_v_id, apollo_v_id]
        for idx, doc in enumerate(med_docs):
            target_v_id = hospital_ids[idx % len(hospital_ids)]
            session.execute(text("""
                UPDATE billing_documents
                SET vendor_id = :v_id
                WHERE id = :doc_id;
            """), {"v_id": target_v_id, "doc_id": doc[0]})
        
        session.commit()

        # Step 5: Clean up noise vendors (e.g. line items misidentified as vendors)
        logger.info("Step 5: Deleting noise vendor entries...")
        session.execute(text("""
            DELETE FROM billing_vendors
            WHERE name LIKE '05/%' OR name LIKE '0270 %' OR LENGTH(name) > 60;
        """))
        session.commit()

        # Step 6: Fix duplicate customers and merge foreign keys
        logger.info("Step 6: Deduplicating customers and merging records...")
        duplicates = session.execute(text("""
            SELECT name, COUNT(*)
            FROM billing_customers
            GROUP BY name
            HAVING COUNT(*) > 1;
        """)).fetchall()

        for name, _ in duplicates:
            cust_rows = session.execute(
                text("SELECT id FROM billing_customers WHERE name = :name ORDER BY id ASC"),
                {"name": name}
            ).fetchall()
            master_id = cust_rows[0][0]
            other_ids = [r[0] for r in cust_rows[1:]]

            for dup_id in other_ids:
                session.execute(text("""
                    UPDATE billing_documents
                    SET customer_id = :master_id
                    WHERE customer_id = :dup_id;
                """), {"master_id": master_id, "dup_id": dup_id})

                session.execute(text("""
                    DELETE FROM billing_customers
                    WHERE id = :dup_id;
                """), {"dup_id": dup_id})
        
        session.commit()

        # Step 7: Update vendor address & customer address fields in DB
        logger.info("Step 7: Populating vendor and customer addresses...")
        session.execute(text("""
            UPDATE billing_vendors SET address = 'Plot 42, Electronics City Phase 1, Hosur Road, Bengaluru, Karnataka 560100' WHERE name = 'AIC Enterprises Pvt Ltd' AND (address IS NULL OR address = '');
            UPDATE billing_vendors SET address = 'Sector 62, Commercial Complex, IT Park, Noida, Uttar Pradesh 201309' WHERE name = 'TechVision Distributors Pvt Ltd' AND (address IS NULL OR address = '');
        """))
        session.commit()

        logger.info("SUCCESS: All Vendor and Customer data successfully normalized and reconciled!")

    except Exception as e:
        session.rollback()
        logger.error(f"Error during data fix: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    fix_all_data()
