import { Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import Header from './components/layout/Header'
import PatientContextBar from './components/layout/PatientContextBar'
import CommandPalette from './components/CommandPalette'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import DashboardLanding from './pages/DashboardLanding'
import PatientList from './pages/PatientList'
import PatientDetail from './pages/PatientDetail'
import RiskAnalysis from './pages/RiskAnalysis'
import CaseComparison from './pages/CaseComparison'
import Settings from './pages/Settings'

function App() {
  return (
    <div className="fixed inset-0 bg-[#f8f9fc] overflow-hidden">
      {/* Sidebar: fixed 256px on the left */}
      <Sidebar />

      {/* Content area: absolute positioned, fills everything right of sidebar (xl+).
          모바일에서는 사이드바가 슬라이드 오버레이라 left-0 풀폭 사용 (F1) */}
      <div className="absolute left-0 xl:left-64 top-0 right-0 bottom-0 flex flex-col">
        <Header />
        <PatientContextBar />
        <main className="flex-1 overflow-auto">
          <div className="w-full px-6 py-6 flex flex-col min-h-full">
            <Routes>
              <Route path="/home" element={<Home />} />
              <Route path="/dashboard" element={<DashboardLanding />} />
              <Route path="/dashboard/:patientId" element={<Dashboard />} />
              <Route path="/patients" element={<PatientList />} />
              <Route path="/patients/:id" element={<PatientDetail />} />
              <Route path="/risk-analysis/:patientId" element={<RiskAnalysis />} />
              <Route path="/case-comparison/:patientId" element={<CaseComparison />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/" element={<Navigate to="/home" replace />} />
            </Routes>
          </div>
        </main>
      </div>

      <CommandPalette />
    </div>
  )
}

export default App
