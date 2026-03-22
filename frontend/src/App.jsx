import { useState, useEffect } from "react"

export default function App() {
  const [tasks, setTasks] = useState([])

  useEffect(() => {
    fetch("http://localhost/api/tasks")
      .then(r => r.json())
      .then(data => setTasks(data))
      .catch(() => setTasks([{ id: 0, title: "API not connected yet", priority: "high" }]))
  }, [])

  return (
    <div className="min-h-screen bg-slate-900 text-white p-8">
      <h1 className="text-3xl font-bold mb-6 text-purple-400">
        TaskFlow — Sprint Board
      </h1>
      <div className="grid gap-4">
        {tasks.map(t => (
          <div key={t.id} className="bg-slate-800 rounded-lg p-4 border border-slate-700">
            <p className="font-semibold">{t.title}</p>
            <p className="text-sm text-slate-400">Priority: {t.priority}</p>
          </div>
        ))}
      </div>
    </div>
  )
}