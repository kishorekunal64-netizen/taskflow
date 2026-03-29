import { useEffect, useState } from 'react'
import api from '../api/client'

export function useHealth() {
  const [connected, setConnected] = useState<boolean | null>(null)

  useEffect(() => {
    const check = async () => {
      try {
        await api.get('/api/dashboard', { timeout: 4000 })
        setConnected(true)
      } catch {
        try {
          await api.get('/health', { timeout: 4000 })
          setConnected(true)
        } catch {
          setConnected(false)
        }
      }
    }

    check()
    const id = setInterval(check, 5000)
    return () => clearInterval(id)
  }, [])

  return connected
}
