import { useEffect, useState, useCallback } from 'react'
import api from '../api/client'

export interface DashboardData {
  market_sentiment: Record<string, unknown> | null
  sector_strength: Record<string, unknown>[] | null
  institutional_flows: Record<string, unknown> | null
  ai_signals: Record<string, unknown> | null
}

export function useDashboard(pollMs = 30000) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(async () => {
    try {
      const res = await api.get<DashboardData>('/api/dashboard')
      setData(res.data)
      setError(null)
    } catch (e: unknown) {
      setError('Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch()
    const id = setInterval(fetch, pollMs)
    return () => clearInterval(id)
  }, [fetch, pollMs])

  return { data, loading, error, refresh: fetch }
}
