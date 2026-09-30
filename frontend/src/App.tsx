import { useState, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from './store/authStore'
type AuthState = Parameters<typeof useAuthStore>[0] extends ((s: infer S) => unknown) ? S : never
import { useAlertWebSocket } from './hooks/useAlertWebSocket'
import { useDashboardOverview } from './api/dashboard'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Recommendations from './pages/Recommendations'
import Budgets from './pages/Budgets'
import Alerts from './pages/Alerts'
import Login from './pages/Login'
import Settings from './pages/Settings'

/* ── Inline SVG Icons (no emoji dependency) ──────────────────────── */
const Icon = {
  grid: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
      <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
    </svg>
  ),
  receipt: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/>
      <path d="M8 10h8"/><path d="M8 14h4"/>
    </svg>
  ),
  wallet: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/>
      <path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>
    </svg>
  ),
  lightbulb: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 18h6"/><path d="M10 22h4"/>
      <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14"/>
    </svg>
  ),
  logout: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  ),
  bell: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"></circle>
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
    </svg>
  ),
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s: AuthState) => s.isAuthenticated)
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" />
}

function NavLink({ href, icon, children, badge }: { href: string; icon: React.ReactNode; children: React.ReactNode; badge?: number }) {
  const location = useLocation()
  const isActive = location.pathname === href || (href !== '/' && location.pathname.startsWith(href))
  return (
    <a href={href} className={isActive ? 'active' : ''} style={{ position: 'relative' }}>
      {icon}
      {children}
      {badge !== undefined && badge > 0 && (
        <span className="nav-badge">{badge > 99 ? '99+' : badge}</span>
      )}
    </a>
  )
}

/* ── Toast Container ──────────────────────────────────────────────── */
function ToastContainer() {
  const [toasts, setToasts] = useState<Array<{ id: number; message: string }>>([])

  const dismissToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      const id = Date.now()
      setToasts(prev => [...prev.slice(-4), { id, message: detail?.description || 'New anomaly alert detected' }])
      setTimeout(() => dismissToast(id), 5000)
    }
    window.addEventListener('phoenix:alert', handler)
    return () => window.removeEventListener('phoenix:alert', handler)
  }, [dismissToast])

  if (toasts.length === 0) return null
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className="toast">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent-amber)" strokeWidth="2" strokeLinecap="round">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          <span style={{ flex: 1 }}>{t.message}</span>
          <button className="toast-close" onClick={() => dismissToast(t.id)}>✕</button>
        </div>
      ))}
    </div>
  )
}

function AppLayout({ children }: { children: React.ReactNode }) {
  const logout = useAuthStore((s: AuthState) => s.logout)
  useAlertWebSocket()
  const { data: dashboardData, error: dashboardError } = useDashboardOverview()
  const unreadAlerts = dashboardData?.unread_alerts ?? 0

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="logo-mark">P</span>
          Phoenix
        </div>
        <nav className="sidebar-nav">
          <NavLink href="/" icon={Icon.grid}>Dashboard</NavLink>
          <NavLink href="/transactions" icon={Icon.receipt}>Transactions</NavLink>
          <NavLink href="/budgets" icon={Icon.wallet}>Budgets</NavLink>
          <NavLink href="/recommendations" icon={Icon.lightbulb}>Recommendations</NavLink>
          <NavLink href="/alerts" icon={Icon.bell} badge={unreadAlerts}>Alerts</NavLink>
          <NavLink href="/settings" icon={Icon.settings}>Settings</NavLink>
          <a href="#" onClick={(e) => { e.preventDefault(); logout(); }}>
            {Icon.logout}
            Sign Out
          </a>
        </nav>
      </aside>
      <main className="main-content">
        {dashboardError && (
          <div style={{
            background: 'rgba(251, 113, 133, 0.1)',
            border: '1px solid rgba(251, 113, 133, 0.3)',
            borderRadius: 12,
            padding: '16px',
            marginBottom: '16px',
            color: 'var(--accent-red)',
            fontSize: '14px',
          }}>
            <strong>⚠️ API Connection Error:</strong> Unable to load dashboard data. Services may be offline.
          </div>
        )}
        {children}
      </main>
      <ToastContainer />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={
          <ProtectedRoute>
            <AppLayout><Dashboard /></AppLayout>
          </ProtectedRoute>
        } />
        <Route path="/transactions" element={
          <ProtectedRoute>
            <AppLayout><Transactions /></AppLayout>
          </ProtectedRoute>
        } />
        <Route path="/budgets" element={
          <ProtectedRoute>
            <AppLayout><Budgets /></AppLayout>
          </ProtectedRoute>
        } />
        <Route path="/recommendations" element={
          <ProtectedRoute>
            <AppLayout><Recommendations /></AppLayout>
          </ProtectedRoute>
        } />
        <Route path="/alerts" element={
          <ProtectedRoute>
            <AppLayout><Alerts /></AppLayout>
          </ProtectedRoute>
        } />
        <Route path="/settings" element={
          <ProtectedRoute>
            <AppLayout><Settings /></AppLayout>
          </ProtectedRoute>
        } />
      </Routes>
    </BrowserRouter>
  )
}
