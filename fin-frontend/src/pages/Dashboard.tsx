import React, { useEffect, useRef } from 'react'
import { Bar } from 'react-chartjs-2'
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip } from 'chart.js'
import { useDashboard } from '../hooks/useDashboard'
import { useHealth } from '../hooks/useHealth'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip)

// ── Helpers ───────────────────────────────────────────────────────────────────

function calcNetFlow(flows: Record<string, unknown> | null): number {
  if (!flows) return 0
  const fiiBuy  = Number(flows.fii_buy  ?? 0)
  const fiiSell = Number(flows.fii_sell ?? 0)
  const diiBuy  = Number(flows.dii_buy  ?? 0)
  const diiSell = Number(flows.dii_sell ?? 0)
  return fiiBuy + diiBuy - fiiSell - diiSell
}

function rankSectors(sectors: Record<string, unknown>[]): Record<string, unknown>[] {
  // Score = momentum_score * 0.6 + relative_strength * 0.4
  const scored = sectors.map(s => ({
    ...s,
    _score: Number(s.momentum_score ?? 0) * 0.6 + Number(s.relative_strength ?? 0) * 0.4,
  }))
  scored.sort((a, b) => b._score - a._score)
  return scored.map((s, i) => ({ ...s, ranking: i + 1 }))
}

const MOCK_SECTORS = [
  { sector: 'Banking', momentum_score: 72, relative_strength: 0.048 },
  { sector: 'Auto',    momentum_score: 71, relative_strength: 0.388 },
  { sector: 'FMCG',   momentum_score: 65, relative_strength: 1.244 },
  { sector: 'IT',      momentum_score: 43, relative_strength: 1.046 },
  { sector: 'Pharma',  momentum_score: 51, relative_strength: 1.380 },
  { sector: 'Energy',  momentum_score: 65, relative_strength: 0.344 },
]

const MOCK_NEWS = [
  { headline: 'Dow Rises As Markets Dgy Tech Earnings Fed Hold The...', source: 'Reuters', time: '45m ago', score: 0.42, tag: 'bull' },
  { headline: "India's Manufacturing PMIs Surge In H1-21", source: 'Economic Times', time: '1h ago', score: 0.31, tag: 'bull' },
]

