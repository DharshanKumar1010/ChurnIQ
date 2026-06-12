import { createContext, useContext, type ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'
import type { User, LoginRequest, RegisterRequest } from '../api/auth'

interface AuthContextValue {
  user: User | null
  loading: boolean
  error: string | null
  login: (c: LoginRequest) => Promise<User>
  register: (p: RegisterRequest) => Promise<User>
  logout: () => Promise<void>
  getCurrentUser: () => Promise<User>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const auth = useAuth()
  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>
}

export function useAuthContext() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuthContext must be used inside AuthProvider')
  return ctx
}
