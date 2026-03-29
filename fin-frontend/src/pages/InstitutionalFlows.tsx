import { Bar } from 'react-chartjs-2'
import {
  Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend,
} from 'chart.js'
import { useDashboard } from '../hooks/useDashboard'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
      <p className="text-xs text-slate-400 mb-1">{label}</p>
      <p className={`text-xl font-bold ${color}`}>{value}</p>
    </div>
  )
}

function fmt(v: unknown) {
  if (typeof v !== 'number') return '—'
  return `₹${(v / 1e7).toFixed(1)} Cr`
}

export default function InstitutionalFlows() {
  const { data, loading } = useDashboard()
  const flows = data?.institutional_flows as Record<string, unknown> | null

  if (loading) return <p className="text-slate-400">Loading…</p>

  if (!flows) {
    return (
      <div>
        <h1 className="text-xl font-bold mb-4">Institutional Flows</h1>
        <p className="text-slate-500">No flow data available yet.</p>
      </div>
    )
  }

  const chartData = {
    labels: ['FII Buy', 'FII Sell', 'DII Buy', 'DII Sell'],
    datasets: [{
      label: '₹ Crore',
      data: [
        Number(flows.fii_buy ?? 0) / 1e7,
        Number(flows.fii_sell ?? 0) / 1e7,
        Number(flows.dii_buy ?? 0) / 1e7,
        Number(flows.dii_sell ?? 0) / 1e7,
      ],
      backgroundColor: [
        'rgba(34,197,94,0.7)',
        'rgba(239,68,68,0.7)',
        'rgba(99,102,241,0.7)',
        'rgba(251,146,60,0.7)',
      ],
      borderRadius: 4,
    }],
  }

  return (
    <div>
      <h1 className="text-xl font-bold mb-6">Institutional Flows</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Stat label="FII Buy" value={fmt(flows.fii_buy)} color="text-green-400" />
        <Stat label="FII Sell" value={fmt(flows.fii_sell)} color="text-red-400" />
        <Stat label="DII Buy" value={fmt(flows.dii_buy)} color="text-brand" />
        <Stat label="DII Sell" value={fmt(flows.dii_sell)} color="text-orange-400" />
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 mb-4">
        <Bar data={chartData} options={{
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
            y: {
              ticks: { color: '#94a3b8', callback: v => `₹${v}Cr` },
              grid: { color: '#1e293b' },
            },
          },
        }} />
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
        <p className="text-sm text-slate-400 mb-1">Net Institutional Flow</p>
        <p className={`text-3xl font-bold ${Number(flows.net_flow ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {fmt(flows.net_flow)}
        </p>
      </div>
    </div>
  )
}
