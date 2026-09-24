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
  Cell,
  Line,
  LineChart as ReLineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { DashboardAuthError, DashboardSummary, fetchInternalDashboard, loginDashboard } from './api'
import abrLogoWhite from './abr-logo-white.svg'

const STATUS_LABELS: Record<string, string> = {
  validated: 'Validado',
  validated_empty: 'Sem registro',
  deprioritized: 'Fora da prioridade',
  candidate: 'Candidato',
  training: 'Em treino',
}

const COLORS = ['#253575', '#F18800', '#12805C', '#B42318', '#6B7280', '#3B82F6']
const DEFAULT_DATE_FROM = '2026-01-01'
const DEFAULT_DATE_TO = new Date().toISOString().slice(0, 10)

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

const INTELLIGENCE_TABS: Array<{ key: IntelligenceTab; label: string; icon: ReactNode }> = [
  { key: 'executive', label: '01 Executivo', icon: <Gauge size={16} /> },
  { key: 'commercial', label: '02 Comercial', icon: <CircleDollarSign size={16} /> },
  { key: 'clients', label: '03 Clientes', icon: <CheckCircle2 size={16} /> },
  { key: 'segments', label: '04 Segmentos', icon: <BarChart3 size={16} /> },
  { key: 'products', label: '05 Produtos', icon: <Boxes size={16} /> },
  { key: 'prices', label: '06 Precos', icon: <LineChartIcon size={16} /> },
  { key: 'margin', label: '07 Margem', icon: <AreaIcon size={16} /> },
  { key: 'quotes', label: '08 Cotacoes', icon: <TableProperties size={16} /> },
  { key: 'competition', label: '09 Concorrencia', icon: <AlertTriangle size={16} /> },
  { key: 'stock', label: '10 Estoque', icon: <Boxes size={16} /> },
  { key: 'purchases', label: '11 Compras', icon: <Database size={16} /> },
  { key: 'forecast', label: '12 Forecast', icon: <LineChartIcon size={16} /> },
  { key: 'logistics', label: '13 Logistica', icon: <SlidersHorizontal size={16} /> },
  { key: 'map', label: '14 Mapa Comercial', icon: <AreaIcon size={16} /> },
]

const MODULES: Record<IntelligenceTab, string[]> = {
  executive: ['Toneladas vendidas mes a mes', 'Receita e margem mes a mes', 'Preco medio R$/kg', 'Carteira e conversao'],
  commercial: ['Volume x margem por vendedor', 'Receita por vendedor', 'Meta x realizado', 'Clientes ativos e reativados'],
  clients: ['Curva ABC', 'Principais clientes em queda', 'RFM', 'Dias desde ultima compra'],
  segments: ['Segmento x toneladas', 'Evolucao mensal por segmento', 'Preco/kg por segmento', 'Margem por segmento'],
  products: ['Familia x toneladas', 'Top SKU', 'SKU em queda', 'Familia x segmento'],
  prices: ['Preco medio R$/kg', 'Minimo x medio x maximo', 'Preco x toneladas', 'Outliers comerciais'],
  margin: ['MCII por mes', 'MCII % por mes', 'MCII/kg por cliente', 'Volume x margem por cliente'],
  quotes: ['Kg cotados x vendidos', 'Conversao mensal', 'Conversao por vendedor', 'Funil comercial'],
  competition: ['Motivo das perdas', 'Perdas por concorrente', 'Diferenca de preco', 'Elasticidade real'],
  stock: ['Estoque em toneladas', 'Estoque x venda', 'Aging', 'Cobertura x margem'],
  purchases: ['Compras mensais', 'R$/kg de compra', 'Compra por fornecedor', 'Preco fornecedor x volume'],
  forecast: ['Real x previsto', 'Forecast por familia', 'Forecast por segmento', 'Necessidade estimada de compra'],
  logistics: ['Frete R$/t', 'Frete por cidade', 'Frete % da venda', 'Custo logistico x margem'],
  map: ['Bolhas por cidade', 'Faturamento por municipio', 'Clientes por cidade', 'Potencial externo futuro'],
}

