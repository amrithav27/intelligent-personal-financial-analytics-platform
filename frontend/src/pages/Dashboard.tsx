import { useDashboardOverview, useFHSHistory } from '../api/dashboard'
import { useSpendingTrends } from '../api/analytics'
import { useBudgets } from '../api/budgets'
import { 
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  LineChart, Line
} from 'recharts'

const COLORS = ['#7c5cfc', '#34d399', '#fbbf24', '#f87171', '#22d3ee', '#a78bfa', '#f472b6', '#2dd4bf']

// ── Null Object Pattern: EmptyState ──────────────────────────────────────────
// Provides a consistent, styled placeholder when a widget has no data.
// Avoids broken/blank charts and guides users toward the next action.
interface EmptyStateProps {
  icon: string
  title: string
  description: string
}
function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 10, padding: '32px 16px', minHeight: 140,
      color: 'var(--text-muted)', textAlign: 'center',
    }}>
      <span style={{ fontSize: 36, lineHeight: 1 }}>{icon}</span>
      <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-secondary)' }}>{title}</div>
      <div style={{ fontSize: 12, maxWidth: 220 }}>{description}</div>
    </div>
  )
}

// ── Data Freshness Notice ─────────────────────────────────────────────────────
function DataFreshnessNotice() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px',
      background: 'rgba(124, 92, 252, 0.08)', border: '1px solid rgba(124, 92, 252, 0.2)',
      borderRadius: 10, marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)',
    }}>
      <span style={{ fontSize: 16 }}>⏳</span>
      <span>
        Your data hasn't been processed yet. Upload a CSV or add transactions to see live insights.
      </span>
    </div>
  )
}

function FHSGauge({ score, dataFreshness }: { score: number; dataFreshness?: string }) {
  const isStale = dataFreshness === 'stale' || score === 0
  const colorClass = score >= 70 ? 'good' : score >= 40 ? 'warning' : 'poor'
  const label = score >= 70 ? 'Excellent' : score >= 40 ? 'Needs Attention' : 'Poor'
  return (
    <div className="card">
      <div className="card-title">Financial Health Score</div>
      {isStale && score === 0 ? (
        <EmptyState
          icon="📊"
          title="No score yet"
          description="Upload transactions to compute your financial health score"
        />
      ) : (
        <>
          <div className={`fhs-score ${colorClass}`}>{score.toFixed(0)}</div>
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)', fontSize: 13, fontWeight: 500 }}>
            {label}
          </div>
        </>
      )}
    </div>
  )
}

