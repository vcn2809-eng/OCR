-- =============================================================================
-- NissiGrid Database Schema Definition (PostgreSQL)
-- Database: scanner
-- =============================================================================

-- 1. Vendors Master Table
CREATE TABLE IF NOT EXISTS billing_vendors (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    gstin TEXT UNIQUE,
    pan TEXT,
    address TEXT,
    phone TEXT,
    email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Customers Master Table
CREATE TABLE IF NOT EXISTS billing_customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    gstin TEXT UNIQUE,
    address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Billing Documents Core Table
CREATE TABLE IF NOT EXISTS billing_documents (
    id SERIAL PRIMARY KEY,
    document_type TEXT NOT NULL,
    document_no TEXT,
    document_date DATE,
    classification_confidence NUMERIC(4, 3),
    classification_reasoning TEXT,
    vendor_id INT REFERENCES billing_vendors(id) ON DELETE SET NULL,
    customer_id INT REFERENCES billing_customers(id) ON DELETE SET NULL,
    validity_date DATE,
    payment_terms TEXT,
    currency TEXT DEFAULT 'INR',
    enquiry_ref TEXT,
    enquiry_date DATE,
    grand_total_taxable NUMERIC(14, 2),
    grand_total_cgst NUMERIC(14, 2),
    grand_total_sgst NUMERIC(14, 2),
    grand_total_final NUMERIC(14, 2),
    grand_total_words TEXT,
    source_file TEXT,
    extraction_status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Line Items Table
CREATE TABLE IF NOT EXISTS billing_document_line_items (
    id SERIAL PRIMARY KEY,
    document_id INT REFERENCES billing_documents(id) ON DELETE CASCADE,
    line_no INT NOT NULL,
    item_code TEXT,
    description TEXT,
    hsn_code TEXT,
    hsn_sac TEXT,
    brand TEXT,
    uom TEXT,
    packing TEXT,
    qty NUMERIC(12, 3),
    unit TEXT,
    rate NUMERIC(12, 2),
    gross_amount NUMERIC(12, 2),
    discount_pct NUMERIC(5, 2),
    discount_amount NUMERIC(12, 2),
    taxable_amount NUMERIC(12, 2),
    cgst_pct NUMERIC(5, 2),
    cgst_amount NUMERIC(12, 2),
    sgst_pct NUMERIC(5, 2),
    sgst_amount NUMERIC(12, 2),
    final_value NUMERIC(12, 2),
    status_eta TEXT,
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason TEXT
);

-- Indexes for high-performance lookup & search
CREATE INDEX IF NOT EXISTS idx_billing_docs_vendor ON billing_documents(vendor_id);
CREATE INDEX IF NOT EXISTS idx_billing_docs_customer ON billing_documents(customer_id);
CREATE INDEX IF NOT EXISTS idx_billing_docs_doc_no ON billing_documents(document_no);
CREATE INDEX IF NOT EXISTS idx_billing_docs_type ON billing_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_billing_line_items_doc_id ON billing_document_line_items(document_id);
CREATE INDEX IF NOT EXISTS idx_billing_line_items_item_code ON billing_document_line_items(item_code);
