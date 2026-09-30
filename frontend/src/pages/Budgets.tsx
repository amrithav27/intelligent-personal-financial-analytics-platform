import { useState } from 'react'
import { useBudgets, useOverrideBudget, BudgetRecommendation } from '../api/budgets'

// ── Helpers ───────────────────────────────────────────────────────────────────

function alertColor(level: 'ok' | 'warning' | 'over') {
    if (level === 'over') return 'var(--accent-red)'
    if (level === 'warning') return 'var(--accent-amber)'
    return 'var(--accent-green)'
}

function alertIcon(level: 'ok' | 'warning' | 'over') {
    if (level === 'over') return '❗'
    if (level === 'warning') return '⚠️'
    return '✅'
}

function bucketLabel(bucket?: string) {
    if (!bucket) return null
    const colors: Record<string, string> = {
        needs: 'var(--accent-primary)',
        wants: 'var(--accent-amber)',
        savings: 'var(--accent-green)',
    }
    return (
        <span style={{
            marginLeft: 8, fontSize: 10, padding: '2px 8px', borderRadius: 10,
            background: `${colors[bucket] ?? 'var(--text-secondary)'}22`,
            color: colors[bucket] ?? 'var(--text-secondary)',
            fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.5px',
        }}>
            {bucket}
        </span>
    )
}

