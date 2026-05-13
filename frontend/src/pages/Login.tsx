import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, setToken } from '../api/client'

export default function Login() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await login(username, password)
      setToken(data.access_token)
      navigate('/')
    } catch {
      setError('Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-base flex items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-xl font-semibold text-white tracking-tight">Polymarket Intelligence</h1>
          <p className="text-muted text-sm mt-1">Sign in to continue</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="bg-panel border border-border rounded-lg p-6 space-y-4"
        >
          <div>
            <label className="block text-sm text-muted mb-1">Username</label>
            <input
              type="text"
              value={username}
              onChange={e => setUsername(e.target.value)}
              className="w-full bg-card border border-border rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
              required
              autoComplete="username"
            />
          </div>

          <div>
            <label className="block text-sm text-muted mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full bg-card border border-border rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-accent"
              required
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p className="text-red text-sm">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-accent hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-medium py-2 rounded transition-colors"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
