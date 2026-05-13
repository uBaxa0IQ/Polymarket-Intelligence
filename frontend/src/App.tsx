import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import ToastProvider from './components/ToastProvider'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Pipeline from './pages/Pipeline'
import RunDetail from './pages/RunDetail'
import Bets from './pages/Bets'
import Settings from './pages/Settings'
import CopyTradingPage from './pages/CopyTrading'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 10_000 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/*"
              element={
                <ProtectedRoute>
                  <Layout>
                    <Routes>
                      <Route path="/" element={<Dashboard />} />
                      <Route path="/pipeline" element={<Pipeline />} />
                      <Route path="/pipeline/:id" element={<RunDetail />} />
                      <Route path="/bets" element={<Bets />} />
                      <Route path="/copy-trading" element={<CopyTradingPage />} />
                      <Route path="/settings" element={<Settings />} />
                      <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                  </Layout>
                </ProtectedRoute>
              }
            />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}
