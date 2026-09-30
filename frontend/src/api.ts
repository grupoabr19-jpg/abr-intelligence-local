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
  sales_summary?: {
    linhas: number
    valor_total: string
    receita_liquida: string
    lucro_bruto: string
    peso_total: string
    preco_medio_kg: string
    clientes: number
    itens: number
    data_min: string | null
    data_max: string | null
    cache_refreshed_at?: string | null
    monthly: Array<{
      mes: string
      linhas: number
      valor_total: string
      receita_liquida?: string
      lucro_bruto?: string
      margem_contribuicao?: string
      notas_fiscais?: number
      clientes?: number
      peso_total: string
      valor_perdido?: string
    }>
    families: Array<{ familia: string; linhas: number; valor_total: string; peso_total: string }>
    clients_abc?: Array<{ cliente: string; linhas: number; valor_total: string; peso_total: string; ultima_compra: string | null }>
    clients_decline?: Array<{ cliente: string; peso_anterior: string; peso_atual: string; queda_peso: string }>
    rfm_segments?: Array<{ segmento: string; total: number }>
    recency_buckets?: Array<{ faixa: string; ordem: number; clientes: number }>
    segments?: Array<{
      segmento: string
      linhas: number
      valor_total: string
      receita_liquida: string
      lucro_bruto: string
      margem_contribuicao?: string
      peso_total: string
    }>
    segment_monthly?: Array<{ mes: string; segmento: string; valor_total: string; peso_total: string }>
    items?: Array<{ produto: string; item: string | null; familia: string; linhas: number; valor_total: string; peso_total: string }>
    item_decline?: Array<{ produto: string; peso_anterior: string; peso_atual: string; queda_peso: string }>
    family_segments?: Array<{ familia: string; segmento: string; valor_total: string; peso_total: string }>
    price_stats?: Array<{ familia: string; min_preco_kg: string; avg_preco_kg: string; max_preco_kg: string; valor_total: string; peso_total: string }>
    price_outliers?: Array<{
      produto: string
      familia: string
      valor_total: string
      peso_total: string
      preco_kg: string
      media_familia_kg: string
      desvio_pct: string
    }>
    price_monthly?: Array<{ mes: string; min_preco_kg: string; avg_preco_kg: string; max_preco_kg: string; valor_total: string; peso_total: string }>
    margin_monthly?: Array<{ mes: string; receita_liquida: string; lucro_bruto: string; margem_contribuicao?: string; peso_total: string }>
    margin_clients?: Array<{ cliente: string; receita_liquida: string; lucro_bruto: string; margem_contribuicao?: string; peso_total: string }>
    losses?: Array<{ motivo: string; linhas: number; valor_perdido: string }>
    sellers?: Array<{ vendedor: string; valor_total: string; valor_perdido: string; peso_total: string }>
    quote_monthly?: Array<{
      mes: string
      kg_cotado: string
      kg_vendido: string
      kg_perdido: string
      valor_cotado: string
      valor_vendido: string
      valor_perdido: string
    }>
    quote_sellers?: Array<{
      vendedor: string
      kg_cotado: string
      kg_vendido: string
      kg_perdido: string
      valor_vendido: string
      valor_perdido: string
    }>
    quote_funnel?: Array<{ etapa: string; kg_total: string }>
    cities?: Array<{ cidade: string; estado: string; clientes: number; valor_total: string; peso_total: string }>
  }
  attendance_summary?: {
    data_available: boolean
    source_grain: string
    rows: number
    valid_rows?: number
    headers: string[]
    latest_imported_at: string | null
    message?: string
    missing_required_fields?: string[]
    summary_rows?: Array<{ metrica: string; valor: string }>
    audit: {
      qtd_excluida_comunicacao_interna: number
      qtd_excluida_liderancas: number
    }
    kpis?: {
      leads_novos: number
      leads_abertos: number
      tempo_mediano_primeira_resposta: number | null
      sla_5_min: number | null
      sla_15_min: number | null
      taxa_nao_resposta: number | null
      pipeline_aberto_qtd: number
      pipeline_aberto_valor: string
      leads_sem_proxima_tarefa: number
      leads_sem_proxima_tarefa_pct: number | null
    }
    win_rate_by_funnel?: Array<{
      funil: string
      ganhas: number
      perdidas: number
      fechadas: number
      abertas: number
      leads_periodo: number
      conversion_rate: number
      win_rate: number
    }>
    ranking_basis?: string
    region_dimension?: Array<{ colaborador: string; funcao: string; regiao_polo: string }>
    ranking_colaboradores?: Array<{
      nome: string
      funcao: string
      regiao_polo: string
      leads: number
      ganhas: number
      perdidas: number
      win_rate: number | null
      sla_5_min: number | null
      pipeline_aberto_qtd: number
      pipeline_aberto_valor: string
      follow_up_cobertura: number | null
    }>
    ranking_regioes?: Array<{
      regiao_polo: string
      colaboradores: string[]
      leads: number
      ganhas: number
      perdidas: number
      win_rate: number | null
      sla_5_min: number | null
      pipeline_aberto_qtd: number
      pipeline_aberto_valor: string
      follow_up_cobertura: number | null
    }>
    unmapped_collaborators?: string[]
    data_quality?: Array<{ regra: string; severidade: string; total: number; checked_at: string | null }>
    daily?: Array<{
      data: string | null
      leads: number
      abertos: number
      ganhos: number
      perdidos: number
      pipeline_valor: string
      sla_validos: number
      sla_5: number
      sla_15: number
    }>
    origins?: Array<{ origem: string; leads: number }>
    event_types?: Array<{ tipo: string; eventos: number }>
    event_stats?: { raw_events: number; linked_events: number }
  }
  market_summary?: {
    sources: Array<{
      source_key: string
      source_name: string
      category: string
      status: string
      configured: boolean
      reachable: boolean
      latest_reference_period: string | null
      last_row_count: number
      last_success_at: string | null
      error_message: string | null
      checked_at: string | null
    }>
    active_filter?: {
      tab: string | null
      date_from: string | null
      date_to: string | null
    }
    filter_defaults?: Record<
      string,
      {
        label: string
        default_months: number | null
        default_days: number | null
        date_from: string | null
        date_to: string | null
        filters: Record<string, unknown>
      }
    >
    decision_layer?: {
      price_pressure: Array<{
        period: string | null
        family: string
        classification: string
        status: string
        score: number | null
        available_components_count: number
        components: Record<string, unknown>
        source_periods: Record<string, unknown>
      }>
      demand_family: Array<{
        period: string | null
        family: string
        classification: string
        status: string
        score: number | null
        available_components_count: number
        drivers: Array<Record<string, unknown>>
        source_periods: Record<string, unknown>
      }>
      cockpit: Array<{
        period: string | null
        signal_key: string
        family: string
        title: string
        classification: string
        score: number | null
        available_components_count: number
        drivers: Array<Record<string, unknown>>
        target_tab: string
        source_periods: Record<string, unknown>
      }>
      opportunities: Array<{
        period: string | null
        polo: string | null
        uf: string | null
        opportunities: number
        high_relevance: number
        total_value: string | null
        avg_relevance_score: string | null
        product_matches: Record<string, unknown>
      }>
    }
    healthy_sources: string[]
    available_tabs: string[]
    overview: {
      healthy_count: number
      configured_count: number
      error_count: number
      latest_periods: Array<{ source_key: string; source_name: string; period: string | null; rows: number; status: string }>
      macro_indicators: MarketIndicator[]
    }
    overview_decision?: {
      date_range: { date_from: string | null; date_to: string | null }
      kpis: Array<{
        id: string
        title: string
        value: string | null
        unit: string | null
        comparison_label: string
        comparison_value: string | null
        source: string
        competence: string | null
        target_tab: string
        tooltip: string
      }>
      signals: Array<{
        dimension: string
        indicator: string
        value: string | null
        unit: string | null
        change_3m: string | null
        yoy: string | null
        signal: string
        source: string
        competence: string | null
      }>
      charts: {
        steel: Array<{ period: string | null; period_label: string | null; consumo_aparente?: string | null; vendas_internas?: string | null }>
        industry: Array<{ period: string | null; period_label: string | null; ibge_pim?: string | null }>
        construction: Array<{ period: string | null; period_label: string | null; ibge_construcao?: string | null; cni_compra_insumos?: string | null }>
        distribution: Array<{ metric: string; value: string | null; period: string | null; period_label: string | null }>
      }
      decision_readings: Array<{ key: string; text: string; severity: string }>
    }
    steel_market?: {
      indicators: MarketIndicator[]
      series: MarketSeriesPoint[]
      decision?: {
        kpis: Array<{
          id: string
          title: string
          value_tons: string | null
          unit: string
          yoy: string | null
          source: string
          competence: string | null
          tooltip: string
          raw_unit: string | null
          normalized_unit: string | null
          scale_factor: string | null
        }>
        market_reading: Array<{
          dimension: string
          indicator: string
          value: string | null
          variation: string | null
          variation_label: string
          direction: string
          signal: string
          source: string
        }>
        balance: {
          classification: string
          demand_pressure: number
          supply_pressure: number
          components: Record<string, number>
          demand_supply_gap: string | null
          demand_supply_gap_label: string
        }
        charts: {
          demand_supply: Array<{ period: string | null; period_label: string | null; internal_sales?: string | null; consumption?: string | null; production?: string | null; imports?: string | null }>
          yoy: Array<{ period: string | null; period_label: string | null; internal_sales?: string | null; consumption?: string | null; production?: string | null; imports?: string | null }>
          import_pressure: Array<{ period: string | null; period_label: string | null; imports_index?: string | null; consumption_index?: string | null }>
          distribution: Array<{ metric: string; value: string | null; period: string | null; period_label: string | null }>
        }
        decision_readings: Array<{ key: string; text: string; severity: string }>
        quality: {
          suspect_values: Array<{ indicator: string; period: string | null; raw_value: string | null; normalized_value: string | null; rule: string }>
          unit_rules: Array<{ indicator: string; raw_unit: string | null; normalized_unit: string | null; scale_factor: string | null }>
        }
      }
    }
    prices?: {
      ptax?: {
        latest: MarketSeriesPoint
        change_period_pct: string | null
        series: MarketSeriesPoint[]
      }
      comex?: MarketComexSummary
      decision?: {
        ptax: {
          latest: {
            date: string | null
            date_label: string | null
            reference_date: string | null
            quoted_at: string | null
            bulletin_type: string | null
            raw_value: string | null
            normalized_value: string | null
            value: string | null
            source: string
            status: string
            validation_error: string | null
            ma20?: string | null
          } | null
          first: {
            reference_date: string | null
            value: string | null
          } | null
          period_change: string | null
          change_30d: string | null
          average: string | null
          series: Array<{
            date: string | null
            date_label: string | null
            reference_date: string | null
            quoted_at: string | null
            bulletin_type: string | null
            raw_value: string | null
            normalized_value: string | null
            value: string | null
            source: string
            status: string
            validation_error: string | null
            ma20?: string | null
          }>
          invalid_values: Array<Record<string, unknown>>
        }
        data_coverage: {
          requested_from: string | null
          requested_to: string | null
          available_from: string | null
          available_to: string | null
          valid_days: number
          is_partial: boolean
          message: string | null
        }
        cards: Array<{
          id: string
          title: string
          value: string | null
          unit: string
          detail: string | null
          detail_label: string
          source: string
          competence: string | null
          tooltip: string
        }>
        comex_status: { status: string; active_ncms: number; records: number; message: string }
        family_pressure: Array<Record<string, unknown>>
        fob_ptax_chart: Array<Record<string, unknown>>
        family_import_chart: Array<Record<string, unknown>>
        pressure_components: Array<{ component: string; status: string; message: string }>
        decision_readings: Array<{ key: string; text: string; severity: string }>
      }
    }
    imports?: MarketComexSummary
    construction?: {
      indicators: MarketIndicator[]
      series: MarketSeriesPoint[]
      public_works?: {
        kpis: { projects: number; investment: string | null; jobs: string | null }
        top_regions: Array<{ uf: string; projects: number; investment: string | null }>
      }
    }
    industry?: {
      indicators: MarketIndicator[]
      series: MarketSeriesPoint[]
    }
    opportunities?: {
      source: string
      kpis: { opportunities: number; high_relevance: number; total_value: string | null; regions: number }
      monthly: Array<{ period: string; period_label: string; opportunities: number }>
      top_regions: Array<{ uf: string; opportunities: number; value: string | null }>
      detail: Array<{
        date: string | null
        uf: string
        municipality: string
        agency: string
        object: string
        value: string | null
        relevance_score: number
        id: string
      }>
    }
    solar?: {
      latest_period: string
      kpis: { last_12_new_mw: string | null; last_12_installations: number; cumulative_mw: string | null }
      monthly: Array<{ period: string; period_label: string; new_mw: string | null; cumulative_mw: string | null; installations: number }>
      top_regions: Array<{ uf: string; new_mw: string | null; installations: number }>
    }
  }
  sales_regions: Array<{ canal: string; regiao: string; linhas: number; valor_total: string }>
  warnings: string[]
}

