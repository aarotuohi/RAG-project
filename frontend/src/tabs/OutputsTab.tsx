import { useState, useEffect } from 'react'
import { t, type Lang } from '../i18n'

interface OfferMeta {
  customer_name?: string
  company_name?: string
  project_name?: string
  document_language?: string
  generated_at?: string    // ISO-8601
  elapsed_total_s?: number
  section_stats?: Record<string, { elapsed_s: number; tokens: number }>
  files?: { docx?: string; pdf?: string; xlsx?: string }
}

interface OutputFile {
  name: string
  path: string
  size: number
  meta?: OfferMeta
}

interface Props {
  lang: Lang
  isActive?: boolean
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatDate(iso: string | undefined, lang: Lang): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return lang === 'fi'
      ? `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
      : d.toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })
  } catch { return iso }
}

function MetaBadge({ label, value }: { label: string; value: string }) {
  return (
    <span style={{ fontSize: 11, color: '#6b7280', background: '#f1f5f9', border: '1px solid #e2e8f0', borderRadius: 4, padding: '1px 6px', marginRight: 4 }}>
      <span style={{ color: '#9ca3af' }}>{label}: </span>{value}
    </span>
  )
}

export default function OutputsTab({ lang, isActive }: Props) {
  const [files, setFiles] = useState<OutputFile[]>([])
  const [loading, setLoading] = useState(true)

  const fetchOutputs = () => {
    setLoading(true)
    fetch('/api/outputs')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => setFiles(Array.isArray(data) ? data : []))
      .catch(() => setFiles([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { if (isActive) fetchOutputs() }, [isActive])

  const download = (path: string) => {
    window.open(`/api/download?path=${encodeURIComponent(path)}`, '_blank')
  }

  const deleteFile = async (file: OutputFile) => {
    if (!confirm(`${t('confirm_delete', lang)} "${file.name}"?`)) return
    try {
      const r = await fetch('/api/delete-output', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: file.path }),
      })
      if (r.ok) setFiles(prev => prev.filter(f => f.path !== file.path))
    } catch { /* ignore */ }
  }

  const docxFiles = files.filter(f => f.name.endsWith('.docx'))
  const pdfFiles  = files.filter(f => f.name.endsWith('.pdf'))

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700 }}>{t('generated_offers', lang)}</h1>
        <button className="btn btn-secondary" onClick={fetchOutputs}>{t('refresh_btn', lang)}</button>
      </div>

      {loading && <div style={{ color: '#6b7280', fontSize: 14 }}>{t('loading', lang)}</div>}

      {!loading && files.length === 0 && (
        <div className="alert alert-info">
          {t('no_offers', lang)} <strong>{t('nav_new_offer', lang)}</strong> {t('no_offers2', lang)}
        </div>
      )}

      {docxFiles.length > 0 && (
        <div className="card">
          <h2>{t('word_docs', lang)}</h2>
          {docxFiles.map(f => (
            <div key={f.path} className="output-item" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
              <div style={{ display: 'flex', width: '100%', alignItems: 'center', gap: 8 }}>
                <span className="output-icon">📝</span>
                <span className="output-name" style={{ flex: 1 }}>{f.name}</span>
                <span className="output-size">{formatSize(f.size)}</span>
                <button className="btn btn-secondary" style={{ padding: '6px 14px' }} onClick={() => download(f.path)}>
                  {t('download_btn', lang)}
                </button>
                <button className="btn btn-secondary" style={{ padding: '6px 14px', color: '#dc2626' }} onClick={() => deleteFile(f)}>
                  {t('delete_btn', lang)}
                </button>
              </div>
              {f.meta && (
                <div style={{ paddingLeft: 32 }}>
                  {(f.meta.company_name || f.meta.customer_name) && (
                    <MetaBadge
                      label={f.meta.company_name ? 'Company' : 'Customer'}
                      value={f.meta.company_name || f.meta.customer_name || ''}
                    />
                  )}
                  {f.meta.project_name && <MetaBadge label="Project" value={f.meta.project_name} />}
                  {f.meta.generated_at && (
                    <MetaBadge label={t('meta_generated', lang)} value={formatDate(f.meta.generated_at, lang)} />
                  )}
                  {f.meta.elapsed_total_s != null && (
                    <MetaBadge label={t('meta_duration', lang)} value={`${f.meta.elapsed_total_s}s`} />
                  )}
                  {f.meta.document_language && (
                    <MetaBadge label={t('meta_language', lang)} value={f.meta.document_language.toUpperCase()} />
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {pdfFiles.length > 0 && (
        <div className="card">
          <h2>{t('pdf_docs', lang)}</h2>
          {pdfFiles.map(f => (
            <div key={f.path} className="output-item">
              <span className="output-icon">📄</span>
              <span className="output-name">{f.name}</span>
              <span className="output-size">{formatSize(f.size)}</span>
              <button className="btn btn-primary" style={{ padding: '6px 14px' }} onClick={() => download(f.path)}>
                {t('download_btn', lang)}
              </button>
              <button className="btn btn-secondary" style={{ padding: '6px 14px', color: '#dc2626' }} onClick={() => deleteFile(f)}>
                {t('delete_btn', lang)}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
