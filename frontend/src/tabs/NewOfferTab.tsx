import { useState, useRef, Fragment, useEffect } from 'react'
import { t, type Lang } from '../i18n'

const REGENERATABLE_SECTIONS = new Set([
  'thank_you', 'section1', 'section2', 'section3', 'section4', 'section5', 'section8',
])


interface Props {
  lang: Lang
}
interface ProjectData {
  customer_name: string; company_name: string
  address: string; postal_code: string; project_name: string
  project_number: string; salesperson_name: string; document_date: string
  project_start: string; project_end: string; goals: string
  constraints: string; payment_type: string; material_deliverables: string
  required_expertise: string; other_notes: string
}

interface ProgressEvent {
  status: 'progress' | 'done' | 'error' | 'warning' | 'stats'
  section: string; message: string
  docx?: string; pdf?: string; xlsx?: string
  elapsed_s?: number; tokens?: number
  elapsed_total_s?: number
  sections?: Record<string, any>
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

const fmtEur = (v: number) =>
  Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0') + '€'

const formatDateFi = (d: Date) => `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}`

const EMPTY: ProjectData = {
  customer_name:'', company_name:'', address:'', postal_code:'',
  project_name:'', project_number:'', salesperson_name:'', document_date:'',
  project_start:'', project_end:'', goals:'', constraints:'',
  payment_type:'hourly', material_deliverables:'', required_expertise:'', other_notes:''
}

const DRAFT_KEY = 'aisales_offer_draft'

interface DraftState {
  project: ProjectData
  webSearch: boolean
  exportPdf: boolean
  costTable: boolean
  documentLanguage: 'en' | 'fi'
}

function loadDraft(): DraftState | null {
  try {
    const raw = localStorage.getItem(DRAFT_KEY)
    if (!raw) return null
    return JSON.parse(raw) as DraftState
  } catch {
    return null
  }
}

function saveDraft(state: DraftState) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify(state))
  } catch { /* quota exceeded — ignore */ }
}