export type MarketIndicator = {
  source_key: string
  indicator_key: string
  name: string
  period: string | null
  geography: string | null
  unit: string | null
  value: string | null
}

export type MarketSeriesPoint = {
  period: string | null
  period_label: string | null
  value: string | null
}

export type MarketComexSummary = {
  latest_period: string
  kpis: { toneladas_12m: string | null; fob_usd_t: string | null; cif_proxy_usd_t: string | null; countries: number }
  monthly: Array<{ period: string; period_label: string; toneladas: string | null; fob_usd_t: string | null; cif_proxy_usd_t: string | null }>
  countries: Array<{ country: string; toneladas: string | null }>
  families: Array<{ family: string; toneladas: string | null; fob_usd_t: string | null }>
  detail: Array<{ ncm: string; family: string; country: string; toneladas: string | null; fob_usd_t: string | null; freight_usd_t: string | null }>
}

const DEFAULT_API_BASE_URL =
  window.location.hostname === '127.0.0.1' && window.location.port === '5173'
    ? 'http://127.0.0.1:8000'
    : window.location.origin
const API_BASE_URL = import.meta.env.VITE_ABR_API_BASE_URL || DEFAULT_API_BASE_URL
const ABR_API_KEY = import.meta.env.VITE_ABR_API_KEY || ''

