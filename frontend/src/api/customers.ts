import api from './client'

export interface Customer {
  id: string
  name: string
  email: string | null
  phone: string | null
  plan: 'free' | 'starter' | 'growth' | 'enterprise'
  monthly_revenue: string
  contract_length_months: number | null
  signup_date: string
  contract_end_date: string | null
  last_activity_date: string | null
  logins_last_30d: number
  feature_usage_score: string | null
  support_tickets_open: number
  support_tickets_total: number
  nps_score: number | null
  billing_issues_count: number
  country: string | null
  industry: string | null
  company_size: string | null
  is_churned: boolean
  churned_at: string | null
  created_at: string
  latest_risk_tier: string | null
  latest_churn_probability: string | null
}

export interface CustomerListResponse {
  items: Customer[]
  total: number
  skip: number
  limit: number
}

export const customersApi = {
  list: (params?: { skip?: number; limit?: number; search?: string }) =>
    api.get<CustomerListResponse>('/api/v1/customers/', { params }),

  get: (id: string) =>
    api.get<Customer>(`/api/v1/customers/${id}`),
}
