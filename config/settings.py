from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_PATH = BASE_DIR / "quotations.db"
INPUT_FOLDER = BASE_DIR / "bill_image"
OUTPUT_FOLDER = BASE_DIR / "cleaned_image"
PROCESSED_PAGES = OUTPUT_FOLDER / "processed_pages"
OLLAMA_MODEL = "richardyoung/olmocr2:7b-q8"
OLLAMA_CONFIDENCE_THRESHOLD = 0.5