function apiHeaders(): HeadersInit {
  return ABR_API_KEY ? { 'x-api-key': ABR_API_KEY } : {}
}

export async function fetchInternalDashboard(filters?: {
  dateFrom?: string
  dateTo?: string
  marketTab?: string
  marketDateFrom?: string
  marketDateTo?: string
}): Promise<DashboardSummary> {
  const params = new URLSearchParams()
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.dateTo) params.set('date_to', filters.dateTo)
  if (filters?.marketTab) params.set('market_tab', filters.marketTab)
  if (filters?.marketDateFrom) params.set('market_date_from', filters.marketDateFrom)
  if (filters?.marketDateTo) params.set('market_date_to', filters.marketDateTo)
  const query = params.toString()
  const response = await fetch(`${API_BASE_URL}/v1/dashboard/internal${query ? `?${query}` : ''}`, {
    credentials: 'include',
    headers: apiHeaders(),
  })

  if (!response.ok) {
    throw new Error(`API respondeu ${response.status}`)
  }

  return response.json()
}

export async function refreshDashboardData(filters?: { dateFrom?: string; dateTo?: string }) {
  const params = new URLSearchParams()
  if (filters?.dateFrom) params.set('date_from', filters.dateFrom)
  if (filters?.dateTo) params.set('date_to', filters.dateTo)
  params.set('force', 'true')
  const response = await fetch(`${API_BASE_URL}/v1/dashboard/refresh?${params.toString()}`, {
    method: 'POST',
    credentials: 'include',
    headers: apiHeaders(),
  })

  if (response.status === 401) {
    throw new Error('Sessao sem permissao para atualizar dados. Recarregue a pagina e tente novamente.')
  }

  if (!response.ok) {
    throw new Error(`API respondeu ${response.status}`)
  }

  return response.json()
}

export async function fetchDashboardRefreshStatus() {
  const response = await fetch(`${API_BASE_URL}/v1/dashboard/refresh`, {
    credentials: 'include',
    headers: apiHeaders(),
  })

  if (response.status === 401) {
    throw new Error('Sessao sem permissao para consultar a atualizacao. Recarregue a pagina e tente novamente.')
  }

  if (!response.ok) {
    throw new Error(`API respondeu ${response.status}`)
  }

  return response.json()
}
