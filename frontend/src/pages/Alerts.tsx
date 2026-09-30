import { useState } from 'react'
import { useAlerts, useAcknowledgeAlert, Alert } from '../api/alerts'

/* ── Severity helpers ────────────────────────────────────────────── */
function getSeverity(z: number): 'high' | 'medium' | 'low' {
  if (z >= 4) return 'high'
  if (z >= 3) return 'medium'
  return 'low'
}

const SEVERITY_CONFIG = {
  high:   { label: 'High',   color: 'var(--accent-red)',   bg: 'rgba(var(--accent-red-rgb), 0.10)',   border: 'rgba(var(--accent-red-rgb), 0.25)' },
  medium: { label: 'Medium', color: 'var(--accent-amber)', bg: 'rgba(var(--accent-amber-rgb), 0.10)', border: 'rgba(var(--accent-amber-rgb), 0.25)' },
  low:    { label: 'Low',    color: 'var(--accent-primary)', bg: 'rgba(var(--accent-primary-rgb), 0.10)', border: 'rgba(var(--accent-primary-rgb), 0.25)' },
}

/* ── Inline SVG Icons ────────────────────────────────────────────── */
const BellOffIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--accent-primary)' }}>
    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>
  </svg>
)

const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12"/>
  </svg>
)

const FilterIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
  </svg>
)

export default function Alerts() {
  const [page, setPage] = useState(1)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const pageSize = 20

  const { data, isLoading } = useAlerts(page, pageSize, unreadOnly)
  const alerts = data?.alerts || []
  const total = data?.total || 0
  const acknowledgeMutation = useAcknowledgeAlert()

  const handleAcknowledge = (alertId: string) => {
    acknowledgeMutation.mutate(alertId)
  }

  if (isLoading) {
    return <div className="loading-spinner"><div className="spinner" /></div>
  }

  const isEmpty = !isLoading && alerts.length === 0

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Alerts</h1>
        <button
          id="btn-toggle-unread"
          className={unreadOnly ? 'btn-primary' : 'btn-secondary'}
          style={{ width: 'auto', padding: '10px 20px', display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}
          onClick={() => { setUnreadOnly(!unreadOnly); setPage(1) }}
        >
          <FilterIcon />
          {unreadOnly ? 'Showing Unread' : 'Show Unread Only'}
        </button>
      </div>

      {/* Empty State */}
      {isEmpty ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <BellOffIcon />
          </div>
          <h2>{unreadOnly ? 'No Unread Alerts' : 'No Alerts Yet'}</h2>
          <p>
            {unreadOnly
              ? 'All caught up! You have no unread anomaly alerts.'
              : 'When the system detects unusual spending patterns, alerts will appear here.'}
          </p>
          {unreadOnly && (
            <button className="btn-secondary" onClick={() => setUnreadOnly(false)}>View All Alerts</button>
          )}
        </div>
      ) : (
        <>
          {/* Alert Cards */}
          <div className="alerts-list" id="alerts-list">
            {alerts.map((alert: Alert) => {
              const severity = getSeverity(alert.z_score)
              const config = SEVERITY_CONFIG[severity]
              const isAcknowledged = !!alert.acknowledged_at

              return (
                <div
                  key={alert.id}
                  className={`alert-card ${isAcknowledged ? 'acknowledged' : ''}`}
                  style={{ '--alert-accent': config.color } as React.CSSProperties}
                >
                  <div className="alert-card-indicator" style={{ background: config.color }} />
                  <div className="alert-card-body">
                    <div className="alert-card-header">
                      <span
                        className="severity-badge"
                        style={{ background: config.bg, color: config.color, borderColor: config.border }}
                      >
                        Z: {alert.z_score.toFixed(1)} · {config.label}
                      </span>
                      {!isAcknowledged && (
                        <button
                          className="btn-acknowledge"
                          onClick={() => handleAcknowledge(alert.id)}
                          disabled={acknowledgeMutation.isPending}
                          title="Acknowledge alert"
                        >
                          <CheckIcon /> Acknowledge
                        </button>
                      )}
                      {isAcknowledged && (
                        <span className="acknowledged-label">
                          <CheckIcon /> Acknowledged
                        </span>
                      )}
                    </div>
                    <p className="alert-card-description">{alert.description}</p>
                    <div className="alert-meta">
                      <span className="badge-chip" style={{ fontSize: 11, background: 'rgba(255,255,255,0.05)' }}>
                        {alert.category_icon} {alert.category_name || 'General'}
                      </span>
                      <span>
                        {new Date(alert.created_at).toLocaleDateString('en-IN', {
                          day: '2-digit', month: 'short', year: 'numeric',
                        })}{' '}
                        at{' '}
                        {new Date(alert.created_at).toLocaleTimeString('en-IN', {
                          hour: '2-digit', minute: '2-digit',
                        })}
                      </span>
                      {alert.transaction_id && (
                        <span className="badge-chip" style={{ fontSize: 11 }}>
                          Txn: {alert.transaction_id.slice(0, 8)}…
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Pagination */}
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 16, padding: '16px 24px', marginTop: 20, borderTop: '1px solid var(--border)' }}>
            <button
              className="btn-secondary"
              style={{ padding: '8px 20px', fontSize: 13 }}
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
            >
              Previous
            </button>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>
              Page {page} of {Math.ceil(total / pageSize) || 1}
            </span>
            <button
              className="btn-secondary"
              style={{ padding: '8px 20px', fontSize: 13 }}
              onClick={() => setPage(p => p + 1)}
              disabled={page * pageSize >= total}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  )
}
