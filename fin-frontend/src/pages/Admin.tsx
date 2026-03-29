import { useEffect, useState } from 'react'
import api from '../api/client'

interface ActivityLog {
  user_id: string
  action: string
  timestamp: string
  ip_address: string
}

interface User {
  user_id: string
  email: string
  role: string
  status: string
  created_at: string
}

export default function Admin() {
  const [tab, setTab] = useState<'users' | 'activity'>('users')
  const [users, setUsers] = useState<User[]>([])
  const [logs, setLogs] = useState<ActivityLog[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (tab === 'users') {
      setLoading(true)
      api.get<User[]>('/admin/users')
        .then(r => setUsers(r.data))
        .finally(() => setLoading(false))
    } else {
      setLoading(true)
      api.get<{ logs: ActivityLog[] }>('/admin/activity?limit=50')
        .then(r => setLogs(r.data.logs))
        .finally(() => setLoading(false))
    }
  }, [tab])

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">Admin Panel</h1>

      <div className="flex gap-2 mb-6">
        {(['users', 'activity'] as const).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
              tab === t
                ? 'bg-brand text-white'
                : 'bg-slate-800 text-slate-400 hover:text-slate-100'
            }`}
          >
            {t === 'users' ? 'Users' : 'Activity Log'}
          </button>
        ))}
      </div>

      {loading && <p className="text-slate-400 text-sm">Loading…</p>}

      {!loading && tab === 'users' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="text-left px-4 py-3">Email</th>
                <th className="text-left px-4 py-3">Role</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.user_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="px-4 py-3">{u.email}</td>
                  <td className="px-4 py-3 capitalize text-brand">{u.role}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      u.status === 'active'
                        ? 'bg-green-900/40 text-green-400'
                        : 'bg-red-900/40 text-red-400'
                    }`}>{u.status}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {new Date(u.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && tab === 'activity' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="text-left px-4 py-3">Action</th>
                <th className="text-left px-4 py-3">User ID</th>
                <th className="text-left px-4 py-3">IP</th>
                <th className="text-left px-4 py-3">Time</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((l, i) => (
                <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      l.action === 'login' ? 'bg-green-900/40 text-green-400' :
                      l.action === 'failed_login' ? 'bg-red-900/40 text-red-400' :
                      l.action === 'logout' ? 'bg-slate-700 text-slate-300' :
                      'bg-brand/20 text-brand'
                    }`}>{l.action}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 font-mono text-xs truncate max-w-[120px]">
                    {l.user_id}
                  </td>
                  <td className="px-4 py-3 text-slate-400">{l.ip_address}</td>
                  <td className="px-4 py-3 text-slate-400">
                    {new Date(l.timestamp).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
