import { useState, useCallback } from 'react'
import { useUploadCSV } from '../api/transactions'

interface Props {
    onClose: () => void
}

export default function CSVUpload({ onClose }: Props) {
    const [dragOver, setDragOver] = useState(false)
    const [progress, setProgress] = useState(0)
    const [result, setResult] = useState<{ ingested: number; skipped: number } | null>(null)
    const { mutate, isPending, error } = useUploadCSV()

    const handleFile = useCallback((file: File) => {
        if (!file.name.endsWith('.csv') && file.type !== 'text/csv') {
            alert('Please upload a .csv file')
            return
        }
        setProgress(0)
        mutate(
            { file, onProgress: setProgress },
            { onSuccess: (data: { ingested: number; skipped: number }) => setResult(data) }
        )
    }, [mutate])

    function onDrop(e: React.DragEvent) {
        e.preventDefault()
        setDragOver(false)
        const file = e.dataTransfer.files[0]
        if (file) handleFile(file)
    }

    function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
        const file = e.target.files?.[0]
        if (file) handleFile(file)
    }

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <span>Upload CSV</span>
                    <button className="modal-close" onClick={onClose}>✕</button>
                </div>

                {result ? (
                    <div style={{ textAlign: 'center', padding: '24px 0' }}>
                        <div style={{ fontSize: 48, marginBottom: 12 }}></div>
                        <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent-green)', marginBottom: 8 }}>
                            Upload Complete
                        </div>
                        <div style={{ color: 'var(--text-secondary)' }}>
                            <strong style={{ color: 'var(--text-primary)' }}>{result.ingested}</strong> transactions imported
                            {result.skipped > 0 && (
                                <span>, <strong>{result.skipped}</strong> skipped (duplicates)</span>
                            )}
                        </div>
                        <button className="btn-primary" style={{ marginTop: 24, width: 'auto', padding: '10px 32px' }} onClick={onClose}>
                            Done
                        </button>
                    </div>
                ) : (
                    <>
                        <div style={{ marginBottom: 16, fontSize: 13, color: 'var(--text-secondary)', background: 'var(--bg-secondary)', padding: '10px 14px', borderRadius: 8 }}>
                            Expected CSV format: <code style={{ color: 'var(--accent-secondary)' }}>date,amount,description</code>
                            <br />
                            <span style={{ opacity: 0.7 }}>Example: <code>2024-01-15,500,Coffee at Starbucks</code></span>
                        </div>

                        <label htmlFor="csv-file-input">
                            <div
                                className={`dropzone${dragOver ? ' active' : ''}`}
                                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                                onDragLeave={() => setDragOver(false)}
                                onDrop={onDrop}
                            >
                                {isPending ? (
                                    <div style={{ textAlign: 'center' }}>
                                        <div style={{ fontSize: 14, marginBottom: 12, color: 'var(--text-secondary)' }}>
                                            Uploading… {progress}%
                                        </div>
                                        <div className="progress-track">
                                            <div className="progress-bar" style={{ width: `${progress}%` }} />
                                        </div>
                                    </div>
                                ) : (
                                    <>
                                        <div style={{ fontSize: 40, marginBottom: 12 }}></div>
                                        <div style={{ fontWeight: 600, marginBottom: 6 }}>Drag &amp; drop your CSV here</div>
                                        <div style={{ fontSize: 14, color: 'var(--text-secondary)' }}>or click to browse</div>
                                    </>
                                )}
                            </div>
                        </label>
                        <input
                            id="csv-file-input"
                            type="file"
                            accept=".csv,text/csv"
                            style={{ display: 'none' }}
                            onChange={onFileChange}
                        />

                        {error && (
                            <p style={{ color: 'var(--accent-red)', marginTop: 12, fontSize: 14 }}>
                                {(error as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Upload failed. Check CSV format.'}
                            </p>
                        )}

                        <button type="button" onClick={onClose}
                            style={{ marginTop: 16, width: '100%', padding: '11px', background: 'var(--bg-secondary)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text-primary)', cursor: 'pointer', fontWeight: 600 }}>
                            Cancel
                        </button>
                    </>
                )}
            </div>
        </div>
    )
}
