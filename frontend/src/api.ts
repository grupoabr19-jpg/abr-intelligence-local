export type Report = {
  query_id: string
  area: string
  name: string
  entity: string
  automation_status: string
  deliverables: string[]
  notes: string
}

export type Requirement = {
  key: string
  title: string
  priority: string
  refresh: string
  grain: string
  objective: string
  fields: string[]
  known_sources: string[]
  gaps: string[]
}

export type DashboardSummary = {
  domain: string
  generated_from: string
  date_range?: {
    date_from: string | null
    date_to: string | null
  }
  kpis: Record<string, number>
  reports: Report[]
  reports_by_status: Array<{ status: string; total: number }>
  reports_by_area: Array<{ area: string; total: number }>
  requirements: Requirement[]
  external_spreadsheet_sources: Array<{
    key: string
    title: string
    local_path: string
    likely_coverage: string[]
    notes: string
  }>
  staging_by_entity: Array<{ entidade: string; linhas: number }>
  recent_history: Array<{
    entidade: string
    sync_id: string
    status: string
    registros_lidos: number
    registros_inseridos: number
    iniciado_em: string | null
  }>
  sales_regions: Array<{ canal: string; regiao: string; linhas: number; valor_total: string }>
  warnings: string[]
}

const DEFAULT_API_BASE_URL =
  window.location.hostname === '127.0.0.1' && window.location.port === '5173'
    ? 'http://127.0.0.1:8000'
    : window.location.origin
const API_BASE_URL = import.meta.env.VITE_ABR_API_BASE_URL || DEFAULT_API_BASE_URL
const DASHBOARD_SESSION_STORAGE_KEY = 'abr_dashboard_session'

export class DashboardAuthError extends Error {
  constructor() {
    super('AUTH_REQUIRED')
  }
}

export async function fetchInternalDashboard(filters?: { dateFrom?: string; dateTo?: string }): Promise<DashboardSummary> {
  const params = new URLSearchParams()
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.dateTo) params.set('date_to', filters.dateTo)
  const query = params.toString()
  const sessionToken = window.localStorage.getItem(DASHBOARD_SESSION_STORAGE_KEY)
  const response = await fetch(`${API_BASE_URL}/v1/dashboard/internal${query ? `?${query}` : ''}`, {
    credentials: 'include',
    headers: sessionToken ? { 'x-dashboard-session': sessionToken } : undefined,
  })

  if (response.status === 401) {
    window.localStorage.removeItem(DASHBOARD_SESSION_STORAGE_KEY)
    throw new DashboardAuthError()
  }
  if (!response.ok) {
    throw new Error(`API respondeu ${response.status}`)
  }

  return response.json()
}

export async function loginDashboard(password: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/v1/auth/dashboard-login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!response.ok) {
    throw new Error('Senha invalida')
  }
  const body = await response.json()
  if (body.session_token) {
    window.localStorage.setItem(DASHBOARD_SESSION_STORAGE_KEY, body.session_token)
  }
}
