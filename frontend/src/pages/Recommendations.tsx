import { useBudgetRecommendations } from '../api/recommendations'

function fmt(n: number) {
  return n.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

function bucketColor(bucket?: string) {
  if (bucket === 'needs') return 'var(--accent-primary)'
  if (bucket === 'wants') return 'var(--accent-amber)'
  if (bucket === 'savings') return 'var(--accent-green)'
  return 'var(--text-secondary)'
}

export default function Recommendations() {
  const { data, isLoading } = useBudgetRecommendations()

  if (isLoading) return <div className="loading-spinner"><div className="spinner" /></div>

  // Group recommendations by bucket
  const needs = data?.recommendations?.filter((r: any) => r.bucket === 'needs') ?? []
  const wants = data?.recommendations?.filter((r: any) => r.bucket === 'wants') ?? []
  const savings = data?.recommendations?.filter((r: any) => r.bucket === 'savings') ?? []

  const needsTotal = needs.reduce((s: number, r: any) => s + r.recommended_amount, 0)
  const wantsTotal = wants.reduce((s: number, r: any) => s + r.recommended_amount, 0)
  const savingsTotal = savings.reduce((s: number, r: any) => s + r.recommended_amount, 0)
  const totalBudget = needsTotal + wantsTotal + savingsTotal

  return (
    <div>
      <h1 className="page-title">Budget Recommendations</h1>
      {data && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">Strategy</div>
          <p style={{ color: 'var(--text-secondary)' }}>
            Using <strong style={{ color: 'var(--accent-secondary)' }}>{data.strategy_used === 'proportional_income' ? 'Proportional Income Strategy' : data.strategy_used}</strong>{' '}
            based on <strong>{data.months_of_history}</strong> months of history.
            Budgets for the current month are computed proportionally from past expenditure ratios,
            scaled to this month's income, with <strong>50/30/20</strong> guardrails applied.
          </p>
          {data.current_month_income > 0 && (
            <p style={{ color: 'var(--accent-primary)', fontWeight: 700, fontSize: 18, marginTop: 8 }}>
              This month's income: ₹{fmt(data.current_month_income)}
            </p>
          )}
        </div>
      )}

      {/* 50/30/20 Allocation Overview */}
      {totalBudget > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">50/30/20 Allocation</div>
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginTop: 12 }}>
            <div style={{ flex: 1, minWidth: 140, padding: '16px 20px', borderRadius: 'var(--radius)', background: `${bucketColor('needs')}15`, borderLeft: `3px solid ${bucketColor('needs')}` }}>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.5px' }}>Needs (50%)</div>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>₹{fmt(needsTotal)}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{totalBudget > 0 ? ((needsTotal / totalBudget) * 100).toFixed(1) : 0}% of total</div>
            </div>
            <div style={{ flex: 1, minWidth: 140, padding: '16px 20px', borderRadius: 'var(--radius)', background: `${bucketColor('wants')}15`, borderLeft: `3px solid ${bucketColor('wants')}` }}>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.5px' }}>Wants (30%)</div>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>₹{fmt(wantsTotal)}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{totalBudget > 0 ? ((wantsTotal / totalBudget) * 100).toFixed(1) : 0}% of total</div>
            </div>
            <div style={{ flex: 1, minWidth: 140, padding: '16px 20px', borderRadius: 'var(--radius)', background: `${bucketColor('savings')}15`, borderLeft: `3px solid ${bucketColor('savings')}` }}>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.5px' }}>Savings (20%)</div>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>₹{fmt(savingsTotal)}</div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{totalBudget > 0 ? ((savingsTotal / totalBudget) * 100).toFixed(1) : 0}% of total</div>
            </div>
          </div>
        </div>
      )}

      {/* Per-category recommendations */}
      <div className="dashboard-grid">
        {data?.recommendations?.map((rec: {
          category_id: number; category_name: string;
          recommended_amount: number; bucket?: string; strategy: string
        }) => (
          <div key={rec.category_id} className="card" style={{ borderLeft: `3px solid ${bucketColor(rec.bucket)}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div className="card-title">{rec.category_name}</div>
              {rec.bucket && (
                <span style={{
                  fontSize: 10, padding: '2px 8px', borderRadius: 10,
                  background: `${bucketColor(rec.bucket)}22`,
                  color: bucketColor(rec.bucket),
                  fontWeight: 700, textTransform: 'uppercase' as const,
                }}>
                  {rec.bucket}
                </span>
              )}
            </div>
            <div className="stat-value">₹{rec.recommended_amount.toLocaleString()}</div>
            <div className="stat-label">
              {rec.strategy === 'proportional_income' ? 'Proportional Allocation' : rec.strategy}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
