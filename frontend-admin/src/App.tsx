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
import ViewBuilder from './pages/ViewBuilder'
import ViewManager from './pages/ViewManager'
import DimensionFamilies from './pages/DimensionFamilies'
import Providers from './pages/Providers'
import Models from './pages/Models'
import Settings from './pages/Settings'
import HierarchyManager from './pages/HierarchyManager'
import Feedback from './pages/Feedback'
import QueryLogs from './pages/QueryLogs'
import DataWarnings from './pages/DataWarnings'
import QueryPatterns from './pages/QueryPatterns'
import ContextOnboarding from './pages/ContextOnboarding'

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
            <Route path="/context-onboarding" element={<ContextOnboarding />} />
            <Route path="/analyzer" element={<Analyzer />} />
            <Route path="/mappings" element={<Mappings />} />
            <Route path="/rules" element={<Rules />} />
            <Route path="/examples" element={<Examples />} />
            <Route path="/view-builder" element={<ViewBuilder />} />
            <Route path="/view-manager" element={<ViewManager />} />
            <Route path="/dimension-families" element={<DimensionFamilies />} />
            <Route path="/hierarchy" element={<HierarchyManager />} />
            <Route path="/providers" element={<Providers />} />
            <Route path="/models" element={<Models />} />
            <Route path="/feedback" element={<Feedback />} />
            <Route path="/query-logs" element={<QueryLogs />} />
            <Route path="/data-warnings" element={<DataWarnings />} />
            <Route path="/query-patterns" element={<QueryPatterns />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </Router>
  )
}

export default App
