import { useState, useEffect, useCallback } from 'react'

interface Toast {
    id: string
    message: string
    type: 'alert' | 'budget_warning'
    category?: string
    pct_used?: number
}

/**
 * ToastContainer
 * Listens for `phoenix:alert` custom events dispatched by useAlertWebSocket
 * and renders dismissable toast notifications.
 *
 * Mount this once at the App root (e.g. inside App.tsx) so toasts appear
 * over every page.
 */
export default function ToastContainer() {
    const [toasts, setToasts] = useState<Toast[]>([])

    const dismiss = useCallback((id: string) => {
        setToasts(prev => prev.filter(t => t.id !== id))
    }, [])

    useEffect(() => {
        function handler(e: Event) {
            const detail = (e as CustomEvent).detail as {
                type?: string
                message?: string
                category?: string
                pct_used?: number
                alert_id?: string
            }

            const toast: Toast = {
                id: detail.alert_id ?? crypto.randomUUID(),
                message: detail.message ?? 'New alert',
                type: detail.type === 'budget_warning' ? 'budget_warning' : 'alert',
                category: detail.category,
                pct_used: detail.pct_used,
            }

            setToasts(prev => {
                // Deduplicate by id
                if (prev.some(t => t.id === toast.id)) return prev
                return [toast, ...prev].slice(0, 5) // max 5 toasts at once
            })

            // Auto-dismiss after 7 s
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== toast.id))
            }, 7000)
        }

        window.addEventListener('phoenix:alert', handler)
        return () => window.removeEventListener('phoenix:alert', handler)
    }, [])

    if (toasts.length === 0) return null

    return (
        <div
            id="toast-container"
            style={{
                position: 'fixed',
                top: 24,
                right: 24,
                zIndex: 9999,
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                maxWidth: 360,
                width: '100%',
            }}
        >
            {toasts.map(toast => {
                const isBudget = toast.type === 'budget_warning'
                const isOver = toast.pct_used !== undefined && toast.pct_used >= 100
                const borderColor = isOver
                    ? 'var(--accent-red)'
                    : isBudget
                        ? 'var(--accent-amber)'
                        : 'var(--accent-primary)'
                const icon = isOver ? '🔴' : isBudget ? '⚠️' : '🔔'

                return (
                    <div
                        key={toast.id}
                        className="card"
                        style={{
                            padding: '14px 16px',
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: 12,
                            borderLeft: `4px solid ${borderColor}`,
                            boxShadow: 'var(--shadow-lg)',
                            animation: 'slideInRight 0.25s ease',
                        }}
                    >
                        <span style={{ fontSize: 20, lineHeight: 1.2, flexShrink: 0 }}>{icon}</span>
                        <div style={{ flex: 1 }}>
                            {toast.category && (
                                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: borderColor, marginBottom: 3 }}>
                                    {toast.category}
                                    {toast.pct_used !== undefined && ` · ${toast.pct_used.toFixed(0)}% used`}
                                </div>
                            )}
                            <div style={{ fontSize: 13, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                                {toast.message}
                            </div>
                        </div>
                        <button
                            onClick={() => dismiss(toast.id)}
                            style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                color: 'var(--text-muted)',
                                fontSize: 16,
                                lineHeight: 1,
                                padding: 0,
                                flexShrink: 0,
                            }}
                            aria-label="Dismiss notification"
                        >
                            ✕
                        </button>
                    </div>
                )
            })}
        </div>
    )
}