function clearDraft() {
  try { localStorage.removeItem(DRAFT_KEY) } catch { /* ignore */ }
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

function getPreviewData(previews: Record<string, any>, key: string): any {
  if (key === 'thank_you') return previews['thankyou']
  if (key === 'section10') return previews['section10_text']
  return previews[key]
}

function SectionPreviewPanel({ sectionKey, data, previews }: {
  sectionKey: string; data: any; previews: Record<string, any>
}) {
  if (!data) return null
  const boxStyle = { whiteSpace: 'pre-wrap' as const, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 10, fontSize: 12, color: '#374151' }

  if (sectionKey === 'section1') {
    return (
      <div>
        <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 12 }}>Company Background</div>
        <div style={boxStyle}>{data.company_background || '\u2014'}</div>
        <div style={{ fontWeight: 600, margin: '8px 0 4px', fontSize: 12 }}>Goals</div>
        <div style={boxStyle}>{data.goals_text || '\u2014'}</div>
      </div>
    )
  }

  if (sectionKey === 'section2') {
    return (
      <>
        {data.description_text && (
          <div style={{ marginBottom: 8 }}>
            <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 12 }}>Description</div>
            <div style={boxStyle}>{data.description_text}</div>
          </div>
        )}
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: '#f1f5f9' }}>
              <th style={{ textAlign: 'left', padding: '4px 8px' }}>Step</th>
              <th style={{ textAlign: 'right', padding: '4px 8px' }}>€/h</th>
              <th style={{ textAlign: 'right', padding: '4px 8px' }}>Hours</th>
              <th style={{ textAlign: 'right', padding: '4px 8px' }}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {(data.steps || []).map((s: any, i: number) => {
              const stepNum = s.step_id?.split(' ').pop() ?? (i + 1)
              return [
                <tr key={`m${i}`} style={{ borderBottom: '1px solid #e5e7eb', background: '#f8fafc' }}>
                  <td style={{ padding: '4px 8px', fontWeight: 700 }}>{s.step_id}: {s.name}</td>
                  <td />
                  <td style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 700 }}>{s.total_hours?.toFixed(1)}</td>
                  <td style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 700 }}>{fmtEur(s.total_cost ?? 0)}</td>
                </tr>,
                ...(s.sub_steps || []).map((ss: any, j: number) => (
                  <tr key={`s${i}-${j}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '3px 8px 3px 20px', color: '#374151' }}>{stepNum}.{j + 1}\u00a0{ss.name}</td>
                    <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{Math.round(ss.hourly_rate ?? 0)}</td>
                    <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{((ss.hours ?? 0) * (ss.persons ?? 1)).toFixed(1)}</td>
                    <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{ss.total?.toFixed(2)}\u20ac</td>
                  </tr>
                )),
              ]
            })}
          </tbody>
          <tfoot>
            <tr style={{ borderTop: '2px solid #e5e7eb', background: '#f1f5f9' }}>
              <td style={{ padding: '4px 8px', fontWeight: 700 }}>Grand Total</td>
              <td />
              <td style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 700 }}>
                {(data.steps || []).reduce((s: number, r: any) => s + (r.total_hours ?? 0), 0).toFixed(1)} h
              </td>
              <td style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 700 }}>{fmtEur(data.grand_total ?? 0)}</td>
            </tr>
          </tfoot>
        </table>
      </>
    )
  }

  if (sectionKey === 'section8') {
    return (
      <>
        {data.intro_text && <div style={{ ...boxStyle, marginBottom: 6 }}>{data.intro_text}</div>}
        {(data.experts || []).length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f1f5f9' }}>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>Name</th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>Title</th>
                <th style={{ textAlign: 'left', padding: '4px 8px' }}>Role on Project</th>
              </tr>
            </thead>
            <tbody>
              {(data.experts || []).map((e: any, i: number) => (
                <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '4px 8px', fontWeight: 600 }}>{e.name}</td>
                  <td style={{ padding: '4px 8px', color: '#6b7280' }}>{e.title}</td>
                  <td style={{ padding: '4px 8px', color: '#374151' }}>{e.role}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </>
    )
  }

  if (sectionKey === 'section9') {
    const payment = previews['section9_payment']
    return (
      <>
        <div style={boxStyle}>{typeof data === 'string' ? data : JSON.stringify(data, null, 2)}</div>
        {payment && (
          <>
            <div style={{ fontWeight: 600, margin: '8px 0 4px', fontSize: 12 }}>Payment Terms</div>
            <div style={boxStyle}>{payment}</div>
          </>
        )}
      </>
    )
  }

  const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  return <div style={boxStyle}>{text}</div>
}

export default function NewOfferTab({ lang }: Props) {
  const _draft = loadDraft()
  const [project, setProject] = useState<ProjectData>(_draft?.project ?? { ...EMPTY, document_date: formatDateFi(new Date()) })
  const [extracting, setExtracting] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [events, setEvents] = useState<ProgressEvent[]>([])
  const [sectionStats, setSectionStats] = useState<Record<string, { elapsed_s: number; tokens: number }>>({})
  const [totalElapsed, setTotalElapsed] = useState<number | null>(null)
  const [result, setResult] = useState<{ docx?: string; pdf?: string; xlsx?: string } | null>(null)
  const [webSearch, setWebSearch] = useState(_draft?.webSearch ?? true)
  const [exportPdf, setExportPdf] = useState(_draft?.exportPdf ?? true)
  const [costTable, setCostTable] = useState(_draft?.costTable ?? true)
  const [documentLanguage, setDocumentLanguage] = useState<'en' | 'fi'>(_draft?.documentLanguage ?? 'en')
  const [draftToast, setDraftToast] = useState<'restored' | 'saved' | null>(_draft ? 'restored' : null)
  const draftToastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [step, setStep] = useState<'upload' | 'form' | 'generating' | 'done'>('upload')
  const [selectedPath, setSelectedPath] = useState('')
  const [selectedName, setSelectedName] = useState('')
  const [extractError, setExtractError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [pickingFile, setPickingFile] = useState(false)
  const [testingSection, setTestingSection] = useState<'section1' | 'section2' | null>(null)
  const [testResult, setTestResult] = useState<{ section: string; result: any } | null>(null)
  const [testError, setTestError] = useState('')
  const abortControllerRef = useRef<AbortController | null>(null)
  const testAbortControllerRef = useRef<AbortController | null>(null)
  const regenAbortRef = useRef<AbortController | null>(null)
  const [regeneratingKey, setRegeneratingKey] = useState<string | null>(null)
  const [regenResults, setRegenResults] = useState<Record<string, { raw: any; elapsed_s: number }>>({})
  const [regenErrors, setRegenErrors] = useState<Record<string, string>>({})
  const [sectionPreviews, setSectionPreviews] = useState<Record<string, any>>({})
  const [expandedPreviews, setExpandedPreviews] = useState<Set<string>>(new Set())
  const [regenPrompts, setRegenPrompts] = useState<Record<string, string>>({})
  const [regenPromptOpen, setRegenPromptOpen] = useState<Set<string>>(new Set())

  // Auto-save draft whenever form fields or options change (skip during generation)
  useEffect(() => {
    if (generating) return
    saveDraft({ project, webSearch, exportPdf, costTable, documentLanguage })
    // Show 'saved' toast briefly; use 'restored' toast only on first render
    if (draftToast !== 'restored') {
      setDraftToast('saved')
      if (draftToastTimer.current) clearTimeout(draftToastTimer.current)
      draftToastTimer.current = setTimeout(() => setDraftToast(null), 2000)
    } else {
      // Dismiss the 'restored' toast after 3 s without restarting on further edits
      if (!draftToastTimer.current) {
        draftToastTimer.current = setTimeout(() => {
          setDraftToast(null)
          draftToastTimer.current = null
        }, 3000)
      }
    }
  }, [project, webSearch, exportPdf, costTable, documentLanguage]) // eslint-disable-line react-hooks/exhaustive-deps

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
      setProject(p => ({ ...p, ...data, document_date: p.document_date || formatDateFi(new Date()) }))
      setStep('form')
    } catch {
      setExtractError('Could not reach the backend.')
    } finally {
      setExtracting(false)
    }
  }

  const startGeneration = async () => {
    const controller = new AbortController()
    abortControllerRef.current = controller
    setGenerating(true)
    setEvents([])
    setSectionStats({})
    setTotalElapsed(null)
    setResult(null)
    setStep('generating')

    try {
      const resp = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project, enable_web_search: webSearch, export_pdf: exportPdf, generate_cost_table: costTable, document_language: documentLanguage }),
        signal: controller.signal,
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        const msg = err.detail || (resp.status === 429 ? t('gen_busy', lang) : t('test_error', lang))
        setEvents([{ status: 'error', section: 'init', message: msg } as ProgressEvent])
        setGenerating(false)
        setStep('generating')  // show the error in the progress view
        return
      }

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
            if (ev.status === 'stats') {
              setSectionStats(prev => ({ ...prev, [ev.section]: { elapsed_s: ev.elapsed_s ?? 0, tokens: ev.tokens ?? 0 } }))
            } else {
              setEvents(prev => [...prev, ev])
              if (ev.status === 'done' && ev.docx) {
                if (ev.elapsed_total_s != null) setTotalElapsed(ev.elapsed_total_s)
                setResult({ docx: ev.docx, pdf: ev.pdf || undefined, xlsx: (ev as any).xlsx || undefined })
                if (ev.sections) setSectionPreviews(ev.sections)
                clearDraft()
                setDraftToast(null)
                setStep('done')
              }
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') throw err
    }
    setGenerating(false)
  }

  const cancelGeneration = () => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setGenerating(false)
    setEvents([])
    setSectionStats({})
    setTotalElapsed(null)
    setResult(null)
    setSectionPreviews({})
    setExpandedPreviews(new Set())
    setStep('form')
  }

  const download = (path: string) => {
    window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
  }

  const regenSection = async (sectionKey: string, userPrompt?: string) => {
    const controller = new AbortController()
    regenAbortRef.current = controller
    setRegeneratingKey(sectionKey)
    setRegenPromptOpen(prev => { const n = new Set(prev); n.delete(sectionKey); return n })
    setRegenErrors(prev => { const n = { ...prev }; delete n[sectionKey]; return n })
    setRegenResults(prev => { const n = { ...prev }; delete n[sectionKey]; return n })
    try {
      const resp = await fetch('/api/regenerate-section', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section_key: sectionKey,
          project,
          enable_web_search: webSearch,
          document_language: documentLanguage,
          docx_path: result?.docx ?? null,
          export_pdf: exportPdf,
          user_prompt: userPrompt || null,
        }),
        signal: controller.signal,
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
            const ev = JSON.parse(line)
            if (ev.status === 'done') {
              setRegenResults(prev => ({ ...prev, [sectionKey]: { raw: ev.result, elapsed_s: ev.elapsed_s ?? 0 } }))
              // Update download paths if rebuild was successful
              if (ev.docx || ev.pdf || ev.xlsx) {
                setResult(prev => prev ? {
                  ...prev,
                  ...(ev.docx && { docx: ev.docx }),
                  ...(ev.pdf  && { pdf: ev.pdf }),
                  ...(ev.xlsx && { xlsx: ev.xlsx }),
                } : prev)
              }
            } else if (ev.status === 'error') {
              setRegenErrors(prev => ({ ...prev, [sectionKey]: ev.message }))
            }
          } catch { /* ignore */ }
        }
      }
    } catch (err: any) {
      if (err?.name !== 'AbortError') setRegenErrors(prev => ({ ...prev, [sectionKey]: t('regen_error', lang) }))
    } finally {
      regenAbortRef.current = null
      setRegeneratingKey(null)
    }
  }

  const cancelSectionTest = () => {
    testAbortControllerRef.current?.abort()
    testAbortControllerRef.current = null
    setTestingSection(null)
    setTestError('')
  }

  const runSectionTest = async (section: 'section1' | 'section2') => {
    const controller = new AbortController()
    testAbortControllerRef.current = controller
    setTestingSection(section)
    setTestResult(null)
    setTestError('')
    try {
      const r = await fetch('/api/test-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section, project, enable_web_search: webSearch, document_language: documentLanguage }),
        signal: controller.signal,
      })
      if (!r.ok) {
        const err = await r.json()
        setTestError(err.detail || t('test_error', lang))
        return
      }
      const data = await r.json()
      setTestResult(data)
    } catch (err: any) {
      if (err?.name !== 'AbortError') setTestError(t('test_error', lang))
    } finally {
      testAbortControllerRef.current = null
      setTestingSection(null)
    }
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
          {draftToast && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: draftToast === 'restored' ? '#eff6ff' : '#f0fdf4', border: `1px solid ${draftToast === 'restored' ? '#bfdbfe' : '#bbf7d0'}`, borderRadius: 6, padding: '8px 14px', marginBottom: 8, fontSize: 13, color: draftToast === 'restored' ? '#1d4ed8' : '#15803d' }}>
              <span>{draftToast === 'restored' ? `💾 ${t('draft_restored', lang)}` : `✓ ${t('draft_saved', lang)}`}</span>
              {draftToast === 'restored' && (
                <button
                  onClick={() => { clearDraft(); setProject({ ...EMPTY, document_date: formatDateFi(new Date()) }); setDraftToast(null) }}
                  style={{ background: 'none', border: '1px solid #bfdbfe', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#1d4ed8', padding: '1px 8px', marginLeft: 12 }}
                >
                  {t('draft_clear', lang)}
                </button>
              )}
            </div>
          )}
          <div className="card">
            <h2>{t('step2_title', lang)}</h2>
            <p style={{ fontSize: 13, color: '#6b7280', marginBottom: 16 }}>
              {t('step2_desc', lang)}
            </p>
            <div className="form-grid">
              <Field label={t('customer_name', lang)} name="customer_name" value={project.customer_name} onChange={set} />
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
            <h2>{t('test_section_title', lang)}</h2>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: testResult || testError ? 16 : 0 }}>
              <button
                className="btn btn-secondary"
                onClick={() => runSectionTest('section1')}
                disabled={!!testingSection || !project.company_name}
                style={{ fontSize: 13 }}
              >
                {testingSection === 'section1' ? <><span className="spinner" /> {t('testing', lang)}</> : t('test_section1_btn', lang)}
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => runSectionTest('section2')}
                disabled={!!testingSection || !project.project_name}
                style={{ fontSize: 13 }}
              >
                {testingSection === 'section2' ? <><span className="spinner" /> {t('testing', lang)}</> : t('test_section2_btn', lang)}
              </button>
              {!!testingSection && (
                <button
                  className="btn btn-secondary"
                  onClick={cancelSectionTest}
                  style={{ fontSize: 13, color: '#dc2626', borderColor: '#dc2626' }}
                >
                  {t('cancel', lang)}
                </button>
              )}
            </div>

            {testError && (
              <div className="alert alert-error" style={{ marginBottom: 8 }}>{testError}</div>
            )}

            {testResult && (
              <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: 16, fontSize: 13 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <strong>{t('test_result_label', lang)}: {testResult.section}</strong>
                  <button className="btn btn-secondary" style={{ fontSize: 12, padding: '3px 10px' }} onClick={() => setTestResult(null)}>{t('test_close', lang)}</button>
                </div>

                {testResult.section === 'section1' && (
                  <>
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('test_company_bg', lang)}</div>
                      <div style={{ whiteSpace: 'pre-wrap', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 10 }}>{testResult.result?.company_background || '—'}</div>
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('test_goals', lang)}</div>
                      <div style={{ whiteSpace: 'pre-wrap', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 10 }}>{testResult.result?.goals_text || '—'}</div>
                    </div>
                  </>
                )}

                {testResult.section === 'section2' && (
                  <>
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('test_description', lang)}</div>
                      <div style={{ whiteSpace: 'pre-wrap', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 10 }}>{testResult.result?.description_text || '—'}</div>
                    </div>
                    <div style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <span style={{ fontWeight: 600 }}>{t('test_steps', lang)}</span>
                        {testResult.result?.xlsx && (
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: 12, padding: '3px 10px' }}
                            onClick={() => download(testResult.result.xlsx)}
                          >
                            {t('download_xlsx', lang)}
                          </button>
                        )}
                      </div>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ background: '#f1f5f9' }}>
                            <th style={{ textAlign: 'left', padding: '4px 8px' }}>Step</th>
                            <th style={{ textAlign: 'right', padding: '4px 8px' }}>Hourly cost [€/h]</th>
                            <th style={{ textAlign: 'right', padding: '4px 8px' }}>Hours estimation [h]</th>
                            <th style={{ textAlign: 'right', padding: '4px 8px' }}>Cost estimation [€]</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(testResult.result?.steps || []).map((s: any, i: number) => {
                            const stepNum = s.step_id?.split(' ').pop() ?? (i + 1)
                            return [
                              <tr key={`main-${i}`} style={{ borderBottom: '1px solid #e5e7eb', background: '#f8fafc' }}>
                                <td style={{ padding: '5px 8px', fontWeight: 700 }}>{s.step_id}: {s.name}</td>
                                <td style={{ padding: '5px 8px' }} />
                                <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>{s.total_hours?.toFixed(1)}</td>
                                  <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>{fmtEur(s.total_cost ?? 0)}</td>
                              </tr>,
                              ...(s.sub_steps || []).map((ss: any, j: number) => (
                                <tr key={`sub-${i}-${j}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                  <td style={{ padding: '3px 8px 3px 20px', color: '#374151' }}>{stepNum}.{j + 1} &nbsp;{ss.name}</td>
                                  <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{Math.round(ss.hourly_rate ?? 0)}</td>
                                  <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{((ss.hours ?? 0) * (ss.persons ?? 1)).toFixed(1)}</td>
                                  <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{ss.total?.toFixed(2)}€</td>
                                </tr>
                              )),
                            ]
                          })}
                        </tbody>
                        <tfoot>
                          <tr style={{ borderTop: '2px solid #e5e7eb', background: '#f1f5f9' }}>
                            <td style={{ padding: '5px 8px', fontWeight: 700 }}>{t('test_total', lang)}</td>
                            <td />
                            <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>
                              {(testResult.result?.steps || []).reduce((sum: number, s: any) => sum + (s.total_hours ?? 0), 0).toFixed(1)} h
                            </td>
                            <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>
                              {fmtEur(testResult.result?.grand_total ?? 0)}
                            </td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          <div className="card">
            <h2>{t('gen_options', lang)}</h2>
            <div style={{ display: 'flex', gap: 24, marginBottom: 16, flexWrap: 'wrap' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={webSearch} onChange={e => setWebSearch(e.target.checked)} />
                <span>{t('web_search_label', lang)}</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                <input type="checkbox" checked={costTable} onChange={e => setCostTable(e.target.checked)} />
                <span>{t('cost_table_label', lang)}</span>
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
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h2 style={{ margin: 0 }}>
              {step === 'done' ? t('offer_generated', lang) : t('generating', lang)}
              {step === 'done' && totalElapsed != null && (
                <span style={{ fontSize: 13, fontWeight: 400, color: '#6b7280', marginLeft: 10 }}>
                  ⏱ {totalElapsed}s total
                </span>
              )}
            </h2>
            {step === 'generating' && (
              <button
                className="btn btn-secondary"
                style={{ fontSize: 13 }}
                onClick={cancelGeneration}
              >
                ✕ {t('back_transcript', lang)}
              </button>
            )}
          </div>
          <ul className="progress-list">
            {SECTIONS_ORDER.map(sectionKey => {
              const SECTION_LABELS = getSectionLabels(lang)
              const ev = events.find(e => e.section === sectionKey)
              const isActive = generating && events.length > 0 && events[events.length - 1].section === sectionKey
              const dotClass = ev
                ? ev.status === 'done' || ev.status === 'progress' ? (step === 'done' ? 'done' : isActive ? 'active' : 'done')
                : ev.status === 'error' ? 'error' : 'warning'
                : 'pending'
              const stats = sectionStats[sectionKey]
              const canRegen = step === 'done' && REGENERATABLE_SECTIONS.has(sectionKey)
              const isRegening = regeneratingKey === sectionKey
              const regenResult = regenResults[sectionKey]
              const regenError = regenErrors[sectionKey]
              const hasPreview = step === 'done' && !['docx', 'pdf'].includes(sectionKey) && !!getPreviewData(sectionPreviews, sectionKey)
              const isExpanded = expandedPreviews.has(sectionKey)
              const isPromptOpen = regenPromptOpen.has(sectionKey)
              const promptValue = regenPrompts[sectionKey] ?? ''
              return (
                <Fragment key={sectionKey}>
                  <li className="progress-item" style={{ display: 'flex', alignItems: 'center' }}>
                    <span className={`progress-dot ${dotClass}`} />
                    <span>{SECTION_LABELS[sectionKey] || sectionKey}</span>
                    {stats && (
                      <span style={{ display: 'inline-flex', gap: 6, marginLeft: 10 }}>
                        <span style={{ fontSize: 11, color: '#6b7280', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 4, padding: '1px 6px' }}>
                          ⏱ {stats.elapsed_s}s
                        </span>
                        {stats.tokens > 0 && (
                          <span style={{ fontSize: 11, color: '#6b7280', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 4, padding: '1px 6px' }}>
                            ~{stats.tokens} tok
                          </span>
                        )}
                      </span>
                    )}
                    {ev && ev.status === 'warning' && <span style={{ fontSize: 12, color: '#c27803', marginLeft: 8 }}>⚠️ {ev.message}</span>}
                    {ev && ev.status === 'error' && <span style={{ fontSize: 12, color: '#dc2626', marginLeft: 8 }}>✕ {ev.message}</span>}
                    {(hasPreview || canRegen) && (
                      <span style={{ marginLeft: 'auto', display: 'inline-flex', gap: 6, alignItems: 'center' }}>
                        {hasPreview && (
                          <button
                            title={isExpanded ? t('preview_section_hide', lang) : t('preview_section', lang)}
                            onClick={() => setExpandedPreviews(prev => { const n = new Set(prev); if (n.has(sectionKey)) n.delete(sectionKey); else n.add(sectionKey); return n })}
                            style={{ fontSize: 12, background: 'none', border: `1px solid ${isExpanded ? '#6366f1' : '#d1d5db'}`, borderRadius: 4, padding: '1px 6px', cursor: 'pointer', color: isExpanded ? '#6366f1' : '#6b7280' }}
                          >
                            {isExpanded ? t('preview_section_hide', lang) : t('preview_section', lang)}
                          </button>
                        )}
                        {canRegen && (
                          <button
                            title={isRegening ? 'Cancel' : 'Regenerate this section'}
                            onClick={() => {
                              if (isRegening) {
                                regenAbortRef.current?.abort()
                                setRegeneratingKey(null)
                              } else {
                                setRegenPromptOpen(prev => {
                                  const n = new Set(prev)
                                  if (n.has(sectionKey)) n.delete(sectionKey)
                                  else n.add(sectionKey)
                                  return n
                                })
                              }
                            }}
                            disabled={regeneratingKey !== null && !isRegening}
                            style={{ fontSize: 13, background: isPromptOpen ? '#eef2ff' : 'none', border: `1px solid ${isPromptOpen ? '#6366f1' : '#d1d5db'}`, borderRadius: 4, padding: '1px 6px', cursor: 'pointer', color: isRegening ? '#c27803' : isPromptOpen ? '#6366f1' : '#6b7280' }}
                          >
                            {isRegening ? t('regen_section_running', lang) : t('regen_section_btn', lang)}
                          </button>
                        )}
                      </span>
                    )}
                  </li>
                  {canRegen && isPromptOpen && !isRegening && (
                    <li style={{ listStyle: 'none', paddingLeft: 24, paddingBottom: 8 }}>
                      <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '10px 12px', fontSize: 13 }}>
                        <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 12, color: '#374151' }}>{t('regen_prompt_label', lang)}</div>
                        <textarea
                          value={promptValue}
                          onChange={e => setRegenPrompts(prev => ({ ...prev, [sectionKey]: e.target.value }))}
                          placeholder={t('regen_prompt_placeholder', lang)}
                          rows={3}
                          style={{ width: '100%', fontSize: 12, border: '1px solid #d1d5db', borderRadius: 4, padding: '6px 8px', resize: 'vertical', boxSizing: 'border-box', fontFamily: 'inherit' }}
                        />
                        <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                          <button
                            className="btn btn-primary"
                            style={{ fontSize: 12, padding: '4px 12px' }}
                            disabled={regeneratingKey !== null}
                            onClick={() => regenSection(sectionKey, promptValue || undefined)}
                          >
                            {t('regen_with_prompt', lang)}
                          </button>
                          <button
                            className="btn btn-secondary"
                            style={{ fontSize: 12, padding: '4px 12px' }}
                            disabled={regeneratingKey !== null}
                            onClick={() => regenSection(sectionKey)}
                          >
                            {t('regen_fresh', lang)}
                          </button>
                          <button
                            style={{ fontSize: 12, padding: '4px 10px', background: 'none', border: '1px solid #d1d5db', borderRadius: 4, cursor: 'pointer', color: '#6b7280' }}
                            onClick={() => setRegenPromptOpen(prev => { const n = new Set(prev); n.delete(sectionKey); return n })}
                          >
                            {t('regen_cancel_open', lang)}
                          </button>
                        </div>
                      </div>
                    </li>
                  )}
                  {(regenResult || regenError) && (
                    <li style={{ listStyle: 'none', paddingLeft: 24, paddingBottom: 8 }}>
                      <div style={{ background: regenError ? '#fef2f2' : '#f8fafc', border: `1px solid ${regenError ? '#fecaca' : '#e2e8f0'}`, borderRadius: 6, padding: '8px 12px', fontSize: 12 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                          {regenResult && <span style={{ color: '#6b7280' }}>⏱ {regenResult.elapsed_s}s</span>}
                          {regenError && <span style={{ color: '#dc2626' }}>{regenError}</span>}
                          <button
                            onClick={() => {
                              setRegenResults(prev => { const n = { ...prev }; delete n[sectionKey]; return n })
                              setRegenErrors(prev => { const n = { ...prev }; delete n[sectionKey]; return n })
                            }}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#9ca3af', fontSize: 13, padding: '0 2px' }}
                          >
                            {t('regen_dismiss', lang)}
                          </button>
                        </div>
                        {regenResult && sectionKey === 'section2' && (() => {
                          const sec2 = regenResult.raw?.section2 ?? {}
                          return (
                            <>
                              {sec2.description_text && (
                                <div style={{ marginBottom: 8 }}>
                                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Description</div>
                                  <div style={{ whiteSpace: 'pre-wrap', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 8 }}>{sec2.description_text}</div>
                                </div>
                              )}
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                                <span style={{ fontWeight: 600 }}>{t('test_steps', lang)}</span>
                                {sec2.xlsx && (
                                  <button className="btn btn-secondary" style={{ fontSize: 11, padding: '2px 8px' }} onClick={() => download(sec2.xlsx)}>
                                    {t('download_xlsx', lang)}
                                  </button>
                                )}
                              </div>
                              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                                <thead>
                                  <tr style={{ background: '#f1f5f9' }}>
                                    <th style={{ textAlign: 'left', padding: '4px 8px' }}>Step</th>
                                    <th style={{ textAlign: 'right', padding: '4px 8px' }}>Hourly cost [€/h]</th>
                                    <th style={{ textAlign: 'right', padding: '4px 8px' }}>Hours estimation [h]</th>
                                    <th style={{ textAlign: 'right', padding: '4px 8px' }}>Cost estimation [€]</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {(sec2.steps || []).map((s: any, i: number) => {
                                    const stepNum = s.step_id?.split(' ').pop() ?? (i + 1)
                                    return [
                                      <tr key={`main-${i}`} style={{ borderBottom: '1px solid #e5e7eb', background: '#f8fafc' }}>
                                        <td style={{ padding: '5px 8px', fontWeight: 700 }}>{s.step_id}: {s.name}</td>
                                        <td style={{ padding: '5px 8px' }} />
                                        <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>{s.total_hours?.toFixed(1)}</td>
                                        <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>{fmtEur(s.total_cost ?? 0)}</td>
                                      </tr>,
                                      ...(s.sub_steps || []).map((ss: any, j: number) => (
                                        <tr key={`sub-${i}-${j}`} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                          <td style={{ padding: '3px 8px 3px 20px', color: '#374151' }}>{stepNum}.{j + 1} &nbsp;{ss.name}</td>
                                          <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{Math.round(ss.hourly_rate ?? 0)}</td>
                                          <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{((ss.hours ?? 0) * (ss.persons ?? 1)).toFixed(1)}</td>
                                          <td style={{ padding: '3px 8px', textAlign: 'right', color: '#6b7280' }}>{ss.total?.toFixed(2)}€</td>
                                        </tr>
                                      )),
                                    ]
                                  })}
                                </tbody>
                                <tfoot>
                                  <tr style={{ borderTop: '2px solid #e5e7eb', background: '#f1f5f9' }}>
                                    <td style={{ padding: '5px 8px', fontWeight: 700 }}>{t('test_total', lang)}</td>
                                    <td />
                                    <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>
                                      {(sec2.steps || []).reduce((sum: number, s: any) => sum + (s.total_hours ?? 0), 0).toFixed(1)} h
                                    </td>
                                    <td style={{ padding: '5px 8px', textAlign: 'right', fontWeight: 700 }}>
                                      {fmtEur(sec2.grand_total ?? 0)}
                                    </td>
                                  </tr>
                                </tfoot>
                              </table>
                            </>
                          )
                        })()}
                        {regenResult && sectionKey === 'section1' && (() => {
                          const sec1 = regenResult.raw?.section1 ?? {}
                          return (
                            <>
                              <div style={{ marginBottom: 8 }}>
                                <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('test_company_bg', lang)}</div>
                                <div style={{ whiteSpace: 'pre-wrap', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 8 }}>{sec1.company_background || '—'}</div>
                              </div>
                              <div>
                                <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('test_goals', lang)}</div>
                                <div style={{ whiteSpace: 'pre-wrap', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 6, padding: 8 }}>{sec1.goals_text || '—'}</div>
                              </div>
                            </>
                          )
                        })()}
                        {regenResult && sectionKey !== 'section1' && sectionKey !== 'section2' && (() => {
                          const val = regenResult.raw ? regenResult.raw[Object.keys(regenResult.raw)[0]] : ''
                          const text = typeof val === 'string' ? val : JSON.stringify(val, null, 2)
                          return <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit', color: '#374151' }}>{text}</pre>
                        })()}
                      </div>
                    </li>
                  )}
                  {isExpanded && (
                    <li style={{ listStyle: 'none', paddingLeft: 24, paddingBottom: 8 }}>
                      <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 6, padding: '10px 14px' }}>
                        <SectionPreviewPanel sectionKey={sectionKey} data={getPreviewData(sectionPreviews, sectionKey)} previews={sectionPreviews} />
                      </div>
                    </li>
                  )}
                </Fragment>
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
              {result.xlsx && (
                <button className="btn btn-secondary" onClick={() => download(result.xlsx!)}>
                  {t('download_xlsx', lang)}
                </button>
              )}
              <button className="btn btn-secondary" onClick={() => { setStep('form'); setEvents([]); setResult(null); setSectionPreviews({}); setExpandedPreviews(new Set()) }}>
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