function fmt(n: number) {
    return n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

// ── BudgetCard ────────────────────────────────────────────────────────────────

function BudgetCard({ item, month }: { item: BudgetRecommendation; month: string }) {
    const { effective_limit, current_spending, pct_used, alert_level, recommended_amount, current_limit } = item
    const clampedPct = Math.min(pct_used, 100)
    const isOverridden = current_limit !== null && current_limit !== recommended_amount
    const isUncategorized = item.category_id === 0

    const [editing, setEditing] = useState(false)
    // Use recommended_amount as fallback if no override active yet (effective_limit could be 0 for savings)
    const defaultInput = String(Math.round(current_limit ?? recommended_amount ?? 1000))
    const [inputVal, setInputVal] = useState(defaultInput)
    const { mutate, isPending } = useOverrideBudget()

    function saveOverride() {
        const val = parseFloat(inputVal)
        if (!val || val <= 0) return
        mutate(
            { categoryId: item.category_id, limitAmount: val, month },
            { onSuccess: () => setEditing(false) }
        )
    }

    return (
        <div className="budget-row-card" style={{
            borderLeft: `3px solid ${alertColor(alert_level)}`,
            opacity: isUncategorized ? 0.85 : 1,
        }}>
            {/* Header row */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                <div>
                    <div style={{ fontWeight: 700, fontSize: 15, display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' as const }}>
                        {alertIcon(alert_level)} {item.category_name}
                        {bucketLabel(item.bucket)}
                        {isUncategorized && (
                            <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 10, background: 'rgba(150,150,150,0.15)', color: 'var(--text-secondary)', fontWeight: 700, letterSpacing: '0.5px' }}>
                                PENDING CATEGORIZATION
                            </span>
                        )}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>
                        {isUncategorized
                            ? 'Transactions not yet categorized by analytics engine'
                            : isOverridden
                                ? <>Custom limit · Recommended: ₹{fmt(recommended_amount)}</>
                                : <>Recommended limit</>
                        }
                        {item.median_spending != null && (
                            <span> · Median: ₹{fmt(item.median_spending)}</span>
                        )}
                    </div>
                </div>
                {/* Only show Set Limit for real, categorized entries */}
                {!editing && !isUncategorized && (
                    <button
                        onClick={() => { setInputVal(String(Math.round(current_limit ?? recommended_amount ?? 1000))); setEditing(true) }}
                        style={{
                            fontSize: 11, padding: '4px 12px', cursor: 'pointer',
                            background: 'var(--bg-secondary)', border: '1px solid var(--border)',
                            borderRadius: 20, color: 'var(--text-secondary)', whiteSpace: 'nowrap' as const,
                            transition: 'border-color 0.2s',
                        }}
                    >
                        Set Limit
                    </button>
                )}
            </div>

            {/* Spending summary */}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6, fontSize: 13 }}>
                <span>
                    <span style={{ fontWeight: 700, color: alertColor(alert_level) }}>₹{fmt(current_spending)}</span>
                    <span style={{ color: 'var(--text-secondary)' }}> spent</span>
                    {!isUncategorized && (
                        <span style={{ color: 'var(--text-secondary)' }}> of <span style={{ fontWeight: 700 }}>₹{fmt(effective_limit)}</span></span>
                    )}
                </span>
                {!isUncategorized && (
                    <span style={{ fontWeight: 700, color: alertColor(alert_level) }}>
                        {pct_used.toFixed(1)}%
                    </span>
                )}
            </div>

            {/* Progress bar — only for categorized entries */}
            {!isUncategorized && (
                <div className="budget-bar-track" style={{ height: 10, borderRadius: 5 }}>
                    <div
                        className={`budget-bar-fill ${alert_level}`}
                        style={{
                            width: `${clampedPct}%`,
                            height: '100%',
                            borderRadius: 5,
                            transition: 'width 0.6s ease',
                        }}
                    />
                </div>
            )}

            {/* Alert message */}
            {alert_level !== 'ok' && !isUncategorized && (
                <div style={{
                    marginTop: 10, fontSize: 12, padding: '6px 10px', borderRadius: 6,
                    background: `${alertColor(alert_level)}15`,
                    color: alertColor(alert_level),
                    fontWeight: 500,
                }}>
                    {alert_level === 'over'
                        ? `Over budget by ₹${fmt(current_spending - effective_limit)}`
                        : `Approaching limit — ₹${fmt(effective_limit - current_spending)} remaining`}
                </div>
            )}

            {/* Override form */}
            {editing && !isUncategorized && (
                <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center', flexWrap: 'wrap' as const }}>
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)', whiteSpace: 'nowrap' as const }}>
                        New limit ₹
                    </span>
                    <input
                        id={`budget-limit-${item.category_id}`}
                        type="number"
                        min="1"
                        step="100"
                        value={inputVal}
                        autoFocus
                        onChange={e => setInputVal(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') saveOverride(); if (e.key === 'Escape') setEditing(false) }}
                        style={{
                            flex: 1, minWidth: 100, padding: '8px 12px',
                            background: 'var(--bg-secondary)', border: '1px solid var(--accent-primary)',
                            borderRadius: 8, color: 'var(--text-primary)', fontSize: 14, outline: 'none',
                        }}
                    />
                    <button
                        onClick={saveOverride}
                        disabled={isPending}
                        className="btn-primary"
                        style={{ width: 'auto', padding: '8px 20px', fontSize: 13 }}
                    >
                        {isPending ? '…' : 'Save'}
                    </button>
                    <button
                        onClick={() => setEditing(false)}
                        style={{
                            padding: '8px 14px', background: 'var(--bg-secondary)',
                            border: '1px solid var(--border)', borderRadius: 8,
                            color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 13,
                        }}
                    >
                        Cancel
                    </button>
                </div>
            )}
        </div>
    )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function Budgets() {
    const now = new Date()
    const defaultMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    const [month, setMonth] = useState(defaultMonth)

    const { data, isLoading, error } = useBudgets(month)

    const monthOptions = Array.from({ length: 6 }, (_, i) => {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
        const val = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
        const label = d.toLocaleString('default', { month: 'long', year: 'numeric' })
        return { val, label }
    })

    // Derive alert summary
    const overCategories = data?.recommendations.filter((r: BudgetRecommendation) => r.alert_level === 'over').length ?? 0
    const warnCategories = data?.recommendations.filter((r: BudgetRecommendation) => r.alert_level === 'warning').length ?? 0
    const totalSpent = data?.recommendations.reduce((s: number, r: BudgetRecommendation) => s + r.current_spending, 0) ?? 0
    const totalLimit = data?.recommendations.reduce((s: number, r: BudgetRecommendation) => s + r.effective_limit, 0) ?? 0

    return (
        <div>
            {/* Page header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
                <h1 className="page-title" style={{ margin: 0 }}>Budget Management</h1>
                <select
                    id="budget-month-select"
                    className="form-select"
                    value={month}
                    onChange={e => setMonth(e.target.value)}
                >
                    {monthOptions.map(o => (
                        <option key={o.val} value={o.val}>{o.label}</option>
                    ))}
                </select>
            </div>

            {isLoading && <div className="loading-spinner"><div className="spinner" /></div>}

            {error && (
                <div className="card" style={{ textAlign: 'center', color: 'var(--accent-red)', padding: 32 }}>
                    Failed to load budget data. Please try again.
                </div>
            )}

            {data && (
                <>
                    {/* Top alert banner */}
                    {overCategories > 0 && (
                        <div style={{
                            background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                            borderRadius: 'var(--radius)', padding: '14px 20px', marginBottom: 16,
                            display: 'flex', alignItems: 'center', gap: 12, animation: 'slideIn 0.3s ease',
                        }}>
                            <span style={{ fontSize: 20 }}></span>
                            <span style={{ fontWeight: 600 }}>
                                {overCategories} {overCategories === 1 ? 'category is' : 'categories are'} over budget this month
                            </span>
                        </div>
                    )}
                    {warnCategories > 0 && overCategories === 0 && (
                        <div style={{
                            background: 'linear-gradient(135deg, rgba(245,158,11,0.2), rgba(245,158,11,0.1))',
                            border: '1px solid var(--accent-amber)',
                            borderRadius: 'var(--radius)', padding: '14px 20px', marginBottom: 16,
                            display: 'flex', alignItems: 'center', gap: 12,
                        }}>
                            <span style={{ fontSize: 20 }}></span>
                            <span style={{ fontWeight: 600, color: 'var(--accent-amber)' }}>
                                {warnCategories} {warnCategories === 1 ? 'category is' : 'categories are'} approaching the budget limit
                            </span>
                        </div>
                    )}

                    {/* Strategy + history chips */}
                    <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
                        <div className="badge-chip">
                             <strong style={{ marginLeft: 4 }}>{data.strategy_used === 'proportional_income' ? 'Proportional Income Strategy' : data.strategy_used}</strong>
                        </div>
                        <div className="badge-chip">
                             <strong style={{ marginLeft: 4 }}>{data.months_of_history}mo</strong> history
                        </div>
                        <div className="badge-chip">
                             50/30/20 guardrails
                        </div>
                    </div>

                    {/* Summary totals card */}
                    {data.recommendations.length > 0 && (
                        <div className="card" style={{ marginBottom: 20, display: 'flex', gap: 32, flexWrap: 'wrap' }}>
                            {data.current_month_income > 0 && (
                                <div>
                                    <div className="stat-value" style={{ fontSize: 22, color: 'var(--accent-primary)' }}>₹{fmt(data.current_month_income)}</div>
                                    <div className="stat-label">Monthly Income</div>
                                </div>
                            )}
                            <div>
                                <div className="stat-value" style={{ fontSize: 22 }}>₹{fmt(totalSpent)}</div>
                                <div className="stat-label">Total Spent</div>
                            </div>
                            <div>
                                <div className="stat-value" style={{ fontSize: 22 }}>₹{fmt(totalLimit)}</div>
                                <div className="stat-label">Total Budget</div>
                            </div>
                            <div>
                                <div className="stat-value" style={{ fontSize: 22, color: totalSpent > totalLimit ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                                    {totalLimit > 0 ? ((totalSpent / totalLimit) * 100).toFixed(1) : '0'}%
                                </div>
                                <div className="stat-label">Overall Used</div>
                            </div>
                            <div>
                                <div className="stat-value" style={{ fontSize: 22 }}>{data.recommendations.length}</div>
                                <div className="stat-label">Categories Tracked</div>
                            </div>
                        </div>
                    )}

                    {/* Budget cards grid */}
                    {!data.recommendations || data.recommendations.length === 0 ? (
                        <div className="empty-state">
                            <div className="empty-state-icon"></div>
                            <h2>No Budget Data Yet</h2>
                            <p>Upload transactions and wait for the analytics engine to categorize them — budget recommendations will appear here.</p>
                        </div>
                    ) : (
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
                            {data.recommendations.map((item: BudgetRecommendation) => (
                                <BudgetCard key={item.category_id} item={item} month={month} />
                            ))}
                        </div>
                    )}
                </>
            )}
        </div>
    )
}
