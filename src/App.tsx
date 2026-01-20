import React from 'react'
import { Link, Navigate, Route, Routes } from 'react-router-dom'
import SkillGapPage from './SkillGapPage'
import SignIn from './pages/SignIn'
import SignUp from './pages/SignUp'
import { useAuth } from './auth/AuthProvider'

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { session, loading } = useAuth()
  if (loading) return <div className="p-6">Loading...</div>
  if (!session) return <Navigate to="/signin" replace />
  return <>{children}</>
}

const TopBar: React.FC = () => {
  const { session } = useAuth()

  async function signOut() {
    await fetch('/logout', { method: 'POST' }).catch(() => {}) // optional: ignore if not used
    await import('./lib/supabaseClient').then(({ supabase }) => supabase.auth.signOut())
  }

  return (
    <div className="flex items-center justify-between border-b bg-white px-4 py-3">
      <Link to="/" className="font-semibold">Skill Gap</Link>
      <div className="flex items-center gap-3">
        {session ? (
          <button onClick={signOut} className="rounded-lg border px-3 py-1.5">Sign out</button>
        ) : (
          <>
            <Link to="/signin" className="text-sm">Sign in</Link>
            <Link to="/signup" className="text-sm">Sign up</Link>
          </>
        )}
      </div>
    </div>
  )
}

const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-50">
      <TopBar />
      <Routes>
        <Route
          path="/"
          element={
            <RequireAuth>
              <SkillGapPage />
            </RequireAuth>
          }
        />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/signup" element={<SignUp />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  )
}

export default App

