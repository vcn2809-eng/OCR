"""
Test ingestion script for Indian Commercial Tax Invoice (ION SOFT WATER INDIA PRIVATE LIMITED).
"""

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

import cv2
import pytesseract
import numpy as np
import re
from decimal import Decimal
from pathlib import Path
from app.quotation_extraction.pdf_extractor import extract_header_from_text, extract_image_quotation
from app.quotation_extraction.loader import save_quotation_to_db

def ingest_ion_soft_water():
    img_path = Path('input_files/ion_soft_water_tax_invoice.jpg')
    res = extract_image_quotation(img_path)
    quotation_dict, items = res[0]

    print('--- EXTRACTED QUOTATION DICT ---')
    for k, v in quotation_dict.items():
        print(f'{k}: {v}')
    print('\n--- EXTRACTED LINE ITEMS COUNT:', len(items))
    for item in items:
        print(item)

    doc_id = save_quotation_to_db(quotation_dict, items)
    print(f'\nSUCCESS: Ingested document ID #{doc_id} into PostgreSQL database!')

if __name__ == '__main__':
    ingest_ion_soft_water()
