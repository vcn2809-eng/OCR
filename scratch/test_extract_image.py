"""
Test script for extract_image_quotation in pdf_extractor.py
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from pathlib import Path
from app.quotation_extraction.pdf_extractor import extract_image_quotation

res = extract_image_quotation(Path('input_files/ion_soft_water_tax_invoice.jpg'))
q_dict, line_items = res[0]

print('--- QUOTATION HEADER ---')
for k, v in q_dict.items():
    print(f'{k}: {v}')

print(f'\n--- EXTRACTED LINE ITEMS ({len(line_items)} items) ---')
for item in line_items:
    print(item)
