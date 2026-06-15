import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { customersApi, type Customer } from '../api/customers'
import { predictionsApi, type CustomerPrediction, type RiskTier } from '../api/predictions'
import { ArrowLeft } from 'lucide-react'

const TIER_STYLES: Record<RiskTier, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-green-100 text-green-700',
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-400">{label}</p>
      <p className="mt-0.5 text-sm text-gray-800">{value}</p>
    </div>
  )
}

export default function CustomerDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [prediction, setPrediction] = useState<CustomerPrediction | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    Promise.all([customersApi.get(id), predictionsApi.getForCustomer(id)])
      .then(([cRes, pRes]) => {
        setCustomer(cRes.data)
        setPrediction(pRes.data)
      })
      .catch(e => setError(e?.response?.data?.detail ?? 'Failed to load customer'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-400">Loading…</div>
    )
  }

  if (error || !customer) {
    return (
      <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700">
        {error ?? 'Customer not found'}
      </div>
    )
  }

  // Build SHAP chart data from top_factors
  const shapData =
    prediction?.top_factors?.map(f => ({
      feature: f.feature.replace(/_/g, ' '),
      value: parseFloat(f.shap_value.toFixed(4)),
      description: f.description,
    })) ?? []

  const churnProb = prediction
    ? (parseFloat(prediction.churn_probability) * 100).toFixed(1) + '%'
    : '—'

  return (
    <div>
      <button
        onClick={() => navigate(-1)}
        className="mb-6 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800"
      >
        <ArrowLeft className="h-4 w-4" /> Back
      </button>

      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{customer.name}</h1>
          <p className="text-sm text-gray-500">{customer.email ?? '—'}</p>
        </div>
        {prediction && (
          <span
            className={`mt-1 inline-block rounded-full px-3 py-1 text-sm font-semibold capitalize ${
              TIER_STYLES[prediction.risk_tier]
            }`}
          >
            {prediction.risk_tier} · {churnProb}
          </span>
        )}
      </div>

      {/* Customer fields */}
      <div className="mb-6 grid grid-cols-2 gap-4 rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-100 md:grid-cols-4">
        <Field label="Plan" value={<span className="capitalize">{customer.plan}</span>} />
        <Field
          label="MRR"
          value={'$' + parseFloat(customer.monthly_revenue).toLocaleString()}
        />
        <Field label="Logins (30d)" value={customer.logins_last_30d} />
        <Field label="NPS" value={customer.nps_score ?? '—'} />
        <Field label="Open tickets" value={customer.support_tickets_open} />
        <Field label="Total tickets" value={customer.support_tickets_total} />
        <Field label="Billing issues" value={customer.billing_issues_count} />
        <Field
          label="Status"
          value={
            customer.is_churned ? (
              <span className="text-red-600">Churned</span>
            ) : (
              <span className="text-emerald-600">Active</span>
            )
          }
        />
      </div>

      {/* SHAP bar chart */}
      {shapData.length > 0 && (
        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-100">
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Churn Factors (SHAP)
          </h2>
          <p className="mb-4 text-xs text-gray-400">
            Positive values push toward churn; negative values reduce it.
          </p>
          <ResponsiveContainer width="100%" height={shapData.length * 48 + 40}>
            <BarChart
              data={shapData}
              layout="vertical"
              margin={{ top: 0, right: 20, left: 130, bottom: 0 }}
            >
              <XAxis type="number" domain={['auto', 'auto']} tick={{ fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="feature"
                tick={{ fontSize: 12 }}
                width={120}
              />
              <Tooltip
                formatter={(v: unknown) => [Number(v).toFixed(4), 'SHAP value']}
                labelFormatter={(_: unknown, payload: unknown) =>
                  (payload as unknown as Array<{ payload?: { description?: string } }>)?.[0]?.payload?.description ?? ''
                }
              />
              <ReferenceLine x={0} stroke="#9ca3af" />
              <Bar dataKey="value" radius={[0, 3, 3, 0]}>
                {shapData.map((entry, i) => (
                  <Cell key={i} fill={entry.value >= 0 ? '#ef4444' : '#22c55e'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {!prediction && (
        <p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-700">
          No prediction found for this customer. Run scoring first.
        </p>
      )}
    </div>
  )
}
