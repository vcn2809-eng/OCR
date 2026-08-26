# NissiGrid Document Intelligence Platform
## Complete Technical Handover & Architectural Master Documentation

---

## 1. Executive Summary & Core Mission

**NissiGrid** is an enterprise-grade, automated document intelligence and financial data extraction platform designed for processing complex medical account statements, tax invoices, purchase orders, proforma billing documents, and quotations.

### Primary Objectives:
1. **Automated Data Ingestion**: Multi-engine parsing of unstructured PDFs (native & scanned image PDFs) and Excel spreadsheets (`.xlsx`, `.xls`).
2. **High-Precision OCR & Table Extraction**: Hybrid extraction leveraging PyMuPDF (`fitz`), `pdfplumber`, and Tesseract OCR to accurately extract line-item detail tables and header metadata.
3. **Intricate 3-Layer Duplicate Protection**: Cryptographic and value-level verification preventing duplicate database record insertion.
4. **Mathematical Verification & Pinpoint Error Detection**: Automatic cross-validation of financial calculations (`qty * rate = gross`, `taxable + CGST + SGST = total`) with pinpoint cell-level mismatch highlighting.
5. **Entity Address Registration**: Automatic extraction and database registration of vendor and buyer registered street addresses.
6. **Executive Analytics & Explorer**: Interactive SVG Donut analytics charts, unified full-text search, and full-row document audit workflows.

---

## 2. Technology Stack & Prerequisites

| Layer | Technology / Library | Description |
| :--- | :--- | :--- |
| **Frontend UI** | React 18, Vite 5, React Router 6, Lucide Icons | Responsive glassmorphic SPA built with Vanilla CSS variables |
| **Backend API** | Node.js, Express.js (Port `5001`), PostgreSQL (`pg` pool) | REST API endpoints for search, filtering, CRUD, and ingestion |
| **Python Core Engine**| Python 3.11+, SQLAlchemy, pandas, openpyxl, rapidfuzz | Data extraction, normalization, fuzzy matching, and loader |
| **OCR & Parsing** | Tesseract OCR 5.0+, PyMuPDF (`fitz`), `pdfplumber`, OpenCV | Native text layer extraction + optical character recognition fallback |
| **Database** | PostgreSQL 14+ (`scanner` database) | Relational SQL database for documents, vendors, customers, line items |

### System Dependencies (OS Level):
- **macOS (Homebrew)**: `brew install tesseract poppler postgresql node`
- **Ubuntu/Debian**: `sudo apt-get install tesseract-ocr libtesseract-dev poppler-utils postgresql nodejs`

---

## 3. Comprehensive Feature Guide & Architecture

