import { useEffect, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  AlertTriangle,
  AreaChart as AreaIcon,
  BarChart3,
  Boxes,
  CalendarDays,
  CheckCircle2,
  CircleDollarSign,
  Database,
  Filter,
  Gauge,
  LineChart as LineChartIcon,
  RefreshCw,
  Search,
  SlidersHorizontal,
  TableProperties,
} from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart as ReLineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { DashboardSummary, fetchDashboardRefreshStatus, fetchInternalDashboard, refreshDashboardData } from './api'
import abrLogoWhite from './abr-logo-white.svg'

const DEFAULT_DATE_FROM = '2026-01-01'
const DEFAULT_DATE_TO = new Date().toISOString().slice(0, 10)
const BAR_LIMIT = 6
const SCATTER_LIMIT = 14
const FORECAST_WEIGHTS = [0.5, 0.3, 0.2]
const REFRESH_TERMINAL_STATUSES = new Set(['succeeded', 'partial', 'failed', 'skipped'])
const wait = (milliseconds: number) => new Promise((resolve) => window.setTimeout(resolve, milliseconds))

type IntelligenceTab =
  | 'executive'
  | 'commercial'
  | 'clients'
  | 'segments'
  | 'products'
  | 'prices'
  | 'margin'
  | 'quotes'
  | 'competition'
  | 'stock'
  | 'purchases'
  | 'forecast'
  | 'logistics'
  | 'map'
  | 'market-overview'
  | 'steel-market'
  | 'market-prices'
  | 'imports'
  | 'construction'
  | 'industry'
  | 'opportunities'
  | 'agro'
  | 'solar'
  | 'regional'
  | 'mills'
  | 'service-overview'
  | 'ranking'
  | 'sla'
  | 'orders'
  | 'deliveries'
  | 'complaints'
  | 'satisfaction'
  | 'channels'

type MacroArea = 'business' | 'market' | 'service'
type RefreshStepStatus = { label: string; status: string; error?: string | null }
type RankingView = 'retail' | 'retail-region' | 'wholesale' | 'representatives'
type RankingMetric = 'ganhas' | 'win_rate' | 'follow_up' | 'sla_5' | 'pipeline_value' | 'leads'

type AttendanceSummary = NonNullable<DashboardSummary['attendance_summary']>
type CollaboratorRankingRow = NonNullable<AttendanceSummary['ranking_colaboradores']>[number]
type RegionRankingRow = NonNullable<AttendanceSummary['ranking_regioes']>[number]
type MarketSummary = NonNullable<DashboardSummary['market_summary']>

function formatNumber(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === '') return 'Sem dados'
  const number = Number(value || 0)
  return new Intl.NumberFormat('pt-BR').format(number)
}

function money(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === '') return 'Sem dados'
  const number = Number(value || 0)
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 0,
  }).format(number)
}

function percent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'Sem dados'
  return `${Number(value).toFixed(1)}%`
}

function minutes(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'Sem dados'
  return `${Number(value).toFixed(0)} min`
}

function numericValue(value: number | string | null | undefined) {
  if (value === null || value === undefined) return 0
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  const parsed = Number(value.replace(/[^\d,-.]/g, '').replace(/\./g, '').replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : 0
}

function nullableNumericValue(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === '') return null
  const number = numericValue(value)
  return Number.isFinite(number) ? number : null
}

function isWholesale(row: { funcao?: string; regiao_polo?: string }) {
  const funcao = String(row.funcao ?? '').toUpperCase()
  const regiao = String(row.regiao_polo ?? '').toUpperCase()
  return regiao === 'ATACADO' || funcao.includes('ATACADO')
}

function isRepresentative(row: { funcao?: string }) {
  return String(row.funcao ?? '').toUpperCase().includes('REPRESENTANTE')
}

function isRetail(row: { funcao?: string; regiao_polo?: string }) {
  return !isWholesale(row) && !isRepresentative(row) && String(row.regiao_polo ?? '').toUpperCase() !== 'SEM CADASTRO'
}

function monthLabel(value: string) {
  const [year, month] = value.split('-')
  if (!year || !month) return value
  return `${month}/${year.slice(2)}`
}

function addMonths(value: string, amount: number) {
  const [year, month] = value.split('-').map(Number)
  if (!year || !month) return value
  const date = new Date(year, month - 1 + amount, 1)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}

function abbreviateLabel(value: string, maxLength = 18) {
  const normalized = value.replace(/\s+/g, ' ').trim()
  if (normalized.length <= maxLength) return normalized
  const ignored = new Set(['DE', 'DA', 'DO', 'DAS', 'DOS', 'E'])
  const words = normalized.split(' ').filter((word) => !ignored.has(word.toUpperCase()))
  const initials = words.slice(1, 4).map((word) => word[0]?.toUpperCase()).filter(Boolean).join('')
  const firstWord = words[0] ?? normalized.slice(0, maxLength - 1)
  const compact = initials ? `${firstWord} ${initials}` : firstWord
  return compact.length <= maxLength ? compact : `${normalized.slice(0, maxLength - 1)}...`
}

function cleanSegmentName(value: string) {
  return value
    .replace('Ind�strias', 'Industrias')
    .replace('Dep�sito', 'Deposito')
    .replace('N�o', 'Nao')
}

function marketNumber(value: number | string | null | undefined, maximumFractionDigits = 1) {
  const number = numericValue(value)
  return new Intl.NumberFormat('pt-BR', { maximumFractionDigits }).format(number)
}

function marketValue(value: number | string | null | undefined, unit?: string | null) {
  if (value === null || value === undefined || value === '') return 'Sem dados'
  const normalizedUnit = String(unit ?? '').trim()
  const loweredUnit = normalizedUnit.toLowerCase()
  if (normalizedUnit === '%') return percent(numericValue(value))
  if (loweredUnit === 'indice') return marketNumber(value, 2)
  if (loweredUnit.includes('us$/t')) return `US$ ${marketNumber(value, 1)}/t`
  if (loweredUnit.includes('us$')) return `US$ ${marketNumber(value, 1)}`
  if (normalizedUnit) return `${marketNumber(value, 1)} ${normalizedUnit}`
  return marketNumber(value, 1)
}

function marketSourceShortName(sourceKey: string) {
  const labels: Record<string, string> = {
    aco_brasil_estatistica_mensal: 'Aco Brasil',
    inda_estatisticas: 'INDA',
    aneel_dados_abertos: 'ANEEL',
    bcb_dolar_ptax: 'BCB',
    cni_sondagem_construcao: 'CNI Construcao',
    cni_sondagem_industrial: 'CNI Industria',
    ibge_construcao_sidra: 'IBGE Construcao',
    ibge_pim_sidra: 'IBGE PIM',
    obrasgov_projetos: 'ObrasGov',
    pncp_consulta: 'PNCP',
    world_bank_wdi: 'World Bank',
  }
  return labels[sourceKey] ?? sourceKey
}

const MACRO_AREAS: Array<{ key: MacroArea; label: string; title: string }> = [
  { key: 'business', label: 'Negocio', title: 'Inteligencia do Negocio' },
  { key: 'market', label: 'Mercado', title: 'Inteligencia de Mercado' },
  { key: 'service', label: 'Atendimento', title: 'Inteligencia de Atendimento' },
]

const TABS_BY_MACRO: Record<MacroArea, Array<{ key: IntelligenceTab; label: string }>> = {
  business: [
    { key: 'executive', label: 'Executivo' },
    { key: 'commercial', label: 'Comercial' },
    { key: 'clients', label: 'Clientes' },
    { key: 'segments', label: 'Segmentos' },
    { key: 'products', label: 'Produtos' },
    { key: 'prices', label: 'Precos' },
    { key: 'margin', label: 'Margem' },
    { key: 'quotes', label: 'Cotacoes' },
    { key: 'stock', label: 'Estoque' },
    { key: 'purchases', label: 'Compras' },
    { key: 'forecast', label: 'Forecast' },
    { key: 'logistics', label: 'Logistica' },
    { key: 'map', label: 'Mapa Comercial' },
  ],
  market: [
    { key: 'market-overview', label: 'Visao Geral' },
    { key: 'steel-market', label: 'Mercado do Aco' },
    { key: 'market-prices', label: 'Precos & Cambio' },
    { key: 'imports', label: 'Importacoes' },
    { key: 'industry', label: 'Industria' },
    { key: 'construction', label: 'Construcao' },
    { key: 'regional', label: 'Regional' },
    { key: 'competition', label: 'Concorrencia' },
    { key: 'opportunities', label: 'Oportunidades' },
    { key: 'solar', label: 'Solar' },
  ],
  service: [
    { key: 'service-overview', label: 'Visao Geral' },
    { key: 'ranking', label: 'Ranking' },
    { key: 'sla', label: 'SLA' },
    { key: 'orders', label: 'Pedidos' },
    { key: 'deliveries', label: 'Entregas' },
    { key: 'complaints', label: 'Reclamacoes' },
    { key: 'satisfaction', label: 'Satisfacao' },
    { key: 'channels', label: 'Canais' },
  ],
}

const DEFAULT_TAB_BY_MACRO: Record<MacroArea, IntelligenceTab> = {
  business: 'executive',
  market: 'market-overview',
  service: 'service-overview',
}

type ChartRow = {
  name: string
  valor_numero: number
  peso_numero: number
  receita_numero?: number
  lucro_numero?: number
  mcii_numero?: number
  linhas?: number
}

