import React, { createContext, useContext, useState } from 'react'
import quotationApi from '../api/quotationClient.js'
import { getFileFormat } from '../pages/QuotationsList.jsx'
import { useToast } from '../ToastContext.jsx'

const IngestionContext = createContext()

export function IngestionProvider({ children }) {
  const [filesQueue, setFilesQueue] = useState([])
  const [ingesting, setIngesting] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(-1)
  const [batchCompleted, setBatchCompleted] = useState(false)
  const [batchStats, setBatchStats] = useState({ total: 0, okCount: 0, reviewCount: 0, failedCount: 0 })
  const [lastExtractedDoc, setLastExtractedDoc] = useState(null)
  const [rateLimitEnabled, setRateLimitEnabled] = useState(() => {
    const saved = localStorage.getItem('batchRateLimitEnabled')
    return saved !== null ? saved === 'true' : true
  })
  const toast = useToast()

  const MAX_BATCH_FILES = 15

  const toggleRateLimit = () => {
    setRateLimitEnabled(prev => {
      const nextVal = !prev
      localStorage.setItem('batchRateLimitEnabled', String(nextVal))
      if (toast) {
        if (nextVal) {
          toast(`Batch Rate Limit Enabled (Max ${MAX_BATCH_FILES} files per batch)`, 'info')
        } else {
          toast('Batch Rate Limit Disabled (Unlimited files per batch allowed)', 'warning')
        }
      }
      return nextVal
    })
  }

  const addFilesToQueue = (newFiles) => {
    if (!newFiles || newFiles.length === 0) return

    const incoming = Array.from(newFiles)
    const currentQueueCount = filesQueue.length

    let allowedFiles = incoming
    if (rateLimitEnabled) {
      if (currentQueueCount >= MAX_BATCH_FILES) {
        toast(`Batch rate limit reached: Maximum ${MAX_BATCH_FILES} files allowed per batch ingestion. Turn off rate limit to upload more.`, 'error')
        return
      }

      if (currentQueueCount + incoming.length > MAX_BATCH_FILES) {
        const allowedCount = MAX_BATCH_FILES - currentQueueCount
        allowedFiles = incoming.slice(0, allowedCount)
        toast(`Batch limit enforced: Only ${allowedCount} file(s) added. Maximum ${MAX_BATCH_FILES} files allowed per batch.`, 'error')
      }
    }

    const added = allowedFiles.map((file, idx) => ({
      id: `${Date.now()}-${idx}-${Math.random().toString(36).substring(2, 7)}`,
      file,
      name: file.name,
      size: (file.size / 1024).toFixed(1),
      format: getFileFormat(file.name),
      status: 'pending',
      progress: 0,
      docId: null,
      docType: null,
      reviewReason: null,
      extractedData: null,
      error: null
    }))

    setFilesQueue(prev => [...prev, ...added])
    setBatchCompleted(false)
  }

  const removeFileFromQueue = (id) => {
    if (ingesting) return
    setFilesQueue(prev => prev.filter(f => f.id !== id))
  }

  const clearQueue = () => {
    if (ingesting) return
    setFilesQueue([])
    setBatchCompleted(false)
    setLastExtractedDoc(null)
  }

  const startBatchIngestion = async () => {
    if (filesQueue.length === 0 || ingesting) return

    setIngesting(true)
    setBatchCompleted(false)
    setLastExtractedDoc(null)
    let okCount = 0
    let reviewCount = 0
    let failedCount = 0
    let latestDocDetail = null

    for (let i = 0; i < filesQueue.length; i++) {
      const item = filesQueue[i]
      setCurrentIndex(i)

      setFilesQueue(prev => prev.map((f, idx) => idx === i ? { ...f, status: 'uploading', progress: 35 } : f))

      try {
        const stepTimer = setInterval(() => {
          setFilesQueue(prev => prev.map((f, idx) => {
            if (idx === i && f.progress < 85) {
              return { ...f, progress: f.progress + 15 }
            }
            return f
          }))
        }, 200)

        const res = await quotationApi.uploadQuotation(item.file)
        clearInterval(stepTimer)

        const qCount = (res.quotations && res.quotations.length > 0) ? res.quotations.length : 1
        const isNeedsReview = res.extraction_status === 'needs_review'
        if (res.is_duplicate) {
          toast(`⚠️ Duplicate Document Detected: An identical document with matching values already exists (Doc #${res.id}).`, 'warning')
        }

        if (isNeedsReview) {
          reviewCount += qCount
        } else {
          okCount += qCount
        }

        let fullDetail = res
        try {
          if (res.id) {
            fullDetail = await quotationApi.getQuotation(res.id)
            if (res.quotations && res.quotations.length > 1) {
              fullDetail.allQuotations = res.quotations
            }
            latestDocDetail = fullDetail
          }
        } catch (detailErr) {
          console.warn('Could not fetch full document detail:', detailErr)
        }

        setFilesQueue(prev => prev.map((f, idx) => idx === i ? {
          ...f,
          status: res.is_duplicate ? 'duplicate' : 'success',
          progress: 100,
          docId: res.id,
          isDuplicate: res.is_duplicate || false,
          duplicateMessage: res.message,
          docType: res.document_type || (fullDetail ? fullDetail.document_type : null),
          extractionStatus: res.extraction_status,
          extractedData: fullDetail
        } : f))

      } catch (err) {
        failedCount++
        setFilesQueue(prev => prev.map((f, idx) => idx === i ? {
          ...f,
          status: 'failed',
          progress: 0,
          error: err.message
        } : f))
      }
    }

    setIngesting(false)
    setCurrentIndex(-1)
    setBatchCompleted(true)
    if (latestDocDetail) {
      setLastExtractedDoc(latestDocDetail)
    }
    setBatchStats({
      total: filesQueue.length,
      okCount,
      reviewCount,
      failedCount
    })

    // Automatically clear ingested items from the queue
    setFilesQueue([])

    if (toast) {
      toast(`Background ingestion complete! ${okCount + reviewCount} file(s) processed and cleared from queue.`, 'success')
    }
  }

  return (
    <IngestionContext.Provider value={{
      filesQueue,
      ingesting,
      currentIndex,
      batchCompleted,
      batchStats,
      lastExtractedDoc,
      rateLimitEnabled,
      toggleRateLimit,
      setRateLimitEnabled,
      addFilesToQueue,
      removeFileFromQueue,
      clearQueue,
      startBatchIngestion
    }}>
      {children}
    </IngestionContext.Provider>
  )
}

export function useIngestion() {
  return useContext(IngestionContext)
}
