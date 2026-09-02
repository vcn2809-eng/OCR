# NissiGrid - Document Intelligence & Financial Extraction Platform

An enterprise-grade, automated document intelligence and financial data extraction platform for processing complex tax invoices, multi-page chemical/industrial quotations, medical account statements, purchase orders, and Excel spreadsheets.

---

## 🛠️ Complete Tech Stack

| Layer | Technologies Used | Purpose |
|---|---|---|
| **Frontend** | React 18, Vite, Lucide Icons, CSS Variables (Dark/Light theming) | Responsive web dashboard, PDF viewer, line-item grid, audit panels |
| **Backend API** | Node.js (v18+ / v20+), Express, Multer, `pg` (node-postgres) | REST API, file upload handling, running Python extraction runner |
| **OCR & Extraction** | Python 3.11+ / 3.13, `pdfplumber`, `pytesseract`, `pdf2image`, `OpenCV` (`cv2`), `openpyxl`, `pandas` | Document parsing, multi-line table unrolling, OCR fallback, layout parsing |
| **AI / Vision (Optional)** | Ollama (`llama3`, `richardyoung/olmocr2:7b-q8`) | Vision LLM extraction fallback for complex unstructured scans |
| **System Binaries** | `tesseract-ocr`, `poppler-utils` (or `poppler` on macOS) | OCR engine & PDF-to-image rendering binaries |
| **Database** | PostgreSQL 14+ (or Docker PostgreSQL container) | Persistence for documents, line items, vendors, customers, audit logs |
| **Containerization** | Docker, Docker Compose (Multi-stage build) | Optional 1-command deployment for zero-setup machines |

---

## 🚀 Option 1: Zero-Config Docker Setup (Recommended)

If the target device has **Docker** and **Docker Compose** installed, no manual runtime installations are required:

```bash
# 1. Clone the repository
git clone https://github.com/vcn2809-eng/OCR.git nissigrid
cd nissigrid

# 2. Build and start the entire stack
docker compose up -d --build
```

**Access the application:** Open `http://localhost:5001` (or `http://<device-ip>:5001`).

---

## 💻 Option 2: Native Setup (Step-by-Step for Any Device)

### 1. Prerequisites Installation

#### macOS (via Homebrew):
```bash
brew install tesseract poppler postgresql@14 node
brew services start postgresql@14
```

#### Ubuntu / Debian Linux:
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv nodejs npm tesseract-ocr poppler-utils postgresql postgresql-contrib
sudo service postgresql start
```

#### Windows:
1. Install **Node.js (LTS)** from [nodejs.org](https://nodejs.org).
2. Install **Python 3.11+** from [python.org](https://python.org) (ensure *"Add Python to PATH"* is checked).
3. Install **PostgreSQL** from [postgresql.org](https://www.postgresql.org).
4. Install **Tesseract OCR** and **Poppler for Windows**, and add their `bin` directories to your System PATH.

---

### 2. Clone Repository

```bash
git clone https://github.com/vcn2809-eng/OCR.git nissigrid
cd nissigrid
```

---

### 3. Database Initialization

Create the PostgreSQL database named `scanner`:

```bash
# On Mac / Linux:
createdb scanner || psql -U postgres -c "CREATE DATABASE scanner;"

# Optional: Run schema script manually (the server will also auto-bootstrap tables on boot)
psql -d scanner -f app/persistence/schema.sql
```

---

### 4. Python Environment & Dependencies

```bash
# Create Python virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate    # On Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

---

### 5. Node.js & React Dependencies

```bash
# Backend dependencies
cd server
npm install
cd ..

# Frontend dependencies & production build
cd frontend
npm install
npm run build
cd ..
```

---

### 6. Start the Application

You can launch both services using the launcher script:

```bash
chmod +x start_app.sh
./start_app.sh
```

Or start them manually in two terminals:

#### Terminal 1 — Backend API (Port 5001):
```bash
cd server
npm start
```
*(The server automatically detects `.venv/bin/python3`, tests the database connection, bootstraps tables, and outputs the extraction summary banner!)*

#### Terminal 2 — Frontend Dev Server (Port 5173):
```bash
cd frontend
npm run dev
```

---

## 🌐 Multi-Device LAN Access (Same Wi-Fi)

Any smartphone, laptop, or tablet on the same local network can access NissiGrid without installing anything:

1. Check your host machine's local IP:
   - **macOS**: `ipconfig getifaddr en0`
   - **Linux**: `hostname -I | awk '{print $1}'`
   - **Windows**: `ipconfig` (Look for IPv4 address)
2. Open `http://<YOUR_LOCAL_IP>:5173` (Dev) or `http://<YOUR_LOCAL_IP>:5001` (Production / Docker) in any browser.

---

## 🧪 Running Automated Tests

Run the complete 248-test automated verification suite:

```bash
source .venv/bin/activate
PYTHONPATH=. pytest -q
```
Expected output:
```text
248 passed in ~100s
```

---

## 🏗️ Architectural Core Features

- **Multi-Line Table Unrolling**: Decomposes multi-line table cells (even without horizontal gridlines) into itemized line items.
- **Header & Address Extraction**: Automatically extracts vendor and customer names, GSTINs, invoice numbers, and physical registered addresses.
- **Row & Grand Total Reconciliation**: Recalculates `Qty × Rate = Gross`, discounts, tax percentages, and validates against printed grand totals.
- **3-Layer Duplicate Protection**: Cryptographic SHA-256 hash check, metadata comparison, and fuzzy line-item similarity matching.
- **Active Learning**: Learns vendor catalog items and description patterns dynamically.
- **Secret Dark/Light Theme**: Toggle anytime in the browser with `Shift + D`.