function App() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [macroArea, setMacroArea] = useState<MacroArea>('business')
  const [intelligenceTab, setIntelligenceTab] = useState<IntelligenceTab>('executive')
  const [statusFilter, setStatusFilter] = useState('todos')
  const [areaFilter, setAreaFilter] = useState('todas')
  const [dateFrom, setDateFrom] = useState(DEFAULT_DATE_FROM)
  const [dateTo, setDateTo] = useState(DEFAULT_DATE_TO)
  const [search, setSearch] = useState('')
  const [rankingView, setRankingView] = useState<RankingView>('retail')
  const [rankingMetric, setRankingMetric] = useState<RankingMetric>('ganhas')
  const [slaView, setSlaView] = useState<RankingView>('retail')
  const [slaMetric, setSlaMetric] = useState<RankingMetric>('sla_5')
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null)
  const [refreshingSources, setRefreshingSources] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setSummary(await fetchInternalDashboard({ dateFrom, dateTo }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao carregar dados')
    } finally {
      setLoading(false)
    }
  }

  const submitFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void load()
  }

  const refreshSources = async () => {
    setRefreshingSources(true)
    setRefreshMessage(null)
    setError(null)
    try {
      const payload = await refreshDashboardData({ dateFrom, dateTo })
      let job = payload?.job
      if (!job) {
        setRefreshMessage('Atualizacao de dados iniciada. Recarregando indicadores.')
        await load()
        return
      }

      setRefreshMessage('Atualizacao de dados em andamento. O dashboard sera recarregado ao terminar.')
      for (let attempt = 0; attempt < 120 && !REFRESH_TERMINAL_STATUSES.has(job.status); attempt += 1) {
        await wait(5000)
        const statusPayload = await fetchDashboardRefreshStatus()
        job = statusPayload?.current ?? statusPayload?.history?.[0] ?? job
      }

      if (!REFRESH_TERMINAL_STATUSES.has(job.status)) {
        setRefreshMessage('Atualizacao ainda em andamento. O dashboard continua usando o ultimo dado valido.')
        return
      }

      const failedSteps: RefreshStepStatus[] = Array.isArray(job.steps)
        ? job.steps.filter((step: RefreshStepStatus) => step.status === 'failed')
        : []
      if (job.status === 'failed') {
        const firstFailure = failedSteps[0]
        const detail = firstFailure
          ? `${firstFailure.label}: ${firstFailure.error || 'sem detalhe retornado'}`
          : 'Confira os logs do backend no Render.'
        throw new Error(`Atualizacao de dados falhou em ${detail}`)
      }

      await load()
      const message =
        job.status === 'partial'
          ? `Atualizacao concluida com pendencias${failedSteps.length ? `: ${failedSteps.map((step: RefreshStepStatus) => step.label).join(', ')}` : ''}. Indicadores recarregados.`
          : 'Atualizacao concluida. Indicadores recarregados.'
      setRefreshMessage(message)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao iniciar atualizacao')
    } finally {
      setRefreshingSources(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const reports = summary?.reports ?? []
  const areas = useMemo(() => Array.from(new Set(reports.map((item) => item.area))).sort(), [reports])
  const activeMacro = MACRO_AREAS.find((item) => item.key === macroArea) ?? MACRO_AREAS[0]
  const market = summary?.market_summary
  const marketAvailableTabsKey = (market?.available_tabs ?? ['market-overview']).join('|')
  const activeTabs = useMemo(() => {
    const tabs = TABS_BY_MACRO[macroArea]
    if (macroArea !== 'market') return tabs
    const available = new Set((marketAvailableTabsKey || 'market-overview').split('|').filter(Boolean))
    const filtered = tabs.filter((item) => available.has(item.key))
    return filtered.length ? filtered : tabs.filter((item) => item.key === 'market-overview')
  }, [macroArea, marketAvailableTabsKey])
  const activeTabLabel = activeTabs.find((item) => item.key === intelligenceTab)?.label ?? 'Visao'
  useEffect(() => {
    if (!activeTabs.some((item) => item.key === intelligenceTab)) {
      setIntelligenceTab(activeTabs[0]?.key ?? DEFAULT_TAB_BY_MACRO[macroArea])
    }
  }, [activeTabs, intelligenceTab, macroArea])
  const filterCopy = {
    business: {
      search: 'Buscar cliente, vendedor, produto ou relatorio',
      status: 'Todos os status',
      group: 'Todas as areas',
      options: areas,
    },
    market: {
      search: 'Buscar fonte, indicador, segmento ou produto siderurgico',
      status: 'Todos os indicadores',
      group: 'Todos os segmentos',
      options: ['Aco', 'Construcao', 'Industria', 'Agro', 'Solar', 'Importacoes', 'Usinas'],
    },
    service: {
      search: 'Buscar cliente, canal, motivo ou ocorrencia',
      status: 'Todos os atendimentos',
      group: 'Todos os canais',
      options: ['Comercial', 'Logistica', 'Telefone', 'E-mail', 'WhatsApp', 'Equipe interna'],
    },
  }[macroArea]
  const selectMacroArea = (nextMacroArea: MacroArea) => {
    setMacroArea(nextMacroArea)
    setIntelligenceTab(DEFAULT_TAB_BY_MACRO[nextMacroArea])
    setAreaFilter('todas')
    setStatusFilter('todos')
    setSearch('')
  }

  const monthlySales = (summary?.sales_summary?.monthly ?? []).map((item) => ({
    ...item,
    mes_label: monthLabel(item.mes),
    valor_numero: Number(item.valor_total),
    receita_numero: Number(item.receita_liquida ?? 0),
    lucro_numero: Number(item.lucro_bruto ?? 0),
    mcii_numero: Number(item.margem_contribuicao ?? 0),
    peso_numero: Number(item.peso_total),
    toneladas_numero: Number(item.peso_total) / 1000,
    perdido_numero: Number(item.valor_perdido ?? 0),
    notas_numero: Number(item.notas_fiscais ?? 0),
    clientes_numero: Number(item.clientes ?? 0),
    ticket_medio_numero: Number(item.notas_fiscais ?? 0) ? Number(item.receita_liquida ?? 0) / Number(item.notas_fiscais ?? 0) : 0,
  }))
  const familyRows: ChartRow[] = (summary?.sales_summary?.families ?? []).map((item) => ({
    name: item.familia,
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
    linhas: item.linhas,
  })).sort((a, b) => b.peso_numero - a.peso_numero)
  const clientAbcRows = (summary?.sales_summary?.clients_abc ?? []).map((item) => ({
    name: item.cliente,
    shortName: abbreviateLabel(item.cliente, 16),
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
  }))
  const clientDeclineRows = (summary?.sales_summary?.clients_decline ?? []).map((item) => ({
    name: item.cliente,
    shortName: abbreviateLabel(item.cliente, 16),
    queda_numero: Number(item.queda_peso),
  }))
  const segmentRows: ChartRow[] = (summary?.sales_summary?.segments ?? [])
    .map((item) => ({
      name: cleanSegmentName(item.segmento),
      valor_numero: Number(item.valor_total),
      peso_numero: Number(item.peso_total),
      receita_numero: Number(item.receita_liquida),
      lucro_numero: Number(item.lucro_bruto),
      mcii_numero: Number(item.margem_contribuicao ?? 0),
      linhas: item.linhas,
    }))
    .sort((a, b) => b.peso_numero - a.peso_numero)
  const topSegments = segmentRows.slice(0, 4).map((item) => item.name)
  const segmentMonthly = Array.from(
    (summary?.sales_summary?.segment_monthly ?? []).reduce((index, item) => {
      const segmentName = cleanSegmentName(item.segmento)
      if (!topSegments.includes(segmentName)) return index
      const mes = monthLabel(item.mes)
      const row = index.get(mes) ?? { mes_label: mes }
      row[segmentName] = Number(item.peso_total) / 1000
      index.set(mes, row)
      return index
    }, new Map<string, Record<string, number | string>>()).values(),
  )
  const itemRows: ChartRow[] = (summary?.sales_summary?.items ?? []).map((item) => ({
    name: item.produto,
    shortName: abbreviateLabel(item.produto, 18),
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
    linhas: item.linhas,
  })).sort((a, b) => b.peso_numero - a.peso_numero)
  const itemDeclineRows = (summary?.sales_summary?.item_decline ?? []).map((item) => ({
    name: item.produto,
    shortName: abbreviateLabel(item.produto, 18),
    queda_numero: Number(item.queda_peso),
  })).sort((a, b) => b.queda_numero - a.queda_numero)
  const familySegmentRows: ChartRow[] = (summary?.sales_summary?.family_segments ?? []).map((item) => ({
    name: `${item.familia} / ${cleanSegmentName(item.segmento)}`,
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
  })).sort((a, b) => b.peso_numero - a.peso_numero)
  const priceStatsRows = (summary?.sales_summary?.price_stats ?? []).map((item) => ({
    name: item.familia,
    min_numero: Number(item.min_preco_kg),
    avg_numero: Number(item.avg_preco_kg),
    max_numero: Number(item.max_preco_kg),
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
  }))
  const priceOutlierRows = (summary?.sales_summary?.price_outliers ?? []).map((item) => ({
    name: item.produto,
    shortName: abbreviateLabel(item.produto, 18),
    familia: item.familia,
    preco_numero: Number(item.preco_kg),
    media_familia_numero: Number(item.media_familia_kg),
    desvio_numero: Number(item.desvio_pct),
    peso_numero: Number(item.peso_total),
  }))
  const priceMonthly = (summary?.sales_summary?.price_monthly ?? []).map((item) => ({
    mes_label: monthLabel(item.mes),
    min_numero: Number(item.min_preco_kg),
    avg_numero: Number(item.avg_preco_kg),
    max_numero: Number(item.max_preco_kg),
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
  }))
  const marginMonthly = (summary?.sales_summary?.margin_monthly ?? []).map((item) => ({
    mes_label: monthLabel(item.mes),
    receita_numero: Number(item.receita_liquida),
    lucro_numero: Number(item.lucro_bruto),
    mcii_numero: Number(item.margem_contribuicao ?? item.lucro_bruto),
    peso_numero: Number(item.peso_total),
    preco_venda_kg_numero: Number(item.peso_total) ? Number(item.receita_liquida) / Number(item.peso_total) : 0,
    mcii_kg_numero: Number(item.peso_total) ? Number(item.margem_contribuicao ?? item.lucro_bruto) / Number(item.peso_total) : 0,
    margem_numero: Number(item.receita_liquida) ? (Number(item.margem_contribuicao ?? item.lucro_bruto) / Number(item.receita_liquida)) * 100 : 0,
  }))
  const marginClientRows = (summary?.sales_summary?.margin_clients ?? []).map((item) => ({
    name: item.cliente,
    shortName: abbreviateLabel(item.cliente, 16),
    receita_numero: Number(item.receita_liquida),
    lucro_numero: Number(item.lucro_bruto),
    mcii_numero: Number(item.margem_contribuicao ?? item.lucro_bruto),
    peso_numero: Number(item.peso_total),
    margem_kg_numero: Number(item.peso_total) ? Number(item.margem_contribuicao ?? item.lucro_bruto) / Number(item.peso_total) : 0,
    margem_numero: Number(item.receita_liquida) ? (Number(item.margem_contribuicao ?? item.lucro_bruto) / Number(item.receita_liquida)) * 100 : 0,
  })).sort((a, b) => b.mcii_numero - a.mcii_numero)
  const lossRows = (summary?.sales_summary?.losses ?? []).map((item) => ({
    name: item.motivo,
    valor_numero: Number(item.valor_perdido),
    linhas: item.linhas,
  }))
  const sellerRows = (summary?.sales_summary?.sellers ?? []).map((item) => ({
    name: item.vendedor,
    valor_numero: Number(item.valor_total),
    perdido_numero: Number(item.valor_perdido),
    peso_numero: Number(item.peso_total),
    conversao_numero: Number(item.valor_total) + Number(item.valor_perdido) > 0 ? (Number(item.valor_total) / (Number(item.valor_total) + Number(item.valor_perdido))) * 100 : 0,
  }))
  const quoteMonthly = (summary?.sales_summary?.quote_monthly ?? []).map((item) => ({
    mes_label: monthLabel(item.mes),
    kg_cotado_numero: Number(item.kg_cotado),
    kg_vendido_numero: Number(item.kg_vendido),
    kg_perdido_numero: Number(item.kg_perdido),
    valor_cotado_numero: Number(item.valor_cotado),
    valor_vendido_numero: Number(item.valor_vendido),
    valor_perdido_numero: Number(item.valor_perdido),
    conversao_numero: Number(item.kg_cotado) ? (Number(item.kg_vendido) / Number(item.kg_cotado)) * 100 : 0,
  }))
  const quoteSellerRows = (summary?.sales_summary?.quote_sellers ?? []).map((item) => ({
    name: item.vendedor,
    shortName: abbreviateLabel(item.vendedor, 16),
    kg_cotado_numero: Number(item.kg_cotado),
    kg_vendido_numero: Number(item.kg_vendido),
    kg_perdido_numero: Number(item.kg_perdido),
    valor_vendido_numero: Number(item.valor_vendido),
    valor_perdido_numero: Number(item.valor_perdido),
    conversao_numero: Number(item.kg_cotado) ? (Number(item.kg_vendido) / Number(item.kg_cotado)) * 100 : 0,
  }))
  const quoteFunnelRows = (summary?.sales_summary?.quote_funnel ?? []).map((item) => ({
    name: item.etapa,
    toneladas_numero: Number(item.kg_total) / 1000,
  }))
  const cityRows = (summary?.sales_summary?.cities ?? []).map((item) => ({
    name: `${item.cidade}/${item.estado}`,
    shortName: abbreviateLabel(`${item.cidade}/${item.estado}`, 16),
    cidade: item.cidade,
    clientes: item.clientes,
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
  }))
  const totalSalesWeight = Number(summary?.sales_summary?.peso_total ?? 0)
  const sortedMonthlySales = [...monthlySales].sort((a, b) => String(a.mes).localeCompare(String(b.mes)))
  const recentForecastBase = sortedMonthlySales.slice(-3)
  const activeForecastWeights = FORECAST_WEIGHTS.slice(0, recentForecastBase.length)
  const activeForecastWeightTotal = activeForecastWeights.reduce((sum, weight) => sum + weight, 0) || 1
  const forecastBaseKg = recentForecastBase.length
    ? recentForecastBase
        .slice()
        .reverse()
        .reduce((sum, item, index) => sum + item.peso_numero * ((activeForecastWeights[index] ?? 0) / activeForecastWeightTotal), 0)
    : 0
  const lastMonthKey = sortedMonthlySales.at(-1)?.mes
  const nextMonthKey = lastMonthKey ? addMonths(lastMonthKey, 1).split('-')[1] : null
  const averageMonthlyKg = sortedMonthlySales.length ? sortedMonthlySales.reduce((sum, item) => sum + item.peso_numero, 0) / sortedMonthlySales.length : 0
  const nextMonthHistory = nextMonthKey ? sortedMonthlySales.filter((item) => String(item.mes).split('-')[1] === nextMonthKey) : []
  const nextMonthAverageKg = nextMonthHistory.length ? nextMonthHistory.reduce((sum, item) => sum + item.peso_numero, 0) / nextMonthHistory.length : averageMonthlyKg
  const seasonalFactor = averageMonthlyKg ? nextMonthAverageKg / averageMonthlyKg : 1
  const forecastNextKg = forecastBaseKg * seasonalFactor
  const currentMonthKg = sortedMonthlySales.at(-1)?.peso_numero ?? 0
  const forecastChange = currentMonthKg ? ((forecastNextKg - currentMonthKg) / currentMonthKg) * 100 : 0
  const forecastMonths = lastMonthKey
    ? [1, 2, 3].map((offset) => ({
        mes: addMonths(lastMonthKey, offset),
        mes_label: monthLabel(addMonths(lastMonthKey, offset)),
        forecast_toneladas: forecastNextKg / 1000,
      }))
    : []
  const realVsForecastRows = [
    ...sortedMonthlySales.slice(-24).map((item) => ({
      mes_label: item.mes_label,
      real_toneladas: item.peso_numero / 1000,
      forecast_toneladas: null as number | null,
    })),
    ...forecastMonths.map((item) => ({
      mes_label: item.mes_label,
      real_toneladas: null as number | null,
      forecast_toneladas: item.forecast_toneladas,
    })),
  ]
  const demandTrendRows = sortedMonthlySales.slice(-24).map((item, index, rows) => {
    const base = rows.slice(Math.max(0, index - 2), index + 1)
    return {
      mes_label: item.mes_label,
      toneladas: item.peso_numero / 1000,
      media_movel: base.reduce((sum, row) => sum + row.peso_numero, 0) / base.length / 1000,
    }
  })
  const seasonalityRows = Object.values(sortedMonthlySales.reduce((index, item) => {
    const month = String(item.mes).split('-')[1] ?? '00'
    const row = index[month] ?? { mes: month, label: month, total: 0, count: 0 }
    row.total += item.peso_numero / 1000
    row.count += 1
    index[month] = row
    return index
  }, {} as Record<string, { mes: string; label: string; total: number; count: number }>))
    .sort((a, b) => a.mes.localeCompare(b.mes))
    .map((item) => ({ label: item.label, toneladas: item.count ? item.total / item.count : 0 }))
  const forecastFamilyRows = familyRows.slice(0, BAR_LIMIT).map((item) => ({
    name: item.name,
    forecast_toneladas: totalSalesWeight ? (forecastNextKg * item.peso_numero) / totalSalesWeight / 1000 : 0,
  }))
  const forecastSegmentRows = segmentRows.slice(0, BAR_LIMIT).map((item) => ({
    name: item.name,
    forecast_toneladas: totalSalesWeight ? (forecastNextKg * item.peso_numero) / totalSalesWeight / 1000 : 0,
  }))
  const forecastCityRows = cityRows
    .slice()
    .sort((a, b) => b.peso_numero - a.peso_numero)
    .slice(0, BAR_LIMIT)
    .map((item) => ({
      name: item.shortName,
      fullName: item.name,
      forecast_toneladas: totalSalesWeight ? (forecastNextKg * item.peso_numero) / totalSalesWeight / 1000 : 0,
    }))
  const quotedKg = quoteMonthly.reduce((sum, item) => sum + item.kg_cotado_numero, 0)
  const attendance = summary?.attendance_summary
  const attendanceKpis = attendance?.kpis
  const attendanceSummaryRows = attendance?.summary_rows ?? []
  const attendanceHasGranularData = Boolean(attendance?.data_available && attendanceKpis)
  const attendanceCollaboratorRanking = attendance?.ranking_colaboradores ?? []
  const attendanceRegionRanking = attendance?.ranking_regioes ?? []
  const unmappedAttendanceCollaborators = attendance?.unmapped_collaborators ?? []
  const attendanceDaily = (attendance?.daily ?? []).map((item) => ({
    ...item,
    data_label: item.data ? new Date(`${item.data}T00:00:00`).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : 'Sem data',
    pipeline_numero: Number(item.pipeline_valor),
  }))
  const attendanceOrigins = attendance?.origins ?? []
  const rankingViewOptions: Array<{ key: RankingView; label: string }> = [
    { key: 'retail', label: '1. Varejo' },
    { key: 'retail-region', label: '2. Varejo por região' },
    { key: 'wholesale', label: '3. Atacado' },
    { key: 'representatives', label: '4. Representantes fixos' },
  ]
  const rankingMetricOptions: Array<{ key: RankingMetric; label: string }> = [
    { key: 'ganhas', label: 'Vendas ganhas' },
    { key: 'win_rate', label: 'Win rate' },
    { key: 'follow_up', label: 'Follow-up' },
    { key: 'sla_5', label: '1a acao ate 5 min' },
    { key: 'pipeline_value', label: 'Valor em pipeline' },
    { key: 'leads', label: 'Leads atendidos' },
  ]
  const rankingMetricValue = (item: CollaboratorRankingRow | RegionRankingRow, metric: RankingMetric) => {
    if (metric === 'win_rate') return Number(item.win_rate ?? -1)
    if (metric === 'follow_up') return Number(item.follow_up_cobertura ?? -1)
    if (metric === 'sla_5') return Number(item.sla_5_min ?? -1)
    if (metric === 'pipeline_value') return numericValue(item.pipeline_aberto_valor)
    return Number(item[metric] ?? 0)
  }
  const sortRankingRows = <T extends CollaboratorRankingRow | RegionRankingRow>(rows: T[], metric: RankingMetric = rankingMetric) =>
    rows.slice().sort((a, b) => {
      const primary = rankingMetricValue(b, metric) - rankingMetricValue(a, metric)
      if (primary !== 0) return primary
      return Number(b.ganhas ?? 0) - Number(a.ganhas ?? 0)
    })
  const retailCollaborators = attendanceCollaboratorRanking.filter(isRetail)
  const wholesaleCollaborators = attendanceCollaboratorRanking.filter(isWholesale)
  const representativeCollaborators = attendanceCollaboratorRanking.filter(isRepresentative)
  const retailRegions = attendanceRegionRanking.filter((item) => isRetail({ regiao_polo: item.regiao_polo }))
  const selectedCollaboratorRanking =
    rankingView === 'wholesale'
      ? sortRankingRows(wholesaleCollaborators)
      : rankingView === 'representatives'
        ? sortRankingRows(representativeCollaborators)
        : sortRankingRows(retailCollaborators)
  const selectedRegionRanking = sortRankingRows(retailRegions)
  const rankingTitle = rankingViewOptions.find((item) => item.key === rankingView)?.label.replace(/^\d+\.\s*/, '') ?? 'Ranking'
  const highlightRows: Array<CollaboratorRankingRow | RegionRankingRow> =
    rankingView === 'retail-region' ? selectedRegionRanking : selectedCollaboratorRanking
  const rankingRowsCount = highlightRows.length
  const bestBy = (metric: RankingMetric) => sortRankingRows(highlightRows).sort((a, b) => rankingMetricValue(b, metric) - rankingMetricValue(a, metric))[0]
  const bestWin = bestBy('win_rate')
  const bestFollow = bestBy('follow_up')
  const bestSla = bestBy('sla_5')
  const bestPipeline = bestBy('pipeline_value')
  const highlightName = (item: CollaboratorRankingRow | RegionRankingRow | undefined) =>
    item ? ('nome' in item ? item.nome : item.regiao_polo) : 'Sem dados'
  const highlightCards = [
    {
      label: 'Maior venda ganha',
      name: highlightName(bestWin),
      value: bestWin && bestWin.win_rate !== null ? percent(bestWin.win_rate) : 'Faltam eventos',
    },
    {
      label: 'Melhor follow-up',
      name: highlightName(bestFollow),
      value: bestFollow && bestFollow.follow_up_cobertura !== null ? percent(bestFollow.follow_up_cobertura) : 'Faltam tarefas',
    },
    {
      label: 'Primeira acao mais rapida',
      name: highlightName(bestSla),
      value: bestSla && bestSla.sla_5_min !== null ? percent(bestSla.sla_5_min) : 'Aguardando eventos',
    },
    {
      label: 'Maior pipeline aberto',
      name: highlightName(bestPipeline),
      value: bestPipeline ? money(bestPipeline.pipeline_aberto_valor) : 'Sem pipeline',
    },
  ]
  const slaMetricOptions: Array<{ key: RankingMetric; label: string }> = [
    { key: 'sla_5', label: '1a acao ate 5 min' },
    { key: 'follow_up', label: 'Follow-up' },
    { key: 'leads', label: 'Leads atendidos' },
    { key: 'win_rate', label: 'Win rate' },
    { key: 'ganhas', label: 'Vendas ganhas' },
  ]
  const selectedSlaCollaborators =
    slaView === 'wholesale'
      ? sortRankingRows(wholesaleCollaborators, slaMetric)
      : slaView === 'representatives'
        ? sortRankingRows(representativeCollaborators, slaMetric)
        : sortRankingRows(retailCollaborators, slaMetric)
  const selectedSlaRegions = sortRankingRows(retailRegions, slaMetric)
  const slaTitle = rankingViewOptions.find((item) => item.key === slaView)?.label.replace(/^\d+\.\s*/, '') ?? 'SLA'
  const slaHighlightRows: Array<CollaboratorRankingRow | RegionRankingRow> =
    slaView === 'retail-region' ? selectedSlaRegions : selectedSlaCollaborators
  const slaRowsCount = slaHighlightRows.length
  const slaBestBy = (metric: RankingMetric) => sortRankingRows(slaHighlightRows, metric)[0]
  const bestSlaFast = slaBestBy('sla_5')
  const bestSlaFollow = slaBestBy('follow_up')
  const bestSlaVolume = slaBestBy('leads')
  const bestSlaWin = slaBestBy('win_rate')
  const slaHighlightCards = [
    {
      label: 'Mais rapido na 1a acao',
      name: highlightName(bestSlaFast),
      value: bestSlaFast && bestSlaFast.sla_5_min !== null ? percent(bestSlaFast.sla_5_min) : 'Aguardando eventos',
    },
    {
      label: 'Melhor follow-up',
      name: highlightName(bestSlaFollow),
      value: bestSlaFollow && bestSlaFollow.follow_up_cobertura !== null ? percent(bestSlaFollow.follow_up_cobertura) : 'Faltam tarefas',
    },
    {
      label: 'Maior volume atendido',
      name: highlightName(bestSlaVolume),
      value: bestSlaVolume ? `${formatNumber(bestSlaVolume.leads)} leads` : 'Sem leads',
    },
    {
      label: 'Melhor conversao',
      name: highlightName(bestSlaWin),
      value: bestSlaWin && bestSlaWin.win_rate !== null ? percent(bestSlaWin.win_rate) : 'Sem conversao',
    },
  ]
  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div>
            <span className="eyebrow">ABR Intelligence</span>
            <h1>{activeMacro.title}</h1>
            <p>Dados do negocio, movimentos do mercado e experiencia do cliente em uma unica visao.</p>
          </div>
        </div>
        <div className="topbar-actions">
          <div className="brand-mark">
            <img src={abrLogoWhite} alt="Grupo ABR" />
          </div>
          <div className="header-controls">
            <div className="macro-switch" aria-label="Macroareas da plataforma">
              {MACRO_AREAS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={macroArea === item.key ? 'macro-pill active' : 'macro-pill'}
                  onClick={() => selectMacroArea(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="header-status">
              <button
                className="icon-button"
                onClick={refreshSources}
                disabled={refreshingSources}
                title="Atualizar dados das fontes"
                type="button"
              >
                <RefreshCw size={17} className={refreshingSources ? 'spin' : ''} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <form className="toolbar" aria-label="Filtros do dashboard" onSubmit={submitFilters}>
        <div className="control search-control">
          <Search size={16} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={filterCopy.search} />
        </div>
        <label className="control date-control">
          <CalendarDays size={16} />
          <span>De</span>
          <input type="date" value={dateFrom} max={dateTo} onChange={(event) => setDateFrom(event.target.value)} />
        </label>
        <label className="control date-control">
          <CalendarDays size={16} />
          <span>Ate</span>
          <input type="date" value={dateTo} min={dateFrom} onChange={(event) => setDateTo(event.target.value)} />
        </label>
        <label className="control">
          <Filter size={16} />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="todos">{filterCopy.status}</option>
            {macroArea === 'business' ? (
              <>
                <option value="validated">Validados</option>
                <option value="validated_empty">Sem registro</option>
                <option value="deprioritized">Fora da prioridade</option>
              </>
            ) : (
              <>
                <option value="active">Ativos</option>
                <option value="attention">Pontos de atencao</option>
                <option value="resolved">Resolvidos</option>
              </>
            )}
          </select>
        </label>
        <label className="control">
          <SlidersHorizontal size={16} />
          <select value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}>
            <option value="todas">{filterCopy.group}</option>
            {filterCopy.options.map((option) => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button className="filter-button" type="submit" disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
          Aplicar
        </button>
      </form>

      {error && (
        <section className="notice error">
          <AlertTriangle size={18} />
          <span>{error}. Confira se o backend esta rodando e se o deploy terminou.</span>
        </section>
      )}

      {refreshMessage && (
        <section className="notice">
          <RefreshCw size={18} />
          <span>{refreshMessage}</span>
        </section>
      )}

      {summary?.warnings.map((warning) => (
        <section className="notice" key={warning}>
          <AlertTriangle size={18} />
          <span>{warning}</span>
        </section>
      ))}

      <nav className="tabs intelligence-tabs" aria-label={`Dashboards de ${activeMacro.label}`}>
        {activeTabs.map((item) => (
          <button key={item.key} className={intelligenceTab === item.key ? 'active' : ''} onClick={() => setIntelligenceTab(item.key)}>
            {item.label}
          </button>
        ))}
      </nav>

      {intelligenceTab === 'executive' && (
        <>
          <section className="kpi-grid">
            <Kpi title="Valor total" displayValue={money(summary?.sales_summary?.valor_total)} detail={`${formatNumber(summary?.sales_summary?.linhas)} vendas por item`} icon={<CircleDollarSign />} />
            <Kpi title="Receita liquida" displayValue={money(summary?.sales_summary?.receita_liquida)} detail="Periodo filtrado" icon={<BarChart3 />} />
            <Kpi title="Lucro bruto" displayValue={money(summary?.sales_summary?.lucro_bruto)} detail={`${summary?.kpis.reports_validated ?? 0} relatorios validados`} icon={<LineChartIcon />} />
            <Kpi title="Toneladas vendidas" displayValue={`${formatNumber(Number(summary?.sales_summary?.peso_total ?? 0) / 1000)} t`} detail={`${formatNumber(summary?.sales_summary?.clientes)} clientes distintos`} icon={<Boxes />} />
          </section>

          <section className="dashboard-grid">
            <Panel title="Toneladas vendidas mes a mes" icon={<LineChartIcon size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <ReLineChart data={monthlySales}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Toneladas']} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Line type="monotone" dataKey="toneladas_numero" name="Toneladas vendidas" stroke="#253575" strokeWidth={3} dot={{ r: 3 }} />
                  </ReLineChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Faturamento mes a mes" icon={<CircleDollarSign size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <ReLineChart data={monthlySales}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                    <Tooltip formatter={(value, name) => [money(String(value)), name]} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Line type="monotone" dataKey="valor_numero" name="Faturamento" stroke="#F18800" strokeWidth={3} dot={{ r: 3 }} />
                  </ReLineChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Receita e margem por mes" icon={<BarChart3 size={17} />} wide>
              <ChartFrame>
                <ResponsiveContainer>
                  <ComposedChart data={monthlySales}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis yAxisId="left" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                    <YAxis yAxisId="right" orientation="right" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                    <Tooltip formatter={(value, name) => [money(String(value)), name]} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Bar yAxisId="left" dataKey="receita_numero" name="Receita liquida" fill="#253575" radius={[5, 5, 0, 0]} />
                    <Line yAxisId="right" type="monotone" dataKey="mcii_numero" name="MC" stroke="#F18800" strokeWidth={3} dot={{ r: 3 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Preco medio R$/kg" icon={<LineChartIcon size={17} />} wide>
              <ChartFrame>
                <ResponsiveContainer>
                  <ReLineChart data={monthlySales.map((item) => ({ ...item, preco_numero: item.peso_numero ? item.receita_numero / item.peso_numero : 0 }))}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                    <Tooltip formatter={(value, name) => [money(String(value)), name]} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Line type="monotone" dataKey="preco_numero" name="Preço médio R$/kg" stroke="#12805C" strokeWidth={3} dot={{ r: 3 }} />
                  </ReLineChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>
          </section>
        </>
      )}

      {intelligenceTab === 'commercial' && (
        <>
          <section className="kpi-grid sales-kpis">
            <Kpi title="Valor total" displayValue={money(summary?.sales_summary?.valor_total)} detail={`${formatNumber(summary?.sales_summary?.linhas)} linhas`} icon={<CircleDollarSign />} />
            <Kpi title="Receita liquida" displayValue={money(summary?.sales_summary?.receita_liquida)} detail="Base de venda por item" icon={<BarChart3 />} />
            <Kpi title="Lucro bruto" displayValue={money(summary?.sales_summary?.lucro_bruto)} detail="Margem antes dos rateios" icon={<LineChartIcon />} />
            <Kpi title="Toneladas vendidas" displayValue={`${formatNumber(Number(summary?.sales_summary?.peso_total ?? 0) / 1000)} t`} detail={`${money(summary?.sales_summary?.preco_medio_kg)} por kg`} icon={<Boxes />} />
            <Kpi title="Clientes" value={summary?.sales_summary?.clientes} detail="Clientes distintos no periodo" icon={<CheckCircle2 />} />
            <Kpi title="Itens" value={summary?.sales_summary?.itens} detail="Itens distintos vendidos" icon={<TableProperties />} />
          </section>

          <section className="dashboard-grid">
            <Panel title="Notas, ticket medio e clientes por mes" icon={<BarChart3 size={17} />} wide>
              <ChartFrame>
                <ResponsiveContainer>
                  <BarChart data={monthlySales}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis yAxisId="count" allowDecimals={false} tickFormatter={(value) => formatNumber(value)} />
                    <YAxis yAxisId="ticket" orientation="right" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                    <Tooltip
                      formatter={(value, name) => [
                        name === 'Ticket médio' ? money(String(value)) : formatNumber(String(value)),
                        name,
                      ]}
                    />
                    <Legend verticalAlign="bottom" height={24} />
                    <Bar yAxisId="count" dataKey="notas_numero" name="Notas fiscais" fill="#253575" radius={[5, 5, 0, 0]} />
                    <Bar yAxisId="ticket" dataKey="ticket_medio_numero" name="Ticket médio" fill="#F18800" radius={[5, 5, 0, 0]} />
                    <Bar yAxisId="count" dataKey="clientes_numero" name="Clientes atendidos" fill="#12805C" radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Top familias por valor" icon={<CircleDollarSign size={17} />} wide>
              <SupportDetails title="Ver ranking de familias">
                <DataTable
                  columns={['Familia', 'Linhas', 'Valor total', 'Peso total']}
                  rows={(summary?.sales_summary?.families ?? []).map((item) => [
                    item.familia,
                    formatNumber(item.linhas),
                    money(item.valor_total),
                    `${formatNumber(item.peso_total)} kg`,
                  ])}
                  empty="Sem resumo comercial em cache para este periodo."
                />
              </SupportDetails>
            </Panel>

            <Panel title="Vendas por canal e regiao" icon={<CircleDollarSign size={17} />} wide>
              <DataTable
                columns={['Canal', 'Regiao', 'Linhas', 'Valor total']}
                rows={(summary?.sales_regions ?? []).map((item) => [
                  item.canal,
                  item.regiao,
                  formatNumber(item.linhas),
                  money(item.valor_total),
                ])}
                empty="Resumo regional fica fora da abertura para manter o dashboard rapido."
              />
            </Panel>
          </section>
        </>
      )}

      {intelligenceTab === 'clients' && (
        <section className="dashboard-grid">
          <Panel title="Curva ABC" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={clientAbcRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 94 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="shortName" width={112} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'Valor total']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <Bar dataKey="valor_numero" fill="#253575" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Principais clientes em queda" icon={<AlertTriangle size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={clientDeclineRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 94 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="category" dataKey="shortName" width={112} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Queda']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <Bar dataKey={(row) => row.queda_numero / 1000} fill="#B42318" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

            <Panel title="Recência, frequência e valor do cliente" icon={<CheckCircle2 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={summary?.sales_summary?.rfm_segments ?? []}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="segmento" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="total" fill="#12805C" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Clientes por dias desde ultima compra" icon={<LineChartIcon size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={summary?.sales_summary?.recency_buckets ?? []}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="faixa" />
                  <YAxis allowDecimals={false} />
                  <Tooltip />
                  <Bar dataKey="clientes" fill="#F18800" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'segments' && (
        <section className="dashboard-grid">
          <Panel title="Segmento x toneladas" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={segmentRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Toneladas']} />
                  <Bar dataKey={(row) => row.peso_numero / 1000} fill="#253575" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Faturamento por segmento" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={segmentRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'Faturamento']} />
                  <Bar dataKey="valor_numero" fill="#F18800" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Evolucao mensal por segmento" icon={<LineChartIcon size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={segmentMonthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <Tooltip formatter={(value, name) => [`${formatNumber(String(value))} t`, name]} />
                  <Legend verticalAlign="bottom" height={24} iconType="line" />
                  {topSegments.map((segment, index) => (
                    <Line key={segment} type="monotone" dataKey={segment} name={segment} stroke={['#253575', '#F18800', '#12805C', '#B42318'][index]} strokeWidth={2.5} dot={{ r: 2 }} />
                  ))}
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Preco/kg por segmento" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={segmentRows.slice(0, BAR_LIMIT).map((item) => ({ ...item, preco_numero: item.peso_numero ? (item.receita_numero ?? 0) / item.peso_numero : 0 }))} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'R$/kg']} />
                  <Bar dataKey="preco_numero" fill="#12805C" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="MC por segmento" icon={<AreaIcon size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={[...segmentRows].sort((a, b) => (b.mcii_numero ?? 0) - (a.mcii_numero ?? 0)).slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'MC']} />
                  <Bar dataKey="mcii_numero" fill="#6B7280" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="MC/kg por segmento" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={segmentRows.map((item) => ({ ...item, mc_kg_numero: item.peso_numero ? (item.mcii_numero ?? 0) / item.peso_numero : 0 })).sort((a, b) => b.mc_kg_numero - a.mc_kg_numero).slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'MC/kg']} />
                  <Bar dataKey="mc_kg_numero" fill="#253575" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'products' && (
        <section className="dashboard-grid">
          <Panel title="Familia x toneladas" icon={<Boxes size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={familyRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Toneladas']} />
                  <Bar dataKey={(row) => row.peso_numero / 1000} fill="#253575" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Top SKU" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={itemRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="category" dataKey="shortName" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Toneladas']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <Bar dataKey={(row) => row.peso_numero / 1000} fill="#F18800" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="SKU em queda" icon={<AlertTriangle size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={itemDeclineRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="category" dataKey="shortName" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Queda em toneladas']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <Bar dataKey={(row) => row.queda_numero / 1000} fill="#B42318" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Familia x segmento" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={familySegmentRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Toneladas']} />
                  <Bar dataKey={(row) => row.peso_numero / 1000} fill="#12805C" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'prices' && (
        <section className="dashboard-grid">
          <Panel title="Preco medio R$/kg" icon={<LineChartIcon size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={priceMonthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <Tooltip formatter={(value, name) => [money(String(value)), name]} />
                  <Legend verticalAlign="bottom" height={24} />
                  <Line type="monotone" dataKey="avg_numero" name="Preço médio R$/kg" stroke="#253575" strokeWidth={3} dot={{ r: 3 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Minimo x medio x maximo" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={priceMonthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <Tooltip formatter={(value, name) => [money(String(value)), name]} />
                  <Legend verticalAlign="bottom" height={24} />
                  <Line type="monotone" dataKey="min_numero" name="Mínimo R$/kg" stroke="#8EA0D8" strokeWidth={2} dot={{ r: 2 }} />
                  <Line type="monotone" dataKey="avg_numero" name="Médio R$/kg" stroke="#253575" strokeWidth={3} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="max_numero" name="Máximo R$/kg" stroke="#F18800" strokeWidth={2} dot={{ r: 2 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Preco x toneladas" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <ScatterChart margin={{ top: 12, right: 18, bottom: 12, left: 6 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" dataKey={(row) => row.peso_numero / 1000} name="Toneladas" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="number" dataKey="avg_numero" name="R$/kg" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    formatter={(value, name) => [name === 'Toneladas' ? `${formatNumber(String(value))} t` : money(String(value)), name]}
                    labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''}
                  />
                  <Scatter data={priceStatsRows.slice(0, SCATTER_LIMIT)} fill="#12805C" />
                </ScatterChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Outliers comerciais" icon={<AlertTriangle size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={priceOutlierRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${Number(value).toFixed(0)}%`} />
                  <YAxis type="category" dataKey="shortName" width={120} interval={0} tickMargin={6} />
                  <Tooltip
                    formatter={(value, name) => [name === 'desvio_numero' ? `${Number(value).toFixed(2)}%` : money(String(value)), name === 'desvio_numero' ? 'Desvio vs familia' : 'R$/kg']}
                    labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''}
                  />
                  <Bar dataKey="desvio_numero" fill="#B42318" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'margin' && (
        <section className="dashboard-grid">
          <Panel title="Preço de venda e margem por mês" icon={<AreaIcon size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <ComposedChart data={marginMonthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis yAxisId="mc" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis yAxisId="percent" orientation="right" tickFormatter={(value) => `${Number(value).toFixed(0)}%`} />
                  <YAxis yAxisId="kg" hide />
                  <Tooltip
                    formatter={(value, name) => {
                      if (name === 'MCII %') return [`${Number(value).toFixed(2)}%`, name]
                      if (name === 'Preço venda/kg' || name === 'MCII/kg') return [money(String(value)), name]
                      return [money(String(value)), name]
                    }}
                  />
                  <Legend verticalAlign="bottom" height={24} />
                  <Bar yAxisId="mc" dataKey="mcii_numero" name="MCII R$" fill="#253575" radius={[5, 5, 0, 0]} />
                  <Line yAxisId="percent" type="monotone" dataKey="margem_numero" name="MCII %" stroke="#F18800" strokeWidth={3} dot={{ r: 3 }} />
                  <Line yAxisId="kg" type="monotone" dataKey="preco_venda_kg_numero" name="Preço venda/kg" stroke="#12805C" strokeWidth={2.5} dot={{ r: 2 }} />
                  <Line yAxisId="kg" type="monotone" dataKey="mcii_kg_numero" name="MCII/kg" stroke="#6B7280" strokeWidth={2.5} dot={{ r: 2 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="MCII/kg por cliente" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={marginClientRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="shortName" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'MCII/kg']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <Bar dataKey="margem_kg_numero" fill="#12805C" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Margem percentual por cliente" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={[...marginClientRows].sort((a, b) => b.margem_numero - a.margem_numero).slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${Number(value).toFixed(1)}%`} />
                  <YAxis type="category" dataKey="shortName" width={120} interval={0} tickMargin={6} />
                  <Tooltip
                    formatter={(value) => [`${Number(value).toFixed(2)}%`, 'MCII %']}
                    labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''}
                  />
                  <Bar dataKey="margem_numero" fill="#253575" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'quotes' && (
        <section className="dashboard-grid">
          <Panel title="Kg cotados x vendidos" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={quoteMonthly.map((item) => ({ ...item, cotado_toneladas: item.kg_cotado_numero / 1000, vendido_toneladas: item.kg_vendido_numero / 1000 }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <Tooltip formatter={(value, name) => [`${formatNumber(String(value))} t`, name]} />
                  <Legend verticalAlign="bottom" height={24} />
                  <Line type="monotone" dataKey="cotado_toneladas" name="Cotado" stroke="#F18800" strokeWidth={3} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="vendido_toneladas" name="Vendido" stroke="#253575" strokeWidth={3} dot={{ r: 3 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Conversao mensal" icon={<LineChartIcon size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={quoteMonthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => `${Number(value).toFixed(1)}%`} />
                  <Tooltip formatter={(value, name) => [`${Number(value).toFixed(2)}%`, name]} />
                  <Legend verticalAlign="bottom" height={24} />
                  <Line type="monotone" dataKey="conversao_numero" name="Conversão" stroke="#12805C" strokeWidth={3} dot={{ r: 3 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Conversao por vendedor" icon={<CheckCircle2 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={quoteSellerRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${Number(value).toFixed(1)}%`} />
                  <YAxis type="category" dataKey="shortName" width={120} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${Number(value).toFixed(2)}%`, 'Conversao']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <Bar dataKey="conversao_numero" fill="#F18800" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Funil comercial" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={quoteFunnelRows}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" />
                  <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Toneladas']} />
                  <Bar dataKey="toneladas_numero" fill="#253575" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'competition' && (
        <section className="dashboard-grid">
          <Panel title="Valor perdido por motivo" icon={<AlertTriangle size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={lossRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 94 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="name" width={112} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'Valor perdido']} />
                  <Bar dataKey="valor_numero" fill="#B42318" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Quantidade de perdas por motivo" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={[...lossRows].sort((a, b) => (b.linhas ?? 0) - (a.linhas ?? 0)).slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 94 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} />
                  <YAxis type="category" dataKey="name" width={112} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [formatNumber(String(value)), 'Ocorrencias']} />
                  <Bar dataKey="linhas" fill="#F18800" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'map' && (
        <section className="dashboard-grid">
          <Panel title="Peso vendido por municipio" icon={<Boxes size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={[...cityRows].sort((a, b) => b.peso_numero - a.peso_numero).slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                  <YAxis type="category" dataKey="shortName" width={108} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Toneladas']} labelFormatter={(_, payload) => payload?.[0]?.payload?.name ?? ''} />
                  <Bar dataKey={(row) => row.peso_numero / 1000} fill="#253575" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Faturamento por municipio" icon={<CircleDollarSign size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={cityRows.slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <YAxis type="category" dataKey="shortName" width={108} interval={0} tickMargin={6} />
                  <Tooltip formatter={(value) => [money(String(value)), 'Valor total']} />
                  <Bar dataKey="valor_numero" fill="#F18800" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
          <Panel title="Clientes por cidade" icon={<CheckCircle2 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={[...cityRows].sort((a, b) => b.clientes - a.clientes).slice(0, BAR_LIMIT)} layout="vertical" margin={{ left: 86 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} />
                  <YAxis type="category" dataKey="shortName" width={108} interval={0} tickMargin={6} />
                  <Tooltip />
                  <Bar dataKey="clientes" fill="#12805C" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {intelligenceTab === 'forecast' && (
        <>
          <section className="kpi-grid">
            <Kpi title="Forecast proximo mes" displayValue={`${formatNumber(forecastNextKg / 1000)} t`} detail="Media ponderada recente ajustada por sazonalidade" icon={<Gauge />} />
            <Kpi title="Variacao vs mes atual" displayValue={`${forecastChange >= 0 ? '+' : ''}${forecastChange.toFixed(1)}%`} detail="Comparado ao ultimo mes da base" icon={<LineChartIcon />} />
            <Kpi title="Cotacoes no periodo" displayValue={`${formatNumber(quotedKg / 1000)} t`} detail="Radar antecipado de demanda" icon={<TableProperties />} />
            <Kpi title="Historico disponivel" displayValue={`${formatNumber(sortedMonthlySales.length)} meses`} detail="Base usada para tendencia e sazonalidade" icon={<CalendarDays />} />
          </section>

          <section className="dashboard-grid">
            <Panel title="Real x forecast em toneladas" icon={<LineChartIcon size={17} />} wide>
              <ChartFrame>
                <ResponsiveContainer>
                  <ReLineChart data={realVsForecastRows}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <Tooltip formatter={(value, name) => [`${formatNumber(String(value))} t`, name]} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Line type="monotone" dataKey="real_toneladas" name="Real" stroke="#253575" strokeWidth={3} dot={{ r: 2 }} connectNulls={false} />
                    <Line type="monotone" dataKey="forecast_toneladas" name="Forecast" stroke="#F18800" strokeWidth={3} strokeDasharray="6 5" dot={{ r: 3 }} connectNulls={false} />
                  </ReLineChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Tendencia da demanda" icon={<LineChartIcon size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <ReLineChart data={demandTrendRows}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <Tooltip formatter={(value, name) => [`${formatNumber(String(value))} t`, name]} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Line type="monotone" dataKey="toneladas" name="Vendido" stroke="#8EA0D8" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="media_movel" name="Média móvel 3 meses" stroke="#253575" strokeWidth={3} dot={{ r: 2 }} />
                  </ReLineChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Sazonalidade historica" icon={<BarChart3 size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <BarChart data={seasonalityRows}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" />
                    <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Media historica']} />
                    <Bar dataKey="toneladas" fill="#12805C" radius={[5, 5, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Forecast por familia" icon={<Boxes size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <BarChart data={forecastFamilyRows} layout="vertical" margin={{ left: 86 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                    <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Forecast']} />
                    <Bar dataKey="forecast_toneladas" fill="#253575" radius={[0, 5, 5, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Forecast por segmento" icon={<SlidersHorizontal size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <BarChart data={forecastSegmentRows} layout="vertical" margin={{ left: 86 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                    <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Forecast']} />
                    <Bar dataKey="forecast_toneladas" fill="#F18800" radius={[0, 5, 5, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Forecast por regiao" icon={<BarChart3 size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <BarChart data={forecastCityRows} layout="vertical" margin={{ left: 86 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <YAxis type="category" dataKey="name" width={120} interval={0} tickMargin={6} />
                    <Tooltip formatter={(value) => [`${formatNumber(String(value))} t`, 'Forecast']} labelFormatter={(_, payload) => payload?.[0]?.payload?.fullName ?? ''} />
                    <Bar dataKey="forecast_toneladas" fill="#6B7280" radius={[0, 5, 5, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <Panel title="Cotacoes x vendas" icon={<LineChartIcon size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <ReLineChart data={quoteMonthly.map((item) => ({ ...item, cotado_toneladas: item.kg_cotado_numero / 1000, vendido_toneladas: item.kg_vendido_numero / 1000 }))}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis tickFormatter={(value) => `${formatNumber(value)} t`} />
                    <Tooltip formatter={(value, name) => [`${formatNumber(String(value))} t`, name]} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Line type="monotone" dataKey="cotado_toneladas" name="Cotado" stroke="#F18800" strokeWidth={3} dot={{ r: 2 }} />
                    <Line type="monotone" dataKey="vendido_toneladas" name="Vendido" stroke="#253575" strokeWidth={3} dot={{ r: 2 }} />
                  </ReLineChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>

            <UnavailablePanel title="Carteira confirmada x demanda prevista" />
            <UnavailablePanel title="Erro do forecast" />
            <UnavailablePanel title="Necessidade estimada de compra" />
          </section>
        </>
      )}

      {macroArea === 'business' && ['stock', 'purchases', 'logistics'].includes(intelligenceTab) && (
        <UnavailableTab title={activeTabLabel} />
      )}

      {macroArea === 'market' && (
        <MarketTab summary={market} tab={intelligenceTab} title={activeTabLabel} />
      )}

      {macroArea === 'service' && intelligenceTab === 'service-overview' && (
        <>
          <section className="kpi-grid">
            <Kpi
              title="Leads novos"
              displayValue={attendanceHasGranularData ? formatNumber(attendanceKpis?.leads_novos) : 'Sem base granular'}
              detail={attendanceHasGranularData ? 'Depois das exclusoes do Kommo' : `${formatNumber(attendance?.rows)} linhas de resumo importadas`}
              icon={<CheckCircle2 />}
            />
            <Kpi
              title="Leads abertos"
              displayValue={attendanceHasGranularData ? formatNumber(attendanceKpis?.leads_abertos) : 'Sem dados'}
              detail="Depende de status por lead"
              icon={<Gauge />}
            />
            <Kpi
              title="Primeira acao"
              displayValue={attendanceKpis?.tempo_mediano_primeira_resposta !== null && attendanceKpis?.tempo_mediano_primeira_resposta !== undefined ? minutes(attendanceKpis.tempo_mediano_primeira_resposta) : 'Aguardando eventos'}
              detail="Mediana entre entrada do lead e primeira acao registrada"
              icon={<LineChartIcon />}
            />
            <Kpi
              title="1a acao ate 5 min"
              displayValue={attendanceKpis?.sla_5_min !== null && attendanceKpis?.sla_5_min !== undefined ? percent(attendanceKpis.sla_5_min) : 'Aguardando eventos'}
              detail="Proxy operacional por evento humano do Kommo"
              icon={<BarChart3 />}
            />
          </section>

          <section className="dashboard-grid">
            {attendanceHasGranularData && (
              <>
                <Panel title="Pipeline aberto" icon={<CircleDollarSign size={17} />}>
                  <div className="empty-state compact">
                    <strong>{money(attendanceKpis?.pipeline_aberto_valor)}</strong>
                    <span>{formatNumber(attendanceKpis?.pipeline_aberto_qtd)} leads em aberto</span>
                  </div>
                </Panel>

                <Panel title="Conversao por funil" icon={<BarChart3 size={17} />}>
                  <ChartFrame>
                    <ResponsiveContainer>
                      <BarChart data={attendance?.win_rate_by_funnel ?? []} margin={{ top: 4, right: 12, left: 0, bottom: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                        <XAxis dataKey="funil" tickFormatter={(value) => abbreviateLabel(String(value), 14)} />
                        <YAxis tickFormatter={(value) => `${value}%`} />
                        <Tooltip
                          formatter={(value, _name, item) => {
                            const row = item.payload as {
                              ganhas?: number
                              perdidas?: number
                              fechadas?: number
                              abertas?: number
                              leads_periodo?: number
                              win_rate?: number
                            }
                            return [
                              `${Number(value).toFixed(1)}% | ${formatNumber(row.ganhas)} ganhas / ${formatNumber(row.leads_periodo)} leads | win rate fechados ${Number(row.win_rate ?? 0).toFixed(1)}% (${formatNumber(row.fechadas)} fechadas)`,
                              'Conversao',
                            ]
                          }}
                        />
                        <Bar dataKey="conversion_rate" name="Conversao" fill="#13875f" radius={[5, 5, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </ChartFrame>
                </Panel>
              </>
            )}

            <Panel title="Leads por dia e status atual" icon={<LineChartIcon size={17} />}>
              <ChartFrame>
                <ResponsiveContainer>
                  <ComposedChart data={attendanceDaily} margin={{ top: 4, right: 12, left: 0, bottom: 16 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="data_label" />
                    <YAxis />
                    <Tooltip formatter={(value, name) => [formatNumber(String(value)), name]} />
                    <Legend verticalAlign="bottom" height={24} />
                    <Bar dataKey="abertos" stackId="status" name="Abertos" fill="#F18800" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="ganhos" stackId="status" name="Ganhos" fill="#13875f" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="perdidos" stackId="status" name="Perdidos" fill="#C2261A" radius={[5, 5, 0, 0]} />
                  </ComposedChart>
                </ResponsiveContainer>
              </ChartFrame>
            </Panel>
          </section>
        </>
      )}

      {macroArea === 'service' && intelligenceTab === 'ranking' && (
        <section className="dashboard-grid">
          <Panel title="Ranking por colaborador" icon={<BarChart3 size={17} />} wide>
            <div className="ranking-toolbar">
              <label>
                <span>Ranking</span>
                <select value={rankingView} onChange={(event) => setRankingView(event.target.value as RankingView)}>
                  {rankingViewOptions.map((item) => (
                    <option key={item.key} value={item.key}>{item.label}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Ordenar por</span>
                <select value={rankingMetric} onChange={(event) => setRankingMetric(event.target.value as RankingMetric)}>
                  {rankingMetricOptions.map((item) => (
                    <option key={item.key} value={item.key}>{item.label}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="ranking-highlights">
              {highlightCards.map((item) => (
                <div className="ranking-highlight" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.name}</strong>
                  <small>{item.value}</small>
                </div>
              ))}
            </div>

            {!attendanceHasGranularData && (
              <div className="empty-state compact">
                <strong>Faltam dados para cruzamentos</strong>
                <span>
                  A regra de regiao ja esta cadastrada por colaborador, mas os indicadores do ranking dependem de uma base granular por lead.
                </span>
              </div>
            )}
            <details className="list-dropdown">
              <summary>
                <span>Ver lista completa</span>
                <strong>{formatNumber(rankingRowsCount)} registros</strong>
              </summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    {rankingView === 'retail-region' ? (
                      <tr>
                        <th>Regiao/Polo</th>
                        <th>Colaboradores</th>
                        <th>Leads</th>
                        <th>Ganhas</th>
                        <th>Perdidas</th>
                        <th>Win rate</th>
                        <th>1a acao ate 5 min</th>
                        <th>Pipeline</th>
                        <th>Valor pipeline</th>
                        <th>Follow-up</th>
                      </tr>
                    ) : (
                      <tr>
                        <th>Nome</th>
                        <th>Funcao</th>
                        <th>Regiao/Polo</th>
                        <th>Leads</th>
                        <th>Ganhas</th>
                        <th>Perdidas</th>
                        <th>Win rate</th>
                        <th>1a acao ate 5 min</th>
                        <th>Pipeline</th>
                        <th>Valor pipeline</th>
                        <th>Follow-up</th>
                      </tr>
                    )}
                  </thead>
                  <tbody>
                    {rankingView === 'retail-region' ? (
                      selectedRegionRanking.length ? selectedRegionRanking.map((item) => (
                        <tr key={item.regiao_polo}>
                          <td>{item.regiao_polo}</td>
                          <td>{item.colaboradores.join(', ')}</td>
                          <td>{formatNumber(item.leads)}</td>
                          <td>{formatNumber(item.ganhas)}</td>
                          <td>{formatNumber(item.perdidas)}</td>
                          <td>{percent(item.win_rate)}</td>
                          <td>{percent(item.sla_5_min)}</td>
                          <td>{formatNumber(item.pipeline_aberto_qtd)}</td>
                          <td>{money(item.pipeline_aberto_valor)}</td>
                          <td>{percent(item.follow_up_cobertura)}</td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={10} className="empty-cell">Faltam dados para cruzamentos em {rankingTitle}</td>
                        </tr>
                      )
                    ) : (
                      selectedCollaboratorRanking.length ? selectedCollaboratorRanking.map((row) => (
                        <tr key={`${row.nome}-${row.funcao}`}>
                          <td>{row.nome}</td>
                          <td>{row.funcao}</td>
                          <td>{row.regiao_polo}</td>
                          <td>{formatNumber(row.leads)}</td>
                          <td>{formatNumber(row.ganhas)}</td>
                          <td>{formatNumber(row.perdidas)}</td>
                          <td>{percent(row.win_rate)}</td>
                          <td>{percent(row.sla_5_min)}</td>
                          <td>{formatNumber(row.pipeline_aberto_qtd)}</td>
                          <td>{money(row.pipeline_aberto_valor)}</td>
                          <td>{percent(row.follow_up_cobertura)}</td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={11} className="empty-cell">Faltam dados para cruzamentos em {rankingTitle}</td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            </details>
          </Panel>

          {unmappedAttendanceCollaborators.length > 0 && (
            <Panel title="Colaboradores sem cadastro de regiao" icon={<AlertTriangle size={17} />} wide>
              <div className="empty-state compact">
                <strong>{formatNumber(unmappedAttendanceCollaborators.length)} nomes sem correspondencia</strong>
                <span>{unmappedAttendanceCollaborators.join(', ')}</span>
              </div>
            </Panel>
          )}
        </section>
      )}

      {macroArea === 'service' && intelligenceTab === 'sla' && (
        <section className="dashboard-grid">
          <Panel title="Tempo ate primeira acao" icon={<Gauge size={17} />} wide>
            <div className="empty-state compact">
              <strong>SLA operacional por evento do Kommo</strong>
              <span>Conta o tempo entre a entrada do lead e a primeira acao humana registrada. Nao usa cidade, cliente ou planilha.</span>
            </div>
            <div className="ranking-toolbar">
              <label>
                <span>Ranking</span>
                <select value={slaView} onChange={(event) => setSlaView(event.target.value as RankingView)}>
                  {rankingViewOptions.map((item) => (
                    <option key={item.key} value={item.key}>{item.label}</option>
                  ))}
                </select>
              </label>
              <label>
                <span>Ordenar por</span>
                <select value={slaMetric} onChange={(event) => setSlaMetric(event.target.value as RankingMetric)}>
                  {slaMetricOptions.map((item) => (
                    <option key={item.key} value={item.key}>{item.label}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="ranking-highlights">
              {slaHighlightCards.map((item) => (
                <div className="ranking-highlight" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.name}</strong>
                  <small>{item.value}</small>
                </div>
              ))}
            </div>

            <details className="list-dropdown">
              <summary>
                <span>Ver lista completa</span>
                <strong>{formatNumber(slaRowsCount)} registros</strong>
              </summary>
              <div className="table-wrap">
                <table>
                  <thead>
                    {slaView === 'retail-region' ? (
                      <tr>
                        <th>Regiao/Polo</th>
                        <th>Colaboradores</th>
                        <th>Leads</th>
                        <th>1a acao ate 5 min</th>
                        <th>Follow-up</th>
                        <th>Win rate</th>
                        <th>Pipeline</th>
                      </tr>
                    ) : (
                      <tr>
                        <th>Nome</th>
                        <th>Funcao</th>
                        <th>Regiao/Polo</th>
                        <th>Leads</th>
                        <th>1a acao ate 5 min</th>
                        <th>Follow-up</th>
                        <th>Win rate</th>
                        <th>Pipeline</th>
                      </tr>
                    )}
                  </thead>
                  <tbody>
                    {slaView === 'retail-region' ? (
                      selectedSlaRegions.length ? selectedSlaRegions.map((item) => (
                        <tr key={item.regiao_polo}>
                          <td>{item.regiao_polo}</td>
                          <td>{item.colaboradores.join(', ')}</td>
                          <td>{formatNumber(item.leads)}</td>
                          <td>{percent(item.sla_5_min)}</td>
                          <td>{percent(item.follow_up_cobertura)}</td>
                          <td>{percent(item.win_rate)}</td>
                          <td>{money(item.pipeline_aberto_valor)}</td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={7} className="empty-cell">Faltam dados para cruzamentos em {slaTitle}</td>
                        </tr>
                      )
                    ) : (
                      selectedSlaCollaborators.length ? selectedSlaCollaborators.map((item) => (
                        <tr key={`${item.nome}-${item.funcao}`}>
                          <td>{item.nome}</td>
                          <td>{item.funcao}</td>
                          <td>{item.regiao_polo}</td>
                          <td>{formatNumber(item.leads)}</td>
                          <td>{percent(item.sla_5_min)}</td>
                          <td>{percent(item.follow_up_cobertura)}</td>
                          <td>{percent(item.win_rate)}</td>
                          <td>{money(item.pipeline_aberto_valor)}</td>
                        </tr>
                      )) : (
                        <tr>
                          <td colSpan={8} className="empty-cell">Faltam dados para cruzamentos em {slaTitle}</td>
                        </tr>
                      )
                    )}
                  </tbody>
                </table>
              </div>
            </details>
          </Panel>
        </section>
      )}

      {macroArea === 'service' && intelligenceTab === 'channels' && (
        <section className="dashboard-grid">
          <Panel title="Origem dos leads" icon={<BarChart3 size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={attendanceOrigins} layout="vertical" margin={{ top: 4, right: 16, left: 120, bottom: 12 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" />
                  <YAxis type="category" dataKey="origem" width={118} tickFormatter={(value) => abbreviateLabel(String(value), 18)} />
                  <Tooltip formatter={(value) => [formatNumber(String(value)), 'Leads']} />
                  <Bar dataKey="leads" name="Leads" fill="#13875f" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {macroArea === 'service' && !['service-overview', 'ranking', 'sla', 'channels'].includes(intelligenceTab) && (
        <UnavailableTab title={activeTabLabel} />
      )}

    </main>
  )
}

function Kpi({ title, value, displayValue, detail, icon }: { title: string; value?: number; displayValue?: string; detail: string; icon: ReactNode }) {
  return (
    <article className="kpi-card" title={`${title}: ${detail}`}>
      <div className="kpi-icon">{icon}</div>
      <div>
        <span>{title}</span>
        <strong>{displayValue ?? formatNumber(value)}</strong>
        <small>{detail}</small>
      </div>
    </article>
  )
}

function Panel({ title, icon, wide, children }: { title: string; icon: ReactNode; wide?: boolean; children: ReactNode }) {
  return (
    <section className={`panel ${wide ? 'wide' : ''}`}>
      <div className="panel-title">
        {icon}
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  )
}

function ChartFrame({ children }: { children: ReactNode }) {
  return <div className="chart-frame">{children}</div>
}

function UnavailablePanel({ title }: { title: string }) {
  return (
    <Panel title={title} icon={<Database size={17} />}>
      <div className="empty-state compact">
        <strong>Faltam dados para cruzamentos</strong>
      </div>
    </Panel>
  )
}

function UnavailableTab({ title }: { title: string }) {
  return (
    <section className="dashboard-grid">
      <Panel title={title} icon={<Database size={17} />} wide>
        <div className="empty-state">
          <strong>Faltam dados para cruzamentos</strong>
          <span>Esta visao depende de bases que ainda nao estao carregadas com granularidade suficiente para gerar o indicador.</span>
        </div>
      </Panel>
    </section>
  )
}

function MarketTab({ summary, tab, title }: { summary?: MarketSummary; tab: IntelligenceTab; title: string }) {
  if (!summary) return <UnavailableTab title={title} />

  if (tab === 'market-overview') return <MarketOverview summary={summary} />
  if (tab === 'steel-market') return <MarketIndicatorTab title="Mercado do Aco" icon={<BarChart3 size={17} />} data={summary.steel_market} unitFallback="mil t" />
  if (tab === 'market-prices') return <MarketPricesTab summary={summary} />
  if (tab === 'imports') return <MarketImportsTab summary={summary} />
  if (tab === 'industry') return <MarketIndicatorTab title="Industria" icon={<Gauge size={17} />} data={summary.industry} unitFallback="indice" />
  if (tab === 'construction') return <MarketConstructionTab summary={summary} />
  if (tab === 'opportunities') return <MarketOpportunitiesTab summary={summary} />
  if (tab === 'solar') return <MarketSolarTab summary={summary} />

  return <UnavailableTab title={title} />
}

function MarketOverview({ summary }: { summary: MarketSummary }) {
  const sourceRows = summary.sources.map((item) => [
    marketSourceShortName(item.source_key),
    item.status,
    item.latest_reference_period ?? 'Sem periodo',
    formatNumber(item.last_row_count),
    item.last_success_at ? new Date(item.last_success_at).toLocaleString('pt-BR') : 'Sem carga',
  ])
  const periodRows = summary.overview.latest_periods.map((item) => [
    marketSourceShortName(item.source_key),
    item.period ?? 'Sem periodo',
    formatNumber(item.rows),
    item.status,
  ])
  const macroRows = summary.overview.macro_indicators.map((item) => [
    item.name,
    item.geography ?? 'BR',
    item.period ?? 'Sem periodo',
    marketValue(item.value, item.unit),
  ])

  return (
    <>
      <section className="kpi-grid">
        <Kpi title="Fontes saudaveis" displayValue={formatNumber(summary.overview.healthy_count)} detail={`${formatNumber(summary.overview.configured_count)} fontes configuradas`} icon={<CheckCircle2 />} />
        <Kpi title="Fontes com erro" displayValue={formatNumber(summary.overview.error_count)} detail="Nao exibidas como aba operacional" icon={<AlertTriangle />} />
        <Kpi title="Abas ativas" displayValue={formatNumber(summary.available_tabs.length)} detail="Somente com fonte saudavel" icon={<TableProperties />} />
        <Kpi title="Indicadores carregados" displayValue={formatNumber(summary.overview.latest_periods.reduce((sum, item) => sum + Number(item.rows || 0), 0))} detail="Linhas agregadas de mercado" icon={<Database />} />
      </section>
      <section className="dashboard-grid">
        <Panel title="Ultimos periodos por fonte" icon={<CalendarDays size={17} />} wide>
          <DataTable columns={['Fonte', 'Periodo', 'Linhas', 'Status']} rows={periodRows} empty="Nenhuma fonte saudavel carregada" />
        </Panel>
        {macroRows.length > 0 && (
          <Panel title="Contexto macro" icon={<LineChartIcon size={17} />} wide>
            <DataTable columns={['Indicador', 'Geografia', 'Periodo', 'Valor']} rows={macroRows} empty="Sem indicadores macro carregados" />
          </Panel>
        )}
        <Panel title="Saude das fontes de mercado" icon={<Database size={17} />} wide>
          <DataTable columns={['Fonte', 'Status', 'Periodo', 'Linhas', 'Ultima carga']} rows={sourceRows} empty="Registry de mercado vazio" />
        </Panel>
      </section>
    </>
  )
}

function MarketIndicatorTab({
  title,
  icon,
  data,
  unitFallback,
}: {
  title: string
  icon: ReactNode
  data?: { indicators: MarketSummary['overview']['macro_indicators']; series: Array<{ period_label: string | null; value: string | null }> }
  unitFallback: string
}) {
  const indicators = data?.indicators ?? []
  const series = (data?.series ?? []).map((item) => ({
    period_label: item.period_label ?? 'Sem periodo',
    value_numero: nullableNumericValue(item.value),
  }))
  if (!indicators.length && !series.length) return <UnavailableTab title={title} />

  const kpis = indicators.slice(0, 4)
  const rows = indicators.map((item) => [
    marketSourceShortName(item.source_key),
    item.name,
    item.period ?? 'Sem periodo',
    item.geography ?? 'BR',
    marketValue(item.value, item.unit),
  ])

  return (
    <>
      {kpis.length > 0 && (
        <section className="kpi-grid">
          {kpis.map((item) => (
            <Kpi
              key={`${item.source_key}-${item.indicator_key}-${item.geography}`}
              title={abbreviateLabel(item.name, 22)}
              displayValue={marketValue(item.value, item.unit)}
              detail={`${marketSourceShortName(item.source_key)} | ${item.period ?? 'Sem periodo'}`}
              icon={<Gauge />}
            />
          ))}
        </section>
      )}
      <section className="dashboard-grid">
        {series.length > 0 && (
          <Panel title={title} icon={icon} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={series}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="period_label" />
                  <YAxis tickFormatter={(value) => marketValue(String(value), unitFallback)} />
                  <Tooltip formatter={(value) => [marketValue(String(value), unitFallback), title]} />
                  <Line type="monotone" dataKey="value_numero" name={title} stroke="#253575" strokeWidth={3} dot={{ r: 2 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        )}
        <Panel title="Indicadores carregados" icon={<TableProperties size={17} />} wide>
          <DataTable columns={['Fonte', 'Indicador', 'Periodo', 'Geografia', 'Valor']} rows={rows} empty="Sem indicadores carregados" />
        </Panel>
      </section>
    </>
  )
}

function MarketPricesTab({ summary }: { summary: MarketSummary }) {
  const prices = summary.prices
  const comex = prices?.comex
  const ptax = prices?.ptax
  if (!comex?.kpis && !ptax?.latest) return <UnavailableTab title="Precos & Cambio" />

  const monthly = (comex?.monthly ?? []).map((item) => ({
    ...item,
    fob_numero: nullableNumericValue(item.fob_usd_t),
    cif_numero: nullableNumericValue(item.cif_proxy_usd_t),
  }))
  const ptaxSeries = (ptax?.series ?? []).map((item) => ({
    period_label: item.period_label ?? 'Sem periodo',
    value_numero: nullableNumericValue(item.value),
  }))
  const familyRows = (comex?.families ?? []).map((item) => [
    item.family,
    marketValue(item.toneladas, 't'),
    marketValue(item.fob_usd_t, 'US$/t'),
  ])

  return (
    <>
      <section className="kpi-grid">
        {ptax?.latest && <Kpi title="PTAX atual" displayValue={marketValue(ptax.latest.value, 'R$')} detail={`BCB | ${ptax.latest.period_label ?? 'Sem periodo'}`} icon={<CircleDollarSign />} />}
        {ptax?.change_period_pct && <Kpi title="PTAX periodo" displayValue={percent(numericValue(ptax.change_period_pct))} detail="Variacao na janela carregada" icon={<LineChartIcon />} />}
        {comex?.kpis && <Kpi title="FOB US$/t" displayValue={marketValue(comex.kpis.fob_usd_t, 'US$/t')} detail="SUM(VL_FOB) / toneladas" icon={<Gauge />} />}
        {comex?.kpis && <Kpi title="Proxy CIF US$/t" displayValue={marketValue(comex.kpis.cif_proxy_usd_t, 'US$/t')} detail="FOB + frete + seguro / toneladas" icon={<BarChart3 />} />}
      </section>
      <section className="dashboard-grid">
        {monthly.length > 0 && (
          <Panel title="Valor unitario do aco importado" icon={<LineChartIcon size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={monthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="period_label" />
                  <YAxis tickFormatter={(value) => marketValue(String(value), 'US$/t')} />
                  <Tooltip formatter={(value, name) => [marketValue(String(value), 'US$/t'), name]} />
                  <Legend verticalAlign="bottom" height={24} />
                  <Line type="monotone" dataKey="fob_numero" name="FOB US$/t" stroke="#253575" strokeWidth={3} dot={{ r: 2 }} />
                  <Line type="monotone" dataKey="cif_numero" name="Proxy CIF US$/t" stroke="#F18800" strokeWidth={3} dot={{ r: 2 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        )}
        {ptaxSeries.length > 0 && (
          <Panel title="PTAX BCB" icon={<CircleDollarSign size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={ptaxSeries}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="period_label" />
                  <YAxis tickFormatter={(value) => marketValue(String(value), 'R$')} />
                  <Tooltip formatter={(value) => [marketValue(String(value), 'R$'), 'PTAX venda']} />
                  <Line type="monotone" dataKey="value_numero" name="PTAX venda" stroke="#F18800" strokeWidth={3} dot={{ r: 2 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        )}
        <Panel title="Pressao por familia ABR" icon={<TableProperties size={17} />} wide>
          <DataTable columns={['Familia', 'Toneladas 12M', 'FOB US$/t']} rows={familyRows} empty="Sem familias Comex aprovadas" />
        </Panel>
      </section>
    </>
  )
}

function MarketImportsTab({ summary }: { summary: MarketSummary }) {
  const imports = summary.imports
  if (!imports?.kpis) return <UnavailableTab title="Importacoes" />
  const monthly = (imports.monthly ?? []).map((item) => ({
    ...item,
    toneladas_numero: nullableNumericValue(item.toneladas),
    fob_numero: nullableNumericValue(item.fob_usd_t),
  }))
  const countryRows = (imports.countries ?? []).map((item) => [item.country, marketValue(item.toneladas, 't')])
  const detailRows = (imports.detail ?? []).map((item) => [
    item.ncm,
    item.family,
    item.country,
    marketValue(item.toneladas, 't'),
    marketValue(item.fob_usd_t, 'US$/t'),
    marketValue(item.freight_usd_t, 'US$/t'),
  ])

  return (
    <>
      <section className="kpi-grid">
        <Kpi title="Toneladas 12M" displayValue={marketValue(imports.kpis.toneladas_12m, 't')} detail={`Comex | ate ${monthLabel(imports.latest_period.slice(0, 7))}`} icon={<Boxes />} />
        <Kpi title="FOB US$/t" displayValue={marketValue(imports.kpis.fob_usd_t, 'US$/t')} detail="Media ponderada por tonelada" icon={<CircleDollarSign />} />
        <Kpi title="Proxy CIF US$/t" displayValue={marketValue(imports.kpis.cif_proxy_usd_t, 'US$/t')} detail="FOB + frete + seguro" icon={<Gauge />} />
        <Kpi title="Paises origem" displayValue={formatNumber(imports.kpis.countries)} detail="Top origens no recorte 12M" icon={<TableProperties />} />
      </section>
      <section className="dashboard-grid">
        <Panel title="Importacoes mensais" icon={<LineChartIcon size={17} />} wide>
          <ChartFrame>
            <ResponsiveContainer>
              <ComposedChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period_label" />
                <YAxis yAxisId="left" tickFormatter={(value) => marketValue(String(value), 't')} />
                <YAxis yAxisId="right" orientation="right" tickFormatter={(value) => marketValue(String(value), 'US$/t')} />
                <Tooltip formatter={(value, name) => [name === 'Toneladas' ? marketValue(String(value), 't') : marketValue(String(value), 'US$/t'), name]} />
                <Legend verticalAlign="bottom" height={24} />
                <Bar yAxisId="left" dataKey="toneladas_numero" name="Toneladas" fill="#253575" radius={[5, 5, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="fob_numero" name="FOB US$/t" stroke="#F18800" strokeWidth={3} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>
        </Panel>
        <Panel title="Paises de origem" icon={<TableProperties size={17} />} wide>
          <DataTable columns={['Pais', 'Toneladas 12M']} rows={countryRows} empty="Sem origem Comex carregada" />
        </Panel>
        <Panel title="Detalhe NCM aprovado" icon={<Database size={17} />} wide>
          <DataTable columns={['NCM', 'Familia', 'Pais', 'Toneladas', 'FOB US$/t', 'Frete US$/t']} rows={detailRows} empty="Sem detalhe Comex carregado" />
        </Panel>
      </section>
    </>
  )
}

function MarketConstructionTab({ summary }: { summary: MarketSummary }) {
  const construction = summary.construction
  const works = construction?.public_works
  const worksRows = (works?.top_regions ?? []).map((item) => [
    item.uf,
    formatNumber(item.projects),
    money(item.investment),
  ])
  return (
    <>
      {works?.kpis && (
        <section className="kpi-grid">
          <Kpi title="Projetos publicos" displayValue={formatNumber(works.kpis.projects)} detail="ObrasGov consolidado" icon={<CheckCircle2 />} />
          <Kpi title="Investimento previsto" displayValue={money(works.kpis.investment)} detail="ObrasGov consolidado" icon={<CircleDollarSign />} />
          <Kpi title="Empregos estimados" displayValue={formatNumber(works.kpis.jobs)} detail="Informado nos projetos" icon={<Gauge />} />
          <Kpi title="Fontes ativas" displayValue={formatNumber(['ibge_construcao_sidra', 'cni_sondagem_construcao', 'obrasgov_projetos'].filter((key) => summary.healthy_sources.includes(key)).length)} detail="IBGE, CNI e ObrasGov" icon={<Database />} />
        </section>
      )}
      <MarketIndicatorTab title="Construcao" icon={<BarChart3 size={17} />} data={construction} unitFallback="indice" />
      {worksRows.length > 0 && (
        <section className="dashboard-grid">
          <Panel title="ObrasGov por UF" icon={<TableProperties size={17} />} wide>
            <DataTable columns={['UF', 'Projetos', 'Investimento']} rows={worksRows} empty="Sem projetos carregados" />
          </Panel>
        </section>
      )}
    </>
  )
}

function MarketOpportunitiesTab({ summary }: { summary: MarketSummary }) {
  const opportunities = summary.opportunities
  if (!opportunities?.kpis) return <UnavailableTab title="Oportunidades" />
  const monthly = (opportunities.monthly ?? []).map((item) => ({
    ...item,
    opportunities_numero: item.opportunities,
  }))
  const regionRows = (opportunities.top_regions ?? []).map((item) => [
    item.uf,
    formatNumber(item.opportunities),
    money(item.value),
  ])
  const detailRows = (opportunities.detail ?? []).map((item) => [
    item.date ? new Date(item.date).toLocaleDateString('pt-BR') : 'Sem data',
    item.uf,
    item.municipality || 'Sem municipio',
    abbreviateLabel(item.agency || 'Sem orgao', 28),
    abbreviateLabel(item.object || 'Sem objeto', 42),
    money(item.value),
    formatNumber(item.relevance_score),
    item.id,
  ])

  return (
    <>
      <section className="kpi-grid">
        <Kpi title="Oportunidades" displayValue={formatNumber(opportunities.kpis.opportunities)} detail={marketSourceShortName(opportunities.source)} icon={<CheckCircle2 />} />
        <Kpi title="Alta relevancia" displayValue={formatNumber(opportunities.kpis.high_relevance)} detail="RelevanceScore >= 3" icon={<Gauge />} />
        <Kpi title="Valor projetos" displayValue={money(opportunities.kpis.total_value)} detail="Valor dos projetos identificados" icon={<CircleDollarSign />} />
        <Kpi title="UFs com oportunidade" displayValue={formatNumber(opportunities.kpis.regions)} detail="Polos/UFs com registros" icon={<TableProperties />} />
      </section>
      <section className="dashboard-grid">
        {monthly.length > 0 && (
          <Panel title="Oportunidades por mes" icon={<LineChartIcon size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={monthly}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="period_label" />
                  <YAxis tickFormatter={(value) => formatNumber(String(value))} />
                  <Tooltip formatter={(value) => [formatNumber(String(value)), 'Oportunidades']} />
                  <Bar dataKey="opportunities_numero" name="Oportunidades" fill="#253575" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        )}
        <Panel title="Oportunidades por UF" icon={<TableProperties size={17} />} wide>
          <DataTable columns={['UF', 'Oportunidades', 'Valor projetos']} rows={regionRows} empty="Sem regioes carregadas" />
        </Panel>
        <Panel title="Projetos para prospeccao" icon={<Database size={17} />} wide>
          <DataTable columns={['Data', 'UF', 'Municipio', 'Orgao', 'Objeto', 'Valor', 'Score', 'ID']} rows={detailRows} empty="Sem projetos detalhados carregados" />
        </Panel>
      </section>
    </>
  )
}

function MarketSolarTab({ summary }: { summary: MarketSummary }) {
  const solar = summary.solar
  if (!solar?.kpis) return <UnavailableTab title="Solar" />
  const monthly = (solar.monthly ?? []).map((item) => ({
    ...item,
    new_mw_numero: nullableNumericValue(item.new_mw),
    cumulative_mw_numero: nullableNumericValue(item.cumulative_mw),
  }))
  const regionRows = (solar.top_regions ?? []).map((item) => [
    item.uf,
    marketValue(item.new_mw, 'MW'),
    formatNumber(item.installations),
  ])

  return (
    <>
      <section className="kpi-grid">
        <Kpi title="MW novos 12 meses" displayValue={marketValue(solar.kpis.last_12_new_mw, 'MW')} detail={`Atualizado ate ${monthLabel(solar.latest_period.slice(0, 7))}`} icon={<LineChartIcon />} />
        <Kpi title="Instalacoes 12 meses" displayValue={formatNumber(solar.kpis.last_12_installations)} detail="ANEEL dados abertos" icon={<CheckCircle2 />} />
        <Kpi title="Potencia acumulada" displayValue={marketValue(solar.kpis.cumulative_mw, 'MW')} detail="Soma nacional por UF" icon={<Gauge />} />
        <Kpi title="UFs no recorte" displayValue={formatNumber(solar.top_regions?.length ?? 0)} detail="Top UFs por MW novo" icon={<TableProperties />} />
      </section>
      <section className="dashboard-grid">
        <Panel title="Geracao solar distribuida" icon={<LineChartIcon size={17} />} wide>
          <ChartFrame>
            <ResponsiveContainer>
              <ComposedChart data={monthly}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period_label" />
                <YAxis yAxisId="left" tickFormatter={(value) => marketValue(String(value), 'MW')} />
                <YAxis yAxisId="right" orientation="right" tickFormatter={(value) => marketNumber(value, 0)} />
                <Tooltip formatter={(value, name) => [name === 'Instalacoes' ? formatNumber(String(value)) : marketValue(String(value), 'MW'), name]} />
                <Legend verticalAlign="bottom" height={24} />
                <Bar yAxisId="left" dataKey="new_mw_numero" name="MW novos" fill="#F18800" radius={[5, 5, 0, 0]} />
                <Line yAxisId="right" type="monotone" dataKey="installations" name="Instalacoes" stroke="#253575" strokeWidth={3} dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartFrame>
        </Panel>
        <Panel title="Top UFs em solar" icon={<TableProperties size={17} />} wide>
          <DataTable columns={['UF', 'MW novos 12 meses', 'Instalacoes']} rows={regionRows} empty="Sem ranking de UFs" />
        </Panel>
      </section>
    </>
  )
}

function SupportDetails({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="support-details">
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  )
}

function DataTable({ columns, rows, empty }: { columns: string[]; rows: string[][]; empty: string }) {
  const table = (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="empty-cell">{empty}</td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={index}>{row.map((cell, cellIndex) => <td key={`${index}-${cellIndex}`}>{cell}</td>)}</tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
  if (rows.length <= 6) return table
  return (
    <details className="list-dropdown">
      <summary>
        <span>Ver lista completa</span>
        <strong>{formatNumber(rows.length)} registros</strong>
      </summary>
      {table}
    </details>
  )
}

export default App
