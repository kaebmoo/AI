import { Suspense, lazy } from 'react'
import { BrowserRouter as Router, Routes, Route, Navigate, Outlet } from 'react-router-dom'
import AdminLayout from './components/Layout/AdminLayout'

const Login = lazy(() => import('./pages/Login'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Users = lazy(() => import('./pages/Users'))
const Schema = lazy(() => import('./pages/Schema'))
const Contexts = lazy(() => import('./pages/Contexts'))
const Analyzer = lazy(() => import('./pages/Analyzer'))
const Mappings = lazy(() => import('./pages/Mappings'))
const Rules = lazy(() => import('./pages/Rules'))
const Examples = lazy(() => import('./pages/Examples'))
const ViewBuilder = lazy(() => import('./pages/ViewBuilder'))
const ViewManager = lazy(() => import('./pages/ViewManager'))
const DimensionFamilies = lazy(() => import('./pages/DimensionFamilies'))
const Providers = lazy(() => import('./pages/Providers'))
const Models = lazy(() => import('./pages/Models'))
const Settings = lazy(() => import('./pages/Settings'))
const HierarchyManager = lazy(() => import('./pages/HierarchyManager'))
const Feedback = lazy(() => import('./pages/Feedback'))
const QueryLogs = lazy(() => import('./pages/QueryLogs'))
const DataWarnings = lazy(() => import('./pages/DataWarnings'))
const QueryPatterns = lazy(() => import('./pages/QueryPatterns'))
const ContextOnboarding = lazy(() => import('./pages/ContextOnboarding'))
const AdminAgent = lazy(() => import('./pages/AdminAgent'))
const ApiKeys = lazy(() => import('./pages/ApiKeys'))
const VannaDocs = lazy(() => import('./pages/VannaDocs'))

const routeFallback = (
  <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#eef2f6', color: '#4b5563' }}>
    Loading admin workspace...
  </div>
)

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
      <Suspense fallback={routeFallback}>
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
              <Route path="/admin-agent" element={<AdminAgent />} />
              <Route path="/api-keys" element={<ApiKeys />} />
              <Route path="/vanna-docs" element={<VannaDocs />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    </Router>
  )
}

export default App