type ChartRow = {
  name: string
  valor_numero: number
  peso_numero: number
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
  const requirements = summary?.requirements ?? []
  const areas = useMemo(() => Array.from(new Set(reports.map((item) => item.area))).sort(), [reports])

  const coverageData = [
    { name: 'Cobertos', value: summary?.kpis.requirements_covered ?? 0 },
    {
      name: 'Com lacuna',
      value: Math.max(
        0,
        (summary?.kpis.requirements_total ?? 0) - (summary?.kpis.requirements_covered ?? 0),
      ),
    },
  ]

  const monthlySales = (summary?.sales_summary?.monthly ?? []).map((item) => ({
    ...item,
    mes_label: monthLabel(item.mes),
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
  }))
  const familyRows: ChartRow[] = (summary?.sales_summary?.families ?? []).map((item) => ({
    name: item.familia,
    valor_numero: Number(item.valor_total),
    peso_numero: Number(item.peso_total),
    linhas: item.linhas,
  }))

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
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>}

      {!needsLogin && <section className="kpi-grid">
        <Kpi title="Valor total" displayValue={money(summary?.sales_summary?.valor_total)} detail={`${formatNumber(summary?.sales_summary?.linhas)} vendas por item`} icon={<CircleDollarSign />} />
        <Kpi title="Receita liquida" displayValue={money(summary?.sales_summary?.receita_liquida)} detail="Periodo filtrado" icon={<BarChart3 />} />
        <Kpi title="Lucro bruto" displayValue={money(summary?.sales_summary?.lucro_bruto)} detail={`${summary?.kpis.reports_validated ?? 0} relatorios validados`} icon={<LineChartIcon />} />
        <Kpi title="Peso vendido" displayValue={`${formatNumber(summary?.sales_summary?.peso_total)} kg`} detail={`${formatNumber(summary?.sales_summary?.clientes)} clientes distintos`} icon={<Boxes />} />
      </section>}

      {!needsLogin && intelligenceTab === 'executive' && (
        <section className="dashboard-grid">
          <Panel title="Toneladas vendidas mes a mes" icon={<LineChartIcon size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={monthlySales}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => formatNumber(value)} />
                  <Tooltip formatter={(value) => [`${formatNumber(String(value))} kg`, 'Peso']} />
                  <Line type="monotone" dataKey="peso_numero" stroke="#253575" strokeWidth={3} dot={{ r: 3 }} />
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
                  <Tooltip formatter={(value) => [money(String(value)), 'Valor total']} />
                  <Line type="monotone" dataKey="valor_numero" stroke="#F18800" strokeWidth={3} dot={{ r: 3 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Receita e margem por mes" icon={<BarChart3 size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={monthlySales}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <Tooltip formatter={(value) => [money(String(value)), 'Valor total']} />
                  <Bar dataKey="valor_numero" fill="#253575" radius={[5, 5, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Preco medio R$/kg" icon={<LineChartIcon size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <ReLineChart data={monthlySales.map((item) => ({ ...item, preco_numero: item.peso_numero ? item.valor_numero / item.peso_numero : 0 }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="mes_label" />
                  <YAxis tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
                  <Tooltip formatter={(value) => [money(String(value)), 'R$/kg']} />
                  <Line type="monotone" dataKey="preco_numero" stroke="#12805C" strokeWidth={3} dot={{ r: 3 }} />
                </ReLineChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Carteira e conversao" icon={<TableProperties size={17} />} wide>
            <SupportDetails title="Fontes e proximas camadas">
              <SourceList items={requirements.filter((item) => item.key.includes('pedidos') || item.key.includes('vendas'))} />
            </SupportDetails>
          </Panel>
        </section>
      )}

      {!needsLogin && intelligenceTab === 'commercial' && (
        <>
          <section className="kpi-grid sales-kpis">
            <Kpi title="Valor total" displayValue={money(summary?.sales_summary?.valor_total)} detail={`${formatNumber(summary?.sales_summary?.linhas)} linhas`} icon={<CircleDollarSign />} />
            <Kpi title="Receita liquida" displayValue={money(summary?.sales_summary?.receita_liquida)} detail="Base de venda por item" icon={<BarChart3 />} />
            <Kpi title="Lucro bruto" displayValue={money(summary?.sales_summary?.lucro_bruto)} detail="Margem antes dos rateios" icon={<LineChartIcon />} />
            <Kpi title="Peso total" displayValue={`${formatNumber(summary?.sales_summary?.peso_total)} kg`} detail={`${money(summary?.sales_summary?.preco_medio_kg)} por kg`} icon={<Boxes />} />
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
            <Panel title="Fontes comerciais" icon={<Database size={17} />}>
              <SupportDetails title="Ver fontes comerciais">
                <SourceList items={requirements.filter((item) => item.key.includes('vendas') || item.key.includes('clientes') || item.key.includes('pedidos'))} />
              </SupportDetails>
            </Panel>
          </section>
        </>
      )}

      {!needsLogin && intelligenceTab !== 'executive' && intelligenceTab !== 'commercial' && (
        <AnalysisTab
          tab={intelligenceTab}
          modules={MODULES[intelligenceTab]}
          monthlySales={monthlySales}
          familyRows={familyRows}
          requirements={requirements}
        />
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

function AnalysisTab({
  tab,
  modules,
  monthlySales,
  familyRows,
  requirements,
}: {
  tab: IntelligenceTab
  modules: string[]
  monthlySales: Array<{ mes_label: string; valor_numero: number; peso_numero: number }>
  familyRows: ChartRow[]
  requirements: DashboardSummary['requirements']
}) {
  const valueLabel = tab === 'prices' || tab === 'margin' ? 'R$/kg' : 'Valor total'
  const priceRows = familyRows.map((item) => ({
    ...item,
    preco_numero: item.peso_numero ? item.valor_numero / item.peso_numero : 0,
  }))

  return (
    <section className="dashboard-grid">
      <Panel title={modules[0]} icon={<BarChart3 size={17} />}>
        <ChartFrame>
          <ResponsiveContainer>
            <BarChart data={familyRows.slice(0, 8)} layout="vertical" margin={{ left: 92 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
              <YAxis type="category" dataKey="name" width={120} />
              <Tooltip formatter={(value) => [money(String(value)), 'Valor total']} />
              <Bar dataKey="valor_numero" fill="#253575" radius={[0, 5, 5, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </Panel>

      <Panel title={modules[1]} icon={<LineChartIcon size={17} />}>
        <ChartFrame>
          <ResponsiveContainer>
            <ReLineChart data={monthlySales}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="mes_label" />
              <YAxis tickFormatter={(value) => formatNumber(value)} />
              <Tooltip formatter={(value) => [`${formatNumber(String(value))} kg`, 'Peso']} />
              <Line type="monotone" dataKey="peso_numero" stroke="#F18800" strokeWidth={3} dot={{ r: 3 }} />
            </ReLineChart>
          </ResponsiveContainer>
        </ChartFrame>
      </Panel>

      <Panel title={modules[2]} icon={<CircleDollarSign size={17} />}>
        <ChartFrame>
          <ResponsiveContainer>
            <BarChart data={priceRows.slice(0, 8)} layout="vertical" margin={{ left: 92 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickFormatter={(value) => money(value).replace('R$', 'R$ ')} />
              <YAxis type="category" dataKey="name" width={120} />
              <Tooltip formatter={(value) => [money(String(value)), valueLabel]} />
              <Bar dataKey="preco_numero" fill="#12805C" radius={[0, 5, 5, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </Panel>

      <Panel title={modules[3]} icon={<AreaIcon size={17} />}>
        <ChartFrame>
          <ResponsiveContainer>
            <BarChart data={familyRows.slice(0, 8)}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" hide />
              <YAxis tickFormatter={(value) => formatNumber(value)} />
              <Tooltip formatter={(value) => [`${formatNumber(String(value))} kg`, 'Peso']} />
              <Bar dataKey="peso_numero" fill="#6B7280" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </Panel>

      <Panel title="Apoio tecnico" icon={<Database size={17} />} wide>
        <SupportDetails title="Ver fontes e requisitos relacionados">
          <SourceList items={requirements} />
        </SupportDetails>
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

function DecisionList({ items }: { items: string[] }) {
  return (
    <div className="decision-list">
      {items.map((item, index) => (
        <article className="decision-item" key={item}>
          <span>{String(index + 1).padStart(2, '0')}</span>
          <strong>{item}</strong>
        </article>
      ))}
    </div>
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

function ReportTable({ reports }: { reports: DashboardSummary['reports'] }) {
  return (
    <DataTable
      columns={['ID', 'Relatorio', 'Area', 'Status', 'Entregaveis']}
      rows={reports.map((report) => [
        report.query_id,
        report.name,
        report.area,
        STATUS_LABELS[report.automation_status] ?? report.automation_status,
        report.deliverables.length ? report.deliverables.join(', ') : '-',
      ])}
      empty="Nenhum relatorio no filtro atual."
    />
  )
}

function SourceList({ items }: { items: DashboardSummary['requirements'] }) {
  return (
    <div className="source-stack">
      {items.length === 0 ? (
        <p className="empty-text">Sem itens para este recorte.</p>
      ) : (
        items.map((item) => (
          <article className="source-item" key={item.key}>
            <strong>{item.title}</strong>
            <span>{item.known_sources.length ? item.known_sources.join(', ') : 'Sem fonte confirmada'}</span>
            <small>{item.gaps[0] ?? item.objective}</small>
          </article>
        ))
      )}
    </div>
  )
}

export default App
