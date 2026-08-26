# 🐍 NissiGrid Standalone Complete Python Backend Code

This folder contains the **entire Python backend engine** consolidated into a **single, fully self-contained Python source file** so you can easily open it in any Python IDE (PyCharm, VS Code, Spyder, Jupyter, IDLE) to review, edit, add custom comments, or copy-paste anywhere.

---

## 📁 File Location

- **File Path**: [`/Users/vishnucharan/nissigrid/backend_standalone/nissigrid_complete_backend.py`](file:///Users/vishnucharan/nissigrid/backend_standalone/nissigrid_complete_backend.py)

---

## 🏗️ Code Structure & Table of Contents

Inside [`nissigrid_complete_backend.py`](file:///Users/vishnucharan/nissigrid/backend_standalone/nissigrid_complete_backend.py), the code is organized into 8 distinct sections with section headers and XML docstrings (`"""..."""`):

1. **SECTION 1: GLOBAL CONFIGURATION & SETTINGS**
   - Contains database connection parameters, feature flags, OCR configuration, and path definitions.

2. **SECTION 2: CUSTOM EXCEPTIONS LIBRARY**
   - Hierarchical exception handling classes (`QuotationParsingError`, `DatabaseError`, `ValidationError`, `OCRError`, `ClassificationError`).

3. **SECTION 3: DOMAIN DATA MODELS & DATACLASSES**
   - Strongly-typed dataclasses for OCR word confidence scores (`WordResult`), page OCR results (`OCRResult`), bounding boxes (`BoundingBox`), and document classification results (`ClassificationResult`).

4. **SECTION 4: DATA NORMALIZATION & ARITHMETIC VALIDATION**
   - Currency and number parser (`to_decimal`), row-level line item arithmetic validator (`validate_row_arithmetic`), and grand total reconciliation engine (`validate_quotation_totals`).

5. **SECTION 5: CLASSIFICATION AGENT (HEURISTICS & LLM FALLBACK)**
   - Keyword density classifier for identifying purchase orders, tax invoices, quotations, patient statements, and generic documents.

6. **SECTION 6: SPREADSHEET EXTRACTOR (EXCEL & MULTI-RECORD CSV)**
   - Handles `.xlsx`, `.xls`, and multi-line CSV files containing embedded JSON invoice payloads (e.g., `batch_1.csv` with 100+ invoices).

7. **SECTION 7: DATABASE PERSISTENCE AGENT (POSTGRESQL & EAV SCHEMA)**
   - Manages connection and writes to PostgreSQL tables (`billing_documents`, `billing_document_line_items`, `billing_vendors`, `billing_customers`).

8. **SECTION 8: PIPELINE ORCHESTRATOR & CLI ENTRY POINT**
   - Main execution function `process_file(file_path)` and CLI runner block (`if __name__ == '__main__': ...`).

---

## 🚀 How to Run & Copy-Paste

### Option A: Open & Review in Any IDE
Open [`nissigrid_complete_backend.py`](file:///Users/vishnucharan/nissigrid/backend_standalone/nissigrid_complete_backend.py) directly in VS Code, PyCharm, or any text editor. You can copy the entire file or individual sections to review or add comments.

### Option B: Execute via Command Line
Run the consolidated script directly from your terminal:

```bash
cd /Users/vishnucharan/nissigrid
python backend_standalone/nissigrid_complete_backend.py input_files/1786690214842-939322100_batch_1.csv
```
