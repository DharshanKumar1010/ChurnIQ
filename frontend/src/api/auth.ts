import api from './client'

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  full_name: string
  email: string
  password: string
}

export interface AuthTokens {
  access_token: string
  token_type: string
}

export interface User {
  id: string
  email: string
  full_name: string
  is_superuser: boolean
}

export const authApi = {
  login: (data: LoginRequest) =>
    api.post<AuthTokens>('/api/v1/auth/login', data),

  register: (data: RegisterRequest) =>
    api.post<AuthTokens>('/api/v1/auth/register', data),

  refresh: () =>
    api.post<AuthTokens>('/api/v1/auth/refresh', {}, { withCredentials: true }),

  me: () => api.get<User>('/api/v1/auth/me'),

  logout: () => api.post('/api/v1/auth/logout', {}, { withCredentials: true }),
}
