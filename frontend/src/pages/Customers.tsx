import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { customersApi, type Customer } from '../api/customers'
import type { RiskTier } from '../api/predictions'

const TIER_STYLES: Record<RiskTier, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-green-100 text-green-700',
}

function RiskBadge({ tier }: { tier: RiskTier | undefined }) {
  if (!tier) return <span className="text-gray-400">—</span>
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${TIER_STYLES[tier]}`}>
      {tier}
    </span>
  )
}

const PAGE_SIZE = 20

export default function Customers() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    customersApi
      .list({ skip: page * PAGE_SIZE, limit: PAGE_SIZE })
      .then(r => {
        setCustomers(r.data.items)
        setTotal(r.data.total)
      })
      .catch(e => setError(e?.response?.data?.detail ?? 'Failed to load customers'))
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div>
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Customers</h1>

      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>
      )}

      <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-gray-100">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">Name</th>
              <th className="px-4 py-3 text-left">Plan</th>
              <th className="px-4 py-3 text-right">MRR</th>
              <th className="px-4 py-3 text-right">Logins (30d)</th>
              <th className="px-4 py-3 text-center">Status</th>
              <th className="px-4 py-3 text-center">Risk</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Loading…
                </td>
              </tr>
            ) : (
              customers.map(c => (
                <tr
                  key={c.id}
                  onClick={() => navigate(`/customers/${c.id}`)}
                  className="cursor-pointer transition-colors hover:bg-gray-50"
                >
                  <td className="px-4 py-3 font-medium text-gray-900">{c.name}</td>
                  <td className="px-4 py-3 capitalize text-gray-600">{c.plan}</td>
                  <td className="px-4 py-3 text-right text-gray-700">
                    ${parseFloat(c.monthly_revenue).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-700">{c.logins_last_30d}</td>
                  <td className="px-4 py-3 text-center">
                    {c.is_churned ? (
                      <span className="text-xs font-medium text-red-600">Churned</span>
                    ) : (
                      <span className="text-xs font-medium text-emerald-600">Active</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <RiskBadge tier={c.latest_risk_tier as RiskTier | undefined} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between text-sm text-gray-500">
          <span>
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => p - 1)}
              disabled={page === 0}
              className="flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
            >
              <ChevronLeft className="h-4 w-4" /> Prev
            </button>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page >= totalPages - 1}
              className="flex items-center gap-1 rounded px-2 py-1 hover:bg-gray-100 disabled:opacity-40"
            >
              Next <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
