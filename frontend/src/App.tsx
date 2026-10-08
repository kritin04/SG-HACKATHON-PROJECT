import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { EvidenceProvider } from './components/Evidence'
import DependencyMap from './pages/DependencyMap'
import Board from './pages/Board'
import ImpactPage from './pages/ImpactPage'

export default function App() {
  return (
    <EvidenceProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/board" replace />} />
          <Route path="/board" element={<Board />} />
          <Route path="/cr/:key" element={<ImpactPage />} />
          <Route path="/map" element={<DependencyMap />} />
        </Routes>
      </Shell>
    </EvidenceProvider>
  )
}
