"""
Central configuration for the PDF/Excel Scanner pipeline.
All agents import from here — never hardcode paths or thresholds.
"""
from pathlib import Path
import os

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Folders
INPUT_FOLDER = PROJECT_ROOT / "input_files"
DB_FOLDER = PROJECT_ROOT / "app" / "db"          # kept for tests that monkeypatch the engine
DB_PATH = DB_FOLDER / "scanner.db"               # used only when DATABASE_URL is not set
CONFIG_FOLDER = PROJECT_ROOT / "app" / "config"
DEBUG_IMAGES_FOLDER = Path("/tmp") / "preprocessing_debug"

# ── PostgreSQL connection ──────────────────────────────────────────────────────
# Set DATABASE_URL to override everything (e.g. on Heroku / Railway / Render):
#   export DATABASE_URL="postgresql://user:password@host:5432/dbname"
# Or set individual vars:
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
DB_HOST: str = os.environ.get("DB_HOST", "localhost")
DB_PORT: str = os.environ.get("DB_PORT", "5432")
DB_NAME: str = os.environ.get("DB_NAME", "scanner")
DB_USER: str = os.environ.get("DB_USER", os.environ.get("USER", "postgres"))
DB_PASSWORD: str = os.environ.get("DB_PASSWORD", "")

_pg_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# DATABASE_URL env var takes precedence over individual vars
DATABASE_URL: str = os.environ.get("DATABASE_URL", _pg_url)

# ── Thresholds ─────────────────────────────────────────────────────────────────
CLASSIFICATION_CONFIDENCE_THRESHOLD: float = 0.6
OCR_CONFIDENCE_THRESHOLD: float = 0.6
LINE_TOTAL_TOLERANCE: float = 0.05

# ── Feature flags ──────────────────────────────────────────────────────────────
DEBUG_MODE: bool = os.environ.get("DEBUG_MODE", "false").lower() == "true"

# ── Config file paths ──────────────────────────────────────────────────────────
CLASSIFICATION_RULES_PATH = CONFIG_FOLDER / "classification_rules.yaml"
FIELD_MAPPINGS_PATH = CONFIG_FOLDER / "field_mappings.yaml"
OCR_CORRECTIONS_PATH = CONFIG_FOLDER / "ocr_corrections.yaml"

# ── LLM ───────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = "gpt-4o-mini"
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "richardyoung/olmocr2:7b-q8")

# ── OCR ───────────────────────────────────────────────────────────────────────
TESSERACT_LANG: str = "eng"
TESSERACT_CONFIG: str = "--oem 3 --psm 6"

# ── Ingestion ─────────────────────────────────────────────────────────────────
ALLOWED_EXTENSIONS: set = {"pdf", "xlsx", "xls", "csv"}

# ── Batch processing ──────────────────────────────────────────────────────────
DEFAULT_BATCH_SIZE: int = 10
