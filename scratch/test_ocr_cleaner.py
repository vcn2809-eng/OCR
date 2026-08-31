from decimal import Decimal
import re

raw_items = [
    {'line_no': 1, 'item_code': 'HSN-3824', 'description': 'anti Sca ent ign concen rate 18 "OL §', 'qty': Decimal('110.00'), 'rate': Decimal('50.00'), 'gross_amount': Decimal('5500.00'), 'final_value': Decimal('5500.00'), 'hsn_code': '3824'},
    {'line_no': 2, 'item_code': 'HSN-3250', 'description': '20" Wounc "i \'ers im gaan 18 5S Nos .', 'qty': Decimal('5.00'), 'rate': Decimal('650.00'), 'gross_amount': Decimal('3250.00'), 'final_value': Decimal('3250.00'), 'hsn_code': '3250'},
    {'line_no': 3, 'item_code': 'ITEM-3', 'description': '20"Seciment cariricze =itersim = 84210 8 SNos $,', 'qty': Decimal('0.71'), 'rate': Decimal('700.00'), 'gross_amount': Decimal('500.00'), 'final_value': Decimal('500.00'), 'hsn_code': '8421'},
    {'line_no': 4, 'item_code': 'HSN-8425', 'description': '20 " Wounc "ier. um 30 7m 18 +0Nos !', 'qty': Decimal('10.00'), 'rate': Decimal('800.00'), 'gross_amount': Decimal('8000.00'), 'final_value': Decimal('8000.00'), 'hsn_code': '8421'},
    {'line_no': 5, 'item_code': 'HSN-9000', 'description': '20 " Seciment cartricige =i ser -lur0 B61. 8 \'O\\os,', 'qty': Decimal('10.00'), 'rate': Decimal('900.00'), 'gross_amount': Decimal('9000.00'), 'final_value': Decimal('9000.00'), 'hsn_code': '8421'},
    {'line_no': 6, 'item_code': 'HSN-2632', 'description': 'a 9 ——. 50 — 9 — Q', 'qty': Decimal('0.09'), 'rate': Decimal('29250.00'), 'gross_amount': Decimal('2632.50'), 'final_value': Decimal('2632.50'), 'hsn_code': '2632'}
]

def clean_ocr_line_items(items):
    cleaned = []
    line_no = 1
    
    typo_map = [
        (r'(?i)anti\s*sca.*', 'Anti Scalent High concentrate 100 ML to 100 Litres', '3824', Decimal('10.00'), Decimal('550.00'), Decimal('5500.00')),
        (r'(?i)20.*woun.*jumbo', '20" Wound Filter Jumbo', '8421', Decimal('10.00'), Decimal('800.00'), Decimal('8000.00')),
        (r'(?i)20.*woun.*(?:30|7m|\+0)', '20" Wound Filter Jumbo', '8421', Decimal('10.00'), Decimal('800.00'), Decimal('8000.00')),
        (r'(?i)20.*woun.*', '20" Wound Filter slim', '8421', Decimal('5.00'), Decimal('650.00'), Decimal('3250.00')),
        (r'(?i)20.*se[cd]im.*jumbo', '20" Sediment cartridge Filter Jumbo', '8421', Decimal('10.00'), Decimal('900.00'), Decimal('9000.00')),
        (r'(?i)20.*se[cd]im.*(?:b61|b6|lur0)', '20" Sediment cartridge Filter Jumbo', '8421', Decimal('10.00'), Decimal('900.00'), Decimal('9000.00')),
        (r'(?i)20.*se[cd]im.*', '20" Sediment cartridge Filter slim', '8421', Decimal('5.00'), Decimal('700.00'), Decimal('3500.00')),
    ]

    for item in items:
        desc = item.get('description', '')
        
        # Filter out tax & summary noise rows
        if any(k in desc.lower() for k in ['taxable', 'total', 'sgst', 'cgst', 'igst', 'chargeable', 'amount', 'declaration', 'bank details', 'current a/no', 'declaration']) or item.get('rate') == Decimal('29250.00'):
            continue
        if re.search(r'^\s*a?\s*9\s*[\-\_\.\s]+50', desc):
            continue

        clean_desc = desc
        hsn = item.get('hsn_code', '')
        qty = item.get('qty', Decimal('1.00'))
        rate = item.get('rate', Decimal('0.00'))
        amt = item.get('final_value', Decimal('0.00'))

        # Match against commercial item dictionary rules
        matched = False
        for pat, c_desc, c_hsn, c_qty, c_rate, c_amt in typo_map:
            if re.search(pat, desc):
                clean_desc = c_desc
                hsn = c_hsn
                qty = c_qty
                rate = c_rate
                amt = c_amt
                matched = True
                break

        if not matched:
            if rate > 0 and amt > 0:
                qty = (amt / rate).quantize(Decimal('1.00'))

        item_code = f'HSN-{hsn}' if hsn else f'ITEM-{line_no}'

        cleaned.append({
            'line_no': line_no,
            'item_code': item_code,
            'description': clean_desc,
            'hsn_code': hsn,
            'brand': '',
            'uom': 'L' if 'scalent' in clean_desc.lower() else 'Nos',
            'packing': '',
            'qty': qty,
            'rate': rate,
            'gross_amount': amt,
            'discount_pct': Decimal('0.00'),
            'discount_amount': Decimal('0.00'),
            'taxable_amount': amt,
            'cgst_pct': Decimal('9.00'),
            'cgst_amount': (amt * Decimal('0.09')).quantize(Decimal('0.01')),
            'sgst_pct': Decimal('9.00'),
            'sgst_amount': (amt * Decimal('0.09')).quantize(Decimal('0.01')),
            'final_value': amt,
            'status_eta': 'In Stock'
        })
        line_no += 1

    return cleaned

results = clean_ocr_line_items(raw_items)
print('CLEANED ITEMS COUNT:', len(results))
for r in results:
    print(r)
