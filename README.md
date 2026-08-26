# OCR - AI Based PDF/Excel Scanner Pipeline

A robust pipeline for ingesting, classifying, and extracting data from PDFs and Excel files.

## System Dependencies

**macOS (brew):**
```bash
brew install tesseract poppler
```

**Ubuntu (apt):**
```bash
sudo apt update
sudo apt install tesseract-ocr poppler-utils
```

## Python Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables

- `OPENAI_API_KEY`: Optional, for LLM fallback.
- `DEBUG_MODE`: Set to `true` or `false` to enable debugging features.

## Running the Application

```bash
uvicorn app.api.main:app --reload
```

## Testing

```bash
pytest tests/
```

## Pipeline Overview

1. **Ingestion**: Handles file uploads and storage.
2. **Classification**: Classifies the document type (e.g., invoice, resume).
3. **Preprocessing**: Cleans and prepares documents for OCR.
4. **OCR**: Extracts text from images or PDFs.
5. **Excel Extraction**: Extracts data directly from Excel files.
6. **Table Detection**: Identifies and extracts tabular data.
7. **Normalization**: Standardizes extracted data formats.
8. **Schema Mapping**: Maps normalized data to expected schemas.
9. **Validation**: Validates data against predefined rules.
10. **Persistence**: Saves data to the database.
11. **Orchestrator**: Coordinates the entire pipeline process.
12. **API**: Exposes endpoints for client interaction.

## Directory Structure

```text
nissigrid/
├── app/
│   ├── api/
│   ├── classification/
│   ├── config/
│   ├── db/
│   ├── excel_extraction/
│   ├── ingestion/
│   ├── normalization/
│   ├── ocr/
│   ├── orchestrator/
│   ├── persistence/
│   ├── preprocessing/
│   ├── schema_mapping/
│   ├── table_detection/
│   └── validation/
├── input_files/
├── tests/
├── README.md
└── requirements.txt
```
