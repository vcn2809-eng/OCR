#!/usr/bin/env python3
"""
NissiGrid - Extracts Diagnostic CLI
Displays all extracted documents, line items, and financial summaries.
"""
import sys
import psycopg2

def main():
    try:
        conn = psycopg2.connect("postgresql://localhost:5432/scanner")
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*), COALESCE(SUM(grand_total_final), 0) FROM billing_documents;")
        total_docs, total_val = cur.fetchone()

        cur.execute("SELECT COUNT(*) FROM billing_document_line_items;")
        total_items = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM billing_vendors;")
        total_vendors = cur.fetchone()[0]

        cur.execute("""
            SELECT COALESCE(document_type, 'invoice'), COUNT(*) 
            FROM billing_documents 
            GROUP BY document_type 
            ORDER BY count DESC;
        """)
        by_type = cur.fetchall()

        cur.execute("""
            SELECT 
                d.id, 
                COALESCE(d.document_no, 'N/A') as doc_no, 
                COALESCE(d.document_type, 'invoice') as doc_type, 
                COALESCE(v.name, 'N/A') as vendor, 
                COALESCE(d.document_date::text, 'N/A') as doc_date, 
                d.grand_total_final, 
                COUNT(li.id) as item_count
            FROM billing_documents d
            LEFT JOIN billing_vendors v ON d.vendor_id = v.id
            LEFT JOIN billing_document_line_items li ON d.id = li.document_id
            GROUP BY d.id, d.document_no, d.document_type, v.name, d.document_date, d.grand_total_final
            ORDER BY d.id DESC;
        """)
        rows = cur.fetchall()

        print("\n" + "="*115)
        print("  📊 NISSIGRID DOCUMENT INTELLIGENCE REPOSITORY — ALL EXTRACTS")
        print("="*115)
        print(f"  • Total Archived Documents : {total_docs:,}")
        print(f"  • Total Line Items Extracted: {total_items:,}")
        print(f"  • Total Vendors Cataloged   : {total_vendors:,}")
        print(f"  • Total Extracted Value     : ₹{total_val:,.2f}")
        print("\n  📂 Category Breakdown:")
        for t, c in by_type:
            print(f"     - {t:<26}: {c:,} documents")

        print("\n" + "-"*115)
        print(f"  {'ID':<5} | {'Document No':<20} | {'Type':<20} | {'Vendor':<28} | {'Date':<12} | {'Total Amount':<14} | {'Items':<5}")
        print("-" * 115)
        for r in rows:
            doc_no = str(r[1])[:20]
            dtype = str(r[2])[:20]
            vendor = str(r[3])[:28]
            dt = str(r[4])[:12]
            tot = f"₹{r[5]:,.2f}" if r[5] is not None else "₹0.00"
            print(f"  {r[0]:<5} | {doc_no:<20} | {dtype:<20} | {vendor:<28} | {dt:<12} | {tot:<14} | {r[6]:<5}")
        print("="*115 + "\n")

    except Exception as e:
        print(f"Error reading extracts: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
