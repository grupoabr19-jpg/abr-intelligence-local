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
  LineChart,
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

type Tab = 'overview' | 'sales' | 'stock' | 'operations' | 'sources'

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

function App() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
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

  const filteredReports = reports.filter((report) => {
    const statusOk = statusFilter === 'todos' || report.automation_status === statusFilter
    const areaOk = areaFilter === 'todas' || report.area === areaFilter
    const needle = search.trim().toLowerCase()
    const searchOk =
      !needle ||
      `${report.query_id} ${report.name} ${report.area} ${report.entity}`.toLowerCase().includes(needle)
    return statusOk && areaOk && searchOk
  })

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

  const tabs: Array<{ key: Tab; label: string; icon: ReactNode }> = [
    { key: 'overview', label: 'Visao geral', icon: <Gauge size={16} /> },
    { key: 'sales', label: 'Vendas', icon: <CircleDollarSign size={16} /> },
    { key: 'stock', label: 'Estoque', icon: <Boxes size={16} /> },
    { key: 'operations', label: 'Operacao', icon: <TableProperties size={16} /> },
    { key: 'sources', label: 'Fontes', icon: <Database size={16} /> },
  ]

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
                Backend trata os dados
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

      {!needsLogin && <nav className="tabs" aria-label="Abas de analise">
        {tabs.map((item) => (
          <button key={item.key} className={tab === item.key ? 'active' : ''} onClick={() => setTab(item.key)}>
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>}

      {!needsLogin && <section className="kpi-grid">
        <Kpi title="Valor total" displayValue={money(summary?.sales_summary?.valor_total)} detail={`${formatNumber(summary?.sales_summary?.linhas)} vendas por item`} icon={<CircleDollarSign />} />
        <Kpi title="Receita liquida" displayValue={money(summary?.sales_summary?.receita_liquida)} detail="Periodo filtrado" icon={<BarChart3 />} />
        <Kpi title="Lucro bruto" displayValue={money(summary?.sales_summary?.lucro_bruto)} detail={`${summary?.kpis.reports_validated ?? 0} relatorios validados`} icon={<LineChart />} />
        <Kpi title="Peso vendido" displayValue={`${formatNumber(summary?.sales_summary?.peso_total)} kg`} detail={`${formatNumber(summary?.sales_summary?.clientes)} clientes distintos`} icon={<Boxes />} />
      </section>}

      {!needsLogin && tab === 'overview' && (
        <section className="dashboard-grid">
          <Panel title="Relatorios por status" icon={<BarChart3 size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={summary?.reports_by_status ?? []}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="status" tickFormatter={(value) => STATUS_LABELS[value] ?? value} />
                  <YAxis allowDecimals={false} />
                  <Tooltip labelFormatter={(value) => STATUS_LABELS[String(value)] ?? value} />
                  <Bar dataKey="total" radius={[5, 5, 0, 0]}>
                    {(summary?.reports_by_status ?? []).map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Cobertura dos requisitos" icon={<AreaIcon size={17} />}>
            <ChartFrame>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={coverageData} dataKey="value" nameKey="name" innerRadius={58} outerRadius={92} paddingAngle={4}>
                    {coverageData.map((_, index) => (
                      <Cell key={index} fill={index === 0 ? '#12805C' : '#F18800'} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>

          <Panel title="Areas de relatorio" icon={<TableProperties size={17} />} wide>
            <ChartFrame>
              <ResponsiveContainer>
                <BarChart data={summary?.reports_by_area ?? []} layout="vertical" margin={{ left: 70 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" allowDecimals={false} />
                  <YAxis type="category" dataKey="area" width={130} />
                  <Tooltip />
                  <Bar dataKey="total" fill="#253575" radius={[0, 5, 5, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartFrame>
          </Panel>
        </section>
      )}

      {!needsLogin && tab === 'sales' && (
        <>
          <section className="kpi-grid sales-kpis">
            <Kpi title="Valor total" displayValue={money(summary?.sales_summary?.valor_total)} detail={`${formatNumber(summary?.sales_summary?.linhas)} linhas`} icon={<CircleDollarSign />} />
            <Kpi title="Receita liquida" displayValue={money(summary?.sales_summary?.receita_liquida)} detail="Base de venda por item" icon={<BarChart3 />} />
            <Kpi title="Lucro bruto" displayValue={money(summary?.sales_summary?.lucro_bruto)} detail="Margem antes dos rateios" icon={<LineChart />} />
            <Kpi title="Peso total" displayValue={`${formatNumber(summary?.sales_summary?.peso_total)} kg`} detail={`${money(summary?.sales_summary?.preco_medio_kg)} por kg`} icon={<Boxes />} />
            <Kpi title="Clientes" value={summary?.sales_summary?.clientes} detail="Clientes distintos no periodo" icon={<CheckCircle2 />} />
            <Kpi title="Itens" value={summary?.sales_summary?.itens} detail="Itens distintos vendidos" icon={<TableProperties />} />
          </section>

          <section className="dashboard-grid">
            <Panel title="Vendas por mes" icon={<BarChart3 size={17} />} wide>
              <ChartFrame>
                <ResponsiveContainer>
                  <BarChart data={(summary?.sales_summary?.monthly ?? []).map((item) => ({
                    ...item,
                    mes_label: monthLabel(item.mes),
                    valor_numero: Number(item.valor_total),
                    peso_numero: Number(item.peso_total),
                  }))}>
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
              <SourceList items={requirements.filter((item) => item.key.includes('vendas') || item.key.includes('clientes') || item.key.includes('pedidos'))} />
            </Panel>
          </section>
        </>
      )}

      {!needsLogin && tab === 'stock' && (
        <section className="dashboard-grid">
          <Panel title="Relatorios de estoque" icon={<Boxes size={17} />} wide>
            <ReportTable reports={filteredReports.filter((item) => item.area.includes('estoque'))} />
          </Panel>
          <Panel title="Staging por entidade" icon={<Database size={17} />}>
            <DataTable
              columns={['Entidade', 'Linhas']}
              rows={(summary?.staging_by_entity ?? []).map((item) => [item.entidade, formatNumber(item.linhas)])}
              empty="Sem staging consultavel agora."
            />
          </Panel>
        </section>
      )}

      {!needsLogin && tab === 'operations' && (
        <section className="dashboard-grid">
          <Panel title="Historico recente" icon={<LineChart size={17} />} wide>
            <DataTable
              columns={['Entidade', 'Sync', 'Status', 'Lidos', 'Inseridos']}
              rows={(summary?.recent_history ?? []).map((item) => [
                item.entidade,
                item.sync_id,
                item.status,
                formatNumber(item.registros_lidos),
                formatNumber(item.registros_inseridos),
              ])}
              empty="Nenhuma carga recente localizada."
            />
          </Panel>
          <Panel title="Requisitos com lacuna" icon={<AlertTriangle size={17} />}>
            <SourceList items={requirements.filter((item) => item.gaps.length > 0)} />
          </Panel>
        </section>
      )}

      {!needsLogin && tab === 'sources' && (
        <section className="dashboard-grid">
          <Panel title="Relatorios filtrados" icon={<Filter size={17} />} wide>
            <ReportTable reports={filteredReports} />
          </Panel>
          <Panel title="Planilhas internas" icon={<Database size={17} />}>
            <div className="source-stack">
              {(summary?.external_spreadsheet_sources ?? []).map((source) => (
                <article className="source-item" key={source.key}>
                  <strong>{source.title}</strong>
                  <span>{source.local_path}</span>
                  <small>{source.likely_coverage.join(', ')}</small>
                </article>
              ))}
            </div>
          </Panel>
        </section>
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
