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
  LockKeyhole,
  LogIn,
  RefreshCw,
  Search,
  ShieldCheck,
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
import { DashboardAuthError, DashboardSummary, fetchInternalDashboard, loginDashboard } from './api'
import abrLogoWhite from './abr-logo-white.svg'

const DEFAULT_DATE_FROM = '2026-01-01'
const DEFAULT_DATE_TO = new Date().toISOString().slice(0, 10)
const BAR_LIMIT = 6
const SCATTER_LIMIT = 14
const FORECAST_WEIGHTS = [0.5, 0.3, 0.2]

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

function formatNumber(value: number | string | undefined) {
  const number = Number(value || 0)
  return new Intl.NumberFormat('pt-BR').format(number)
}

function money(value: number | string | undefined) {
  const number = Number(value || 0)
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    maximumFractionDigits: 0,
  }).format(number)
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

const INTELLIGENCE_TABS: Array<{ key: IntelligenceTab; label: string }> = [
  { key: 'executive', label: 'Executivo' },
  { key: 'commercial', label: 'Comercial' },
  { key: 'clients', label: 'Clientes' },
  { key: 'segments', label: 'Segmentos' },
  { key: 'products', label: 'Produtos' },
  { key: 'prices', label: 'Precos' },
  { key: 'margin', label: 'Margem' },
  { key: 'quotes', label: 'Cotacoes' },
  { key: 'competition', label: 'Concorrencia' },
  { key: 'stock', label: 'Estoque' },
  { key: 'purchases', label: 'Compras' },
  { key: 'forecast', label: 'Forecast' },
  { key: 'logistics', label: 'Logistica' },
  { key: 'map', label: 'Mapa Comercial' },
]

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
  const [intelligenceTab, setIntelligenceTab] = useState<IntelligenceTab>('executive')
  const [statusFilter, setStatusFilter] = useState('todos')
  const [areaFilter, setAreaFilter] = useState('todas')
  const [dateFrom, setDateFrom] = useState(DEFAULT_DATE_FROM)
  const [dateTo, setDateTo] = useState(DEFAULT_DATE_TO)
  const [search, setSearch] = useState('')
  const [needsLogin, setNeedsLogin] = useState(false)
  const [password, setPassword] = useState('')
  const [loginError, setLoginError] = useState<string | null>(null)
  const [authenticating, setAuthenticating] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      setSummary(await fetchInternalDashboard({ dateFrom, dateTo }))
      setNeedsLogin(false)
    } catch (err) {
      if (err instanceof DashboardAuthError) {
        setNeedsLogin(true)
      } else {
        setError(err instanceof Error ? err.message : 'Falha ao carregar dados')
      }
    } finally {
      setLoading(false)
    }
  }

  const submitFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void load()
  }

  const submitLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setAuthenticating(true)
    setLoginError(null)
    try {
      await loginDashboard(password)
      setPassword('')
      await load()
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : 'Falha ao autenticar')
    } finally {
      setAuthenticating(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const reports = summary?.reports ?? []
  const areas = useMemo(() => Array.from(new Set(reports.map((item) => item.area))).sort(), [reports])

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

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div>
            <span className="eyebrow">ABR Intelligence</span>
            <h1>Inteligencia de Mercado</h1>
            <p>Duas frentes conectadas: inteligencia interna da operacao e inteligencia externa do mercado.</p>
          </div>
        </div>
        <div className="topbar-actions">
          <div className="brand-mark">
            <img src={abrLogoWhite} alt="Grupo ABR" />
          </div>
          <div className="header-controls">
            <div className="front-switch" aria-label="Frentes da inteligencia de mercado">
              <span className="front-pill active">Interna</span>
              <span className="front-pill">Externa</span>
            </div>
            <div className="header-status">
              <span className="status-pill">
                <ShieldCheck size={15} />
                Inteligencia interna
              </span>
              <button className="icon-button" onClick={load} disabled={loading} title="Atualizar">
                <RefreshCw size={17} className={loading ? 'spin' : ''} />
              </button>
            </div>
          </div>
        </div>
      </header>

      <form className="toolbar" aria-label="Filtros do dashboard" onSubmit={submitFilters}>
        <div className="control search-control">
          <Search size={16} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar relatorio, area ou entidade" />
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
            <option value="todos">Todos os status</option>
            <option value="validated">Validados</option>
            <option value="validated_empty">Sem registro</option>
            <option value="deprioritized">Fora da prioridade</option>
          </select>
        </label>
        <label className="control">
          <SlidersHorizontal size={16} />
          <select value={areaFilter} onChange={(event) => setAreaFilter(event.target.value)}>
            <option value="todas">Todas as areas</option>
            {areas.map((area) => (
              <option value={area} key={area}>
                {area}
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

      {needsLogin && (
        <section className="login-panel">
          <div className="login-panel-copy">
            <LockKeyhole size={24} />
            <div>
              <h2>Acesso ao dashboard</h2>
              <p>Informe a senha de leitura da Inteligencia de Mercado.</p>
            </div>
          </div>
          <form onSubmit={submitLogin} className="login-form">
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Senha do dashboard"
              autoComplete="current-password"
            />
            <button type="submit" disabled={authenticating || !password}>
              <LogIn size={16} />
              {authenticating ? 'Entrando' : 'Entrar'}
            </button>
          </form>
          {loginError && <span className="login-error">{loginError}</span>}
        </section>
      )}

      {summary?.warnings.map((warning) => (
        <section className="notice" key={warning}>
          <AlertTriangle size={18} />
          <span>{warning}</span>
        </section>
      ))}

      {!needsLogin && <nav className="tabs intelligence-tabs" aria-label="Campos de atuacao">
        {INTELLIGENCE_TABS.map((item) => (
          <button key={item.key} className={intelligenceTab === item.key ? 'active' : ''} onClick={() => setIntelligenceTab(item.key)}>
            {item.label}
          </button>
        ))}
      </nav>}

      {!needsLogin && intelligenceTab === 'executive' && (
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

      {!needsLogin && intelligenceTab === 'commercial' && (
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
            <Panel title="Vendas por mes" icon={<BarChart3 size={17} />} wide>
              <ChartFrame>
                <ResponsiveContainer>
                  <BarChart data={monthlySales}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="mes_label" />
                    <YAxis tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                    <Tooltip formatter={(value, name) => [name === 'valor_numero' ? money(String(value)) : formatNumber(String(value)), name === 'valor_numero' ? 'Valor total' : 'Peso']} />
                    <Bar dataKey="valor_numero" fill="#253575" radius={[5, 5, 0, 0]} />
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

      {!needsLogin && intelligenceTab === 'clients' && (
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

      {!needsLogin && intelligenceTab === 'segments' && (
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

      {!needsLogin && intelligenceTab === 'products' && (
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

      {!needsLogin && intelligenceTab === 'prices' && (
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

      {!needsLogin && intelligenceTab === 'margin' && (
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

      {!needsLogin && intelligenceTab === 'quotes' && (
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

      {!needsLogin && intelligenceTab === 'competition' && (
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

      {!needsLogin && intelligenceTab === 'map' && (
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

      {!needsLogin && intelligenceTab === 'forecast' && (
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

      {!needsLogin && ['stock', 'purchases', 'logistics'].includes(intelligenceTab) && (
        <UnavailableTab title={INTELLIGENCE_TABS.find((item) => item.key === intelligenceTab)?.label.replace(/^\d+\s/, '') ?? 'Visao'} />
      )}

    </main>
  )
}

function Kpi({ title, value, displayValue, detail, icon }: { title: string; value?: number; displayValue?: string; detail: string; icon: ReactNode }) {
  return (
    <article className="kpi-card">
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

function SupportDetails({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="support-details">
      <summary>{title}</summary>
      <div>{children}</div>
    </details>
  )
}

function DataTable({ columns, rows, empty }: { columns: string[]; rows: string[][]; empty: string }) {
  return (
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
}

export default App
