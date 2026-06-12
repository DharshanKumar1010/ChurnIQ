import { useState, useEffect, useCallback } from 'react'
import { authApi, type User, type LoginRequest, type RegisterRequest } from '../api/auth'
import { tokenStorage } from '../api/client'

interface AuthState {
  user: User | null
  loading: boolean
  error: string | null
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    loading: true,
    error: null,
  })

  const setError = (error: string | null) =>
    setState((s) => ({ ...s, error, loading: false }))

  // Restore session on mount
  useEffect(() => {
    const token = tokenStorage.getAccess()
    if (!token) {
      setState({ user: null, loading: false, error: null })
      return
    }
    authApi
      .me()
      .then(({ data }) => setState({ user: data, loading: false, error: null }))
      .catch(() => {
        tokenStorage.clear()
        setState({ user: null, loading: false, error: null })
      })
  }, [])

  const login = useCallback(async (credentials: LoginRequest) => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const { data } = await authApi.login(credentials)
      tokenStorage.setAccess(data.access_token)
      const { data: user } = await authApi.me()
      setState({ user, loading: false, error: null })
      return user
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? 'Login failed'
      setError(msg)
      throw err
    }
  }, [])

  const register = useCallback(async (payload: RegisterRequest) => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const { data } = await authApi.register(payload)
      tokenStorage.setAccess(data.access_token)
      const { data: user } = await authApi.me()
      setState({ user, loading: false, error: null })
      return user
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? 'Registration failed'
      setError(msg)
      throw err
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch {
      // best-effort
    } finally {
      tokenStorage.clear()
      setState({ user: null, loading: false, error: null })
    }
  }, [])

  const getCurrentUser = useCallback(async () => {
    const { data } = await authApi.me()
    setState((s) => ({ ...s, user: data }))
    return data
  }, [])

  return {
    user: state.user,
    loading: state.loading,
    error: state.error,
    login,
    register,
    logout,
    getCurrentUser,
  }
}
