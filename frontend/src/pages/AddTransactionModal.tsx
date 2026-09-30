import { useState } from 'react'
import { useAddTransaction, ManualTransactionPayload } from '../api/transactions'

interface Props {
    onClose: () => void
}

export default function AddTransactionModal({ onClose }: Props) {
    const today = new Date().toISOString().split('T')[0]
    const [type, setType] = useState<'expense' | 'income'>('expense')
    const [form, setForm] = useState<ManualTransactionPayload>({
        amount: 0,
        description: '',
        merchant_name: '',
        date: today,
        currency: 'INR',
    })
    const [success, setSuccess] = useState(false)
    const { mutate, isPending, error } = useAddTransaction()

    function handleSubmit(e: React.FormEvent) {
        e.preventDefault()
        if (!form.amount || !form.description) return

        // Multiplier based on type: Expense = negative, Income = positive
        const amount = Number(form.amount)
        const finalAmount = type === 'expense' ? -Math.abs(amount) : Math.abs(amount)

        const payload: ManualTransactionPayload = {
            amount: finalAmount,
            description: form.description,
            currency: 'INR',
        }
        if (form.merchant_name) payload.merchant_name = form.merchant_name
        if (form.date) payload.date = form.date

        // Note: mcc_code can be used to influence categorization!
        // We'll map some helpful labels to descriptions to help the analytics engine
        mutate(payload, {
            onSuccess: () => {
                setSuccess(true)
                setTimeout(onClose, 1200)
            },
        })
    }

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 450 }}>
                <div className="modal-header">
                    <span>Add Transaction</span>
                    <button className="modal-close" onClick={onClose}>✕</button>
                </div>

                {success ? (
                    <div style={{ textAlign: 'center', padding: '32px 0' }}>
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--accent-green)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: 12 }}>
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                            <polyline points="22 4 12 14.01 9 11.01" />
                        </svg>
                        <div style={{ color: 'var(--accent-green)', fontSize: 16, fontWeight: 600 }}>
                            Transaction added successfully
                        </div>
                    </div>
                ) : (
                    <form onSubmit={handleSubmit}>
                        {/* Transaction Type Toggle */}
                        <div style={{ display: 'flex', background: 'var(--bg-secondary)', padding: 4, borderRadius: 8, marginBottom: 20 }}>
                            <button
                                type="button"
                                style={{
                                    flex: 1, padding: '8px', border: 'none', borderRadius: 6, cursor: 'pointer',
                                    fontWeight: 600, transition: 'all 0.2s',
                                    background: type === 'expense' ? 'var(--accent-red)' : 'transparent',
                                    color: type === 'expense' ? 'white' : 'var(--text-secondary)'
                                }}
                                onClick={() => setType('expense')}
                            >
                                💸 Expense
                            </button>
                            <button
                                type="button"
                                style={{
                                    flex: 1, padding: '8px', border: 'none', borderRadius: 6, cursor: 'pointer',
                                    fontWeight: 600, transition: 'all 0.2s',
                                    background: type === 'income' ? 'var(--accent-green)' : 'transparent',
                                    color: type === 'income' ? 'white' : 'var(--text-secondary)'
                                }}
                                onClick={() => setType('income')}
                            >
                                💰 Income
                            </button>
                        </div>

                        <div className="form-group">
                            <label>Amount (₹) <span style={{ color: 'var(--accent-red)' }}>*</span></label>
                            <input
                                id="txn-amount"
                                type="number"
                                step="0.01"
                                min="0.01"
                                required
                                placeholder="500"
                                value={form.amount || ''}
                                style={{ color: type === 'expense' ? 'var(--accent-red)' : 'var(--accent-green)', fontWeight: 600 }}
                                onChange={e => setForm(f => ({ ...f, amount: parseFloat(e.target.value) || 0 }))}
                            />
                        </div>

                        <div className="form-group">
                            <label>Merchant Name <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(optional)</span></label>
                            <input
                                id="txn-merchant"
                                type="text"
                                placeholder="e.g. Starbucks or Salary"
                                value={form.merchant_name ?? ''}
                                onChange={e => setForm(f => ({ ...f, merchant_name: e.target.value }))}
                            />
                        </div>

                        <div className="form-group">
                            <label>Description <span style={{ color: 'var(--accent-red)' }}>*</span></label>
                            <input
                                id="txn-desc"
                                type="text"
                                required
                                placeholder="e.g. Morning Coffee"
                                value={form.description}
                                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                            />
                        </div>

                        <div className="form-group">
                            <label>Date</label>
                            <input
                                id="txn-date"
                                type="date"
                                value={form.date ?? today}
                                onChange={e => setForm(f => ({ ...f, date: e.target.value }))}
                                style={{ colorScheme: 'dark' }}
                            />
                        </div>

                        {error && (
                            <p style={{ color: 'var(--accent-red)', marginBottom: 16, fontSize: 14 }}>
                                {(error as Error).message || 'Failed to add transaction'}
                            </p>
                        )}

                        <div style={{ display: 'flex', gap: 12 }}>
                            <button type="button" className="btn-secondary" onClick={onClose} style={{ flex: 1, padding: 12 }}>
                                Cancel
                            </button>
                            <button type="submit" className="btn-primary" style={{ flex: 2 }} disabled={isPending}>
                                {isPending ? 'Saving…' : 'Save Transaction'}
                            </button>
                        </div>
                    </form>
                )}
            </div>
        </div>
    )
}
