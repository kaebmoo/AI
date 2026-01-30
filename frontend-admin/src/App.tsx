import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import Login from './pages/Login'
import AdminLayout from './components/Layout/AdminLayout'
import Dashboard from './pages/Dashboard'
import Users from './pages/Users'
import Schema from './pages/Schema'
import Contexts from './pages/Contexts'
import Analyzer from './pages/Analyzer'
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
            <Route path="/schema" element={<Schema />} />
            <Route path="/contexts" element={<Contexts />} />
            <Route path="/analyzer" element={<Analyzer />} />
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
