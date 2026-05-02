import { ApplicationList } from './pages/ApplicationList'

function App() {
  return (
    <div className="min-h-screen bg-gray-950">
      <nav className="border-b border-gray-800 px-6 py-4">
        <span className="text-gray-100 font-semibold tracking-tight">Job Tracker</span>
      </nav>
      <main className="max-w-6xl mx-auto">
        <ApplicationList />
      </main>
    </div>
  )
}

export default App
