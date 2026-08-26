# NissiGrid - Document Intelligence & Extraction Platform

An enterprise-grade, automated document intelligence and financial data extraction platform for processing complex tax invoices, quotations, medical account statements, purchase orders, and Excel sheets.

---

## 📋 System Prerequisites

### 1. OS-Level Dependencies

**macOS (via Homebrew):**
```bash
brew install tesseract poppler postgresql node
```

**Ubuntu / Debian (via APT):**
```bash
sudo apt update
sudo apt install -y tesseract-ocr libtesseract-dev poppler-utils postgresql nodejs npm
```

**Windows:**
- Install [Tesseract OCR for Windows](https://github.com/UB-Mannheim/tesseract/wiki) and add to PATH.
- Install [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases/) and add `bin` to PATH.
- Install [PostgreSQL](https://www.postgresql.org/download/windows/) and [Node.js](https://nodejs.org/).

---

## ⚙️ Installation & Setup

### Step 1: Clone Repository

```bash
git clone https://github.com/vcn2809-eng/OCR.git
cd OCR
```

### Step 2: Python Environment

```bash
python3 -m venv .venv
source .venv/bin/activate    # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Node.js Dependencies

Install dependencies for both frontend and backend services:

```bash
# Express API Backend
cd server
npm install
cd ..

# React Frontend
cd frontend
npm install
cd ..
```

### Step 4: Database Setup

Ensure PostgreSQL is running, then create the database and load schema:

```bash
# Create database 'scanner'
createdb scanner

# Run schema initialization
psql -d scanner -f app/persistence/schema.sql
```

*(Optional)* Copy `.env.example` to `.env` if you need custom PostgreSQL credentials:
```bash
cp .env.example .env
```

---

## 🚀 Running the Application

### Option A: One-Click Launcher (macOS / Linux)

```bash
chmod +x start_app.sh
./start_app.sh
```

### Option B: Run Services Manually

1. **Start Express API Server (Port 5001):**
   ```bash
   cd server
   node server.js
   ```

2. **Start React Frontend (Port 5173):**
   ```bash
   cd frontend
   npm run dev
   ```

3. Open **`http://localhost:5173`** in your browser.

---

## 🧪 Running Tests

Run the test suite (188 tests):

```bash
source .venv/bin/activate
pytest tests/
```

Verify frontend build:
```bash
cd frontend && npm run build
```

---

## 🏗️ Architecture & Pipeline Overview

- **Ingestion**: Multi-engine parsing of unstructured PDFs (native & OCR fallback) and Excel files (`.xlsx`, `.xls`, `.csv`).
- **3-Layer Duplicate Protection**: Cryptographic SHA-256 hash check, header metadata comparison, and fuzzy line-item similarity matching.
- **Mathematical Verification**: Pinpoint calculation discrepancy detection (`qty * rate = gross`, `subtotal + tax = final`).
- **Entity Management**: Automatic vendor and customer registered address parsing.
- **Executive Analytics**: Interactive SVG Donut chart and live document search.

---

## 📁 Directory Structure

```text
nissigrid/
├── app/                              # Python Extraction & Processing Core
│   ├── api/                          # FastAPI endpoints & routers
│   ├── classification/               # Document type classification
│   ├── config/                       # Settings & classification YAML rules
│   ├── db/                           # SQLite / test database helpers
│   ├── excel_extraction/             # Excel parsing logic
│   ├── ingestion/                    # Ingestion handlers
│   ├── normalization/                # Number, date, currency standardizers
│   ├── ocr/                          # Tesseract OCR & image conversion
│   ├── orchestrator/                 # End-to-end extraction pipeline
│   ├── persistence/                  # PostgreSQL schema, models & DB session
│   ├── preprocessing/                # Image binarization, deskewing
│   ├── quotation_extraction/         # Hybrid PDF/Excel extraction & loader
│   ├── schema_mapping/               # Schema field transformers
│   ├── table_detection/              # Table boundary detection
│   └── validation/                   # Data validation models & rules
├── frontend/                         # React 18 + Vite SPA Single Page Application
├── server/                           # Express.js REST API Server (Port 5001)
├── tests/                            # Unit & integration test suite (188 tests)
├── input_files/                      # Sample documents for testing & ingestion
├── start_app.sh                      # One-click system launcher script
├── .env.example                      # Configuration template
├── HANDOVER_DOCUMENTATION.md         # Comprehensive Architectural Master Document
├── requirements.txt                  # Python dependencies
└── README.md                         # Project documentation
```
