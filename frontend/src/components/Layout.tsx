import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Users, MessageSquare, LogOut, TrendingDown } from 'lucide-react'
import { useAuthContext } from '../context/AuthContext'

const nav = [
  { to: '/dashboard', label: 'Dashboard', Icon: LayoutDashboard },
  { to: '/customers', label: 'Customers', Icon: Users },
  { to: '/chat', label: 'AI Assistant', Icon: MessageSquare },
]

export default function Layout() {
  const { user, logout } = useAuthContext()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="flex w-56 flex-shrink-0 flex-col bg-gray-900">
        {/* Logo */}
        <div className="flex items-center gap-2 px-5 py-5">
          <TrendingDown className="h-5 w-5 text-indigo-400" />
          <span className="text-lg font-bold text-white">ChurnIQ</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 space-y-1 px-3 py-2">
          {nav.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-indigo-600 text-white'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* User + logout */}
        <div className="border-t border-gray-800 px-3 py-4">
          <div className="mb-2 truncate px-3 text-xs text-gray-500">{user?.email}</div>
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-400 transition-colors hover:bg-gray-800 hover:text-white"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
