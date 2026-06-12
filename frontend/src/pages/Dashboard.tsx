import { useEffect, useState } from 'react'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { analyticsApi, type AnalyticsSummary } from '../api/analytics'
import StatCard from '../components/StatCard'

const TIER_COLORS: Record<string, string> = {
  Critical: '#ef4444',
  High: '#f97316',
  Medium: '#eab308',
  Low: '#22c55e',
}

function pct(val: string | null): string {
  if (val == null) return '—'
  return (parseFloat(val) * 100).toFixed(1) + '%'
}

function fmtMrr(val: string | null): string {
  if (val == null) return '—'
  const n = parseFloat(val)
  if (isNaN(n)) return val
  return '$' + n.toLocaleString(undefined, { maximumFractionDigits: 0 })
}

export default function Dashboard() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    analyticsApi
      .summary()
      .then(r => setSummary(r.data))
      .catch(e => setError(e?.response?.data?.detail ?? 'Failed to load summary'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-400">
        Loading analytics…
      </div>
    )
  }

  if (error || !summary) {
    return (
      <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
        {error ?? 'No data available'}
      </div>
    )
  }

  const pieData = [
    { name: 'Critical', value: summary.critical_risk_count },
    { name: 'High', value: summary.high_risk_count },
    { name: 'Medium', value: summary.medium_risk_count },
    { name: 'Low', value: summary.low_risk_count },
  ]

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Overview</h1>

      {/* Stat cards */}
      <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Total Customers"
          value={summary.total_customers.toLocaleString()}
          sub={`${summary.active_customers.toLocaleString()} active`}
        />
        <StatCard
          label="Churn Rate"
          value={pct(summary.churn_rate)}
          sub={`${summary.churned_this_period} churned last 30d`}
          accent="red"
        />
        <StatCard
          label="MRR"
          value={fmtMrr(summary.mrr)}
          sub={fmtMrr(summary.mrr_at_risk) + ' at risk'}
          accent="green"
        />
        <StatCard
          label="Avg Churn Prob"
          value={pct(summary.avg_churn_probability)}
          sub={`${summary.critical_risk_count} critical`}
          accent="yellow"
        />
      </div>

      {/* Risk distribution donut */}
      <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-100">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Risk Distribution
        </h2>
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="50%"
              innerRadius={70}
              outerRadius={110}
              paddingAngle={3}
              dataKey="value"
            >
              {pieData.map(entry => (
                <Cell key={entry.name} fill={TIER_COLORS[entry.name]} />
              ))}
            </Pie>
            <Tooltip formatter={(v: number) => [v.toLocaleString(), 'Customers']} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
