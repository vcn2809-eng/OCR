import React, { useState } from 'react'
import { Routes, Route, NavLink } from 'react-router-dom'
import { LayoutDashboard, Upload, FileText, Building2, AlertTriangle, Layers, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import Dashboard from './pages/Dashboard.jsx'
import UploadPage from './pages/Upload.jsx'
import QuotationsList from './pages/QuotationsList.jsx'
import QuotationDetail from './pages/QuotationDetail.jsx'
import Vendors from './pages/Vendors.jsx'
import Quarantine from './pages/Quarantine.jsx'
import { ToastProvider } from './ToastContext.jsx'
import { IngestionProvider } from './context/IngestionContext.jsx'
import BackgroundIngestionStatus from './components/BackgroundIngestionStatus.jsx'

export default function App() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)

  return (
    <ToastProvider>
      <IngestionProvider>
        <div className="app-container">
          {/* Persistent Sidebar Navigation */}
          <aside className={`sidebar${isSidebarOpen ? '' : ' collapsed'}`}>
            <div className="brand" style={{ justifyContent: 'space-between', paddingRight: 4 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Layers className="brand-icon" size={24} />
                <span className="brand-title">NissiGrid</span>
              </div>
              <button
                type="button"
                className="btn-icon"
                onClick={() => setIsSidebarOpen(false)}
                title="Collapse Sidebar"
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: 4 }}
              >
                <PanelLeftClose size={18} />
              </button>
            </div>

            <nav className="nav-menu">
              <NavLink to="/" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <LayoutDashboard size={18} /> Executive Dashboard
              </NavLink>

              <NavLink to="/upload" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <Upload size={18} /> Upload Document
              </NavLink>

              <NavLink to="/quotations" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <FileText size={18} /> Document Explorer
              </NavLink>

              <NavLink to="/vendors" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <Building2 size={18} /> Vendors Directory
              </NavLink>

              <NavLink to="/quarantine" className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
                <AlertTriangle size={18} /> Quarantine Review
              </NavLink>
            </nav>
          </aside>

          {/* Main Application Pages Viewport */}
          <main className="main-content">
            {!isSidebarOpen && (
              <div style={{ marginBottom: 16 }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setIsSidebarOpen(true)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 12px', color: 'var(--cyan)', borderColor: 'rgba(0, 212, 255, 0.3)' }}
                  title="Open Navigation Sidebar"
                >
                  <PanelLeftOpen size={16} /> Open Navigation Sidebar
                </button>
              </div>
            )}

            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/documents" element={<QuotationsList />} />
              <Route path="/documents/:id" element={<QuotationDetail />} />
              <Route path="/quotations" element={<QuotationsList />} />
              <Route path="/quotations/:id" element={<QuotationDetail />} />
              <Route path="/vendors" element={<Vendors />} />
              <Route path="/quarantine" element={<Quarantine />} />
            </Routes>
          </main>

          {/* Persistent Floating Background Ingestion Status Banner */}
          <BackgroundIngestionStatus />
        </div>
      </IngestionProvider>
    </ToastProvider>
  )
}
