import { Bar, Line } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement,
  LineElement, PointElement, Tooltip, Filler,
} from 'chart.js'
import { useDashboard } from '../hooks/useDashboard'

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Filler)

const MOCK_SECTORS = [
  { sector: 'IT', momentum_score: 78, relative_strength: 1.2, ranking: 1 },
  { sector: 'Auto', momentum_score: 71, relative_strength: 0.9, ranking: 2 },
  { sector: 'FMCG', momentum_score: 63, relative_strength: 0.0, ranking: 3 },
  { sector: 'Pharma', momentum_score: 65, relative_strength: 0.0, ranking: 4 },
  { sector: 'Energy', momentum_score: 55, relative_strength: 0.0, ranking: 5 },
]

const FLOW_LABELS = ['1d', '5d', '1m', '3m', '6m', '1y']
const MOCK_FLOW = [180, 250, 320, 400, 480, 560, 620]

export default function Sectors() {
  const { data } = useDashboard()
  const sectors = (data?.sector_strength as Record<string, unknown>[] | null) ?? MOCK_SECTORS
  const flows = data?.institutional_flows as Record<string, unknown> | null

  const sorted = [...sectors].sort((a, b) => Number(a.ranking ?? 99) - Number(b.ranking ?? 99))

  const barData = {
    labels: sorted.map(s => s.sector as string),
    datasets: [{
      label: 'Momentum',
      data: sorted.map(s => Number(s.momentum_score ?? 0)),
      backgroundColor: sorted.map(s =>
        Number(s.momentum_score ?? 0) >= 70 ? 'rgba(52,211,153,0.85)' : 'rgba(52,211,153,0.45)'
      ),
      borderRadius: 3,
      barThickness: 32,
    }],
  }

  const netFlowPoints = flows
    ? FLOW_LABELS.map((_, i) => Number(flows.net_flow ?? 0) * (0.5 + i * 0.1))
    : MOCK_FLOW

  const lineData = {
    labels: FLOW_LABELS,
    datasets: [{
      label: 'Net Flow',
      data: netFlowPoints,
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
        <h1 className="text-base font-semibold text-slate-200">Sectors</h1>
        <span className="text-xs text-slate-400">user@finintelligence.com</span>
      </div>

      {/* Sector Momentum Chart */}
      <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Sector Momentum</h2>
        <div style={{ height: 160 }}>
          <Bar data={barData} options={{
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { display: false } },
              y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e293b' }, min: 40, max: 120 },
            },
          }} />
        </div>
      </div>

      {/* Rankings + Flow */}
      <div className="grid grid-cols-2 gap-4">
        {/* Sector Strength Rankings */}
        <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Sector Strength Rankings</h2>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800">
                <th className="text-left pb-2">Sector</th>
                <th className="text-right pb-2">Momentum</th>
                <th className="text-right pb-2">Rel. Strength</th>
                <th className="text-right pb-2">Rank</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s, i) => (
                <tr key={i} className="border-b border-slate-800/40 hover:bg-slate-800/20">
                  <td className="py-2 flex items-center gap-2">
                    <span className="w-1 h-3 rounded-sm bg-emerald-500 inline-block" />
                    {s.sector as string}
                  </td>
                  <td className="py-2 text-right text-emerald-400">{Number(s.momentum_score).toFixed(0)}</td>
                  <td className="py-2 text-right">
                    <span className={Number(s.relative_strength) > 0 ? 'text-emerald-400' : 'text-slate-400'}>
                      {Number(s.relative_strength) > 0 ? '+' : ''}{Number(s.relative_strength).toFixed(1)}
                    </span>
                    {' '}
                    <span className="text-slate-500">{Number(s.momentum_score) >= 65 ? 'Strong' : 'Neutral'}</span>
                  </td>
                  <td className="py-2 text-right text-slate-300">{Number(s.ranking ?? i + 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Net Institutional Flow */}
        <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Net Institutional Flow</h2>
          <div style={{ height: 160 }}>
            <Line data={lineData} options={{
              responsive: true, maintainAspectRatio: false,
              plugins: { legend: { display: false } },
              scales: {
                x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e293b' } },
              },
            }} />
          </div>
        </div>
      </div>
    </div>
  )
}
