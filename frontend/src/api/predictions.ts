import api from './client'

export type RiskTier = 'low' | 'medium' | 'high' | 'critical'

export interface TopFactor {
  feature: string
  shap_value: number
  direction: 'positive' | 'negative'
  feature_value: number
  description: string
}

export interface CustomerPrediction {
  id: string
  customer_id: string
  model_version_id: string
  churn_probability: string
  risk_tier: RiskTier
  predicted_at: string
  top_factors: TopFactor[] | null
  shap_values: Record<string, number> | null
}

export interface ModelVersion {
  id: string
  version_name: string
  algorithm: string
  is_active: boolean
  training_rows: number | null
  auc_roc: string | null
  accuracy: string | null
  precision_score: string | null
  recall_score: string | null
  f1_score: string | null
  trained_at: string
}

export interface PredictionRunResponse {
  scored: number
  model_version_id: string
  model_version_name: string
  risk_distribution: { low: number; medium: number; high: number; critical: number }
}

export const predictionsApi = {
  getForCustomer: (customerId: string) =>
    api.get<CustomerPrediction>(`/api/v1/predictions/${customerId}`),

  run: () =>
    api.post<PredictionRunResponse>('/api/v1/predictions/run'),

  listModelVersions: () =>
    api.get<ModelVersion[]>('/api/v1/predictions/model-versions'),
}
