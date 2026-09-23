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
const API_KEY = import.meta.env.VITE_ABR_API_KEY || ''

export async function fetchInternalDashboard(apiKeyOverride = ''): Promise<DashboardSummary> {
  const apiKey = apiKeyOverride || API_KEY
  const response = await fetch(`${API_BASE_URL}/v1/dashboard/internal`, {
    headers: apiKey ? { 'x-api-key': apiKey } : undefined,
  })

  if (!response.ok) {
    throw new Error(`API respondeu ${response.status}`)
  }

  return response.json()
}
