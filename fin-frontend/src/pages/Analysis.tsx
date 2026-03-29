import { useState } from 'react'
import api from '../api/client'

export default function Analysis() {
  const [status, setStatus] = useState<'idle' | 'loading' | 'queued' | 'error'>('idle')
  const [result, setResult] = useState<Record<string, unknown> | null>(null)

  async function runAnalysis() {
    setStatus('loading')
    setResult(null)
    try {
      const res = await api.post('/analysis/run')
      setResult(res.data)
      setStatus('queued')
    } catch {
      setStatus('error')
    }
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">Analysis Tools</h1>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 max-w-lg">
        <h2 className="font-semibold mb-2">Trigger AI Analysis</h2>
        <p className="text-slate-400 text-sm mb-4">
          Manually trigger the AI analysis engine. Results will be stored in the result cache
          and visible on the dashboard within seconds.
        </p>

        <button
          onClick={runAnalysis}
          disabled={status === 'loading'}
          className="bg-brand hover:bg-brand-dark disabled:opacity-50 rounded-lg px-5 py-2 text-sm font-semibold transition"
        >
          {status === 'loading' ? 'Triggering…' : 'Run Analysis'}
        </button>

        {status === 'queued' && result && (
          <div className="mt-4 bg-green-900/30 border border-green-700 rounded-lg px-4 py-3 text-sm text-green-300">
            Analysis queued at {result.timestamp as string}
          </div>
        )}

        {status === 'error' && (
          <div className="mt-4 bg-red-900/30 border border-red-700 rounded-lg px-4 py-3 text-sm text-red-300">
            Failed to trigger analysis. Check your permissions or try again.
          </div>
        )}
      </div>
    </div>
  )
}
