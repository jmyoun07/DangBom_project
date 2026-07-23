import { Routes, Route, Navigate, Link } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import Header from './components/layout/Header'
import PatientContextBar from './components/layout/PatientContextBar'
import CommandPalette from './components/CommandPalette'
import Home from './pages/Home'
import Dashboard from './pages/Dashboard'
import DashboardLanding from './pages/DashboardLanding'
import PatientList from './pages/PatientList'
import PatientDetail from './pages/PatientDetail'
import ExamHistory from './pages/ExamHistory'
import IntegratedReport from './pages/IntegratedReport'
import RiskAnalysis from './pages/RiskAnalysis'
import CaseComparison from './pages/CaseComparison'
import Settings from './pages/Settings'

// 404 catch-all — 잘못된 경로에서 빈 화면 대신 안내 + 홈 링크
function NotFound() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 py-24 text-center">
      <p className="text-4xl font-bold text-gray-300">404</p>
      <p className="text-sm text-gray-600">페이지를 찾을 수 없습니다.</p>
      <Link to="/home" className="text-sm text-accent font-semibold hover:underline">
        홈으로 돌아가기
      </Link>
    </div>
  )
}

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
              <Route path="/exam-history/:patientId" element={<ExamHistory />} />
              <Route path="/report/:patientId" element={<IntegratedReport />} />
              <Route path="/risk-analysis/:patientId" element={<RiskAnalysis />} />
              <Route path="/case-comparison/:patientId" element={<CaseComparison />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/" element={<Navigate to="/home" replace />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </div>
        </main>
      </div>

      <CommandPalette />
    </div>
  )
}

export default App
