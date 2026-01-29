import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Login from './pages/Login'
import AdminLayout from './components/Layout/AdminLayout'
import Dashboard from './pages/Dashboard'
import Users from './pages/Users'
import Mappings from './pages/Mappings'
import Rules from './pages/Rules'
import Examples from './pages/Examples'

// Simple Auth Guard
const ProtectedRoute = () => {
  const token = localStorage.getItem('token')
  if (!token) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AdminLayout />}>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/users" element={<Users />} />
            <Route path="/schema" element={<div>Schema Explorer (Coming Soon)</div>} />
            <Route path="/mappings" element={<Mappings />} />
            <Route path="/rules" element={<Rules />} />
            <Route path="/examples" element={<Examples />} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Router>
  )
}

export default App
