import api from './client'

export interface AnalyticsSummary {
  id: string | null
  snapshot_date: string
  total_customers: number
  active_customers: number
  churned_this_period: number
  churn_rate: string | null
  mrr: string | null
  mrr_at_risk: string | null
  avg_churn_probability: string | null
  critical_risk_count: number
  high_risk_count: number
  medium_risk_count: number
  low_risk_count: number
  created_at: string | null
}

export const analyticsApi = {
  summary: () =>
    api.get<AnalyticsSummary>('/api/v1/analytics/summary'),

  createSnapshot: () =>
    api.post<AnalyticsSummary>('/api/v1/analytics/snapshot'),
}
