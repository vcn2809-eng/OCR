import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Upload, FileText, CheckCircle, AlertTriangle, Loader2, Trash2, ArrowRight, Layers, FileCode, Check, Eye, Code, FileSpreadsheet, Download } from 'lucide-react'
import { useIngestion } from '../context/IngestionContext.jsx'
import quotationApi from '../api/quotationClient.js'
import { useToast } from '../ToastContext.jsx'
import { formatDocumentType, getDocTypeColor, getFileFormat, getFileFormatBadgeStyle, formatIndianCurrency } from './QuotationsList.jsx'
import { exportTableToExcel } from '../utils/excelExporter.js'

export default function UploadPage() {
  const [activeTab, setActiveTab] = useState('files') // 'files' | 'raw_text'
  const [rawTextInput, setRawTextInput] = useState('')
  const [textIngesting, setTextIngesting] = useState(false)
  const [textExtractedDoc, setTextExtractedDoc] = useState(null)
  
  const {
    filesQueue,
    ingesting,
    currentIndex,
    batchCompleted,
    batchStats,
    lastExtractedDoc,
    rateLimitEnabled,
    toggleRateLimit,
    addFilesToQueue,
    removeFileFromQueue,
    clearQueue,
    startBatchIngestion
  } = useIngestion()

  const toast = useToast()

  const handleExportUploadedDocExcel = (doc) => {
    if (!doc || !doc.line_items) return
    const cols = [
      { header: 'Line #', key: 'line_no' },
      { header: 'Item Code', key: 'item_code' },
      { header: 'Description', key: 'description' },
      { header: 'Quantity', key: 'qty' },
      { header: 'Rate', key: 'rate' },
      { header: 'Final Amount', key: 'final_value' },
    ]
    exportTableToExcel({ filename: `extracted_doc_${doc.id}_items`, columns: cols, data: doc.line_items })
  }

  const handleExportBatchListExcel = (allDocs) => {
    if (!allDocs || allDocs.length === 0) return
    const cols = [
      { header: 'Doc ID', key: 'id' },
      { header: 'Invoice / Quotation No', key: 'quotation_no' },
      { header: 'Vendor Name', key: 'vendor_name' },
      { header: 'Customer Name', key: 'customer_name' },
      { header: 'Extraction Status', key: 'extraction_status' },
    ]
    exportTableToExcel({ filename: `batch_ingested_documents`, columns: cols, data: allDocs })
  }

  const handleFileChange = (e) => {
    addFilesToQueue(e.target.files)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  const handleDrop = (e) => {
    e.preventDefault()
    addFilesToQueue(e.dataTransfer.files)
  }

  const handleDirectTextIngest = async () => {
    if (!rawTextInput || !rawTextInput.trim() || textIngesting) return

    setTextIngesting(true)
    setTextExtractedDoc(null)

    try {
      const res = await quotationApi.ingestTextData(rawTextInput)
      const isOk = res.quotations && res.quotations.length > 0
      
      if (isOk) {
        const firstQuote = res.quotations[0]
        let fullDetail = firstQuote
        try {
          if (firstQuote.id) {
            fullDetail = await quotationApi.getQuotation(firstQuote.id)
          }
        } catch (detailErr) {
          console.warn('Could not fetch detail:', detailErr)
        }

        setTextExtractedDoc(fullDetail)
        toast(`Successfully ingested ${res.quotations.length} document(s) from pasted text!`, 'success')
      } else {
        toast('No document items could be extracted from the pasted text.', 'error')
      }
    } catch (err) {
      toast(`Text ingestion error: ${err.message}`, 'error')
    } finally {
      setTextIngesting(false)
    }
  }

  const loadSampleCSV = () => {
    setRawTextInput(`filename,json_data,ocred_text
invoice_51109301.pdf,"{
  ""invoice_no"": ""51109301"",
  ""date_of_issue"": ""03/07/2023"",
  ""seller"": {
    ""name"": ""TechVision Distributors Pvt Ltd"",
    ""tax_id"": ""27AABCT1234F1Z5""
  },
  ""client"": {
    ""name"": ""Raj Electronics Pvt Ltd"",
    ""tax_id"": ""901-95-4704""
  },
  ""items"": [
    {
      ""item_no"": ""1."",
      ""description"": ""Garmin Fenix 7 Solar Multisport GPS"",
      ""quantity"": ""9.00"",
      ""net_price"": ""74,120.00"",
      ""net_worth"": ""667,080.00"",
      ""gross_worth"": ""733,788.00""
    },
    {
      ""item_no"": ""2."",
      ""description"": ""Apple Watch Series 9 GPS 45mm Midnight"",
      ""quantity"": ""8.00"",
      ""net_price"": ""52,083.00"",
      ""net_worth"": ""416,664.00"",
      ""gross_worth"": ""458,330.40""
    }
  ],
  ""summary"": {
    ""net_worth"": ""1,676,976.00"",
    ""gross_worth"": ""1,844,673.60""
  }
}"`)
  }

  const loadSampleOCRStatement = () => {
    setRawTextInput(`Lilavati Hospital
Bandra Reclamation, Mumbai, Maharashtra 400050
NPI: 1482950384 | Phone: (555) 019-8372

PATIENT ACCOUNT STATEMENT

Statement Date: 05/22/2026 Primary Insurance: HDFC ERGO General Insurance
Guarantor No: MRN-1039485 Group No: GRP-2960
Patient Name: Amit Singh Primary Diagnosis: Hyperlipidemia
Date of Birth: 1978-11-03 ICD-10 Code: E78.5

Date CPT Description Charges
05/22/2026 0260 IV Therapy $243.00
05/22/2026 99283 Emergency Room Level 3 $801.00
05/22/2026 36415 Venipuncture $15.00
05/22/2026 0250 Pharmacy Services $393.00
05/22/2026 80076 Hepatic Function Panel $56.00

Total Billed Charges: $1508.00
Insurance Adjustments: -$1309.00
PATIENT AMOUNT DUE: $199.00`)
  }

  return (
    <div style={{ maxWidth: 860, margin: '30px auto' }}>
      <div className="mb-4 text-center">
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: 0, background: 'linear-gradient(135deg, #00d4ff, #a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          Document Ingestion & Extraction Portal
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 6 }}>
          Upload files or paste raw CSV/JSON/OCR text directly to extract, validate, and store itemization lines
        </p>
      </div>

      {/* Mode Switcher Tabs */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 10 }}>
        <button
          type="button"
          className={`btn ${activeTab === 'files' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('files')}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, borderRadius: 8, padding: '10px 18px', fontSize: 14 }}
        >
          <Upload size={16} /> File Upload / Batch Files
        </button>
        <button
          type="button"
          className={`btn ${activeTab === 'raw_text' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('raw_text')}
          style={{ display: 'inline-flex', alignItems: 'center', gap: 8, borderRadius: 8, padding: '10px 18px', fontSize: 14 }}
        >
          <Code size={16} /> Paste Raw Text / CSV / JSON Data
        </button>
      </div>

      {/* TAB 1: FILE UPLOAD / BATCH FILES */}
      {activeTab === 'files' && (
        <>
          {/* Drag & Drop Upload Dropzone */}
          <div className="card" style={{ padding: '28px', marginBottom: 20 }}>
            <div
              style={{
                border: '2px dashed var(--border)',
                borderRadius: 12,
                padding: '44px 32px',
                textAlign: 'center',
                background: 'rgba(0, 212, 255, 0.01)',
                cursor: ingesting ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
              }}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              onClick={() => !ingesting && document.getElementById('batch-file-input').click()}
              className="drop-zone"
            >
              <Upload size={48} style={{ color: 'var(--cyan)', marginBottom: 14 }} />
              <div style={{ fontSize: 17, fontWeight: 700, color: '#fff', marginBottom: 6 }}>
                Drag & Drop your document or image files here
              </div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10 }}>
                or click to select single or multiple files from your computer
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                Supports all file types: PDF, Excel (XLSX/XLS/CSV), and Images (JPG/PNG/BMP/TIFF)
              </div>
              <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={(e) => e.stopPropagation()}>
                <button
                  type="button"
                  onClick={toggleRateLimit}
                  className="btn btn-sm"
                  style={{
                    borderRadius: 20,
                    padding: '4px 14px',
                    fontSize: 12,
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    cursor: 'pointer',
                    background: rateLimitEnabled ? 'rgba(0, 212, 255, 0.12)' : 'rgba(234, 179, 8, 0.12)',
                    color: rateLimitEnabled ? 'var(--cyan)' : 'var(--yellow)',
                    border: `1px solid ${rateLimitEnabled ? 'rgba(0, 212, 255, 0.4)' : 'rgba(234, 179, 8, 0.4)'}`,
                    transition: 'all 0.2s'
                  }}
                  title="Click to turn Batch Rate Limit ON or OFF"
                >
                  <span className="badge-dot" style={{ background: rateLimitEnabled ? 'var(--cyan)' : 'var(--yellow)' }} />
                  {rateLimitEnabled ? '⚡ Batch Rate Limit: ON (Max 15 files)' : '🔓 Batch Rate Limit: OFF (Unlimited files)'}
                </button>
              </div>
              <input
                id="batch-file-input"
                type="file"
                multiple
                disabled={ingesting}
                onChange={handleFileChange}
                accept="*"
                style={{ display: 'none' }}
              />
            </div>
          </div>

          {/* Live Ingestion Queue Card */}
          {filesQueue.length > 0 && (
            <div className="card" style={{ padding: 24, marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, borderBottom: '1px solid var(--border)', paddingBottom: 12, flexWrap: 'wrap', gap: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Layers size={18} style={{ color: 'var(--cyan)' }} />
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
                    Selected Files Queue ({filesQueue.length})
                  </h3>
                </div>
                {!ingesting && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={toggleRateLimit}
                      className="btn btn-sm"
                      style={{
                        borderRadius: 20,
                        padding: '3px 10px',
                        fontSize: 11,
                        fontWeight: 600,
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        background: rateLimitEnabled ? 'rgba(0, 212, 255, 0.1)' : 'rgba(234, 179, 8, 0.1)',
                        color: rateLimitEnabled ? 'var(--cyan)' : 'var(--yellow)',
                        border: `1px solid ${rateLimitEnabled ? 'rgba(0, 212, 255, 0.3)' : 'rgba(234, 179, 8, 0.3)'}`
                      }}
                    >
                      {rateLimitEnabled ? '⚡ Limit: ON (15)' : '🔓 Limit: OFF'}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => document.getElementById('batch-file-input').click()}
                    >
                      + Select More Files
                    </button>
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      onClick={clearQueue}
                      style={{ color: 'var(--red)' }}
                    >
                      Clear Queue
                    </button>
                  </div>
                )}
              </div>

              {/* Files List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 360, overflowY: 'auto', paddingRight: 4 }}>
                {filesQueue.map((item, idx) => {
                  const isCurrent = currentIndex === idx
                  const formatStyle = getFileFormatBadgeStyle(item.format)

                  return (
                    <div
                      key={item.id}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        background: isCurrent ? 'rgba(0, 212, 255, 0.04)' : 'rgba(255, 255, 255, 0.02)',
                        border: `1px solid ${isCurrent ? 'rgba(0, 212, 255, 0.3)' : 'var(--border)'}`,
                        borderRadius: 8,
                        padding: '12px 16px',
                        transition: 'all 0.2s'
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
                          <span style={{ fontSize: 10, fontWeight: 800, padding: '2px 6px', borderRadius: 4, ...formatStyle }}>
                            {item.format}
                          </span>
                          <span style={{ fontSize: 13, fontWeight: 600, color: '#fff', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                            {item.name}
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
                            ({item.size} KB)
                          </span>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0 }}>
                          {item.status === 'pending' && (
                            <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.08)', color: 'var(--text-secondary)', fontSize: 11 }}>
                              Queued
                            </span>
                          )}
                          {item.status === 'uploading' && (
                            <span className="badge badge-processing" style={{ fontSize: 11 }}>
                              <Loader2 size={12} className="spinner" /> Ingesting & Extracting...
                            </span>
                          )}
                          {item.status === 'success' && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                              {item.docType && (
                                <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', color: getDocTypeColor(item.docType), background: `${getDocTypeColor(item.docType)}1A`, padding: '2px 6px', borderRadius: 4 }}>
                                  {formatDocumentType(item.docType)}
                                </span>
                              )}
                              <span className={`badge badge-${item.extractionStatus || 'ok'}`} style={{ fontSize: 11 }}>
                                <CheckCircle size={12} /> {item.extractionStatus === 'needs_review' ? 'Needs Review' : 'Ok'}
                              </span>
                              {item.docId && (
                                <Link to={`/quotations/${item.docId}`} className="btn btn-secondary btn-sm" style={{ padding: '2px 8px', fontSize: 11 }}>
                                  Audit
                                </Link>
                              )}
                            </div>
                          )}
                          {item.status === 'failed' && (
                            <span className="badge badge-failed" style={{ fontSize: 11 }}>
                              <AlertTriangle size={12} /> Failed
                            </span>
                          )}

                          {!ingesting && item.status !== 'uploading' && (
                            <button
                              type="button"
                              className="btn-icon"
                              onClick={() => removeFileFromQueue(item.id)}
                              style={{ width: 26, height: 26, color: 'var(--text-muted)' }}
                            >
                              <Trash2 size={13} />
                            </button>
                          )}
                        </div>
                      </div>

                      {item.status === 'uploading' && (
                        <div style={{ marginTop: 8 }}>
                          <div style={{ height: 4, background: 'rgba(255, 255, 255, 0.06)', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${item.progress}%`, background: 'linear-gradient(90deg, var(--cyan), var(--purple))', transition: 'width 0.3s ease' }} />
                          </div>
                        </div>
                      )}

                      {item.error && (
                        <div style={{ fontSize: 11, color: 'var(--red)', marginTop: 6 }}>
                          Error: {item.error}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)', display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={ingesting || filesQueue.length === 0}
                  onClick={startBatchIngestion}
                  style={{ padding: '12px 24px', fontSize: 14, borderRadius: 8, display: 'inline-flex', alignItems: 'center', gap: 8 }}
                >
                  {ingesting ? (
                    <>
                      <Loader2 size={16} className="spinner" />
                      Extracting File {currentIndex + 1} of {filesQueue.length}...
                    </>
                  ) : (
                    <>
                      <Layers size={16} />
                      Ingest & Extract Document{filesQueue.length > 1 ? 's' : ''} ({filesQueue.length})
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Extracted Document Preview Table */}
          {lastExtractedDoc && (
            <div className="card" style={{ padding: 24, marginBottom: 20 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, borderBottom: '1px solid var(--border)', paddingBottom: 12 }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <CheckCircle size={18} style={{ color: 'var(--green)' }} />
                    <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: '#fff' }}>
                      Extracted Document Details (ID: #{lastExtractedDoc.id})
                    </h3>
                  </div>
                  <p style={{ margin: '4px 0 0 26px', fontSize: 12, color: 'var(--text-secondary)' }}>
                    Source: {lastExtractedDoc.source_file}
                  </p>
                </div>
                <Link to={`/quotations/${lastExtractedDoc.id}`} className="btn btn-secondary btn-sm" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <Eye size={14} /> Full Audit View
                </Link>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 20, background: 'rgba(255,255,255,0.02)', padding: 14, borderRadius: 8, border: '1px solid var(--border)' }}>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Vendor</span>
                  <strong style={{ fontSize: 13, color: '#fff' }}>{lastExtractedDoc.vendor_name || lastExtractedDoc.name || 'N/A'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Customer / Patient</span>
                  <strong style={{ fontSize: 13, color: '#fff' }}>{lastExtractedDoc.customer_name || 'N/A'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Document No</span>
                  <strong style={{ fontSize: 13, color: 'var(--cyan)' }}>{lastExtractedDoc.document_no || lastExtractedDoc.quotation_no || `ID: ${lastExtractedDoc.id}`}</strong>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Grand Total</span>
                  <strong style={{ fontSize: 14, color: 'var(--green)' }}>{formatIndianCurrency(lastExtractedDoc.grand_total_final)}</strong>
                </div>
              </div>

              <h4 style={{ margin: '0 0 10px 0', fontSize: 14, fontWeight: 700 }}>Extracted Itemization ({lastExtractedDoc.line_items?.length || 0} Items)</h4>
              <div className="table-container" style={{ marginBottom: 0 }}>
                <table className="quote-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item Code</th>
                      <th>Description</th>
                      <th className="text-right">Qty</th>
                      <th className="text-right">Rate</th>
                      <th className="text-right">Final Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(!lastExtractedDoc.line_items || lastExtractedDoc.line_items.length === 0) ? (
                      <tr>
                        <td colSpan="6" style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)' }}>
                          No individual line items parsed. Check audit review page for details.
                        </td>
                      </tr>
                    ) : (
                      lastExtractedDoc.line_items.map((item, idx) => (
                        <tr key={idx}>
                          <td>{item.line_no || idx + 1}</td>
                          <td style={{ fontWeight: 600 }}>{item.item_code || '-'}</td>
                          <td style={{ color: '#fff' }}>{item.description || 'N/A'}</td>
                          <td className="text-right">{item.qty}</td>
                          <td className="text-right">{formatIndianCurrency(item.rate)}</td>
                          <td className="text-right" style={{ fontWeight: 600, color: 'var(--cyan)' }}>
                            {formatIndianCurrency(item.final_value || item.gross_amount)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {lastExtractedDoc.allQuotations && lastExtractedDoc.allQuotations.length > 1 && (
                <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                  <h4 style={{ margin: '0 0 10px 0', fontSize: 14, fontWeight: 700, color: '#fff' }}>
                    Batch Ingested Documents List ({lastExtractedDoc.allQuotations.length} Invoices Created)
                  </h4>
                  <div className="table-container" style={{ maxHeight: 300, overflowY: 'auto' }}>
                    <table className="quote-table">
                      <thead>
                        <tr>
                          <th>Doc ID</th>
                          <th>Invoice No</th>
                          <th>Vendor</th>
                          <th>Customer / Patient</th>
                          <th>Status</th>
                          <th className="text-right">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {lastExtractedDoc.allQuotations.map((q) => (
                          <tr key={q.id}>
                            <td>#{q.id}</td>
                            <td style={{ fontWeight: 600, color: 'var(--cyan)' }}>{q.quotation_no || '-'}</td>
                            <td>{q.vendor_name || 'TechVision Distributors'}</td>
                            <td style={{ color: '#fff' }}>{q.customer_name || '-'}</td>
                            <td>
                              <span className={`badge badge-${q.extraction_status || 'ok'}`}>
                                {q.extraction_status === 'needs_review' ? 'Needs Review' : 'Ok'}
                              </span>
                            </td>
                            <td className="text-right">
                              <Link to={`/quotations/${q.id}`} className="btn btn-secondary btn-sm" style={{ padding: '2px 8px', fontSize: 11 }}>
                                Audit
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Batch Summary Report Card upon Completion */}
          {batchCompleted && (
            <div className="card" style={{ padding: 24, background: 'rgba(34, 197, 94, 0.04)', border: '1px solid rgba(34, 197, 94, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                <CheckCircle size={24} style={{ color: 'var(--green)' }} />
                <div>
                  <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: '#fff' }}>
                    Ingestion Completed
                  </h3>
                  <p style={{ margin: 0, fontSize: 12, color: 'var(--text-secondary)' }}>
                    All queued documents have been extracted and stored into PostgreSQL
                  </p>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 16 }}>
                <div style={{ background: 'rgba(255,255,255,0.03)', padding: 12, borderRadius: 8, textAlign: 'center' }}>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Total Ingested</span>
                  <strong style={{ fontSize: 20, color: '#fff' }}>{batchStats.total}</strong>
                </div>
                <div style={{ background: 'rgba(34, 197, 94, 0.1)', padding: 12, borderRadius: 8, textAlign: 'center' }}>
                  <span style={{ fontSize: 11, color: 'var(--green)', display: 'block' }}>Valid (Ok)</span>
                  <strong style={{ fontSize: 20, color: 'var(--green)' }}>{batchStats.okCount}</strong>
                </div>
                <div style={{ background: 'rgba(251, 191, 36, 0.1)', padding: 12, borderRadius: 8, textAlign: 'center' }}>
                  <span style={{ fontSize: 11, color: 'var(--amber)', display: 'block' }}>Needs Review</span>
                  <strong style={{ fontSize: 20, color: 'var(--amber)' }}>{batchStats.reviewCount}</strong>
                </div>
                {batchStats.failedCount > 0 && (
                  <div style={{ background: 'rgba(244, 63, 94, 0.1)', padding: 12, borderRadius: 8, textAlign: 'center' }}>
                    <span style={{ fontSize: 11, color: 'var(--red)', display: 'block' }}>Failed</span>
                    <strong style={{ fontSize: 20, color: 'var(--red)' }}>{batchStats.failedCount}</strong>
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={clearQueue}
                >
                  Ingest Another File / Batch
                </button>
                <Link to="/documents" className="btn btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  View Documents Explorer <ArrowRight size={14} />
                </Link>
              </div>
            </div>
          )}
        </>
      )}

      {/* TAB 2: RAW TEXT / CSV / JSON DATA INGESTION */}
      {activeTab === 'raw_text' && (
        <div className="card" style={{ padding: 24, marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#fff' }}>
                Paste Raw Ingestion Payload
              </h3>
              <p style={{ margin: '4px 0 0 0', fontSize: 12, color: 'var(--text-secondary)' }}>
                Paste single or multi-record CSV rows, OCR statement text, or JSON payload blocks directly into the input box below.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={loadSampleCSV}
              >
                + Sample CSV Payload
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={loadSampleOCRStatement}
              >
                + Sample OCR Statement
              </button>
            </div>
          </div>

          <textarea
            rows={14}
            value={rawTextInput}
            onChange={(e) => setRawTextInput(e.target.value)}
            placeholder={`filename,json_data,ocred_text\ninvoice_51109301.pdf,"{\n  ""invoice_no"": ""51109301"",\n  ""date_of_issue"": ""03/07/2023"",\n  ""items"": [\n    { ""item_no"": ""1."", ""description"": ""Garmin Fenix 7 Solar"", ""quantity"": ""9.00"", ""net_price"": ""74120.00"", ""gross_worth"": ""733788.00"" }\n  ]\n}"`}
            style={{
              width: '100%',
              background: '#090d16',
              color: 'var(--cyan)',
              fontFamily: 'monospace',
              fontSize: 12,
              padding: 14,
              borderRadius: 8,
              border: '1px solid var(--border)',
              outline: 'none',
              resize: 'vertical',
              lineHeight: 1.5
            }}
          />

          <div style={{ marginTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {rawTextInput.length} characters pasted
            </span>
            <button
              type="button"
              className="btn btn-primary"
              disabled={textIngesting || !rawTextInput.trim()}
              onClick={handleDirectTextIngest}
              style={{ padding: '10px 22px', fontSize: 14, display: 'inline-flex', alignItems: 'center', gap: 8 }}
            >
              {textIngesting ? (
                <>
                  <Loader2 size={16} className="spinner" /> Parsing & Extracting Payload...
                </>
              ) : (
                <>
                  <Code size={16} /> Process & Ingest Pasted Text Data
                </>
              )}
            </button>
          </div>

          {/* Extracted Text Preview Card */}
          {textExtractedDoc && (
            <div style={{ marginTop: 24, paddingTop: 20, borderTop: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CheckCircle size={18} style={{ color: 'var(--green)' }} />
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#fff' }}>
                    Extracted Text Document Details (ID: #{textExtractedDoc.id})
                  </h3>
                </div>
                <Link to={`/quotations/${textExtractedDoc.id}`} className="btn btn-secondary btn-sm" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <Eye size={14} /> Full Audit View
                </Link>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 12, marginBottom: 20, background: 'rgba(255,255,255,0.02)', padding: 14, borderRadius: 8, border: '1px solid var(--border)' }}>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Vendor</span>
                  <strong style={{ fontSize: 13, color: '#fff' }}>{textExtractedDoc.vendor_name || textExtractedDoc.name || 'N/A'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Customer / Patient</span>
                  <strong style={{ fontSize: 13, color: '#fff' }}>{textExtractedDoc.customer_name || 'N/A'}</strong>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Document No</span>
                  <strong style={{ fontSize: 13, color: 'var(--cyan)' }}>{textExtractedDoc.document_no || textExtractedDoc.quotation_no || `ID: ${textExtractedDoc.id}`}</strong>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: 'var(--text-muted)', display: 'block' }}>Grand Total</span>
                  <strong style={{ fontSize: 14, color: 'var(--green)' }}>{formatIndianCurrency(textExtractedDoc.grand_total_final)}</strong>
                </div>
              </div>

              <h4 style={{ margin: '0 0 10px 0', fontSize: 14, fontWeight: 700 }}>Extracted Itemization ({textExtractedDoc.line_items?.length || 0} Items)</h4>
              <div className="table-container" style={{ marginBottom: 0 }}>
                <table className="quote-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Item Code</th>
                      <th>Description</th>
                      <th className="text-right">Qty</th>
                      <th className="text-right">Rate</th>
                      <th className="text-right">Final Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(!textExtractedDoc.line_items || textExtractedDoc.line_items.length === 0) ? (
                      <tr>
                        <td colSpan="6" style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)' }}>
                          No individual line items parsed. Check audit review page for details.
                        </td>
                      </tr>
                    ) : (
                      textExtractedDoc.line_items.map((item, idx) => (
                        <tr key={idx}>
                          <td>{item.line_no || idx + 1}</td>
                          <td style={{ fontWeight: 600 }}>{item.item_code || '-'}</td>
                          <td style={{ color: '#fff' }}>{item.description || 'N/A'}</td>
                          <td className="text-right">{item.qty}</td>
                          <td className="text-right">{formatIndianCurrency(item.rate)}</td>
                          <td className="text-right" style={{ fontWeight: 600, color: 'var(--cyan)' }}>
                            {formatIndianCurrency(item.final_value || item.gross_amount)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