// ── Component ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const { data, loading, refresh } = useDashboard(60000) // 60s refresh
  const connected = useHealth()

  const rawSectors = (data?.sector_strength as Record<string, unknown>[] | null) ?? MOCK_SECTORS
  const sectors = rankSectors(rawSectors)
  const flows = data?.institutional_flows as Record<string, unknown> | null
  const aiSignals = data?.ai_signals as Record<string, unknown> | null
  const sentiment = data?.market_sentiment as Record<string, unknown> | null

  const netFlow = calcNetFlow(flows)
  const isBull = netFlow >= 0
  const direction = aiSignals?.direction as string ?? 'Bullish'
  const confidence = aiSignals?.confidence ? Math.round(Number(aiSignals.confidence) * 100) : 82
  const signalTime = aiSignals?.timestamp
    ? new Date(aiSignals.timestamp as string).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) + ' IST'
    : new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Kolkata' }) + ' IST'

  const globalScore = sentiment ? Number(sentiment.composite_score ?? 0.22) : 0.22
  const domesticScore = sentiment ? Number(sentiment.index_momentum ?? 0.48) : 0.48
  const globalClass = globalScore > 0.3 ? 'Bullish' : globalScore < -0.3 ? 'Bearish' : 'Neutral'
  const domesticClass = domesticScore > 0.3 ? 'Bullish' : domesticScore < -0.3 ? 'Bearish' : 'Neutral'

  const chartData = {
    labels: sectors.map(s => s.sector as string),
    datasets: [{
      data: sectors.map(s => Number(s.momentum_score ?? 0)),
      backgroundColor: sectors.map(s =>
        Number(s.momentum_score ?? 0) >= 70 ? 'rgba(52,211,153,0.85)' : 'rgba(52,211,153,0.45)'
      ),
      borderRadius: 3,
      barThickness: 28,
    }],
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-base font-semibold text-slate-200">Dashboard</h1>
        <div className="flex items-center gap-3">
          {/* Health indicator */}
          <span className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border ${
            connected === true  ? 'border-emerald-700 text-emerald-400 bg-emerald-900/20' :
            connected === false ? 'border-red-700 text-red-400 bg-red-900/20' :
            'border-slate-700 text-slate-400'
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${
              connected === true ? 'bg-emerald-400' : connected === false ? 'bg-red-400' : 'bg-slate-500'
            }`} />
            {connected === true ? 'Backend connected' : connected === false ? 'Backend offline' : 'Checking…'}
          </span>
          <span className="text-xs text-slate-400">user@finintelligence.com</span>
          <button onClick={refresh} className="text-xs text-slate-400 hover:text-emerald-400 border border-slate-700 rounded px-2 py-1">↻</button>
        </div>
      </div>

      {/* Market Sentiment Panel */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-[#0d1117] border border-slate-800 rounded-lg px-4 py-3 flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-500 mb-0.5">Global Sentiment</p>
            <span className={`text-lg font-bold ${globalScore >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {globalScore >= 0 ? '+' : ''}{globalScore.toFixed(2)}
            </span>
            <span className="text-xs text-slate-400 ml-2">({globalClass})</span>
          </div>
          <div className="text-right">
            <p className="text-xs text-slate-500 mb-0.5">Domestic Sentiment</p>
            <span className={`text-lg font-bold ${domesticScore >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {domesticScore >= 0 ? '+' : ''}{domesticScore.toFixed(2)}
            </span>
            <span className="text-xs text-slate-400 ml-2">({domesticClass})</span>
          </div>
        </div>
        <div className="bg-[#0d1117] border border-slate-800 rounded-lg px-4 py-3 flex items-center gap-3">
          <span className="text-xs text-slate-500">Auto-refresh:</span>
          <span className="text-xs text-emerald-400">every 60s</span>
          <span className="text-xs text-slate-600">|</span>
          <span className="text-xs text-slate-500">Last update:</span>
          <span className="text-xs text-slate-300">{new Date().toLocaleTimeString()}</span>
        </div>
      </div>

      {/* Sector Bar Chart */}
      <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
        <div style={{ height: 130 }}>
          <Bar data={chartData} options={{
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
              x: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { display: false } },
              y: { ticks: { color: '#64748b', font: { size: 10 } }, grid: { color: '#1e293b' }, min: 0, max: 125 },
            },
          }} />
        </div>
      </div>

      {/* Sector Table + Right Panels */}
      <div className="grid grid-cols-3 gap-4">
        {/* Sector Rotation Table */}
        <div className="col-span-2 bg-[#0d1117] border border-slate-800 rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Sector Rotation</h2>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-800">
                <th className="text-left pb-2">Sector</th>
                <th className="text-right pb-2">Momentum</th>
                <th className="text-right pb-2">Relative Strength</th>
                <th className="text-right pb-2">Ranking</th>
              </tr>
            </thead>
            <tbody>
              {sectors.map((s, i) => (
                <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                  <td className="py-2 flex items-center gap-2">
                    <span className="w-1 h-4 rounded-sm bg-emerald-500 inline-block" />
                    {s.sector as string}
                  </td>
                  <td className="py-2 text-right text-emerald-400">{Number(s.momentum_score).toFixed(0)}</td>
                  <td className="py-2 text-right">
                    <span className={Number(s.relative_strength) > 0 ? 'text-emerald-400' : 'text-red-400'}>
                      {Number(s.relative_strength) > 0 ? '+' : ''}{Number(s.relative_strength).toFixed(3)}
                    </span>
                    {' '}
                    <span className="text-slate-400">{Number(s.momentum_score) >= 65 ? 'Strong' : 'Neutral'}</span>
                  </td>
                  <td className="py-2 text-right text-slate-300">{Number(s.ranking)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Right panels */}
        <div className="space-y-4">
          {/* Institutional Flow */}
          <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-slate-300 mb-2">Institutional Flow</h2>
            <div className="flex items-center justify-between mb-2">
              <span className={`text-lg font-bold ${isBull ? 'text-emerald-400' : 'text-red-400'}`}>
                {isBull ? 'Bull' : 'Bear'}
              </span>
              <span className={`text-sm font-semibold ${isBull ? 'text-emerald-400' : 'text-red-400'}`}>
                {isBull ? '+' : ''}₹{Math.abs(netFlow).toLocaleString('en-IN')} Cr
              </span>
            </div>
            {flows && (
              <div className="text-[10px] text-slate-500 space-y-0.5">
                <div className="flex justify-between"><span>FII Buy</span><span className="text-emerald-400">₹{Number(flows.fii_buy ?? 0).toLocaleString()}</span></div>
                <div className="flex justify-between"><span>FII Sell</span><span className="text-red-400">₹{Number(flows.fii_sell ?? 0).toLocaleString()}</span></div>
                <div className="flex justify-between"><span>DII Buy</span><span className="text-emerald-400">₹{Number(flows.dii_buy ?? 0).toLocaleString()}</span></div>
                <div className="flex justify-between"><span>DII Sell</span><span className="text-red-400">₹{Number(flows.dii_sell ?? 0).toLocaleString()}</span></div>
              </div>
            )}
            <div className="flex items-end gap-0.5 h-8 mt-2">
              {[3,5,4,7,6,8,5,9,7,10,8,11].map((v,i) => (
                <div key={i} className="flex-1 bg-emerald-500/60 rounded-sm" style={{ height: `${v*8}%` }} />
              ))}
            </div>
          </div>

          {/* AI Signal */}
          <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
            <h2 className="text-sm font-semibold text-slate-300 mb-3">Latest AI Signal</h2>
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-emerald-900/50 border border-emerald-700 flex items-center justify-center text-emerald-400">
                {direction === 'Bullish' ? '↑' : direction === 'Bearish' ? '↓' : '→'}
              </div>
              <div className="flex-1 space-y-1">
                <div className="flex items-center justify-between">
                  <span className={`font-semibold text-sm ${direction === 'Bullish' ? 'text-emerald-400' : direction === 'Bearish' ? 'text-red-400' : 'text-yellow-400'}`}>
                    {direction}
                  </span>
                  <span className="text-[10px] text-slate-400">Confidence <span className="text-emerald-400">{confidence}%</span></span>
                </div>
                <p className="text-[10px] text-slate-500">Generated: {signalTime}</p>
                <p className="text-[10px] text-slate-500">Engine: AI Engine v1.2</p>
                <p className="text-[10px] text-slate-600">
                  Trigger: {aiSignals?.supporting_factors
                    ? String((aiSignals.supporting_factors as string[])[0] ?? 'Sector momentum + Institutional flow')
                    : 'Sector momentum + Institutional flow'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* News Sentiment */}
      <div className="bg-[#0d1117] border border-slate-800 rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Latest Market News</h2>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-slate-800">
              <th className="text-left pb-2">Headline</th>
              <th className="text-right pb-2">Sentiment</th>
              <th className="text-right pb-2">Source</th>
              <th className="text-right pb-2">Time</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_NEWS.map((n, i) => (
              <tr key={i} className="border-b border-slate-800/40 hover:bg-slate-800/20">
                <td className="py-2 text-slate-300 max-w-xs truncate">{n.headline}</td>
                <td className="py-2 text-right">
                  <span className={n.score >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {n.score >= 0 ? '+' : ''}{n.score.toFixed(2)}
                  </span>
                </td>
                <td className="py-2 text-right text-slate-400">{n.source}</td>
                <td className="py-2 text-right text-slate-500">{n.time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
