import { useState } from 'react'

interface ProjectData {
  first_name: string; last_name: string; company_name: string
  address: string; postal_code: string; project_name: string
  project_number: string; salesperson_name: string; document_date: string
  project_start: string; project_end: string; goals: string
  constraints: string; payment_type: string; material_deliverables: string
  required_expertise: string; other_notes: string
}

interface ProgressEvent {
  status: 'progress' | 'done' | 'error' | 'warning'
  section: string; message: string
  docx?: string; pdf?: string
}

const SECTIONS_ORDER = [
  'thank_you','section1','section2','section3','section4',
  'section5','section6','section7','section8','section9','section10','docx','pdf'
]

const SECTION_LABELS: Record<string, string> = {
  thank_you: 'Thank-you paragraph', section1: '1. Background & Goals',
  section2: '2. Cost Estimation', section3: '3. Timetable',
  section4: '4. Restrictions', section5: '5. Material Transformation',
  section6: '6. Documentation', section7: '7. Quality Assurance',
  section8: '8. Project Team', section9: '9. Delivery Terms',
  section10: '10. Contact Information', docx: 'Assembling DOCX', pdf: 'Converting to PDF',
}

const EMPTY: ProjectData = {
  first_name:'', last_name:'', company_name:'', address:'', postal_code:'',
  project_name:'', project_number:'', salesperson_name:'', document_date:'',
  project_start:'', project_end:'', goals:'', constraints:'',
  payment_type:'hourly', material_deliverables:'', required_expertise:'', other_notes:''
}

function Field({ label, name, value, onChange, full=false, area=false }: {
  label: string; name: string; value: string
  onChange: (n: string, v: string) => void; full?: boolean; area?: boolean
}) {
  return (
    <div className={full ? 'form-full' : ''}>
      <label>{label}</label>
      {area
        ? <textarea value={value} rows={3} onChange={e => onChange(name, e.target.value)} />
        : <input type="text" value={value} onChange={e => onChange(name, e.target.value)} />
      }
    </div>
  )
}

