import { useState, useMemo } from 'react'
import { useTransactions, useCategories, TransactionFilters } from '../api/transactions'
import AddTransactionModal from './AddTransactionModal'
import CSVUpload from './CSVUpload'

const CATEGORY_COLORS: Record<string, string> = {
  Groceries: '#34d399',
  Transportation: '#60a5fa',
  Utilities: '#fbbf24',
  Entertainment: '#a78bfa',
  Healthcare: '#f87171',
  Dining: '#fb923c',
  Shopping: '#f472b6',
  Education: '#818cf8',
  Travel: '#2dd4bf',
  Investments: '#34d399',
  'Rent/Housing': '#a78bfa',
  Insurance: '#94a3b8',
  'Personal Care': '#e879f9',
  Subscriptions: '#22d3ee',
  Other: '#6b7280',
}

function getCategoryColor(name: string) {
  return CATEGORY_COLORS[name] || CATEGORY_COLORS['Other']
}

/* ── Inline SVG icons ────────────────────────────────────────────── */
const PlusIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
    <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
  </svg>
)
const UploadIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
  </svg>
)
const SearchIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', pointerEvents: 'none' }}>
    <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
)
const InboxIcon = () => (
  <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--accent-primary)' }}>
    <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
    <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
  </svg>
)

export default function Transactions() {
  const [page, setPage] = useState(1)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showCSVModal, setShowCSVModal] = useState(false)

  // Filter state
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [amountMin, setAmountMin] = useState('')
  const [amountMax, setAmountMax] = useState('')

  const filters: TransactionFilters = useMemo(() => {
    const f: TransactionFilters = {}
    if (search.trim()) f.search = search.trim()
    if (category) f.category = category
    if (dateFrom) f.dateFrom = dateFrom
    if (dateTo) f.dateTo = dateTo
    if (amountMin) f.amountMin = Number(amountMin)
    if (amountMax) f.amountMax = Number(amountMax)
    return f
  }, [search, category, dateFrom, dateTo, amountMin, amountMax])

  const { data, isLoading } = useTransactions(page, 20, filters)
  const { data: categories } = useCategories()

  // Reset page when filters change
  const handleFilterChange = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setter(e.target.value)
    setPage(1)
  }

  const hasActiveFilters = search || category || dateFrom || dateTo || amountMin || amountMax
  const clearFilters = () => {
    setSearch(''); setCategory(''); setDateFrom(''); setDateTo('')
    setAmountMin(''); setAmountMax(''); setPage(1)
  }

  if (isLoading) return <div className="loading-spinner"><div className="spinner" /></div>

  const isEmpty = !data?.total

  // Derive category list from API or fallback
  const categoryList: string[] = categories
    ? categories.map((c: { category: string }) => c.category)
    : Object.keys(CATEGORY_COLORS)

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <h1 className="page-title" style={{ margin: 0 }}>Transactions</h1>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            id="btn-upload-csv"
            className="btn-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
            onClick={() => setShowCSVModal(true)}
          >
            <UploadIcon /> Upload CSV
          </button>
          <button
            id="btn-add-transaction"
            className="btn-primary"
            style={{ width: 'auto', padding: '10px 20px', display: 'inline-flex', alignItems: 'center', gap: 8 }}
            onClick={() => setShowAddModal(true)}
          >
            <PlusIcon /> Add Transaction
          </button>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="filter-bar" id="transaction-filters">
        <div className="filter-group" style={{ position: 'relative', flex: '1 1 200px' }}>
          <SearchIcon />
          <input
            id="filter-search"
            className="filter-input"
            type="text"
            placeholder="Search description or merchant..."
            value={search}
            onChange={handleFilterChange(setSearch)}
            style={{ paddingLeft: 36, width: '100%' }}
          />
        </div>
        <div className="filter-group">
          <select
            id="filter-category"
            className="form-select"
            value={category}
            onChange={handleFilterChange(setCategory)}
          >
            <option value="">All Categories</option>
            {categoryList.map((cat: string) => (
              <option key={cat} value={cat}>{cat}</option>
            ))}
          </select>
        </div>
        <div className="filter-group">
          <input
            id="filter-date-from"
            className="filter-input"
            type="date"
            value={dateFrom}
            onChange={handleFilterChange(setDateFrom)}
            title="From date"
          />
          <span className="filter-separator">→</span>
          <input
            id="filter-date-to"
            className="filter-input"
            type="date"
            value={dateTo}
            onChange={handleFilterChange(setDateTo)}
            title="To date"
          />
        </div>
        <div className="filter-group">
          <input
            id="filter-amount-min"
            className="filter-input filter-input-sm"
            type="number"
            placeholder="₹ Min"
            value={amountMin}
            onChange={handleFilterChange(setAmountMin)}
          />
          <span className="filter-separator">–</span>
          <input
            id="filter-amount-max"
            className="filter-input filter-input-sm"
            type="number"
            placeholder="₹ Max"
            value={amountMax}
            onChange={handleFilterChange(setAmountMax)}
          />
        </div>
        {hasActiveFilters && (
          <button id="btn-clear-filters" className="btn-clear-filters" onClick={clearFilters}>
            ✕ Clear
          </button>
        )}
      </div>

      {isEmpty ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <InboxIcon />
          </div>
          <h2>{hasActiveFilters ? 'No Matching Transactions' : 'No Transactions Yet'}</h2>
          <p>{hasActiveFilters
            ? 'Try adjusting your filters to find what you\'re looking for.'
            : 'Get started by adding a transaction manually or uploading a CSV file.'
          }</p>
          {hasActiveFilters ? (
            <button className="btn-secondary" onClick={clearFilters}>Clear Filters</button>
          ) : (
            <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginTop: 4 }}>
              <button className="btn-primary" style={{ width: 'auto', padding: '12px 28px', display: 'inline-flex', alignItems: 'center', gap: 8 }} onClick={() => setShowAddModal(true)}>
                <PlusIcon /> Add Transaction
              </button>
              <button className="btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }} onClick={() => setShowCSVModal(true)}>
                <UploadIcon /> Upload CSV
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <table className="transactions-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Description</th>
                <th>Category</th>
                <th style={{ textAlign: 'right' }}>Amount</th>
                <th>Currency</th>
              </tr>
            </thead>
            <tbody>
              {data?.transactions?.map((t: {
                id: string; ts: string; raw_description: string; merchant_name: string;
                amount: number; currency: string; category_name: string | null; category_icon: string | null
              }) => (
                <tr key={t.id}>
                  <td style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                    {new Date(t.ts).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </td>
                  <td style={{ fontWeight: 500 }}>{t.merchant_name || t.raw_description}</td>
                  <td>
                    <span
                      className="category-badge"
                      style={{
                        background: `${getCategoryColor(t.category_name || 'Other')}14`,
                        color: getCategoryColor(t.category_name || 'Other'),
                        borderColor: `${getCategoryColor(t.category_name || 'Other')}30`,
                      }}
                    >
                      {t.category_name || 'Uncategorized'}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600, textAlign: 'right', fontFeatureSettings: '"tnum"', color: t.amount < 0 ? 'var(--accent-red)' : 'var(--accent-green)' }}>
                    {t.amount < 0 ? '-' : '+'}₹{Math.abs(t.amount).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 12 }}>{t.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 16, padding: '16px 24px', borderTop: '1px solid var(--border)' }}>
            <button className="btn-secondary" style={{ padding: '8px 20px', fontSize: 13 }}
              onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>
              Previous
            </button>
            <span style={{ fontSize: 13, color: 'var(--text-secondary)', fontFeatureSettings: '"tnum"' }}>
              Page {page} of {Math.ceil((data?.total || 0) / 20)}
            </span>
            <button className="btn-secondary" style={{ padding: '8px 20px', fontSize: 13 }}
              onClick={() => setPage(p => p + 1)} disabled={!data || page * 20 >= data.total}>
              Next
            </button>
          </div>
        </div>
      )}

      {showAddModal && <AddTransactionModal onClose={() => setShowAddModal(false)} />}
      {showCSVModal && <CSVUpload onClose={() => setShowCSVModal(false)} />}
    </div>
  )
}