### 3.1 Multi-Engine Document Processing Pipeline
Located in [`app/quotation_extraction/`](file:///Users/vishnucharan/nissigrid/app/quotation_extraction):
- **`run.py`**: CLI & programmatic entry point for ingesting single files or folders.
- **`pdf_extractor.py`**:
  1. *Fast-Pass Native Layer*: Extracts text using PyMuPDF (`fitz`). If clean text is found, parses tables via `pdfplumber`.
  2. *OCR Fallback*: If page text is missing or scanned image-based, applies OpenCV preprocessing (deskewing, binarization) and passes frames to `pytesseract`.
  3. *Header Metadata Parser*: Extracts Document/Invoice Number, Issue Date, Validity Date, Payment Terms, Currency, Enquiry References, Vendor Name/GSTIN, Customer Name/GSTIN, and Registered Addresses.
- **`excel_extractor.py`**: Reads `.xlsx`/`.xls` sheets using `openpyxl`/`pandas`, detecting header rows dynamically and standardizing column headers.

---

### 3.2 Intricate 3-Layer Duplicate Detection Engine
Located in [`app/quotation_extraction/loader.py`](file:///Users/vishnucharan/nissigrid/app/quotation_extraction/loader.py):
When a file is ingested, the system checks whether the document already exists using a 3-layer validation mechanism:
1. **Layer 1: Binary SHA-256 Cryptographic Hash**: Computes binary file hash (`compute_file_sha256`) to immediately catch identical files.
2. **Layer 2: Header Metadata Cross-Verification**: Compares `document_no`, `grand_total_final`, `document_date`, `vendor_name`, and `customer_name` against existing records in PostgreSQL.
3. **Layer 3: Line-Item Structure & Fuzzy Value Match**: Cross-validates all extracted line items (`qty`, `rate`, `final_value`, `item_code`, and fuzzy description similarity using `rapidfuzz`).

*Result*: If a duplicate is detected, insertion is skipped, and a warning toast (`"Duplicate document detected! Matches existing Document #ID"`) is presented to the user without duplicating data.

---

### 3.3 Mathematical Discrepancy & Pinpoint Highlight Engine
Located in [`frontend/src/pages/QuotationDetail.jsx`](file:///Users/vishnucharan/nissigrid/frontend/src/pages/QuotationDetail.jsx) and [`Quarantine.jsx`](file:///Users/vishnucharan/nissigrid/frontend/src/pages/Quarantine.jsx):
For every document line item, the system verifies:
$$\text{Calculated Gross} = \text{Quantity} \times \text{Unit Rate}$$
$$\text{Calculated Final} = \text{Taxable Subtotal} + \text{CGST Amount} + \text{SGST Amount}$$

If a discrepancy exceeds $\pm 0.50$ INR:
- The document is flagged with status `needs_review` and routed to **Quarantine Review**.
- **Pinpoint Highlighting**: Instead of showing generic text warning badges, the UI evaluates math per cell and applies a soft rose background glow (`rgba(244, 63, 94, 0.16)`) and red border (`#f43f5e`) **specifically on the single input field causing the math mismatch**.

---

### 3.4 Interactive SVG Donut Chart (Document Type Distribution)
Located in [`frontend/src/pages/Dashboard.jsx`](file:///Users/vishnucharan/nissigrid/frontend/src/pages/Dashboard.jsx):
- Custom vector SVG Donut Chart (`280px × 280px`) displaying document classification metrics (`Tax Invoice`, `Quotation`, `Patient Statement`, `Proforma Invoice`, `Purchase Order`).
- **Interactive Features**:
  - Hovering a pie slice smoothly expands the arc (`outerR: 138px`) and dims remaining slices.
  - Dynamic center counter displays total documents (`212`) by default, updating on hover to show category name, document count, and percentage (`e.g., Tax Invoice: 167 (80.3%)`).
  - Synchronized legend grid allowing single-click filtering to Document Explorer.

---

### 3.5 Registered Address Extraction & Entity Management
Located in [`app/quotation_extraction/pdf_extractor.py`](file:///Users/vishnucharan/nissigrid/app/quotation_extraction/pdf_extractor.py), [`loader.py`](file:///Users/vishnucharan/nissigrid/app/quotation_extraction/loader.py), and [`Vendors.jsx`](file:///Users/vishnucharan/nissigrid/frontend/src/pages/Vendors.jsx):
- Extracts multi-line street address blocks during parsing.
- Registers addresses under `BillingVendor.address` and `BillingCustomer.address` in PostgreSQL.
- Renders vendor and customer addresses in the Header Metadata cards of Document Audit view (`📍 Vendor Registered Address`).

---

### 3.6 Documents & Items Explorer (`/quotations`)
Located in [`frontend/src/pages/QuotationsList.jsx`](file:///Users/vishnucharan/nissigrid/frontend/src/pages/QuotationsList.jsx):
- **Full-Row Clickability**: Clicking anywhere on a document table row (or line item search match) opens the audit page directly.
- **Unified Multi-Column Search**: Live search across Document Number, Vendor Name, Customer Name, Line Item Code, Description, and Amounts with exact match text highlighting.
- **Excel Export**: Exports filtered table views to `.xlsx` format.
- **Post-Ingestion Auto-Clearing**: Ingestion queue automatically resets upon batch completion.

---

## 4. Database Schema Reference

Database Name: `scanner`

```sql
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
    hsn_sac TEXT,
    qty NUMERIC(12, 3),
    unit TEXT,
    rate NUMERIC(12, 2),
    gross_amount NUMERIC(12, 2),
    discount_amount NUMERIC(12, 2),
    taxable_amount NUMERIC(12, 2),
    cgst_pct NUMERIC(5, 2),
    cgst_amount NUMERIC(12, 2),
    sgst_pct NUMERIC(5, 2),
    sgst_amount NUMERIC(12, 2),
    final_value NUMERIC(12, 2),
    needs_review BOOLEAN DEFAULT FALSE,
    review_reason TEXT
);
```

---

## 5. System Setup & Running Guide

### 5.1 Environment Setup
1. **Clone & Virtual Environment**:
   ```bash
   git clone <repository-url>
   cd nissigrid
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Frontend Dependencies**:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

3. **Backend Dependencies**:
   ```bash
   cd server
   npm install
   cd ..
   ```

4. **Database Initialization**:
   ```bash
   createdb scanner
   psql -d scanner -f app/persistence/schema.sql
   ```

---

### 5.2 Launching the Application
Execute the single-command launcher script:
```bash
./start_app.sh
```
Or start backend and frontend independently:
- **Express Backend API**: `node server/server.js` (Runs on `http://localhost:5001`)
- **React Frontend SPA**: `cd frontend && npm run dev` (Runs on `http://localhost:5173`)

---

## 6. Testing & Quality Verification

Run the full Python test suite (188 unit tests):
```bash
.venv/bin/pytest tests/
```

Run frontend production build verification:
```bash
cd frontend && npm run build
```

---

## 7. Project File Map

```
nissigrid/
├── app/                              # Python Extraction & Processing Core
│   ├── config/                       # Settings & classification YAML rules
│   ├── quotation_extraction/         # PDF & Excel extraction pipeline
│   │   ├── pdf_extractor.py          # PyMuPDF + Tesseract OCR header & table parser
│   │   ├── excel_extractor.py        # Excel sheet parser
│   │   ├── loader.py                 # Intricate 3-layer duplicate & DB loader
│   │   └── run.py                    # Ingestion runner script
│   └── persistence/                  # SQLAlchemy models & DB connection
│       ├── models.py                 # BillingDocument, Vendor, Customer models
│       └── schema.sql                # PostgreSQL table initialization script
├── server/                           # Express.js Backend API
│   ├── server.js                     # REST API endpoints (Port 5001)
│   └── package.json                  # Node dependencies (pg, express, multer)
├── frontend/                         # React Vite Single Page Application
│   ├── src/
│   │   ├── App.jsx                   # Main application router & sidebar navigation
│   │   ├── pages/
│   │   │   ├── Dashboard.jsx         # Executive analytics & SVG Donut chart
│   │   │   ├── Upload.jsx            # Drag-and-drop batch document uploader
│   │   │   ├── QuotationsList.jsx    # Documents & Items Explorer (clickable rows)
│   │   │   ├── QuotationDetail.jsx   # Document Audit view with pinpoint mismatch glow
│   │   │   ├── Quarantine.jsx        # Flagged document audit quarantine
│   │   │   └── Vendors.jsx           # Registered vendor directory & addresses
│   │   ├── context/
│   │   │   └── IngestionContext.jsx  # Global batch ingestion state
│   │   └── api/                      # Axios API client functions
├── tests/                            # Pytest unit test suite (188 tests)
├── start_app.sh                      # Executable single-command application launcher
└── HANDOVER_DOCUMENTATION.md         # Master Technical Handover Document
```

---
*Documentation compiled and verified for NissiGrid Platform.*
