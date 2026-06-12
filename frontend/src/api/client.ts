import axios from 'axios'

const TOKEN_KEY = 'churniq_access_token'
const REFRESH_KEY = 'churniq_refresh_token'

export const tokenStorage = {
  getAccess: () => localStorage.getItem(TOKEN_KEY),
  setAccess: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  setRefresh: (t: string) => localStorage.setItem(REFRESH_KEY, t),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
})

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = tokenStorage.getAccess()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// On 401: attempt token refresh, then retry; on failure clear and redirect
let refreshing = false
let refreshQueue: Array<(token: string) => void> = []

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config

    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error)
    }
    original._retry = true

    if (refreshing) {
      return new Promise((resolve) => {
        refreshQueue.push((token) => {
          original.headers.Authorization = `Bearer ${token}`
          resolve(api(original))
        })
      })
    }

    refreshing = true
    try {
      const { data } = await axios.post(
        `${BASE_URL}/api/v1/auth/refresh`,
        {},
        { withCredentials: true },
      )
      const newToken: string = data.access_token
      tokenStorage.setAccess(newToken)
      refreshQueue.forEach((cb) => cb(newToken))
      refreshQueue = []
      original.headers.Authorization = `Bearer ${newToken}`
      return api(original)
    } catch {
      tokenStorage.clear()
      window.location.href = '/login'
      return Promise.reject(error)
    } finally {
      refreshing = false
    }
  },
)

export default api
