import { useState, useRef } from 'react'

interface PreviewEntry { time: string; url: string; title: string }
interface PreviewResponse { seed: number; weeks: number; total_visits: number; preview: PreviewEntry[] }

const WEEKS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
const STREAM = [
  { time: '10:42', title: 'Google Classroom – Stream' },
  { time: '10:38', title: 'Khan Academy – AP Calculus' },
  { time: '10:25', title: 'Khan Academy – Organic Chem' },
  { time: '10:12', title: 'ChatGPT – Explain derivatives' },
  { time: '09:58', title: 'Student Learning Space' },
  { time: '09:45', title: 'Wikipedia – Photosynthesis' },
  { time: '09:31', title: 'Desmos Graphing Calculator' },
  { time: '09:15', title: 'Google – "A level math 2024"' },
  { time: '09:02', title: 'Quizlet – Biology Flashcards' },
  { time: '08:48', title: 'Google Docs – Essay Draft' },
]

function App() {
  const [weeks, setWeeks] = useState(3)
  const [seed, setSeed] = useState<number | ''>('')
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [downloadInfo, setDownloadInfo] = useState<{ seed: number; visits: number } | null>(null)
  const seedRef = useRef<HTMLInputElement>(null)
  const API = import.meta.env.PROD ? '' : ''

  const handlePreview = async () => {
    setLoading(true)
    try {
      const p = new URLSearchParams({ weeks: weeks.toString() })
      if (seed !== '') p.set('seed', seed.toString())
      setPreview(await (await fetch(`${API}/api/preview?${p}`)).json())
    } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  const handleDownload = async () => {
    setLoading(true)
    try {
      const p = new URLSearchParams({ weeks: weeks.toString() })
      if (seed !== '') p.set('seed', seed.toString())
      const r = await fetch(`${API}/api/generate?${p}`)
      const s = parseInt(r.headers.get('X-Seed') || '0')
      const v = parseInt(r.headers.get('X-Visits') || '0')
      const b = await r.blob(); const u = window.URL.createObjectURL(b)
      const a = document.createElement('a'); a.href = u; a.download = 'History'
      document.body.appendChild(a); a.click()
      window.URL.revokeObjectURL(u); document.body.removeChild(a)
      setDownloadInfo({ seed: s, visits: v })
    } catch (e) { console.error(e) } finally { setLoading(false) }
  }

  return (
    <div className="page">
      <header className="header">
        <h1 className="title">Chrome History Generator</h1>
        <p className="desc">Generate a realistic browser history of a student through a spoofed Chrome history file.</p>
      </header>

      <div className="card">
        {/* Embedded scrolling data stream */}
        <div className="stream">
          <div className="stream-track">
            {[...STREAM, ...STREAM, ...STREAM, ...STREAM].map((e, i) => (
              <div key={i} className="stream-item">
                <span className="stream-time">{e.time}</span>
                <span className="stream-title">{e.title}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card-body">
          <div className="card-grid">
            <div>
              <div className="field-label">Duration</div>
              <div className="weeks">
                {WEEKS.map(w => (
                  <button key={w} className={`chip${weeks === w ? ' on' : ''}`}
                    onClick={() => setWeeks(w)} id={`w-${w}`}>{w}</button>
                ))}
              </div>
            </div>
            <div>
              <div className="field-label">Seed</div>
              <div className="term" onClick={() => seedRef.current?.focus()}>
                <span className="term-p">&gt;</span>
                <input ref={seedRef} type="number" className="term-in" placeholder="random"
                  value={seed} onChange={e => setSeed(e.target.value ? parseInt(e.target.value) : '')} id="seed" />
              </div>
              <p className="hint">Same seed → identical output</p>
            </div>
          </div>

          <div className="divider" />

          <div className="actions">
            <button onClick={handlePreview} disabled={loading} className="btn btn-ghost" id="preview-btn">
              {loading && <span className="spin" />} Preview
            </button>
            <button onClick={handleDownload} disabled={loading} className="btn btn-fill" id="dl-btn">
              {loading ? <span className="spin" /> : (
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
                </svg>
              )} Download History
            </button>
          </div>
        </div>
      </div>

      {(downloadInfo || preview) && (
        <div className="results">
          {downloadInfo && (
            <div className="success">
              <div className="success-row">
                <svg className="success-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                <span className="success-label">Download complete</span>
              </div>
              <p className="success-body">
                <strong>{downloadInfo.visits.toLocaleString()}</strong> visits · seed <code className="code">{downloadInfo.seed}</code> · Place <code className="code">History</code> in Chrome's profile dir.
              </p>
            </div>
          )}
          {preview && (
            <div className="window">
              <div className="window-bar">
                <span className="dot" /><span className="dot" /><span className="dot" />
                <span className="window-label">preview</span>
                <div className="window-meta">
                  <span><span className="window-meta-val">{preview.total_visits.toLocaleString()}</span> visits</span>
                  <span>seed <code className="code">{preview.seed}</code></span>
                </div>
              </div>
              <div className="window-body">
                <table><thead><tr><th>Time</th><th>Page</th></tr></thead>
                  <tbody>{preview.preview.map((e, i) => (
                    <tr key={i}>
                      <td className="t-time">{e.time}</td>
                      <td>
                        <div className="t-title" title={e.title}>{e.title || '(Untitled)'}</div>
                        <div className="t-url" title={e.url}>{e.url}</div>
                      </td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      <footer className="footer">
        Classroom, SLS, educational sites, AI assistants. No social media, gaming, or entertainment.
      </footer>
    </div>
  )
}

export default App
