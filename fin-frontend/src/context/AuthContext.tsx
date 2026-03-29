import React, { createContext, useContext, useState, useCallback } from 'react'
import api from '../api/client'

interface AuthState {
  token: string | null
  role: string | null
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isAuthenticated: boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>(() => ({
    token: sessionStorage.getItem('token'),
    role: sessionStorage.getItem('role'),
  }))

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post('/auth/login', { email, password })
    const { access_token } = res.data
    // Decode role from JWT payload (base64)
    const payload = JSON.parse(atob(access_token.split('.')[1]))
    sessionStorage.setItem('token', access_token)
    sessionStorage.setItem('role', payload.role)
    setAuth({ token: access_token, role: payload.role })
  }, [])

  const logout = useCallback(async () => {
    try { await api.post('/auth/logout') } catch { /* ignore */ }
    sessionStorage.clear()
    setAuth({ token: null, role: null })
  }, [])

  return (
    <AuthContext.Provider value={{ ...auth, login, logout, isAuthenticated: !!auth.token }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
