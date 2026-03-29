import { NavLink, Outlet } from 'react-router-dom'

const navItems = [
  { to: '/dashboard', label: 'Dashboard', icon: '⊞' },
  { to: '/sectors', label: 'Sectors', icon: '◫' },
  { to: '/flows', label: 'Institutional Flow', icon: '⇅' },
  { to: '/sentiment', label: 'Sentiment', icon: '◎' },
  { to: '/analysis', label: 'Analysis', icon: '⚡' },
  { to: '/admin', label: 'Admin', icon: '⚙' },
]

export default function Layout() {
  return (
    <div className="flex min-h-screen bg-[#080c10]">
      {/* Sidebar */}
      <aside className="w-52 bg-[#0d1117] border-r border-slate-800 flex flex-col">
        <div className="px-4 py-4 border-b border-slate-800 flex items-center gap-2">
          <span className="text-emerald-400 text-lg">≋</span>
          <span className="text-slate-100 font-semibold text-sm">FinIntelligence</span>
        </div>
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          {navItems.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-md text-xs transition ${
                  isActive
                    ? 'bg-emerald-900/30 text-emerald-400 font-medium'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                }`
              }
            >
              <span className="text-sm">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-2 py-3 border-t border-slate-800">
          <button className="flex items-center gap-2.5 px-3 py-2 w-full text-xs text-slate-500 hover:text-red-400 transition rounded-md hover:bg-slate-800/50">
            <span>↩</span> Logout
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto p-5 bg-[#080c10]">
        <Outlet />
      </main>
    </div>
  )
}
