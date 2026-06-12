interface StatCardProps {
  label: string
  value: string | number
  sub?: string
  accent?: 'default' | 'red' | 'green' | 'yellow'
}

const accentClass: Record<string, string> = {
  default: 'text-gray-900',
  red: 'text-red-600',
  green: 'text-emerald-600',
  yellow: 'text-amber-600',
}

export default function StatCard({ label, value, sub, accent = 'default' }: StatCardProps) {
  return (
    <div className="rounded-xl bg-white p-5 shadow-sm ring-1 ring-gray-100">
      <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</p>
      <p className={`mt-2 text-2xl font-bold ${accentClass[accent]}`}>{value}</p>
      {sub && <p className="mt-1 text-sm text-gray-400">{sub}</p>}
    </div>
  )
}