function SpendingPieChart({ data }: { data: Array<{ category: string; amount: number }> }) {
  const total = data.reduce((s, d) => s + d.amount, 0)
  return (
    <div className="card">
      <div className="card-title">Spending by Category</div>
      {data.length === 0 ? (
        <EmptyState
          icon="🥧"
          title="No spending data this month"
          description="Add or upload transactions to see your category breakdown"
        />
      ) : (
        // Increased height to 300 to give Legend room beneath the donut.
        // Labels are rendered via <Legend> (never clipped by the SVG viewBox)
        // instead of the inline `label` prop that caused text to overflow the card.
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={data}
              dataKey="amount"
              nameKey="category"
              cx="50%"
              cy="45%"
              innerRadius={55}
              outerRadius={80}
              paddingAngle={2}
              label={false}      // 🔥 IMPORTANT
              labelLine={false}  // 🔥 IMPORTANT
            >
              {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip
              itemStyle={{ color: 'white' }}
              formatter={(value: number) => [
                `₹${(value as number).toLocaleString('en-IN')}`,
                `(${total > 0 ? ((value as number / total) * 100).toFixed(1) : 0}%)`,
              ]}
              contentStyle={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                fontSize: 13,
                color: 'white',
              }}
            />
            {/* Legend renders outside SVG — labels never overflow the card */}
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{
                fontSize: 11,
                color: 'var(--text-secondary)',
                paddingTop: 8,
                lineHeight: '20px',
              }}
              formatter={(value: string, entry: any) => {
                const pct = total > 0 ? ((entry.payload.amount / total) * 100).toFixed(1) : '0'
                return `${value} ${pct}%`
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

function BudgetBars() {
  const { data, isLoading } = useBudgets()

  if (isLoading) {
    return (
      <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="spinner" style={{ width: 24, height: 24 }} />
      </div>
    )
  }

  const budgets = data?.recommendations || []

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column' }}>
      <div className="card-title">Budget Status</div>
      {budgets.length === 0 ? (
        <EmptyState
          icon="💰"
          title="No budgets computed here"
          description="Wait for transactions to be categorized to see live budgets."
        />
      ) : (
        <div style={{ flex: 1, overflowY: 'auto', maxHeight: '250px', paddingRight: '8px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {budgets.map(b => {
             // Avoid uncategorized displaying with a budget limit of 0 causing NaN bar overflows
            if (b.category_id === 0) return null

            return (
              <div key={b.category_id} className="budget-bar" style={{ marginBottom: 0 }}>
                <div className="budget-bar-label">
                  <span style={{ fontWeight: 500 }}>{b.category_name}</span>
                  <span style={{ color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>
                    ₹{b.current_spending.toLocaleString('en-IN', { maximumFractionDigits: 0 })} / ₹{b.effective_limit.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                  </span>
                </div>
                <div className="budget-bar-track">
                  <div className={`budget-bar-fill ${b.alert_level}`} style={{ width: `${Math.min(b.pct_used, 100)}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function SpendingTrendsChart({ data }: { data: any[] }) {
  // Ensure data is an array
  const safeData = Array.isArray(data) ? data : []
  const latestMoM = safeData && safeData.length > 0 ? safeData[safeData.length - 1].mom_change_percent : null
  
  return (
    <div className="card" style={{ gridColumn: 'span 2' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div className="card-title" style={{ marginBottom: 0 }}>Monthly Spending Trends</div>
        {latestMoM !== null && (
          <div className={`badge-chip ${latestMoM > 0 ? 'warning-chip' : ''}`} style={{ 
            background: latestMoM > 0 ? 'rgba(251, 113, 133, 0.1)' : 'rgba(52, 211, 153, 0.1)',
            borderColor: latestMoM > 0 ? 'rgba(251, 113, 133, 0.2)' : 'rgba(52, 211, 153, 0.2)',
            color: latestMoM > 0 ? 'var(--accent-red)' : 'var(--accent-green)'
          }}>
            {latestMoM > 0 ? '↑' : '↓'} {Math.abs(latestMoM)}% MoM
          </div>
        )}
      </div>
      {safeData.length === 0 ? (
        <EmptyState
          icon="📈"
          title="No trend data yet"
          description="Spending trends will appear once you have transactions across multiple months"
        />
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <AreaChart data={safeData}>
            <defs>
              <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.3}/>
                <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis 
              dataKey="month" 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
              dy={10}
            />
            <YAxis 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
              tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`}
            />
            <Tooltip 
              contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 12, boxShadow: 'var(--shadow-lg)' }}
              itemStyle={{ color: 'var(--text-primary)', fontWeight: 600 }}
              labelStyle={{ color: 'var(--text-muted)', marginBottom: 4, fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}
              formatter={(value: number) => [`₹${value.toLocaleString('en-IN')}`, 'Total Spending']}
            />
            <Area 
              type="monotone" 
              dataKey="total" 
              stroke="var(--accent-primary)" 
              strokeWidth={3}
              fillOpacity={1} 
              fill="url(#colorTotal)" 
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

function FHSHistoryChart({ data }: { data: any[] }) {
  // Ensure data is an array
  const safeData = Array.isArray(data) ? data : []
  // data comes in DESC order from API, reverse for chart
  const chartData = [...safeData].reverse().map(d => {
    // Normalize Python datetime str format ("2026-05-05 12:00:00") to ISO 8601 ("2026-05-05T12:00:00")
    const raw = String(d.computed_at || '').replace(' ', 'T')
    const parsed = new Date(raw)
    const dateLabel = isNaN(parsed.getTime())
      ? String(d.computed_at || '').slice(0, 10)
      : parsed.toLocaleDateString('en-IN', { month: 'short', day: '2-digit' })
    return { ...d, date: dateLabel }
  })

  return (
    <div className="card" style={{ gridColumn: 'span 2' }}>
      <div className="card-title">Financial Health History</div>
      {chartData.length === 0 ? (
        <EmptyState
          icon="🏥"
          title="No health score history yet"
          description="Your FHS history will be tracked each time analytics runs after a transaction upload"
        />
      ) : (
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
            <XAxis 
              dataKey="date" 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
              dy={10}
            />
            <YAxis 
              domain={[0, 100]}
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            />
            <Tooltip 
              contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 12, boxShadow: 'var(--shadow-lg)' }}
              itemStyle={{ fontWeight: 600 }}
              labelStyle={{ color: 'var(--text-muted)', marginBottom: 4, fontSize: 11, fontWeight: 700, textTransform: 'uppercase' }}
            />
            <Line 
              type="monotone" 
              dataKey="score" 
              stroke="var(--accent-green)" 
              strokeWidth={3} 
              dot={{ fill: 'var(--accent-green)', r: 4, strokeWidth: 2, stroke: 'var(--bg-primary)' }}
              activeDot={{ r: 6, strokeWidth: 0 }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

function TransactionTable({ transactions }: { transactions: Array<{
  id: string; amount: number; merchant_name: string; description: string; ts: string; category: string
}> }) {
  return (
    <div className="card" style={{ gridColumn: '1 / -1', padding: 0, overflow: 'hidden' }}>
      <div style={{ padding: '20px 24px 0' }}>
        <div className="card-title">Recent Transactions</div>
      </div>
      {transactions.length === 0 ? (
        <div style={{ padding: '0 24px 24px' }}>
          <EmptyState
            icon="🧾"
            title="No transactions yet"
            description="Upload a CSV bank statement or add a transaction manually to get started"
          />
        </div>
      ) : (
        <table className="transactions-table">
          <thead>
            <tr><th>Date</th><th>Description</th><th>Category</th><th style={{ textAlign: 'right' }}>Amount</th></tr>
          </thead>
          <tbody>
            {transactions.map(t => (
              <tr key={t.id}>
                <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                  {new Date(t.ts).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}
                </td>
                <td style={{ fontWeight: 500 }}>{t.merchant_name || t.description}</td>
                <td><span className="category-badge">{t.category}</span></td>
                <td style={{ fontWeight: 600, textAlign: 'right', fontFeatureSettings: '"tnum"' }}>
                  ₹{Math.abs(t.amount).toLocaleString('en-IN')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default function Dashboard() {
  const { data, isLoading: isOverviewLoading, error: overviewError } = useDashboardOverview()
  const { data: trendsData, isLoading: isTrendsLoading } = useSpendingTrends(6)
  const { data: fhsHistory, isLoading: isFHSLoading } = useFHSHistory(12)

  const isLoading = isOverviewLoading || isTrendsLoading || isFHSLoading
  const error = overviewError

  if (isLoading) return <div className="loading-spinner"><div className="spinner" /></div>
  if (error) return <p style={{ color: 'var(--accent-red)' }}>Failed to load dashboard</p>
  if (!data) return null

  // Show freshness notice when FHS is stale (no processed data yet)
  const showFreshnessNotice = data.fhs?.data_freshness === 'stale'

  return (
    <div>
      <h1 className="page-title">Dashboard</h1>
      {data.unread_alerts > 0 && (
        <div className="alert-banner">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          You have {data.unread_alerts} unread alert{data.unread_alerts > 1 ? 's' : ''}
        </div>
      )}
      {showFreshnessNotice && <DataFreshnessNotice />}
      <div className="dashboard-grid">
        <FHSGauge score={data.fhs?.score || 0} dataFreshness={data.fhs?.data_freshness} />
        <SpendingPieChart data={data.categories || []} />
        <BudgetBars />
        <div className="card">
          <div className="card-title">Quick Stats</div>
          <div style={{ display: 'grid', gap: 20 }}>
            <div>
              <div className="stat-value">{data.categories?.length || 0}</div>
              <div className="stat-label">Active Categories</div>
            </div>
            <div>
              <div className="stat-value">{data.recent_transactions?.length || 0}+</div>
              <div className="stat-label">Recent Transactions</div>
            </div>
          </div>
        </div>
        <SpendingTrendsChart data={trendsData || []} />
        <FHSHistoryChart data={fhsHistory || []} />
      </div>
      <TransactionTable transactions={data.recent_transactions || []} />
    </div>
  )
}
