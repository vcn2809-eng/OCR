const express = require('express');
const cors = require('cors');
const multer = require('multer');
const { Pool } = require('pg');
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 5001;

// CORS configuration
app.use(cors());
app.use(express.json());

// Postgres Connection Pool
const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  database: process.env.DB_NAME || 'scanner',
  user: process.env.DB_USER || process.env.USER || 'vishnucharan',
  password: process.env.DB_PASSWORD || '',
});

// Configure Multer for File Uploads
const inputDir = path.join(__dirname, '..', 'input_files');
if (!fs.existsSync(inputDir)) {
  fs.mkdirSync(inputDir, { recursive: true });
}

const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    cb(null, inputDir);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1e9);
    cb(null, `${uniqueSuffix}_${file.originalname}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 500 * 1024 * 1024 } // 500 MB max per file
});

// Serve source files statically for split-screen audit comparison
app.use('/files', express.static(inputDir));
app.get('/api/files/:filename', (req, res) => {
  const filename = req.params.filename;
  const filePath = path.join(inputDir, filename);
  if (!fs.existsSync(filePath)) {
    return res.status(404).json({ error: 'File not found' });
  }
  res.sendFile(filePath);
});

// Helper to validate a line item row (arithmetic constraints)
function validateRowArithmetic(item) {
  const reasons = [];
  
  const toNum = (val) => {
    if (val === null || val === undefined || val === '') return 0.0;
    const clean = String(val).replace(/,/g, '').trim();
    if (clean.toLowerCase() === 'n/a' || clean.toLowerCase() === '-') return 0.0;
    const num = parseFloat(clean);
    return isNaN(num) ? 0.0 : num;
  };

  const qty = toNum(item.qty);
  const rate = toNum(item.rate);
  const gross = toNum(item.gross_amount);
  const discPct = toNum(item.discount_pct);
  const discAmt = toNum(item.discount_amount);
  const taxable = toNum(item.taxable_amount);
  const cgstPct = toNum(item.cgst_pct);
  const cgstAmt = toNum(item.cgst_amount);
  const sgstPct = toNum(item.sgst_pct);
  const sgstAmt = toNum(item.sgst_amount);
  const finalVal = toNum(item.final_value);

  // 1. Gross Amount = Rate * Qty
  const expectedGross = rate * qty;
  if (Math.abs(gross - expectedGross) > 0.02) {
    reasons.push(`Gross Amount mismatch: calculated ${expectedGross.toFixed(2)}, got ${gross.toFixed(2)}`);
  }

  // 2. Discount Amount = Gross * Discount % / 100
  const expectedDisc = (gross * discPct) / 100.0;
  if (Math.abs(discAmt - expectedDisc) > 0.02) {
    reasons.push(`Discount Amount mismatch: calculated ${expectedDisc.toFixed(2)}, got ${discAmt.toFixed(2)}`);
  }

  // 3. Taxable Amount = Gross - Discount
  const expectedTaxable = gross - discAmt;
  if (Math.abs(taxable - expectedTaxable) > 0.02) {
    reasons.push(`Taxable Amount mismatch: calculated ${expectedTaxable.toFixed(2)}, got ${taxable.toFixed(2)}`);
  }

  // 4. CGST Amount = Taxable * CGST% / 100
  const expectedCgst = (taxable * cgstPct) / 100.0;
  if (Math.abs(cgstAmt - expectedCgst) > 0.02) {
    reasons.push(`CGST Amount mismatch: calculated ${expectedCgst.toFixed(2)}, got ${cgstAmt.toFixed(2)}`);
  }

  // 5. SGST Amount = Taxable * SGST% / 100
  const expectedSgst = (taxable * sgstPct) / 100.0;
  if (Math.abs(sgstAmt - expectedSgst) > 0.02) {
    reasons.push(`SGST Amount mismatch: calculated ${expectedSgst.toFixed(2)}, got ${sgstAmt.toFixed(2)}`);
  }

  // 6. Final Value = Taxable + CGST + SGST
  const expectedFinal = taxable + cgstAmt + sgstAmt;
  if (Math.abs(finalVal - expectedFinal) > 0.02) {
    reasons.push(`Final Value mismatch: calculated ${expectedFinal.toFixed(2)}, got ${finalVal.toFixed(2)}`);
  }

  const needsReview = reasons.length > 0;
  return {
    needs_review: needsReview,
    review_reason: needsReview ? reasons.join('; ') : null,
  };
}

// Helper function for fuzzy similarity
function similarity(s1, s2) {
  let longer = s1;
  let shorter = s2;
  if (s1.length < s2.length) {
    longer = s2;
    shorter = s1;
  }
  let longerLength = longer.length;
  if (longerLength === 0) {
    return 1.0;
  }
  return (longerLength - editDistance(longer, shorter)) / parseFloat(longerLength);
}

function editDistance(s1, s2) {
  s1 = s1.toLowerCase();
  s2 = s2.toLowerCase();
  let costs = new Array();
  for (let i = 0; i <= s1.length; i++) {
    let lastValue = i;
    for (let j = 0; j <= s2.length; j++) {
      if (i == 0)
        costs[j] = j;
      else {
        if (j > 0) {
          let newValue = costs[j - 1];
          if (s1.charAt(i - 1) != s2.charAt(j - 1))
            newValue = Math.min(Math.min(newValue, lastValue), costs[j]) + 1;
          costs[j - 1] = lastValue;
          lastValue = newValue;
        }
      }
    }
    if (i > 0)
      costs[s2.length] = lastValue;
  }
  return costs[s2.length];
}

// ==========================================
// API ENDPOINTS
// ==========================================

// GET /api/quotations (Retains alias for backwards compatibility)
app.get('/api/quotations', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 10;
    const offset = (page - 1) * limit;
    const search = req.query.search || req.query.q || '';
    const status = req.query.status || '';
    const documentType = req.query.document_type || req.query.type || req.query.doc_type || '';
    const vendorId = req.query.vendor_id || '';

    const conditions = ['1=1'];
    const params = [];
    let paramIndex = 1;

    if (search) {
      const colonIdx = search.indexOf(':');
      if (colonIdx > 0) {
        const prefix = search.substring(0, colonIdx).toLowerCase().trim();
        const term = search.substring(colonIdx + 1).trim();
        const pIdx = paramIndex++;
        params.push(`%${term}%`);

        if (['vendor', 'v'].includes(prefix)) {
          conditions.push(`v.name ILIKE $${pIdx}`);
        } else if (['customer', 'c'].includes(prefix)) {
          conditions.push(`c.name ILIKE $${pIdx}`);
        } else if (['brand', 'b'].includes(prefix)) {
          conditions.push(`EXISTS (SELECT 1 FROM billing_document_line_items li WHERE li.document_id = d.id AND li.brand ILIKE $${pIdx})`);
        } else if (['code', 'item_code', 'item'].includes(prefix)) {
          conditions.push(`EXISTS (SELECT 1 FROM billing_document_line_items li WHERE li.document_id = d.id AND li.item_code ILIKE $${pIdx})`);
        } else if (['hsn', 'hsn_code'].includes(prefix)) {
          conditions.push(`EXISTS (SELECT 1 FROM billing_document_line_items li WHERE li.document_id = d.id AND li.hsn_code ILIKE $${pIdx})`);
        } else if (['doc', 'document_no', 'number'].includes(prefix)) {
          conditions.push(`d.document_no ILIKE $${pIdx}`);
        } else if (['type', 'document_type'].includes(prefix)) {
          conditions.push(`(d.document_type ILIKE $${pIdx} OR (CASE d.document_type WHEN 'invoice_final' THEN 'tax invoice final' WHEN 'invoice_proforma' THEN 'proforma invoice' WHEN 'patient_account_statement' THEN 'patient account statement' WHEN 'purchase_order' THEN 'purchase order po' WHEN 'quotation' THEN 'quotation quote' ELSE d.document_type END) ILIKE $${pIdx})`);
        } else if (['desc', 'description'].includes(prefix)) {
          conditions.push(`EXISTS (SELECT 1 FROM billing_document_line_items li WHERE li.document_id = d.id AND li.description ILIKE $${pIdx})`);
        } else {
          conditions.push(`(d.document_no ILIKE $${pIdx} OR v.name ILIKE $${pIdx} OR c.name ILIKE $${pIdx} OR d.document_type ILIKE $${pIdx} OR (CASE d.document_type WHEN 'invoice_final' THEN 'tax invoice final' WHEN 'invoice_proforma' THEN 'proforma invoice' WHEN 'patient_account_statement' THEN 'patient account statement' WHEN 'purchase_order' THEN 'purchase order po' WHEN 'quotation' THEN 'quotation quote' ELSE d.document_type END) ILIKE $${pIdx} OR d.source_file ILIKE $${pIdx} OR EXISTS (SELECT 1 FROM billing_document_line_items li WHERE li.document_id = d.id AND (li.description ILIKE $${pIdx} OR li.brand ILIKE $${pIdx} OR li.item_code ILIKE $${pIdx} OR li.hsn_code ILIKE $${pIdx})))`);
        }
      } else {
        const pIdx = paramIndex++;
        params.push(`%${search}%`);
        conditions.push(`(d.document_no ILIKE $${pIdx} OR v.name ILIKE $${pIdx} OR c.name ILIKE $${pIdx} OR d.document_type ILIKE $${pIdx} OR (CASE d.document_type WHEN 'invoice_final' THEN 'tax invoice final' WHEN 'invoice_proforma' THEN 'proforma invoice' WHEN 'patient_account_statement' THEN 'patient account statement' WHEN 'purchase_order' THEN 'purchase order po' WHEN 'quotation' THEN 'quotation quote' ELSE d.document_type END) ILIKE $${pIdx} OR d.source_file ILIKE $${pIdx} OR EXISTS (SELECT 1 FROM billing_document_line_items li WHERE li.document_id = d.id AND (li.description ILIKE $${pIdx} OR li.brand ILIKE $${pIdx} OR li.item_code ILIKE $${pIdx} OR li.hsn_code ILIKE $${pIdx})))`);
      }
    }

    if (status && status !== 'all') {
      conditions.push(`LOWER(d.extraction_status) = LOWER($${paramIndex})`);
      params.push(status);
      paramIndex++;
    }

    if (documentType && documentType !== 'all') {
      const dtLower = documentType.toLowerCase().trim();
      if (dtLower === 'invoice' || dtLower === 'tax_invoice' || dtLower === 'tax invoice') {
        conditions.push(`(d.document_type IN ('invoice_final', 'invoice_proforma', 'invoice') OR d.document_type ILIKE '%invoice%')`);
      } else if (dtLower === 'invoice_final') {
        conditions.push(`d.document_type = 'invoice_final'`);
      } else if (dtLower === 'invoice_proforma') {
        conditions.push(`d.document_type = 'invoice_proforma'`);
      } else if (dtLower === 'patient_account_statement' || dtLower === 'patient_statement' || dtLower === 'patient statement') {
        conditions.push(`d.document_type IN ('patient_account_statement', 'patient_statement')`);
      } else if (dtLower === 'quotation' || dtLower === 'quote') {
        conditions.push(`d.document_type IN ('quotation', 'quote')`);
      } else if (dtLower === 'purchase_order' || dtLower === 'po') {
        conditions.push(`d.document_type IN ('purchase_order', 'po')`);
      } else {
        conditions.push(`(LOWER(d.document_type) = LOWER($${paramIndex}) OR d.document_type ILIKE $${paramIndex})`);
        params.push(`%${dtLower}%`);
        paramIndex++;
      }
    }

    if (vendorId && vendorId !== 'all') {
      conditions.push(`d.vendor_id = $${paramIndex}`);
      params.push(parseInt(vendorId));
      paramIndex++;
    }


    const whereClause = conditions.join(' AND ');

    const baseQuery = `
      FROM billing_documents d
      LEFT JOIN billing_vendors v ON d.vendor_id = v.id
      LEFT JOIN billing_customers c ON d.customer_id = c.id
      WHERE ${whereClause}
    `;

    // Get total count with same filters
    const countRes = await pool.query(`SELECT COUNT(*) ${baseQuery}`, params);
    const total = parseInt(countRes.rows[0].count);

    const dataParams = [...params, limit, offset];
    const dataRes = await pool.query(
      `SELECT d.id, d.vendor_id, v.name as vendor_name, d.document_no as quotation_no, d.document_date as quotation_date,
              c.name as customer_name, d.grand_total_final, d.extraction_status, d.document_type, d.source_file
       ${baseQuery}
       ORDER BY d.id DESC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      dataParams
    );

    res.json({
      items: dataRes.rows,
      total,
      page,
      limit,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database query failed' });
  }
});

