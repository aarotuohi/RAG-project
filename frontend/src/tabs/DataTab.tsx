import { useState, useEffect, useRef } from 'react'
import { t, type Lang } from '../i18n'

interface Props {
  lang: Lang
  isActive: boolean
}

interface FolderEntry {
  folder: string
  files: { name: string; size: number }[]
}

export default function DataTab({ lang, isActive }: Props) {
  const [folders, setFolders] = useState<FolderEntry[]>([])
  const [selectedFolder, setSelectedFolder] = useState('')
  const [newFolderName, setNewFolderName] = useState('')
  const [creatingFolder, setCreatingFolder] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchFolders = () => {
    fetch('/api/cost-history-folders')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setFolders)
      .catch(() => setFolders([]))
  }

  useEffect(() => {
    if (isActive) fetchFolders()
  }, [isActive])

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    setCreatingFolder(true)
    setMessage(null)
    try {
      const r = await fetch('/api/cost-history-folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_name: newFolderName.trim() }),
      })
      if (r.ok) {
        setNewFolderName('')
        fetchFolders()
      } else {
        const d = await r.json()
        setMessage({ type: 'error', text: d.detail || t('upload_error', lang) })
      }
    } catch {
      setMessage({ type: 'error', text: t('upload_error', lang) })
    } finally {
      setCreatingFolder(false)
    }
  }

  const handleUpload = async () => {
    const file = fileInputRef.current?.files?.[0]
    if (!file || !selectedFolder) return
    setUploading(true)
    setMessage(null)
    try {
      const form = new FormData()
      form.append('file', file)
      const r = await fetch(`/api/ingest?collection=cost_history&folder=${encodeURIComponent(selectedFolder)}`, {
        method: 'POST',
        body: form,
      })
      if (r.ok) {
        const d = await r.json()
        setMessage({ type: 'success', text: `${t('upload_success', lang)} ${d.file}` })
        if (fileInputRef.current) fileInputRef.current.value = ''
        fetchFolders()
      } else {
        const d = await r.json()
        setMessage({ type: 'error', text: d.detail || t('upload_error', lang) })
      }
    } catch {
      setMessage({ type: 'error', text: t('upload_error', lang) })
    } finally {
      setUploading(false)
    }
  }

  const fmtSize = (bytes: number) =>
    bytes < 1024 ? `${bytes} B` : bytes < 1_048_576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1_048_576).toFixed(1)} MB`

  const folderLabel = (name: string) =>
    name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())

  return (
    <div className="tab-section">
      <h2>{t('data_title', lang)}</h2>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ marginBottom: 8 }}>{t('cost_history_folders', lang)}</h3>
        <p style={{ color: '#6b7280', marginBottom: 16, fontSize: 14 }}>{t('cost_history_desc', lang)}</p>

        {/* Folder list */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
          {folders.map(entry => (
            <div
              key={entry.folder}
              style={{
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                padding: '12px 16px',
                minWidth: 180,
                background: '#f9fafb',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>📁 {folderLabel(entry.folder)}</div>
              <div style={{ fontSize: 13, color: '#6b7280' }}>
                {entry.files.length > 0
                  ? `${entry.files.length} ${t('files_in_folder', lang)}`
                  : t('no_files', lang)}
              </div>
              {entry.files.map(f => (
                <div key={f.name} style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>
                  {f.name} ({fmtSize(f.size)})
                </div>
              ))}
            </div>
          ))}
        </div>

        {/* Create new folder */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 20 }}>
          <label style={{ fontSize: 14, minWidth: 160 }}>{t('new_folder_label', lang)}</label>
          <input
            type="text"
            value={newFolderName}
            onChange={e => setNewFolderName(e.target.value)}
            placeholder="e.g. mechanical_design"
            style={{ flex: 1, maxWidth: 220 }}
            onKeyDown={e => e.key === 'Enter' && handleCreateFolder()}
          />
          <button
            className="btn"
            onClick={handleCreateFolder}
            disabled={creatingFolder || !newFolderName.trim()}
          >
            {t('create_folder_btn', lang)}
          </button>
        </div>

        {/* Upload form */}
        <div style={{ display: 'grid', gap: 8 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label style={{ fontSize: 14, minWidth: 160 }}>{t('folder_label', lang)}</label>
            <select
              value={selectedFolder}
              onChange={e => setSelectedFolder(e.target.value)}
              style={{ flex: 1, maxWidth: 220 }}
            >
              <option value="">{t('select_folder', lang)}</option>
              {folders.map(f => (
                <option key={f.folder} value={f.folder}>{folderLabel(f.folder)}</option>
              ))}
            </select>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <label style={{ fontSize: 14, minWidth: 160 }}>{t('upload_file_label', lang)}</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              style={{ flex: 1 }}
            />
          </div>
          <div>
            <button
              className="btn btn-primary"
              onClick={handleUpload}
              disabled={uploading || !selectedFolder}
            >
              {uploading ? t('uploading', lang) : t('upload_btn', lang)}
            </button>
          </div>
        </div>

        {message && (
          <div
            style={{
              marginTop: 12,
              padding: '8px 12px',
              borderRadius: 6,
              background: message.type === 'success' ? '#d1fae5' : '#fee2e2',
              color: message.type === 'success' ? '#065f46' : '#991b1b',
              fontSize: 14,
            }}
          >
            {message.text}
          </div>
        )}
      </div>
    </div>
  )
}