export default function NewOfferTab() {
  const [project, setProject] = useState<ProjectData>({ ...EMPTY, document_date: new Date().toISOString().slice(0,10) })
  const [extracting, setExtracting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [result, setResult] = useState<{ docx?: string; pdf?: string } | null>(null)
  const [webSearch, setWebSearch] = useState(true)
  const [exportPdf, setExportPdf] = useState(true)
  const [step, setStep] = useState<'upload' | 'form' | 'generating' | 'done'>('upload')
  const [transcriptPath, setTranscriptPath] = useState('')
  const [extractError, setExtractError] = useState('')

  const set = (name: string, value: string) => setProject(p => ({ ...p, [name]: value }))

  const handleTranscriptPath = async () => {
    const path = transcriptPath.trim()
    if (!path) return
    setExtracting(true)
    setExtractError('')
    try {
      const r = await fetch('/api/extract-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: path }),
      })
      if (!r.ok) {
        const err = await r.json()
        setExtractError(err.detail || 'Extraction failed.')
        return
      }
      const data: Partial<ProjectData> = await r.json()
      setProject(p => ({ ...p, ...data, document_date: p.document_date || new Date().toISOString().slice(0,10) }))
      setStep('form')
    } catch {
      setExtractError('Could not reach the backend.')
    } finally {
      setExtracting(false)
    }
  }

  const startGeneration = async () => {
    setGenerating(true)
    setEvents([])
    setResult(null)
    setStep('generating')

    const resp = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project, enable_web_search: webSearch, export_pdf: exportPdf }),
    })

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.trim()) continue
        try {
          const ev: ProgressEvent = JSON.parse(line)
          setEvents(prev => [...prev, ev])
          if (ev.status === 'done' && ev.docx) {
            setResult({ docx: ev.docx, pdf: ev.pdf || undefined })
            setStep('done')
          }
        } catch { /* ignore */ }
      }
    }
    setGenerating(false)
  }

  const download = (path: string) => {
    window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
  }

  return (
    <div>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 20 }}>New Offer</h1>

      {/* Step 1: Transcript path */}
      {step === 'upload' && (
        <div className="card">
          <h2>Step 1 — Meeting Transcript</h2>
          <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
            Enter the full path to the meeting transcript (.docx, .txt, .pdf).
            The AI will extract the project details automatically.
          </p>
          {extractError && (
            <div className="alert alert-error" style={{ marginBottom: 12 }}>{extractError}</div>
          )}
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input
              style={{ flex: 1, fontFamily: 'monospace', fontSize: 13 }}
              placeholder="e.g. C:\Users\...\meeting_transcript.docx"
              value={transcriptPath}
              onChange={e => setTranscriptPath(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleTranscriptPath() }}
            />
            <button
              className="btn btn-primary"
              onClick={handleTranscriptPath}
              disabled={extracting || !transcriptPath.trim()}
            >
              {extracting ? <span className="spinner" /> : 'Extract'}
            </button>
          </div>
          <div style={{ textAlign: 'center' }}>
            <button className="btn btn-secondary" onClick={() => setStep('form')}>
              Skip — fill in manually
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Form */}
      {(step === 'form' || step === 'upload') && step !== 'upload' && (
        <>
          <div className="card">
            <h2>Step 2 — Customer & Project Details</h2>
            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
              Review and correct the extracted fields before generating the offer.
            </p>
            <div className="form-grid">
              <Field label="First Name" name="first_name" value={project.first_name} onChange={set} />
              <Field label="Last Name" name="last_name" value={project.last_name} onChange={set} />
              <Field label="Company Name *" name="company_name" value={project.company_name} onChange={set} />
              <Field label="Document Date" name="document_date" value={project.document_date} onChange={set} />
              <Field label="Address" name="address" value={project.address} onChange={set} />
              <Field label="Postal Code" name="postal_code" value={project.postal_code} onChange={set} />
            </div>
          </div>

          <div className="card">
            <h2>Project Information</h2>
            <div className="form-grid">
              <Field label="Project Name *" name="project_name" value={project.project_name} onChange={set} />
              <Field label="Project Number" name="project_number" value={project.project_number} onChange={set} />
              <Field label="Salesperson Name" name="salesperson_name" value={project.salesperson_name} onChange={set} />
              <div>
                <label>Payment Type</label>
                <select value={project.payment_type} onChange={e => set('payment_type', e.target.value)}>
                  <option value="hourly">Hourly</option>
                  <option value="fixed">Fixed Price</option>
                </select>
              </div>
              <Field label="Project Start" name="project_start" value={project.project_start} onChange={set} />
              <Field label="Project End" name="project_end" value={project.project_end} onChange={set} />
              <Field label="Goals & Objectives" name="goals" value={project.goals} onChange={set} full area />
              <Field label="Constraints & Limitations" name="constraints" value={project.constraints} onChange={set} full area />
              <Field label="Material Deliverables" name="material_deliverables" value={project.material_deliverables} onChange={set} full />
              <Field label="Required Expertise" name="required_expertise" value={project.required_expertise} onChange={set} full />
              <Field label="Other Notes" name="other_notes" value={project.other_notes} onChange={set} full area />
            </div>
          </div>

          <div className="card">
            <h2>Generation Options</h2>
            <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={webSearch} onChange={e => setWebSearch(e.target.checked)} />
                <span>Enable web search (Section 1 company background)</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={exportPdf} onChange={e => setExportPdf(e.target.checked)} />
                <span>Export PDF (requires Microsoft Word)</span>
              </label>
            </div>
            <button
              className="btn btn-primary"
              style={{ fontSize: 15, padding: '11px 28px' }}
              onClick={startGeneration}
              disabled={!project.project_name}
            >
              Generate Offer ✨
            </button>
          </div>
        </>
      )}

      {/* Step 3: Generating */}
      {(step === 'generating' || step === 'done') && (
        <div className="card">
          <h2>{step === 'done' ? '✅ Offer Generated' : '⏳ Generating Offer…'}</h2>
          <ul className="progress-list">
            {SECTIONS_ORDER.map(sectionKey => {
              const ev = events.find(e => e.section === sectionKey)
              const isActive = generating && events.length > 0 && events[events.length - 1].section === sectionKey
              const dotClass = ev
                ? ev.status === 'done' || ev.status === 'progress' ? (step === 'done' ? 'done' : isActive ? 'active' : 'done')
                : ev.status === 'error' ? 'error' : 'warning'
                : 'pending'
              return (
                <li key={sectionKey} className="progress-item">
                  <span className={`progress-dot ${dotClass}`} />
                  <span>{SECTION_LABELS[sectionKey] || sectionKey}</span>
                  {ev && ev.status === 'warning' && <span style={{ fontSize: 12, color: '#c27803' }}>⚠️ {ev.message}</span>}
                </li>
              )
            })}
          </ul>

          {result && (
            <div style={{ marginTop: 20, display: 'flex', gap: 12 }}>
              {result.docx && (
                <button className="btn btn-success" onClick={() => download(result.docx!)}>
                  ⬇️ Download DOCX
                </button>
              )}
              {result.pdf && (
                <button className="btn btn-primary" onClick={() => download(result.pdf!)}>
                  ⬇️ Download PDF
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => { setStep('form'); setEvents([]); setResult(null) }}>
                ✏️ Edit & Regenerate
              </button>
            </div>
          )}
        </div>
      )}

      {/* Back button */}
      {step === 'form' && (
        <button className="btn btn-secondary" onClick={() => setStep('upload')} style={{ marginTop: 8 }}>
          ← Back to transcript upload
        </button>
      )}
    </div>
  )
}
