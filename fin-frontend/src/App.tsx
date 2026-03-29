import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Sectors from './pages/Sectors'
import InstitutionalFlows from './pages/InstitutionalFlows'
import Sentiment from './pages/Sentiment'
import Analysis from './pages/Analysis'
import Admin from './pages/Admin'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="sectors" element={<Sectors />} />
            <Route path="flows" element={<InstitutionalFlows />} />
            <Route path="sentiment" element={<Sentiment />} />
            <Route path="analysis" element={<Analysis />} />
            <Route path="admin" element={<Admin />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
