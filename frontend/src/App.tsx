import { Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { EvidenceProvider } from './components/Evidence'
import ImpactAnalyzer from './pages/ImpactAnalyzer'
import ReleaseReadiness from './pages/ReleaseReadiness'
import DocHealth from './pages/DocHealth'

export default function App() {
  return (
    <EvidenceProvider>
      <Shell>
        <Routes>
          <Route path="/" element={<Navigate to="/impact" replace />} />
          <Route path="/impact" element={<ImpactAnalyzer />} />
          <Route path="/impact/:key" element={<ImpactAnalyzer />} />
          <Route path="/release" element={<ReleaseReadiness />} />
          <Route path="/release/:pr" element={<ReleaseReadiness />} />
          <Route path="/docs" element={<DocHealth />} />
        </Routes>
      </Shell>
    </EvidenceProvider>
  )
}
