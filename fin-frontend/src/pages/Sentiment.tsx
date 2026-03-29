import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale,
  LineElement, PointElement, Tooltip, Filler,
} from 'chart.js'
import { useDashboard } from '../hooks/useDashboard'

ChartJS.register(CategoryScale, LinearScale, LineElement, PointElement, Tooltip, Filler)

const MOCK_NEWS = [
  { ticker: 'FGBR 3416', headline: 'Dow Rises As Markets Dgy Tech Earnings Fed Hold The...', source: 'Reuters · 45m ago', market: 'Nasdaq · Inpulse · 8 1.23 14.6', tag: 'bull' },
  { ticker: 'AGDX 2609', headline: "India's Manufacturing Pmis Surg In Ih-21", source: 'Economic Times · 1h ago', market: 'Intraday Revg · 0 1.55 18.2', tag: 'bull' },
]

function GaugeCard({ value, label, change }: { value: number; label: string; change: string }) {
  const isPositive = value >= 0
  const color = value > 0.3 ? '#10b981' : value < -0.3 ? '#ef4444' : '#f59e0b'
  const classification = value > 0.3 ? 'Bullish' : value < -0.3 ? 'Bearish' : 'Neutral'
  const pct = Math.min(100, Math.max(0, ((value + 1) / 2) * 100))

  return (
    <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-5 flex flex-col items-center">
      {/* Circular gauge */}
      <div className="relative w-24 h-24 mb-3">
        <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
          <circle cx="50" cy="50" r="40" fill="none" stroke="#1e293b" strokeWidth="10" />
          <circle
            cx="50" cy="50" r="40" fill="none"
            stroke={color} strokeWidth="10"
            strokeDasharray={`${pct * 2.51} 251`}
            strokeLinecap="round"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold" style={{ color }}>{value >= 0 ? '+' : ''}{value.toFixed(2)}</span>
        </div>
      </div>
      <p className="text-sm font-semibold text-slate-300">{label}</p>
      <p className="text-xs mt-0.5" style={{ color }}>{classification}</p>
      <p className="text-[10px] text-slate-500 mt-1">{change}</p>
    </div>
  )
}

export default function Sentiment() {
  const { data } = useDashboard()
  const sentiment = data?.market_sentiment as Record<string, unknown> | null

  const globalScore = sentiment ? Number(sentiment.composite_score ?? 0.22) : 0.22
  const domesticScore = sentiment ? Number(sentiment.index_momentum ?? 0.48) : 0.48

  const lineLabels = ['1d', '5d', '1m', '3m', '6m', '1y']
  const lineData = {
    labels: lineLabels,
    datasets: [{
      label: 'Domestic Sentiment',
      data: [180, 250, 320, 400, 480, 560],
      borderColor: 'rgba(52,211,153,0.8)',
      backgroundColor: 'rgba(52,211,153,0.08)',
      fill: true,
      tension: 0.4,
      pointRadius: 3,
      pointBackgroundColor: 'rgba(52,211,153,1)',
    }],
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-base font-semibold text-slate-200">Sentiment</h1>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">user@finintelligence.com</span>
          <select className="text-xs bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-300">
            <option>User</option>
          </select>
          <select className="text-xs bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-300">
            <option>Actout</option>
          </select>
          <select className="text-xs bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-300">
            <option>Date</option>
          </select>
        </div>
      </div>

      {/* Global Sentiment header */}
      <h2 className="text-sm font-semibold text-slate-300">Global Sentiment</h2>

      <div className="grid grid-cols-3 gap-4">
        {/* Gauge cards */}
        <GaugeCard value={globalScore} label="Global Sentiment" change={`↑ ${Math.abs(globalScore * 100).toFixed(0)}d`} />
        <GaugeCard value={domesticScore} label="Domestic Sentiment" change={`↑ 0.0% week`} />

        {/* Domestic Sentiment chart */}
        <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-slate-300">Domestic Sentiment</h3>
            <span className="text-[10px] text-emerald-400">+1 71 3b min. ×</span>
          </div>
          <div style={{ height: 100 }}>
            <Line data={lineData} options={{
              responsive: true, maintainAspectRatio: false,
              plugins: { legend: { display: false } },
              scales: {
                x: { ticks: { color: '#64748b', font: { size: 9 } }, grid: { display: false } },
                y: { ticks: { color: '#64748b', font: { size: 9 } }, grid: { color: '#1e293b' } },
              },
            }} />
          </div>
        </div>
      </div>

      {/* News Feed */}
      <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Global Sentiment</h2>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-slate-800">
              <th className="text-left pb-2">Caller</th>
              <th className="text-left pb-2">Headline</th>
              <th className="text-right pb-2">Date</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_NEWS.map((n, i) => (
              <tr key={i} className="border-b border-slate-800/40 hover:bg-slate-800/20">
                <td className="py-2 text-slate-400 font-mono">{n.ticker}</td>
                <td className="py-2">
                  <p className="text-slate-300 truncate max-w-xs">{n.headline}</p>
                  <p className="text-slate-500 text-[10px]">{n.source}</p>
                </td>
                <td className="py-2 text-right">
                  <p className="text-slate-400 text-[10px]">{n.market}</p>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${n.tag === 'bull' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400'}`}>
                    {n.tag}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
