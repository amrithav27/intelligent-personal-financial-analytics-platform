import { useState } from 'react'
import { useAuthStore } from '../store/authStore'
import { authAPI } from '../api/auth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [isRegister, setIsRegister] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const setTokens = useAuthStore(s => s.setTokens)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const response = isRegister
        ? await authAPI.register({ email, display_name: displayName, password })
        : await authAPI.login({ email, password })

      const { access_token, refresh_token } = response.data
      setTokens(access_token, refresh_token)
      window.location.href = '/'
    } catch (err: unknown) {
      const message = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Authentication failed'
      setError(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <h1>
          <span className="logo-mark">P</span>
          Phoenix
        </h1>
        <form onSubmit={handleSubmit}>
          {isRegister && (
            <div className="form-group">
              <label>Display Name</label>
              <input
                type="text"
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                placeholder="Your name"
                required
              />
            </div>
          )}
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
            />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              minLength={8}
            />
          </div>
          {error && <p style={{ color: 'var(--accent-red)', marginBottom: 16, fontSize: 14 }}>{error}</p>}
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Please wait...' : (isRegister ? 'Create Account' : 'Sign In')}
          </button>
          <p style={{ textAlign: 'center', marginTop: 20, color: 'var(--text-secondary)', fontSize: 13 }}>
            {isRegister ? 'Already have an account? ' : "Don't have an account? "}
            <a href="#" onClick={(e) => { e.preventDefault(); setIsRegister(!isRegister); setError('') }}
               style={{ color: 'var(--accent-secondary)', fontWeight: 600, textDecoration: 'none' }}>
              {isRegister ? 'Sign In' : 'Register'}
            </a>
          </p>
        </form>
      </div>
    </div>
  )
}
