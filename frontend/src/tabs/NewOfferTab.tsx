import { useState } from 'react'
import { t, type Lang } from '../i18n'

interface Props {
  lang: Lang
}
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

function getSectionLabels(lang: Lang): Record<string, string> {
  return {
    thank_you: t('sec_thank_you', lang), section1: t('sec_section1', lang),
    section2: t('sec_section2', lang), section3: t('sec_section3', lang),
    section4: t('sec_section4', lang), section5: t('sec_section5', lang),
    section6: t('sec_section6', lang), section7: t('sec_section7', lang),
    section8: t('sec_section8', lang), section9: t('sec_section9', lang),
    section10: t('sec_section10', lang), docx: t('sec_docx', lang), pdf: t('sec_pdf', lang),
  }
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

export default function NewOfferTab({ lang }: Props) {
  const [project, setProject] = useState<ProjectData>({ ...EMPTY, document_date: new Date().toISOString().slice(0,10) })
  const [extracting, setExtracting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [result, setResult] = useState<{ docx?: string; pdf?: string } | null>(null)
  const [webSearch, setWebSearch] = useState(true)
  const [exportPdf, setExportPdf] = useState(true)
  const [documentLanguage, setDocumentLanguage] = useState<'en' | 'fi'>('en')
  const [step, setStep] = useState<'upload' | 'form' | 'generating' | 'done'>('upload')
  const [selectedPath, setSelectedPath] = useState('')
  const [selectedName, setSelectedName] = useState('')
  const [extractError, setExtractError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [pickingFile, setPickingFile] = useState(false)

  const set = (name: string, value: string) => setProject(p => ({ ...p, [name]: value }))

  const selectFile = async () => {
    setPickingFile(true)
    try {
      const r = await fetch('/api/open-file-dialog')
      const d = await r.json()
      if (d.path) {
        setSelectedPath(d.path)
        setSelectedName(d.path.split(/[\\/]/).pop() || d.path)
        setExtractError('')
      }
    } catch {
      setExtractError('Could not open file dialog.')
    } finally {
      setPickingFile(false)
    }
  }

  const handleFileDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (!file) return
    setExtractError('')
    // pywebview exposes the OS path directly — use it
    const osPath: string | undefined = (file as any).path
    if (osPath) {
      setSelectedPath(osPath)
      setSelectedName(file.name)
      return
    }
    // Fallback: upload the file content to the backend and get back a saved path
    try {
      const form = new FormData()
      form.append('file', file, file.name)
      const r = await fetch('/api/upload-transcript', { method: 'POST', body: form })
      if (!r.ok) throw new Error()
      const d = await r.json()
      setSelectedPath(d.path)
      setSelectedName(d.name)
    } catch {
      setExtractError(t('drop_upload_failed', lang))
    }
  }

  const handleExtract = async (filePath: string) => {
    if (!filePath) return
    setExtracting(true)
    setExtractError('')
    try {
      const r = await fetch('/api/extract-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_path: filePath }),
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
      body: JSON.stringify({ project, enable_web_search: webSearch, export_pdf: exportPdf, document_language: documentLanguage }),
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
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 20 }}>{t('new_offer', lang)}</h1>

      {/* Step 1: Transcript selection */}
      {step === 'upload' && (
        <div className="card">
          <h2>{t('step1_title', lang)}</h2>
          <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>{t('step1_desc', lang)}</p>

          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={e => { e.preventDefault(); setDragOver(false) }}
            onDrop={handleFileDrop}
            style={{
              border: dragOver ? '2px dashed #6366f1' : selectedPath ? '2px solid #22c55e' : '2px dashed #d1d5db',
              borderRadius: 12,
              padding: '32px 24px',
              marginBottom: 16,
              background: dragOver ? '#eef2ff' : selectedPath ? '#f0fdf4' : '#fafafa',
              textAlign: 'center',
              transition: 'all .15s',
              cursor: 'default',
            }}
          >
            {selectedPath ? (
              <div>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
                <div style={{ fontWeight: 600, fontSize: 14, color: '#15803d', marginBottom: 4 }}>{selectedName}</div>
                <div style={{ fontSize: 11, color: '#6b7280', fontFamily: 'monospace', wordBreak: 'break-all' }}>{selectedPath}</div>
                <button
                  onClick={() => { setSelectedPath(''); setSelectedName(''); setExtractError('') }}
                  style={{ marginTop: 10, fontSize: 11, color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  {t('clear_file', lang)}
                </button>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: 36, marginBottom: 8 }}>📂</div>
                <div style={{ fontWeight: 600, fontSize: 14, color: '#374151', marginBottom: 4 }}>{t('drop_file_here', lang)}</div>
                <div style={{ fontSize: 12, color: '#9ca3af' }}>.txt &nbsp;·&nbsp; .docx &nbsp;·&nbsp; .pdf &nbsp;·&nbsp; .md</div>
              </div>
            )}
          </div>

          {/* Select file button */}
          {!selectedPath && (
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <button
                className="btn btn-primary"
                onClick={selectFile}
                disabled={pickingFile}
                style={{ fontSize: 14, padding: '10px 28px' }}
              >
                {pickingFile ? <><span className="spinner" /> {t('opening', lang)}</> : t('select_file_btn', lang)}
              </button>
            </div>
          )}

          {extractError && (
            <div className="alert alert-error" style={{ marginBottom: 12 }}>{extractError}</div>
          )}

          {/* Actions once file is chosen */}
          {selectedPath && (
            <div style={{ display: 'flex', gap: 10, marginBottom: 12, justifyContent: 'center' }}>
              <button
                className="btn btn-primary"
                style={{ fontSize: 14, padding: '10px 28px' }}
                onClick={() => handleExtract(selectedPath)}
                disabled={extracting}
              >
                {extracting ? <><span className="spinner" /> {t('extracting', lang)}</> : t('extract_btn', lang)}
              </button>
            </div>
          )}

          <div style={{ textAlign: 'center' }}>
            <button
              className="btn btn-secondary"
              onClick={() => setStep('form')}
              style={{ fontSize: 12 }}
            >
              {t('skip_btn', lang)}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Form */}
      {(step === 'form' || step === 'upload') && step !== 'upload' && (
        <>
          <div className="card">
            <h2>{t('step2_title', lang)}</h2>
            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
              {t('step2_desc', lang)}
            </p>
            <div className="form-grid">
              <Field label={t('first_name', lang)} name="first_name" value={project.first_name} onChange={set} />
              <Field label={t('last_name', lang)} name="last_name" value={project.last_name} onChange={set} />
              <Field label={t('company_name', lang)} name="company_name" value={project.company_name} onChange={set} />
              <Field label={t('doc_date', lang)} name="document_date" value={project.document_date} onChange={set} />
              <Field label={t('address', lang)} name="address" value={project.address} onChange={set} />
              <Field label={t('postal_code', lang)} name="postal_code" value={project.postal_code} onChange={set} />
            </div>
          </div>

          <div className="card">
            <h2>{t('project_info', lang)}</h2>
            <div className="form-grid">
              <Field label={t('project_name', lang)} name="project_name" value={project.project_name} onChange={set} />
              <Field label={t('project_number', lang)} name="project_number" value={project.project_number} onChange={set} />
              <Field label={t('salesperson_name', lang)} name="salesperson_name" value={project.salesperson_name} onChange={set} />
              <div>
                <label>{t('payment_type', lang)}</label>
                <select value={project.payment_type} onChange={e => set('payment_type', e.target.value)}>
                  <option value="hourly">{t('payment_hourly', lang)}</option>
                  <option value="fixed">{t('payment_fixed', lang)}</option>
                </select>
              </div>
              <Field label={t('project_start', lang)} name="project_start" value={project.project_start} onChange={set} />
              <Field label={t('project_end', lang)} name="project_end" value={project.project_end} onChange={set} />
              <Field label={t('goals', lang)} name="goals" value={project.goals} onChange={set} full area />
              <Field label={t('constraints', lang)} name="constraints" value={project.constraints} onChange={set} full area />
              <Field label={t('material_deliverables', lang)} name="material_deliverables" value={project.material_deliverables} onChange={set} full />
              <Field label={t('required_expertise', lang)} name="required_expertise" value={project.required_expertise} onChange={set} full />
              <Field label={t('other_notes', lang)} name="other_notes" value={project.other_notes} onChange={set} full area />
            </div>
          </div>

          <div className="card">
            <h2>{t('gen_options', lang)}</h2>
            <div style={{ display: 'flex', gap: 24, marginBottom: 16, flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={webSearch} onChange={e => setWebSearch(e.target.checked)} />
                <span>{t('web_search_label', lang)}</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={exportPdf} onChange={e => setExportPdf(e.target.checked)} />
                <span>{t('export_pdf_label', lang)}</span>
              </label>
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontWeight: 600, fontSize: 13, display: 'block', marginBottom: 6 }}>{t('doc_language', lang)}</label>
              <div style={{ display: 'flex', gap: 12 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input type="radio" name="doc_lang" value="en" checked={documentLanguage === 'en'} onChange={() => setDocumentLanguage('en')} />
                  <span>🇬🇧 {lang === 'fi' ? 'Englanti' : 'English'}</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                  <input type="radio" name="doc_lang" value="fi" checked={documentLanguage === 'fi'} onChange={() => setDocumentLanguage('fi')} />
                  <span>🇫🇮 {lang === 'fi' ? 'Suomi' : 'Finnish'}</span>
                </label>
              </div>
            </div>
            <button
              className="btn btn-primary"
              style={{ fontSize: 15, padding: '11px 28px' }}
              onClick={startGeneration}
              disabled={!project.project_name}
            >
              {t('generate_btn', lang)}
            </button>
          </div>
        </>
      )}

      {/* Step 3: Generating */}
      {(step === 'generating' || step === 'done') && (
        <div className="card">
          <h2>{step === 'done' ? t('offer_generated', lang) : t('generating', lang)}</h2>
          <ul className="progress-list">
            {SECTIONS_ORDER.map(sectionKey => {
              const SECTION_LABELS = getSectionLabels(lang)
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
                  {t('download_docx', lang)}
                </button>
              )}
              {result.pdf && (
                <button className="btn btn-primary" onClick={() => download(result.pdf!)}>
                  {t('download_pdf', lang)}
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => { setStep('form'); setEvents([]); setResult(null) }}>
                {t('edit_regenerate', lang)}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Back button */}
      {step === 'form' && (
        <button className="btn btn-secondary" onClick={() => setStep('upload')} style={{ marginTop: 8 }}>
          {t('back_transcript', lang)}
        </button>
      )}
    </div>
  )
}
