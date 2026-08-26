import sqlite3
import pandas as pd

DB_NAME = "quotations.db"


def init_db():
    """Initializes the SQLite database table for storing quotation line items."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quotation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_no TEXT,
            quotation_date TEXT,
            brand TEXT,
            code TEXT,
            description TEXT,
            category TEXT,
            uom TEXT,
            quantity INTEGER,
            rate REAL,
            gross_amount REAL,
            taxable_amount REAL,
            cgst_amount REAL,
            sgst_amount REAL,
            final_value REAL,
            eta TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_quotation_to_db(data: dict):
    """Inserts extracted quotation metadata and line items into SQLite database."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    q_no = data.get("quotation_number", "N/A")
    q_date = data.get("quotation_date", "N/A")
    items = data.get("line_items", [])

    for item in items:
        cursor.execute(
            """
            INSERT INTO quotation_items (
                quotation_no, quotation_date, brand, code, description,
                category, uom, quantity, rate, gross_amount, taxable_amount,
                cgst_amount, sgst_amount, final_value, eta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                q_no,
                q_date,
                item.get("brand", "N/A"),
                item.get("code", "N/A"),
                item.get("description", "N/A"),
                item.get("category", "Others"),
                item.get("uom", "N/A"),
                item.get("quantity", 0),
                item.get("rate", 0.0),
                item.get("gross_amount", 0.0),
                item.get("taxable_amount", 0.0),
                item.get("cgst_amount", 0.0),
                item.get("sgst_amount", 0.0),
                item.get("final_value", 0.0),
                item.get("eta", "N/A"),
            ),
        )

    conn.commit()
    conn.close()


def fetch_all_items_df() -> pd.DataFrame:
    """Reads all stored database rows into a Pandas DataFrame."""
    init_db()
    conn = sqlite3.connect(DB_NAME)
    try:
        df = pd.read_sql_query("SELECT * FROM quotation_items", conn)
    except Exception:
        init_db()
        df = pd.read_sql_query("SELECT * FROM quotation_items", conn)
    finally:
        conn.close()
    return df
