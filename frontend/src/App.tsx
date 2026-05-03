import { Routes, Route, Navigate, Link } from 'react-router-dom'
import { ApplicationList } from './pages/ApplicationList'
import { ApplicationDetail } from './pages/ApplicationDetail'
import { AddApplication } from './pages/AddApplication'

function App() {
  return (
    <div className="min-h-screen bg-background">
      <nav className="border-b border-surface px-6 py-4 flex items-center justify-between">
        <Link to="/applications" className="text-white font-semibold tracking-tight hover:text-accent transition-colors">
          Job Tracker
        </Link>
        <Link
          to="/applications/new"
          className="px-4 py-1.5 rounded bg-accent hover:bg-accent-hover text-white text-sm font-medium transition-colors"
        >
          + New Application
        </Link>
      </nav>
      <main className="max-w-6xl mx-auto">
        <Routes>
          <Route path="/" element={<Navigate to="/applications" replace />} />
          <Route path="/applications" element={<ApplicationList />} />
          <Route path="/applications/new" element={<AddApplication />} />
          <Route path="/applications/:id" element={<ApplicationDetail />} />
          <Route path="*" element={<Navigate to="/applications" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