// GET /api/quotations/:id
app.get('/api/quotations/:id', async (req, res) => {
  try {
    const { id } = req.params;
    
    const quoteRes = await pool.query(`
      SELECT d.id, d.document_type, d.document_no as quotation_no, d.document_date as quotation_date,
             d.validity_date, d.payment_terms, d.currency, d.enquiry_ref, d.enquiry_date,
             d.grand_total_taxable, d.total_discount, d.grand_total_cgst, d.grand_total_sgst, d.grand_total_final,
             d.grand_total_words, d.source_file, d.extraction_status, d.vendor_id, d.customer_id,
             v.name as vendor_name, v.gstin as vendor_gstin, v.address as vendor_address,
             c.name as customer_name, c.gstin as customer_gstin, c.address as customer_address
      FROM billing_documents d
      LEFT JOIN billing_vendors v ON d.vendor_id = v.id
      LEFT JOIN billing_customers c ON d.customer_id = c.id
      WHERE d.id = $1
    `, [id]);

    if (quoteRes.rows.length === 0) {
      return res.status(404).json({ error: 'Document not found' });
    }
    
    const itemsRes = await pool.query(
      'SELECT * FROM billing_document_line_items WHERE document_id = $1 ORDER BY line_no ASC, id ASC',
      [id]
    );

    res.json({
      ...quoteRes.rows[0],
      line_items: itemsRes.rows,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database query failed' });
  }
});

// GET /api/quotations/:id/line-items
app.get('/api/quotations/:id/line-items', async (req, res) => {
  try {
    const { id } = req.params;
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 20;
    const offset = (page - 1) * limit;

    const countRes = await pool.query(
      'SELECT COUNT(*) FROM billing_document_line_items WHERE document_id = $1',
      [id]
    );
    const total = parseInt(countRes.rows[0].count);

    const itemsRes = await pool.query(
      'SELECT * FROM billing_document_line_items WHERE document_id = $1 ORDER BY line_no ASC, id ASC LIMIT $2 OFFSET $3',
      [id, limit, offset]
    );

    res.json({
      items: itemsRes.rows,
      total,
      page,
      limit,
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database query failed' });
  }
});

// GET /api/review-queue
app.get('/api/review-queue', async (req, res) => {
  try {
    const queryText = `
      SELECT li.*, d.document_no as quotation_no, v.name as vendor_name
      FROM billing_document_line_items li
      JOIN billing_documents d ON li.document_id = d.id
      LEFT JOIN billing_vendors v ON d.vendor_id = v.id
      WHERE li.needs_review = true
      ORDER BY d.id DESC, li.line_no ASC, li.id ASC
    `;
    const result = await pool.query(queryText);
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database query failed' });
  }
});

// GET /api/search with whitespace normalization and line-item row matching
app.get('/api/search', async (req, res) => {
  const { q, vendor_id, document_type, type, doc_type, status, start_date, end_date } = req.query;
  const docTypeParam = document_type || type || doc_type || '';

  if (!q || !q.trim()) {
    return res.json({ items: [], suggestion: null });
  }

  try {
    const cleanQ = q.trim().toLowerCase();
    const normalizedQ = cleanQ.replace(/[\s\r\n]+/g, ' ');
    const tokens = cleanQ.split(/\s+/).filter(Boolean);
    const regexPattern = tokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[\\s\\r\\n\\-_]+');

    let sql = `
      SELECT DISTINCT d.id, d.document_type, d.document_no as quotation_no, d.document_date as quotation_date,
             d.vendor_id, v.name as vendor_name, c.name as customer_name, d.grand_total_final, d.extraction_status,
             d.classification_confidence
      FROM billing_documents d
      LEFT JOIN billing_vendors v ON d.vendor_id = v.id
      LEFT JOIN billing_customers c ON d.customer_id = c.id
      LEFT JOIN billing_document_line_items li ON li.document_id = d.id
      WHERE (
        REGEXP_REPLACE(d.document_no, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(v.name, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(c.name, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(d.source_file, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.description, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.item_code, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.brand, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.hsn_code, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.uom, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.packing, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.status_eta, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        li.description ~* $2 OR
        li.item_code ~* $2 OR
        d.grand_total_final::text ILIKE $1 OR
        li.qty::text ILIKE $1 OR
        li.rate::text ILIKE $1 OR
        li.taxable_amount::text ILIKE $1 OR
        li.final_value::text ILIKE $1
      )
    `;
    const params = [`%${normalizedQ}%`, regexPattern];

    if (status && status !== 'all') {
      params.push(status);
      sql += ` AND LOWER(d.extraction_status) = LOWER($${params.length})`;
    }

    if (vendor_id && vendor_id !== 'all') {
      params.push(vendor_id);
      sql += ` AND d.vendor_id = $${params.length}`;
    }

    if (docTypeParam && docTypeParam !== 'all') {
      const dtLower = docTypeParam.toLowerCase().trim();
      if (dtLower === 'invoice' || dtLower === 'tax_invoice' || dtLower === 'tax invoice') {
        sql += ` AND (d.document_type IN ('invoice_final', 'invoice_proforma', 'invoice') OR d.document_type ILIKE '%invoice%')`;
      } else if (dtLower === 'invoice_final') {
        sql += ` AND d.document_type = 'invoice_final'`;
      } else if (dtLower === 'invoice_proforma') {
        sql += ` AND d.document_type = 'invoice_proforma'`;
      } else if (dtLower === 'patient_account_statement' || dtLower === 'patient_statement' || dtLower === 'patient statement') {
        sql += ` AND d.document_type IN ('patient_account_statement', 'patient_statement')`;
      } else if (dtLower === 'quotation' || dtLower === 'quote') {
        sql += ` AND d.document_type IN ('quotation', 'quote')`;
      } else if (dtLower === 'purchase_order' || dtLower === 'po') {
        sql += ` AND d.document_type IN ('purchase_order', 'po')`;
      } else {
        params.push(`%${dtLower}%`);
        sql += ` AND (LOWER(d.document_type) = LOWER($${params.length}) OR d.document_type ILIKE $${params.length})`;
      }
    }

    if (start_date) {
      params.push(start_date);
      sql += ` AND d.document_date >= $${params.length}`;
    }
    if (end_date) {
      params.push(end_date);
      sql += ` AND d.document_date <= $${params.length}`;
    }


    sql += ' ORDER BY d.document_date DESC, d.id DESC LIMIT 50';

    const searchResults = await pool.query(sql, params);
    
    // Attach matching line item rows for each document result
    const docsWithMatchingItems = await Promise.all(searchResults.rows.map(async (doc) => {
      const itemsRes = await pool.query(`
        SELECT * FROM billing_document_line_items
        WHERE document_id = $1 AND (
          REGEXP_REPLACE(description, '[\\s\\r\\n]+', ' ', 'g') ILIKE $2 OR
          REGEXP_REPLACE(item_code, '[\\s\\r\\n]+', ' ', 'g') ILIKE $2 OR
          REGEXP_REPLACE(brand, '[\\s\\r\\n]+', ' ', 'g') ILIKE $2 OR
          REGEXP_REPLACE(hsn_code, '[\\s\\r\\n]+', ' ', 'g') ILIKE $2 OR
          REGEXP_REPLACE(uom, '[\\s\\r\\n]+', ' ', 'g') ILIKE $2 OR
          REGEXP_REPLACE(packing, '[\\s\\r\\n]+', ' ', 'g') ILIKE $2 OR
          REGEXP_REPLACE(status_eta, '[\\s\\r\\n]+', ' ', 'g') ILIKE $2 OR
          description ~* $3 OR
          item_code ~* $3 OR
          qty::text ILIKE $2 OR
          rate::text ILIKE $2 OR
          taxable_amount::text ILIKE $2 OR
          final_value::text ILIKE $2
        )
        ORDER BY line_no ASC, id ASC
      `, [doc.id, `%${normalizedQ}%`, regexPattern]);

      return {
        ...doc,
        matching_line_items: itemsRes.rows
      };
    }));

    res.json({
      items: docsWithMatchingItems,
      suggestion: null,
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// GET /api/search/line-items (universal line-item search across all documents)
app.get('/api/search/line-items', async (req, res) => {
  const { q } = req.query;
  if (!q || !q.trim()) {
    return res.json({ items: [] });
  }

  try {
    const cleanQ = q.trim().toLowerCase();
    const normalizedQ = cleanQ.replace(/[\s\r\n]+/g, ' ');
    const tokens = cleanQ.split(/\s+/).filter(Boolean);
    const regexPattern = tokens.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('[\\s\\r\\n\\-_]+');

    const sql = `
      SELECT li.*, d.document_no as quotation_no, d.document_date as quotation_date, d.document_type,
             d.source_file, v.name as vendor_name, c.name as customer_name, d.grand_total_final
      FROM billing_document_line_items li
      JOIN billing_documents d ON li.document_id = d.id
      LEFT JOIN billing_vendors v ON d.vendor_id = v.id
      LEFT JOIN billing_customers c ON d.customer_id = c.id
      WHERE (
        REGEXP_REPLACE(li.description, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.item_code, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.brand, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.hsn_code, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.uom, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.packing, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        REGEXP_REPLACE(li.status_eta, '[\\s\\r\\n]+', ' ', 'g') ILIKE $1 OR
        li.description ~* $2 OR
        li.item_code ~* $2 OR
        li.line_no::text ILIKE $1 OR
        li.qty::text ILIKE $1 OR
        li.rate::text ILIKE $1 OR
        li.gross_amount::text ILIKE $1 OR
        li.taxable_amount::text ILIKE $1 OR
        li.final_value::text ILIKE $1
      )
      ORDER BY d.id DESC, li.line_no ASC
      LIMIT 100
    `;

    const result = await pool.query(sql, [`%${normalizedQ}%`, regexPattern]);
    res.json({ items: result.rows });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// POST /api/search/feedback (records feedback and handles promotion)
app.post('/api/search/feedback', async (req, res) => {
  const { alias, canonical, accepted } = req.body;
  if (!alias || !canonical || !accepted) {
    return res.status(400).json({ error: 'Missing feedback fields' });
  }

  try {
    const aliasLower = alias.trim().toLowerCase();
    const canonicalLower = canonical.trim().toLowerCase();

    const existAlias = await pool.query('SELECT 1 FROM search_aliases WHERE alias = $1 AND canonical = $2', [aliasLower, canonicalLower]);
    if (existAlias.rows.length > 0) {
      return res.json({ promoted: true });
    }

    const learnedResult = await pool.query('SELECT * FROM learned_aliases WHERE alias = $1 AND canonical_name = $2', [aliasLower, canonicalLower]);
    if (learnedResult.rows.length === 0) {
      await pool.query('INSERT INTO learned_aliases (alias, canonical_name, category, occurrence_count, confidence, learned_at, updated_at) VALUES ($1, $2, $3, $4, $5, NOW(), NOW())', [aliasLower, canonicalLower, 'global', 1, 1.0]);
      res.json({ promoted: false, count: 1 });
    } else {
      const newCount = learnedResult.rows[0].occurrence_count + 1;
      if (newCount >= 3) {
        await pool.query('INSERT INTO search_aliases (alias, canonical, scope, source, confidence, created_at) VALUES ($1, $2, $3, $4, $5, NOW())', [aliasLower, canonicalLower, 'global', 'learned', 0.9]);
        await pool.query('DELETE FROM learned_aliases WHERE alias = $1 AND canonical_name = $2', [aliasLower, canonicalLower]);
        res.json({ promoted: true, count: newCount });
      } else {
        await pool.query('UPDATE learned_aliases SET occurrence_count = $1 WHERE alias = $2 AND canonical_name = $3', [newCount, aliasLower, canonicalLower]);
        res.json({ promoted: false, count: newCount });
      }
    }
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// POST /api/upload
app.post('/api/upload', upload.single('file'), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No file uploaded' });
  }

  const filePath = req.file.path;
  const projectRoot = path.join(__dirname, '..');
  const pythonBinary = path.join(projectRoot, '.venv', 'bin', 'python');

  const cmd = `"${pythonBinary}" -m app.quotation_extraction.run "${filePath}"`;

  exec(cmd, { cwd: projectRoot, timeout: 600000, maxBuffer: 50 * 1024 * 1024 }, (error, stdout, stderr) => {
    if (error) {
      console.error(`Exec error: ${error}`);
      console.error(`Stderr: ${stderr}`);
      return res.status(500).json({ error: 'Pipeline processing failed', detail: stderr || error.message });
    }

    console.log(`Pipeline stdout: ${stdout}`);

    const match = stdout.match(/JSON_OUTPUT:(.*)/);
    if (!match) {
      return res.status(500).json({ error: 'Pipeline completed but produced no readable JSON output' });
    }

    try {
      const parsed = JSON.parse(match[1]);
      if (parsed.status === 'success' && parsed.quotations && parsed.quotations.length > 0) {
        const primaryQuote = parsed.quotations[0];
        res.json({
          id: primaryQuote.id,
          is_duplicate: primaryQuote.is_duplicate || false,
          message: primaryQuote.message || (primaryQuote.is_duplicate ? `Duplicate document detected (matches existing Document #${primaryQuote.id} with identical content and extracted values).` : 'Document processed successfully'),
          extraction_status: primaryQuote.extraction_status,
          quotations: parsed.quotations
        });
      } else {
        res.status(500).json({ error: 'Pipeline failed or returned empty results', detail: parsed.message });
      }
    } catch (e) {
      console.error(`Failed to parse pipeline output: ${e}`);
      res.status(500).json({ error: 'Failed to parse pipeline output JSON' });
    }
  });
});

// POST /api/quotations/ingest-text
app.post('/api/quotations/ingest-text', async (req, res) => {
  const { raw_text } = req.body;
  if (!raw_text || !raw_text.trim()) {
    return res.status(400).json({ error: 'No raw text provided' });
  }

  const projectRoot = path.join(__dirname, '..');
  const pythonBinary = path.join(projectRoot, '.venv', 'bin', 'python');
  const tempFilePath = path.join(inputDir, `raw_ingest_${Date.now()}.txt`);

  try {
    fs.writeFileSync(tempFilePath, raw_text, 'utf-8');
  } catch (fsErr) {
    return res.status(500).json({ error: 'Failed to write temporary text file', detail: fsErr.message });
  }

  const cmd = `"${pythonBinary}" -m app.quotation_extraction.text_ingester "${tempFilePath}"`;

  exec(cmd, { cwd: projectRoot }, (error, stdout, stderr) => {
    if (fs.existsSync(tempFilePath)) {
      try { fs.unlinkSync(tempFilePath); } catch (e) {}
    }

    if (error) {
      console.error(`Exec error: ${error}`);
      console.error(`Stderr: ${stderr}`);
      return res.status(500).json({ error: 'Text ingestion failed', detail: stderr || error.message });
    }

    const match = stdout.match(/JSON_OUTPUT:(.*)/);
    if (!match) {
      return res.status(500).json({ error: 'Text ingestion completed but produced no readable JSON output' });
    }

    try {
      const parsed = JSON.parse(match[1]);
      if (parsed.status === 'success' && parsed.quotations && parsed.quotations.length > 0) {
        const primaryQuote = parsed.quotations[0];
        res.json({
          id: primaryQuote.id,
          extraction_status: primaryQuote.extraction_status,
          quotations: parsed.quotations
        });
      } else {
        res.status(500).json({ error: 'Text ingestion returned no valid documents', detail: parsed.message });
      }
    } catch (e) {
      console.error(`Failed to parse text ingestion output: ${e}`);
      res.status(500).json({ error: 'Failed to parse text ingestion output JSON' });
    }
  });
});

// PATCH /api/line-items/:id
app.patch('/api/line-items/:id', async (req, res) => {
  const { id } = req.params;
  const fields = req.body;

  if (Object.keys(fields).length === 0) {
    return res.status(400).json({ error: 'No fields provided for update' });
  }

  try {
    const currentRes = await pool.query('SELECT * FROM billing_document_line_items WHERE id = $1', [id]);
    if (currentRes.rows.length === 0) {
      return res.status(404).json({ error: 'Line item not found' });
    }

    const fs = require('fs');
    const path = require('path');
    const datasetPath = path.join(__dirname, '../app/db/review_dataset.jsonl');
    const dir = path.dirname(datasetPath);
    if (!fs.existsSync(dir)){
      fs.mkdirSync(dir, { recursive: true });
    }

    for (const [key, val] of Object.entries(fields)) {
      const originalValue = currentRes.rows[0][key];
      if (originalValue !== undefined && String(originalValue) !== String(val)) {
        const logEntry = {
          timestamp: new Date().toISOString(),
          line_item_id: id,
          document_id: currentRes.rows[0].document_id,
          field: key,
          original_value: originalValue,
          corrected_value: val,
          document_crop: currentRes.rows[0].bounding_box || null
        };
        fs.appendFileSync(datasetPath, JSON.stringify(logEntry) + '\n', 'utf8');
      }
    }

    const mergedItem = { ...currentRes.rows[0], ...fields };
    const validation = validateRowArithmetic(mergedItem);

    const setClauses = [];
    const params = [];
    let pIdx = 1;

    for (const [key, val] of Object.entries(fields)) {
      setClauses.push(`${key} = $${pIdx}`);
      params.push(val);
      pIdx++;
    }

    setClauses.push(`needs_review = $${pIdx}`);
    params.push(validation.needs_review);
    pIdx++;

    setClauses.push(`review_reason = $${pIdx}`);
    params.push(validation.review_reason);
    pIdx++;

    params.push(id);
    const queryText = `
      UPDATE billing_document_line_items
      SET ${setClauses.join(', ')}
      WHERE id = $${pIdx}
      RETURNING *
    `;

    const updateRes = await pool.query(queryText, params);
    const updatedRow = updateRes.rows[0];

    const docId = updatedRow.document_id;
    const countRes = await pool.query(
      'SELECT COUNT(*) FROM billing_document_line_items WHERE document_id = $1 AND needs_review = true',
      [docId]
    );
    const remainingFlagged = parseInt(countRes.rows[0].count);

    let parentStatus = 'ok';
    if (remainingFlagged > 0) {
      parentStatus = 'needs_review';
    }

    await pool.query(
      'UPDATE billing_documents SET extraction_status = $1 WHERE id = $2',
      [parentStatus, docId]
    );

    // Trigger background active learning sync so learned memory updates in real-time
    const { exec } = require('child_process');
    const pythonPath = path.join(__dirname, '../.venv/bin/python');
    const syncCmd = `"${pythonPath}" -m app.learning.sync_memory ${docId}`;
    exec(syncCmd, (syncErr) => {
      if (syncErr) console.warn('Active learning sync warning:', syncErr.message);
    });

    res.json({
      line_item: updatedRow,
      quotation_status: parentStatus,
      remaining_flagged: remainingFlagged
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Database update failed' });
  }
});

// DELETE /api/quotations/:id - Delete single document and its line items
app.delete('/api/quotations/:id', async (req, res) => {
  try {
    const { id } = req.params;
    await pool.query('DELETE FROM billing_document_line_items WHERE document_id = $1', [id]);
    const deleteRes = await pool.query('DELETE FROM billing_documents WHERE id = $1 RETURNING *', [id]);
    if (deleteRes.rows.length === 0) {
      return res.status(404).json({ error: 'Document not found' });
    }
    res.json({ success: true, message: `Document #${id} deleted successfully` });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// POST /api/quotations/batch-delete - Delete multiple documents at once
app.post('/api/quotations/batch-delete', async (req, res) => {
  try {
    const { ids } = req.body;
    if (!ids || !Array.isArray(ids) || ids.length === 0) {
      return res.status(400).json({ error: 'No document IDs provided for deletion' });
    }
    await pool.query('DELETE FROM billing_document_line_items WHERE document_id = ANY($1::int[])', [ids]);
    const deleteRes = await pool.query('DELETE FROM billing_documents WHERE id = ANY($1::int[]) RETURNING id', [ids]);
    res.json({ success: true, deleted_count: deleteRes.rows.length, deleted_ids: deleteRes.rows.map(r => r.id) });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message });
  }
});

// GET /api/stats - Dashboard analytics and aggregated database metrics
app.get('/api/stats', async (req, res) => {
  try {
    const totalRes = await pool.query('SELECT COUNT(*) as total, COALESCE(SUM(grand_total_final), 0) as total_value FROM billing_documents');
    const totalDocs = parseInt(totalRes.rows[0].total) || 0;
    const totalValue = parseFloat(totalRes.rows[0].total_value) || 0;

    const quarantineRes = await pool.query("SELECT COUNT(*) as quarantined FROM billing_documents WHERE extraction_status = 'needs_review'");
    const quarantinedCount = parseInt(quarantineRes.rows[0].quarantined) || 0;

    const byTypeRes = await pool.query('SELECT document_type, COUNT(*) as count FROM billing_documents GROUP BY document_type ORDER BY count DESC');
    const by_type = {};
    let invoiceCount = 0;

    byTypeRes.rows.forEach(r => {
      const typeKey = r.document_type || 'generic';
      const countNum = parseInt(r.count);
      by_type[typeKey] = countNum;
      if (['invoice_final', 'invoice_proforma', 'purchase_order', 'patient_account_statement'].includes(typeKey)) {
        invoiceCount += countNum;
      }
    });

    const recentRes = await pool.query(`
      SELECT d.id, d.document_no, d.document_type, d.document_date, d.grand_total_final, d.extraction_status, d.source_file,
             v.name as vendor_name, c.name as customer_name
      FROM billing_documents d
      LEFT JOIN billing_vendors v ON d.vendor_id = v.id
      LEFT JOIN billing_customers c ON d.customer_id = c.id
      ORDER BY d.id DESC
      LIMIT 50
    `);


    res.json({
      total_documents: totalDocs,
      total_value_extracted: totalValue,
      extracted_invoices: invoiceCount,
      quarantined_count: quarantinedCount,
      by_type,
      recent_documents: recentRes.rows
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch dashboard stats' });
  }
});

// GET /api/vendors - List all vendors
app.get('/api/vendors', async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT id, id as vendor_id, name as vendor_name, name, gstin, state, phone, email, address, created_at, updated_at
      FROM billing_vendors
      ORDER BY name ASC
    `);
    res.json(result.rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch vendors' });
  }
});

// GET /api/vendors/:id - Fetch vendor by ID
app.get('/api/vendors/:id', async (req, res) => {
  try {
    const { id } = req.params;
    const result = await pool.query(`
      SELECT id, id as vendor_id, name as vendor_name, name, gstin, state, phone, email, address, created_at, updated_at
      FROM billing_vendors
      WHERE id = $1
    `, [id]);
    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Vendor not found' });
    }
    res.json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'Failed to fetch vendor detail' });
  }
});

// POST /api/vendors - Create vendor
app.post('/api/vendors', async (req, res) => {
  try {
    const { vendor_name, name, address, gstin, state, phone, email } = req.body;
    const vName = (vendor_name || name || '').trim();
    if (!vName) {
      return res.status(400).json({ error: 'Vendor name is required' });
    }
    const result = await pool.query(`
      INSERT INTO billing_vendors (name, gstin, state, phone, email, address, created_at, updated_at)
      VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
      RETURNING id, id as vendor_id, name as vendor_name, name, gstin, state, phone, email, address, created_at, updated_at
    `, [vName, gstin ? gstin.trim() : null, state || null, phone || null, email || null, address || null]);
    res.status(201).json(result.rows[0]);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: err.message || 'Failed to create vendor' });
  }
});

// GET /api/ghost-suggest - Universal Ghost-Text completion
app.get('/api/ghost-suggest', async (req, res) => {
  const { q } = req.query;
  if (!q || !q.trim()) {
    return res.json({ suggestion: null, match: null });
  }

  const rawQuery = q.trim();
  const lowerQuery = rawQuery.toLowerCase();

  try {
    const colonIdx = rawQuery.indexOf(':');
    if (colonIdx > 0) {
      const colPrefix = rawQuery.substring(0, colonIdx).toLowerCase().trim();
      const searchTerm = rawQuery.substring(colonIdx + 1).trim();

      if (searchTerm.length > 0) {
        let fieldQuery = null;
        let canonicalPrefix = colPrefix;

        if (['vendor', 'v'].includes(colPrefix)) {
          canonicalPrefix = 'vendor';
          fieldQuery = pool.query(
            `SELECT name as val, COUNT(*) as freq FROM billing_vendors WHERE LOWER(name) LIKE $1 GROUP BY name ORDER BY (LOWER(name) LIKE $2) DESC, freq DESC, LENGTH(name) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        } else if (['customer', 'c'].includes(colPrefix)) {
          canonicalPrefix = 'customer';
          fieldQuery = pool.query(
            `SELECT name as val, COUNT(*) as freq FROM billing_customers WHERE LOWER(name) LIKE $1 GROUP BY name ORDER BY (LOWER(name) LIKE $2) DESC, freq DESC, LENGTH(name) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        } else if (['brand', 'b'].includes(colPrefix)) {
          canonicalPrefix = 'brand';
          fieldQuery = pool.query(
            `SELECT brand as val, COUNT(*) as freq FROM billing_document_line_items WHERE brand IS NOT NULL AND brand != '' AND LOWER(brand) LIKE $1 GROUP BY brand ORDER BY (LOWER(brand) LIKE $2) DESC, freq DESC, LENGTH(brand) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        } else if (['code', 'item_code', 'item'].includes(colPrefix)) {
          canonicalPrefix = 'code';
          fieldQuery = pool.query(
            `SELECT item_code as val, COUNT(*) as freq FROM billing_document_line_items WHERE item_code IS NOT NULL AND item_code != '' AND LOWER(item_code) LIKE $1 GROUP BY item_code ORDER BY (LOWER(item_code) LIKE $2) DESC, freq DESC, LENGTH(item_code) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        } else if (['hsn', 'hsn_code'].includes(colPrefix)) {
          canonicalPrefix = 'hsn';
          fieldQuery = pool.query(
            `SELECT hsn_code as val, COUNT(*) as freq FROM billing_document_line_items WHERE hsn_code IS NOT NULL AND hsn_code != '' AND LOWER(hsn_code) LIKE $1 GROUP BY hsn_code ORDER BY (LOWER(hsn_code) LIKE $2) DESC, freq DESC, LENGTH(hsn_code) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        } else if (['doc', 'document_no', 'number'].includes(colPrefix)) {
          canonicalPrefix = 'doc';
          fieldQuery = pool.query(
            `SELECT document_no as val, COUNT(*) as freq FROM billing_documents WHERE document_no IS NOT NULL AND document_no != '' AND LOWER(document_no) LIKE $1 GROUP BY document_no ORDER BY (LOWER(document_no) LIKE $2) DESC, freq DESC, LENGTH(document_no) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        } else if (['type', 'document_type'].includes(colPrefix)) {
          canonicalPrefix = 'type';
          fieldQuery = pool.query(
            `SELECT document_type as val, COUNT(*) as freq FROM billing_documents WHERE document_type IS NOT NULL AND document_type != '' AND LOWER(document_type) LIKE $1 GROUP BY document_type ORDER BY (LOWER(document_type) LIKE $2) DESC, freq DESC, LENGTH(document_type) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        } else if (['desc', 'description'].includes(colPrefix)) {
          canonicalPrefix = 'desc';
          fieldQuery = pool.query(
            `SELECT description as val, COUNT(*) as freq FROM billing_document_line_items WHERE description IS NOT NULL AND description != '' AND LOWER(description) LIKE $1 GROUP BY description ORDER BY (LOWER(description) LIKE $2) DESC, freq DESC, LENGTH(description) ASC LIMIT 1`,
            [`%${searchTerm.toLowerCase()}%`, `${searchTerm.toLowerCase()}%`]
          );
        }

        if (fieldQuery) {
          const result = await fieldQuery;
          if (result.rows.length > 0 && result.rows[0].val) {
            const realVal = result.rows[0].val;
            return res.json({
              suggestion: `${canonicalPrefix}:${realVal}`,
              matchedValue: realVal,
              prefix: `${canonicalPrefix}:`
            });
          }
        }
      }
    }

    // Free-Text Ghost Suggestion across all corpus fields
    const searchPattern = `%${lowerQuery}%`;
    const prefixPattern = `${lowerQuery}%`;

    const unionQuery = `
      WITH candidates AS (
        SELECT name AS val, 'vendor' AS field, COUNT(*) AS freq FROM billing_vendors WHERE LOWER(name) LIKE $1 GROUP BY name
        UNION ALL
        SELECT name AS val, 'customer' AS field, COUNT(*) AS freq FROM billing_customers WHERE LOWER(name) LIKE $1 GROUP BY name
        UNION ALL
        SELECT brand AS val, 'brand' AS field, COUNT(*) AS freq FROM billing_document_line_items WHERE brand IS NOT NULL AND brand != '' AND LOWER(brand) LIKE $1 GROUP BY brand
        UNION ALL
        SELECT item_code AS val, 'item_code' AS field, COUNT(*) AS freq FROM billing_document_line_items WHERE item_code IS NOT NULL AND item_code != '' AND LOWER(item_code) LIKE $1 GROUP BY item_code
        UNION ALL
        SELECT description AS val, 'description' AS field, COUNT(*) AS freq FROM billing_document_line_items WHERE description IS NOT NULL AND description != '' AND LOWER(description) LIKE $1 GROUP BY description
        UNION ALL
        SELECT hsn_code AS val, 'hsn_code' AS field, COUNT(*) AS freq FROM billing_document_line_items WHERE hsn_code IS NOT NULL AND hsn_code != '' AND LOWER(hsn_code) LIKE $1 GROUP BY hsn_code
        UNION ALL
        SELECT document_no AS val, 'document_no' AS field, COUNT(*) AS freq FROM billing_documents WHERE document_no IS NOT NULL AND document_no != '' AND LOWER(document_no) LIKE $1 GROUP BY document_no
        UNION ALL
        SELECT status_eta AS val, 'status_eta' AS field, COUNT(*) AS freq FROM billing_document_line_items WHERE status_eta IS NOT NULL AND status_eta != '' AND LOWER(status_eta) LIKE $1 GROUP BY status_eta
      )
      SELECT val, field, freq
      FROM candidates
      ORDER BY (LOWER(val) LIKE $2) DESC, freq DESC, LENGTH(val) ASC
      LIMIT 1
    `;

    const result = await pool.query(unionQuery, [searchPattern, prefixPattern]);

    if (result.rows.length > 0 && result.rows[0].val) {
      const realVal = result.rows[0].val;
      return res.json({
        suggestion: realVal,
        matchedValue: realVal,
        field: result.rows[0].field
      });
    }

    return res.json({ suggestion: null, match: null });
  } catch (err) {
    console.error('Ghost suggestion error:', err);
    return res.json({ suggestion: null, match: null });
  }
});

// Serve Compiled React Frontend (Production & Docker Mode)
const frontendDistPath = path.join(__dirname, '../frontend/dist');
if (fs.existsSync(frontendDistPath)) {
  app.use(express.static(frontendDistPath));
  app.get('*', (req, res, next) => {
    if (req.path.startsWith('/api') || req.path.startsWith('/files')) {
      return next();
    }
    res.sendFile(path.join(frontendDistPath, 'index.html'));
  });
}

// Start Server
app.listen(PORT, () => {
  console.log(`Express API server running on port ${PORT}`);
});

