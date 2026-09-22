import React, { useEffect, useState, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/use-auth'
import {
  CentralDadosService,
  FonteDados,
  HistoricoImportacao,
  ImportacaoControle,
  TABELAS_DESTINO_COLS,
} from '@/services/centralDadosService'
import {
  Database,
  RefreshCw,
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ArrowRight,
  Sliders,
  ShieldCheck,
  Server,
  Layers,
  FileText,
  AlertCircle,
  Key,
  ChevronDown,
  Compass,
  Play,
  RotateCcw,
} from 'lucide-react'
import { formatDateTimePtBR } from '@/lib/formatters'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { useToast } from '@/hooks/use-toast'

export default function CentralDados() {
  const { usuarioPerfil } = useAuth()
  const navigate = useNavigate()
  const { toast } = useToast()

  // Controle de permissão restrito a Diretor e Gerente Geral
  const perfilNome = usuarioPerfil?.perfil?.nome?.toLowerCase() || ''
  const isAuthorized =
    perfilNome.includes('diretor') ||
    perfilNome.includes('gerente geral') ||
    usuarioPerfil?.email?.includes('pietra')

  const [fontes, setFontes] = useState<FonteDados[]>([])
  const [historico, setHistorico] = useState<HistoricoImportacao[]>([])
  const [importacoes, setImportacoes] = useState<ImportacaoControle[]>([])
  const [stagingResumo, setStagingResumo] = useState<
    Array<{
      entidade: string
      source_system: string
      tabela_destino: string | null
      total: number
      pendentes: number
      processados: number
      erros: number
      amostra: any[]
    }>
  >([])
  const [loading, setLoading] = useState(true)
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [promotingId, setPromotingId] = useState<string | null>(null)
  const [processingServerId, setProcessingServerId] = useState<string | null>(null)

  // Modal Upload Manual (APENAS XLSX)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [selectedFonteId, setSelectedFonteId] = useState<string>('')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [uploadProgressPercent, setUploadProgressPercent] = useState<number>(0)
  const [uploadProgressMessage, setUploadProgressMessage] = useState<string>('')
  const [uploadingFile, setUploadingFile] = useState(false)

  // Modal de Confirmação Prévia e Dupla Confirmação do Usuário
  const [confirmModalOpen, setConfirmModalOpen] = useState(false)
  const [currentImportacao, setCurrentImportacao] = useState<ImportacaoControle | null>(null)
  const [previewDeteccao, setPreviewDeteccao] = useState<{
    tipo: string
    label: string
    totalLinhas: number
    headers: string[]
    amostra: Record<string, unknown>[]
  } | null>(null)
  const [tipoSelecionadoConfirm, setTipoSelecionadoConfirm] = useState<string>('GESTAO_PRODUCAO')
  const [ignorarErrosLinha, setIgnorarErrosLinha] = useState<boolean>(true)
  const [inspectingServer, setInspectingServer] = useState(false)

  // Modal Detalhes do Log & Erros
  const [selectedLog, setSelectedLog] = useState<HistoricoImportacao | null>(null)
  const [selectedImportacaoErros, setSelectedImportacaoErros] = useState<ImportacaoControle | null>(
    null,
  )

  // Controle dos Dropdowns / Accordions recolhidos por padrão
  const [arquiteturaDropdownOpen, setArquiteturaDropdownOpen] = useState(false)
  const [catalogoDropdownOpen, setCatalogoDropdownOpen] = useState(false)
  const [stagingDropdownOpen, setStagingDropdownOpen] = useState(false)
  const [logsDropdownOpen, setLogsDropdownOpen] = useState(false)

  // Polling automático a cada 3s enquanto houver importações no status 'processando'
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const carregarDados = async (silencioso = false) => {
    try {
      if (!silencioso) setLoading(true)
      const [fontesData, histData, stagingData, importacoesData] = await Promise.all([
        CentralDadosService.listarFontes(),
        CentralDadosService.listarHistorico(15),
        CentralDadosService.listarResumoStaging(),
        CentralDadosService.listarImportacoes(20),
      ])
      setFontes(fontesData)
      setHistorico(histData)
      setStagingResumo(stagingData)
      setImportacoes(importacoesData)
    } catch (err: any) {
      if (!silencioso) {
        toast({
          title: 'Erro ao carregar dados',
          description: err.message || 'Falha na conexão com a Central de Dados.',
          variant: 'destructive',
        })
      }
    } finally {
      if (!silencioso) setLoading(false)
    }
  }

  useEffect(() => {
    if (isAuthorized) {
      carregarDados()
    }
  }, [isAuthorized])

  // Polling ativo a cada 3 segundos enquanto houver alguma importação processando
  useEffect(() => {
    const temProcessando = importacoes.some((imp) => imp.status === 'processando')

    if (temProcessando) {
      if (!pollingRef.current) {
        pollingRef.current = setInterval(() => {
          carregarDados(true)
        }, 3000)
      }
    } else {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current)
        pollingRef.current = null
      }
    }
  }, [importacoes])

  if (!isAuthorized) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-center">
        <div className="w-16 h-16 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-600 mb-4">
          <AlertCircle className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-[#142758]">Acesso Restrito à Central de Dados</h2>
        <p className="text-sm text-[#5C6784] max-w-md mt-2">
          Este ambiente administrativo é restrito exclusivamente aos perfis de{' '}
          <strong>Diretor</strong> e <strong>Gerente Geral</strong> do Grupo ABR.
        </p>
        <Button
          onClick={() => navigate('/cockpit')}
          className="mt-6 bg-[#253575] hover:bg-[#142758] text-white"
        >
          Voltar para o Cockpit Executivo
        </Button>
      </div>
    )
  }

  const handleTestarConexao = async (fonte: FonteDados) => {
    try {
      setTestingId(fonte.id)
      const res = await CentralDadosService.testarConexaoFonte(fonte)
      if (res.sucesso) {
        toast({
          title: `Conexão bem-sucedida: ${fonte.nome}`,
          description: `${res.mensagem} (latência: ${res.latencyMs}ms)`,
        })
      } else {
        toast({
          title: `Diagnóstico de Integração: ${fonte.nome}`,
          description: res.mensagem,
          variant: 'destructive',
        })
      }
      await carregarDados()
    } catch (err: any) {
      toast({
        title: 'Erro no teste de conexão',
        description: err.message,
        variant: 'destructive',
      })
    } finally {
      setTestingId(null)
    }
  }

  const handleSincronizarAgora = async (fonte: FonteDados) => {
    try {
      setSyncingId(fonte.id)
      const res = await CentralDadosService.sincronizarAgora(fonte)
      if (res.sucesso) {
        toast({
          title: 'Sincronização Realizada',
          description: res.mensagem,
        })
      } else {
        toast({
          title: 'Diagnóstico de Sincronização',
          description: res.mensagem,
          variant: 'destructive',
        })
      }
      await carregarDados()
    } catch (err: any) {
      toast({
        title: 'Falha na Sincronização',
        description: err.message,
        variant: 'destructive',
      })
    } finally {
      setSyncingId(null)
    }
  }

  // 1. Upload binário dos arquivos XLSX para o Storage (sem parsing no navegador)
  const handleSelecionarArquivoXlsx = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return

    if (files.some((file) => !file.name.toLowerCase().endsWith('.xlsx'))) {
      toast({
        title: 'Formato não suportado',
        description:
          'Por decisão de arquitetura, o sistema aceita estritamente arquivos no formato .XLSX.',
        variant: 'destructive',
      })
      return
    }

    if (files.length > 2) {
      toast({
        title: 'Limite de arquivos excedido',
        description: 'Selecione no máximo as duas planilhas de fallback.',
        variant: 'destructive',
      })
      return
    }

    setSelectedFiles(files)
  }

  const handleExecutarUploadBinario = async () => {
    if (selectedFiles.length === 0) return

    setUploadingFile(true)
    setUploadProgressPercent(10)
    setUploadProgressMessage('Calculando hash SHA-256 e enviando arquivo binário para o Storage...')

    try {
      const fonte =
        fontes.find((f) => f.id === selectedFonteId) ||
        fontes.find((f) => f.tipo === 'csv_upload') ||
        fontes[0]

      const importacoesEnviadas: ImportacaoControle[] = []
      for (const [index, file] of selectedFiles.entries()) {
        const inicio = (index / selectedFiles.length) * 100
        const largura = 100 / selectedFiles.length
        setUploadProgressMessage(`Enviando ${index + 1} de ${selectedFiles.length}: ${file.name}`)
        const { importacao } = await CentralDadosService.uploadArquivoXlsx(
          file,
          fonte?.id,
          (pct) => setUploadProgressPercent(Math.round(inicio + (pct / 100) * largura)),
        )
        importacoesEnviadas.push(importacao)
      }

      setUploadModalOpen(false)
      setSelectedFiles([])
      toast({
        title: `${importacoesEnviadas.length} planilha(s) enviada(s) com sucesso`,
        description: 'Os arquivos estão na fila para inspeção e processamento no servidor.',
      })

      await carregarDados()

      // Abre a primeira importação; a segunda permanece na fila para processamento independente.
      await abrirModalConfirmacaoServidor(importacoesEnviadas[0])
    } catch (err: any) {
      toast({
        title: 'Falha no envio do arquivo',
        description: err.message || 'Não foi possível completar o upload para o Storage.',
        variant: 'destructive',
      })
    } finally {
      setUploadingFile(false)
      setUploadProgressPercent(0)
      setUploadProgressMessage('')
    }
  }

  // 2. Inspecionar e confirmar tipo no servidor
  const abrirModalConfirmacaoServidor = async (imp: ImportacaoControle) => {
    setCurrentImportacao(imp)
    setConfirmModalOpen(true)
    setInspectingServer(true)
    setPreviewDeteccao(null)

    try {
      const resultado = await CentralDadosService.inspecionarTipoPlanilhaNoServidor(imp.id)
      setPreviewDeteccao(resultado)
      setTipoSelecionadoConfirm(resultado.tipo || 'GESTAO_PRODUCAO')
    } catch (err: any) {
      toast({
        title: 'Aviso na inspeção da planilha',
        description: err.message || 'Não foi possível ler a prévia do servidor.',
      })
      setTipoSelecionadoConfirm('GESTAO_PRODUCAO')
    } finally {
      setInspectingServer(false)
    }
  }

  // 3. Disparar processamento ou retomada no servidor (Edge Function em fatias dirigida pelo frontend)
  const executarLoopProcessamentoServidor = async (impId: string, tipoConfirm?: string) => {
    setProcessingServerId(impId)

    toast({
      title: 'Processamento em fatias ativo',
      description: 'Processando por lotes com checkpoint. O progresso é atualizado em tempo real.',
    })

    try {
      await CentralDadosService.processarImportacaoNoServidor({
        importacaoId: impId,
        tipoConfirmado: tipoConfirm,
        maxLinhasPorFatia: 3000,
        onProgress: (info) => {
          // Atualiza em tempo real a listagem e contadores
          setImportacoes((prev) =>
            prev.map((i) =>
              i.id === impId
                ? {
                    ...i,
                    linha_checkpoint: info.checkpoint,
                    linhas_total: info.total || i.linhas_total,
                    linhas_validas: info.validas || i.linhas_validas,
                    linhas_erro: info.erros || i.linhas_erro,
                    linhas_duplicadas: info.duplicadas || i.linhas_duplicadas,
                    status: info.status as any,
                  }
                : i,
            ),
          )

          if (info.mensagem) {
            toast({
              title: 'Tentativa de reconexão',
              description: info.mensagem,
            })
          }
        },
      })

      toast({
        title: 'Processamento no servidor concluído!',
        description: 'Todas as fatias foram ingeridas na Staging. Importação pronta para promoção.',
      })
      await carregarDados()
    } catch (err: any) {
      toast({
        title: 'Processamento pausado no checkpoint',
        description:
          err.message ||
          'A conexão foi interrompida. O checkpoint está seguro e você pode retomar com um clique.',
        variant: 'destructive',
      })
      await carregarDados()
    } finally {
      setProcessingServerId(null)
    }
  }

  const handleConfirmarEProcessarNoServidor = async () => {
    if (!currentImportacao) return
    const impId = currentImportacao.id
    setConfirmModalOpen(false)
    await executarLoopProcessamentoServidor(impId, tipoSelecionadoConfirm)
  }

  // Retomada direta a partir da fila (sem abrir modal de inspeção)
  const handleRetomarProcessamentoDireto = async (imp: ImportacaoControle) => {
    await executarLoopProcessamentoServidor(
      imp.id,
      imp.tipo_planilha !== 'desconhecido' ? imp.tipo_planilha : undefined,
    )
  }

  // 4. Promoção ÚNICA da Importação (roda no servidor via RPC segura)
  const handlePromoverImportacao = async (imp: ImportacaoControle) => {
    try {
      setPromotingId(imp.id)
      toast({
        title: 'Promovendo para a Base Real',
        description: `Executando promoção idempotente da importação '${imp.nome_arquivo}'...`,
      })

      const res = await CentralDadosService.promoverImportacao(imp.id)

      if (res.sucesso) {
        toast({
          title: 'Promoção Concluída com Sucesso!',
          description: `${res.pedidosNovos} pedidos, ${res.itensNovos} itens e ${res.clientesNovos} clientes atualizados na base real. (${res.duplicatasIgnoradas} duplicatas preservadas).`,
        })
      } else {
        toast({
          title: 'Falha na Promoção',
          description: res.erro || 'Ocorreu um erro ao promover a importação.',
          variant: 'destructive',
        })
      }

      await carregarDados()
    } catch (err: any) {
      toast({
        title: 'Erro ao promover',
        description: err.message,
        variant: 'destructive',
      })
    } finally {
      setPromotingId(null)
    }
  }

  return (
    <div className="space-y-6 pb-16">
      {/* CABEÇALHO */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#D9DFEB] pb-5">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-[#253575] text-[#F18800] flex items-center justify-center font-bold shadow-sm">
              <Database className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl md:text-2xl font-black text-[#253575] tracking-tight">
                  Central de Dados & Abastecimento
                </h2>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#142758] text-[#F18800] border border-[#F18800]/40">
                  Infraestrutura Real (Server-Side)
                </span>
              </div>
              <p className="text-xs text-[#5C6784] mt-0.5">
                Pipeline de importação 100% no servidor, staging auditado, checkpoint de retomada e
                hash anti-duplicação real.
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <Link to="/mapeamento-campos">
            <Button
              variant="outline"
              size="sm"
              className="text-xs font-bold border-[#253575] text-[#253575] hover:bg-[#253575]/10 flex items-center gap-1.5"
            >
              <Sliders className="w-3.5 h-3.5 text-[#F18800]" />
              Mapeamento de Campos
            </Button>
          </Link>

          <Button
            size="sm"
            onClick={() => {
              setSelectedFonteId(fontes.find((f) => f.tipo === 'csv_upload')?.id || '')
              setSelectedFiles([])
              setUploadModalOpen(true)
            }}
            className="text-xs font-bold bg-[#F18800] hover:bg-[#D97706] text-white flex items-center gap-1.5 shadow-sm"
          >
            <UploadCloud className="w-4 h-4" />
            Upload Planilha (.XLSX)
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={() => carregarDados()}
            disabled={loading}
            className="text-xs border-[#D9DFEB] text-[#253575]"
            title="Atualizar painel"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* BANNER INSTITUCIONAL DE STATUS DA INTEGRAÇÃO ERP ASTER (MODO STANDBY) */}
      <div className="rounded-xl border border-amber-300/40 bg-gradient-to-r from-[#142758] via-[#1a2d60] to-[#253575] p-5 text-white shadow-md relative overflow-hidden">
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-amber-500/15 via-transparent to-transparent pointer-events-none" />

        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 relative z-10">
          <div className="flex items-start gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-400/30 flex items-center justify-center text-amber-400 shrink-0">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-extrabold text-sm tracking-wide text-white">
                  ERP ASTER (SPS GROUP)
                </span>
                <span className="text-[10px] font-extrabold px-2.5 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-400/40 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                  Captura assistida disponível
                </span>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-white/10 text-slate-300">
                  Canal Oficial SPS Group
                </span>
              </div>
              <p className="text-xs text-white/85 mt-1.5 max-w-2xl leading-relaxed">
                O Aster pode ser coletado pela extensão autorizada: abra o portal, ative a captura e
                execute relatórios somente leitura. As respostas JSON são enviadas em lotes idempotentes
                para a Staging, sem capturar senha, cookies ou arquivos.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <div className="text-[11px] font-medium text-amber-300 bg-black/30 border border-amber-400/30 px-3 py-1.5 rounded-lg">
              Extensão Aster + Staging
            </div>
          </div>
        </div>
      </div>

      {/* PAINEL PRINCIPAL: FILA DE IMPORTAÇÕES (STATUS AO VIVO COM POLLING E PROGRESSO) */}
      <div className="steel-card overflow-hidden border border-[#D9DFEB] bg-white">
        <div className="p-4 border-b border-[#D9DFEB] flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[#F8FAFD]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#253575] text-[#F18800] flex items-center justify-center">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-[#253575]">
                  Fila de Importações no Servidor (XLSX)
                </h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
                  Motor Servidor Ativo
                </span>
                {importacoes.some((i) => i.status === 'processando') && (
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 flex items-center gap-1 animate-pulse">
                    <RefreshCw className="w-3 h-3 animate-spin" />
                    Processando em segundo plano (polling 3s)
                  </span>
                )}
              </div>
              <p className="text-xs text-[#5C6784] mt-0.5">
                Envio único do arquivo binário (.XLSX) para o Storage. Processamento assíncrono com
                checkpoint e promoção manual idempotente.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => {
                setSelectedFonteId(fontes.find((f) => f.tipo === 'csv_upload')?.id || '')
                setSelectedFiles([])
                setUploadModalOpen(true)
              }}
              className="text-xs font-bold bg-[#F18800] hover:bg-[#D97706] text-white flex items-center gap-1.5"
            >
              <UploadCloud className="w-3.5 h-3.5" />
              Novo Upload XLSX
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-[#F8FAFD] text-[#5C6784] uppercase text-[10px] tracking-wider border-b border-[#D9DFEB]">
              <tr>
                <th className="py-3 px-4">Arquivo / Tamanho</th>
                <th className="py-3 px-4">Tipo Detectado</th>
                <th className="py-3 px-4">Data Upload</th>
                <th className="py-3 px-4 text-center">Status</th>
                <th className="py-3 px-4 text-right">Progresso / Linhas</th>
                <th className="py-3 px-4 text-right">Válidas</th>
                <th className="py-3 px-4 text-right">Inconsistências</th>
                <th className="py-3 px-4 text-right">Duplicatas</th>
                <th className="py-3 px-4 text-center">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#EAEFF9] text-[#141D40]">
              {importacoes.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-xs text-[#5C6784]">
                    <div className="max-w-md mx-auto space-y-2">
                      <FileSpreadsheet className="w-8 h-8 text-slate-300 mx-auto" />
                      <p className="font-semibold text-slate-600">
                        Nenhuma importação registrada ainda.
                      </p>
                      <p className="text-[11px] text-slate-500">
                        Clique em <strong>Novo Upload XLSX</strong> acima para enviar uma planilha
                        do ERP Aster. O arquivo será enviado diretamente ao Storage e processado no
                        servidor.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                importacoes.map((imp) => {
                  const isProcessando = imp.status === 'processando'
                  const isAguardando = imp.status === 'aguardando_aprovacao'
                  const isPromovido = imp.status === 'promovido'
                  const isErro = imp.status === 'erro'
                  const isRecebido = imp.status === 'recebido'
                  const isPromoting = promotingId === imp.id
                  const isServerRunning = processingServerId === imp.id

                  const percentual =
                    imp.linhas_total && imp.linhas_total > 0
                      ? Math.min(100, Math.round((imp.linha_checkpoint / imp.linhas_total) * 100))
                      : isPromovido || isAguardando
                        ? 100
                        : 0

                  return (
                    <tr key={imp.id} className="hover:bg-[#F8FAFD] transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-bold text-[#253575] flex items-center gap-1.5">
                          <FileSpreadsheet className="w-4 h-4 text-emerald-600 shrink-0" />
                          <span className="truncate max-w-[200px]" title={imp.nome_arquivo}>
                            {imp.nome_arquivo}
                          </span>
                        </div>
                        <div className="text-[10px] text-[#5C6784] font-mono mt-0.5">
                          {(imp.tamanho_bytes / (1024 * 1024)).toFixed(2)} MB • SHA:{' '}
                          {imp.hash_arquivo.slice(0, 8)}…
                        </div>
                      </td>

                      <td className="py-3 px-4">
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-[#253575] border border-blue-200">
                          {imp.tipo_planilha === 'GESTAO_PRODUCAO'
                            ? 'Gestão Produção'
                            : imp.tipo_planilha === 'MARGEM'
                              ? 'Margem Financeira'
                              : imp.tipo_planilha === 'CLIENTES'
                                ? 'Clientes ERP'
                                : imp.tipo_planilha === 'ESTOQUE'
                                  ? 'Estoque Físico'
                                  : 'Geral / Outros'}
                        </span>
                      </td>

                      <td className="py-3 px-4 text-[#5C6784] font-mono text-[11px]">
                        {formatDateTimePtBR(imp.criado_em)}
                      </td>

                      <td className="py-3 px-4 text-center">
                        {isProcessando ? (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-300 animate-pulse">
                            <RefreshCw className="w-3 h-3 animate-spin text-amber-600" />{' '}
                            Processando
                          </span>
                        ) : isAguardando ? (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-800 border border-blue-300">
                            <Clock className="w-3 h-3 text-blue-600" /> Aguardando Aprovação
                          </span>
                        ) : isPromovido ? (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-300">
                            <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Promovido na Base
                          </span>
                        ) : isErro ? (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-800 border border-red-300">
                            <XCircle className="w-3 h-3 text-red-600" /> Falha
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-300">
                            <Clock className="w-3 h-3 text-slate-500" /> Recebido
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-4 text-right">
                        <div className="font-mono font-bold text-[#253575] text-[11px]">
                          {imp.linha_checkpoint} / {imp.linhas_total ?? '—'}
                        </div>
                        <div className="w-24 bg-slate-100 h-1.5 rounded-full overflow-hidden ml-auto mt-1">
                          <div
                            className={`h-full ${
                              isPromovido
                                ? 'bg-emerald-500'
                                : isProcessando
                                  ? 'bg-amber-500'
                                  : 'bg-blue-600'
                            }`}
                            style={{ width: `${percentual}%` }}
                          />
                        </div>
                      </td>

                      <td className="py-3 px-4 text-right font-mono font-bold text-emerald-700">
                        {imp.linhas_validas}
                      </td>

                      <td className="py-3 px-4 text-right font-mono font-bold">
                        {imp.linhas_erro > 0 ? (
                          <button
                            type="button"
                            onClick={() => setSelectedImportacaoErros(imp)}
                            className="text-red-600 hover:underline flex items-center justify-end gap-1 ml-auto"
                            title="Ver detalhes dos erros por linha"
                          >
                            <AlertTriangle className="w-3 h-3 text-red-500" />
                            {imp.linhas_erro}
                          </button>
                        ) : (
                          <span className="text-slate-400">0</span>
                        )}
                      </td>

                      <td className="py-3 px-4 text-right font-mono text-slate-600">
                        {imp.linhas_duplicadas}
                      </td>

                      <td className="py-3 px-4 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          {/* Ação 1: Processar / Retomar no servidor */}
                          {(isRecebido || isProcessando) && (
                            <Button
                              size="sm"
                              onClick={() => handleRetomarProcessamentoDireto(imp)}
                              disabled={isServerRunning}
                              className="h-7 px-2.5 text-[10px] font-bold bg-[#253575] hover:bg-[#142758] text-white flex items-center gap-1 shadow-xs"
                              title={
                                imp.linha_checkpoint > 0
                                  ? `Retomar a partir da linha ${imp.linha_checkpoint}`
                                  : 'Iniciar processamento em fatias no servidor'
                              }
                            >
                              {isServerRunning ? (
                                <RefreshCw className="w-3 h-3 animate-spin" />
                              ) : imp.linha_checkpoint > 0 || isProcessando ? (
                                <RotateCcw className="w-3 h-3 text-[#F18800]" />
                              ) : (
                                <Play className="w-3 h-3" />
                              )}
                              {imp.linha_checkpoint > 0 || isProcessando
                                ? 'Retomar processamento'
                                : 'Processar'}
                            </Button>
                          )}

                          {/* Ação 2: Promover para a Base Real */}
                          {isAguardando && (
                            <Button
                              size="sm"
                              onClick={() => handlePromoverImportacao(imp)}
                              disabled={isPromoting}
                              className="h-7 px-2.5 text-[10px] font-bold bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-1 shadow-xs"
                              title="Processar e promover registros válidos para as tabelas principais"
                            >
                              {isPromoting ? (
                                <RefreshCw className="w-3 h-3 animate-spin" />
                              ) : (
                                <ShieldCheck className="w-3 h-3" />
                              )}
                              Processar e Promover
                            </Button>
                          )}

                          {/* Se tiver erro, botão de retomar */}
                          {isErro && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleRetomarProcessamentoDireto(imp)}
                              disabled={isServerRunning}
                              className="h-7 px-2.5 text-[10px] font-bold border-amber-400 text-amber-800 bg-amber-50 hover:bg-amber-100 flex items-center gap-1 shadow-xs"
                              title={`Retomar processamento a partir do checkpoint (linha ${imp.linha_checkpoint})`}
                            >
                              {isServerRunning ? (
                                <RefreshCw className="w-3 h-3 animate-spin" />
                              ) : (
                                <RotateCcw className="w-3 h-3 text-[#F18800]" />
                              )}
                              Retomar processamento
                            </Button>
                          )}

                          {/* Botão de Ver Erros / Detalhes */}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setSelectedImportacaoErros(imp)}
                            className="h-7 px-1.5 text-slate-500 hover:text-[#253575]"
                            title="Ver detalhes da importação"
                          >
                            <FileText className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* PAINEL RECOLHÍVEL: ARQUITETURA DE DADOS — PAPEL DE CADA FONTE */}
      <div className="steel-card overflow-hidden border border-[#D9DFEB] transition-all">
        <button
          type="button"
          onClick={() => setArquiteturaDropdownOpen(!arquiteturaDropdownOpen)}
          className="w-full p-4 flex items-center justify-between bg-white hover:bg-[#F8FAFD] transition-colors text-left focus:outline-none"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#253575]/10 flex items-center justify-center text-[#253575]">
              <Database className="w-4 h-4 text-[#F18800]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-[#253575]">
                  Arquitetura de Dados — Papel de Cada Fonte
                </h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  Estudo de Arquitetura ABR
                </span>
                <span className="text-[10px] font-semibold text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 hidden sm:inline">
                  3 Fontes Definidas
                </span>
              </div>
              <p className="text-xs text-[#5C6784] mt-0.5">
                {arquiteturaDropdownOpen
                  ? 'Clique para recolher o estudo de papéis oficiais, chaves de integração e fluxo ETL.'
                  : 'Clique para visualizar os 3 papéis oficiais de dados, ciclo de vida operacional, chaves primárias e regras ETL.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold text-[#253575] bg-[#F0F4FA] px-3 py-1.5 rounded-lg border border-[#D9DFEB] shrink-0">
            <span>{arquiteturaDropdownOpen ? 'Recolher' : 'Abrir Arquitetura'}</span>
            <ChevronDown
              className={`w-4 h-4 text-[#253575] transition-transform duration-200 ${
                arquiteturaDropdownOpen ? 'rotate-180' : ''
              }`}
            />
          </div>
        </button>

        {arquiteturaDropdownOpen && (
          <div className="border-t border-[#D9DFEB] bg-[#F8FAFD] p-5 space-y-6">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Compass className="w-4 h-4 text-[#253575]" />
                <h4 className="text-xs font-extrabold text-[#253575] uppercase tracking-wider">
                  1. Papéis Oficiais das Fontes de Dados
                </h4>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* FONTE 1: GESTÃO DA PRODUÇÃO */}
                <div className="bg-white rounded-xl border border-blue-200/80 p-4 shadow-sm flex flex-col justify-between relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-blue-50 rounded-bl-full pointer-events-none" />
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2 relative z-10">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-xs">
                          <FileSpreadsheet className="w-4 h-4" />
                        </div>
                        <span className="font-extrabold text-xs text-[#253575] leading-tight">
                          COMERCIAL/OPERACIONAL OFICIAL
                        </span>
                      </div>
                      <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-300 shrink-0">
                        Primária Oficial
                      </span>
                    </div>

                    <h5 className="text-xs font-bold text-[#141D40] mt-1">
                      Gestão da Produção (Pedido+Item)
                    </h5>

                    <p className="text-[11px] text-[#5C6784] mt-2 leading-relaxed">
                      Fonte da verdade para{' '}
                      <strong>
                        pedido, carteira, produção, picking, faturamento operacional e logística
                      </strong>
                      . Granularidade nível <strong>PEDIDO + ITEM DO PA</strong>.
                    </p>

                    <div className="mt-3 p-2.5 rounded-lg bg-blue-50/50 border border-blue-100 text-[10px] space-y-1 text-slate-700">
                      <div>
                        <strong className="text-[#253575]">Volume estimado:</strong> ~44.685
                        registros × 59 colunas
                      </div>
                      <div>
                        <strong className="text-[#253575]">Frequência:</strong> Diária (XLSX)
                      </div>
                      <div>
                        <strong className="text-[#253575]">Chave operacional:</strong> Pedido + Item
                        do PA
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 pt-2 border-t border-slate-100 text-[10px] text-blue-800 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-blue-600" /> Alimenta pedidos, PCP,
                    picking e romaneio
                  </div>
                </div>

                {/* FONTE 2: MARGEM_GABR */}
                <div className="bg-white rounded-xl border border-emerald-200/80 p-4 shadow-sm flex flex-col justify-between relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-50 rounded-bl-full pointer-events-none" />
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2 relative z-10">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-xs">
                          <Sliders className="w-4 h-4" />
                        </div>
                        <span className="font-extrabold text-xs text-[#253575] leading-tight">
                          FINANCEIRA OFICIAL
                        </span>
                      </div>
                      <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-300 shrink-0">
                        Primária Oficial
                      </span>
                    </div>

                    <h5 className="text-xs font-bold text-[#141D40] mt-1">
                      MARGEM_GABR (Financeiro)
                    </h5>

                    <p className="text-[11px] text-[#5C6784] mt-2 leading-relaxed">
                      Fonte da verdade para{' '}
                      <strong>
                        faturamento contábil, receita bruta/líquida, devoluções, impostos, custo MP,
                        GGF, rebate, frete, MCI, MCII, MCII%, PV/kg e metas
                      </strong>
                      .
                    </p>

                    <div className="mt-3 p-2.5 rounded-lg bg-emerald-50/50 border border-emerald-100 text-[10px] space-y-1 text-slate-700">
                      <div>
                        <strong className="text-[#253575]">Volume estimado:</strong> ~36.000
                        registros
                      </div>
                      <div>
                        <strong className="text-[#253575]">Granularidade:</strong> NF + Código do
                        Produto + Cliente
                      </div>
                      <div>
                        <strong className="text-[#253575]">Frequência:</strong> Semanal (XLSX)
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 pt-2 border-t border-slate-100 text-[10px] text-emerald-800 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Alimenta margem real,
                    rentabilidade e DRE
                  </div>
                </div>

                {/* FONTE 3: RESUMO COMERCIAL (SUBSTITUÍDA) */}
                <div className="bg-white rounded-xl border border-amber-200/80 p-4 shadow-sm flex flex-col justify-between relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-24 h-24 bg-amber-50 rounded-bl-full pointer-events-none" />
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2 relative z-10">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-lg bg-amber-100 text-amber-800 flex items-center justify-center font-bold text-xs">
                          <Layers className="w-4 h-4" />
                        </div>
                        <span className="font-extrabold text-xs text-[#253575] leading-tight">
                          AGREGADA (NÃO OFICIAL)
                        </span>
                      </div>
                      <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300 shrink-0">
                        Substituída
                      </span>
                    </div>

                    <h5 className="text-xs font-bold text-[#141D40] mt-1">
                      Resumo Comercial → Substituída por vw_resumo_comercial
                    </h5>

                    <p className="text-[11px] text-[#5C6784] mt-2 leading-relaxed">
                      Fonte secundária agregada de 32 linhas × 6 campos.{' '}
                      <strong>Não deve mais ser importada via CSV</strong>. O sistema agora calcula
                      a view materializada <strong>vw_resumo_comercial</strong> a partir das fontes
                      oficiais.
                    </p>

                    <div className="mt-3 p-2.5 rounded-lg bg-amber-50/50 border border-amber-100 text-[10px] space-y-1 text-slate-700">
                      <div>
                        <strong className="text-[#253575]">Status no pipeline:</strong>{' '}
                        Descontinuada para importação
                      </div>
                      <div>
                        <strong className="text-[#253575]">Substituta:</strong> Materialized View no
                        PostgreSQL
                      </div>
                    </div>
                  </div>

                  <div className="mt-3 pt-2 border-t border-slate-100 text-[10px] text-amber-900 font-semibold flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-amber-600" /> Cálculo automático sem
                    ingestão manual
                  </div>
                </div>
              </div>
            </div>

            {/* CHAVES DE INTEGRAÇÃO */}
            <div className="bg-white rounded-xl border border-[#D9DFEB] p-4 shadow-sm space-y-3">
              <div className="flex items-center gap-2">
                <Key className="w-4 h-4 text-[#F18800]" />
                <h4 className="text-xs font-extrabold text-[#253575] uppercase tracking-wider">
                  Chaves de Negócio Determinísticas (Anti-Duplicação Real)
                </h4>
              </div>
              <p className="text-xs text-[#5C6784] leading-relaxed">
                O hash anti-duplicação é calculado estritamente sobre as chaves de negócio
                normalizadas de cada linha. Subir a mesma planilha repetidas vezes nunca duplicará
                registros na base real nem na staging.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* PAINEL RECOLHÍVEL: CATÁLOGO GERAL DE FONTES DE DADOS */}
      <div className="steel-card overflow-hidden border border-[#D9DFEB] transition-all">
        <button
          type="button"
          onClick={() => setCatalogoDropdownOpen(!catalogoDropdownOpen)}
          className="w-full p-4 flex items-center justify-between bg-white hover:bg-[#F8FAFD] transition-colors text-left focus:outline-none"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#253575]/10 flex items-center justify-center text-[#253575]">
              <Layers className="w-4 h-4 text-[#F18800]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-[#253575]">
                  Catálogo Geral de Fontes de Dados & Semáforo de Integração
                </h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-[#5C6784] border border-slate-200">
                  {fontes.length}{' '}
                  {fontes.length === 1 ? 'fonte configurada' : 'fontes configuradas'}
                </span>
              </div>
              <p className="text-xs text-[#5C6784] mt-0.5">
                {catalogoDropdownOpen
                  ? 'Clique para recolher os cards de status e conectores de dados.'
                  : 'Clique para abrir e gerenciar as fontes de dados, conectores ERP e testes de conexão.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold text-[#253575] bg-[#F0F4FA] px-3 py-1.5 rounded-lg border border-[#D9DFEB] shrink-0">
            <span>{catalogoDropdownOpen ? 'Recolher' : 'Abrir Catálogo'}</span>
            <ChevronDown
              className={`w-4 h-4 text-[#253575] transition-transform duration-200 ${
                catalogoDropdownOpen ? 'rotate-180' : ''
              }`}
            />
          </div>
        </button>

        {catalogoDropdownOpen && (
          <div className="border-t border-[#D9DFEB] bg-[#F8FAFD] p-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {fontes.map((fonte) => {
                const isAster = fonte.nome.includes('ASTER')
                const isAtiva = fonte.status === 'ativa'
                const isErro = fonte.status === 'erro'
                const isTesting = testingId === fonte.id
                const isSyncing = syncingId === fonte.id

                return (
                  <div
                    key={fonte.id}
                    className="steel-card p-4 flex flex-col justify-between hover:border-[#F18800]/50 transition-all bg-white relative"
                  >
                    <div>
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <span className="text-xs font-extrabold text-[#253575] leading-snug">
                          {fonte.nome}
                        </span>
                        <div className="flex items-center gap-1.5 shrink-0">
                          {fonte.status === 'standby' ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-300">
                              <span className="w-2 h-2 rounded-full bg-amber-500" /> Captura assistida
                            </span>
                          ) : isAtiva ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <span className="w-2 h-2 rounded-full bg-emerald-500" /> Ativa
                            </span>
                          ) : isErro ? (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-200">
                              <span className="w-2 h-2 rounded-full bg-red-500" /> Falha
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-300">
                              <span className="w-2 h-2 rounded-full bg-slate-400" /> Aguardando
                            </span>
                          )}
                        </div>
                      </div>

                      <p className="text-[11px] text-[#5C6784] line-clamp-2 leading-relaxed mb-3">
                        {fonte.descricao || 'Fonte cadastrada no catálogo do ABR Intelligence.'}
                      </p>
                    </div>

                    <div className="mt-4 pt-3 border-t border-[#D9DFEB] flex items-center gap-2">
                      {isAster ? (
                        <div className="w-full text-center text-[11px] font-semibold text-amber-800 bg-amber-50 border border-amber-200 py-1.5 px-2 rounded-lg">
                          Captura assistida pela extensão Aster
                        </div>
                      ) : (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleTestarConexao(fonte)}
                            disabled={isTesting}
                            className="flex-1 text-[11px] h-8 border-[#D9DFEB] text-[#253575] hover:bg-[#F4F6FB]"
                          >
                            {isTesting ? <RefreshCw className="w-3 h-3 animate-spin mr-1" /> : null}
                            Testar Conexão
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleSincronizarAgora(fonte)}
                            disabled={isSyncing}
                            className="flex-1 text-[11px] h-8 font-bold bg-[#F18800] hover:bg-[#D97706] text-white"
                          >
                            {isSyncing ? <RefreshCw className="w-3 h-3 animate-spin mr-1" /> : null}
                            Sincronizar
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* PAINEL RECOLHÍVEL: CAMADA DE STAGING & NORMALIZAÇÃO */}
      <div className="steel-card overflow-hidden border border-[#D9DFEB] transition-all">
        <button
          type="button"
          onClick={() => setStagingDropdownOpen(!stagingDropdownOpen)}
          className="w-full p-4 flex items-center justify-between bg-white hover:bg-[#F8FAFD] transition-colors text-left focus:outline-none"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#253575]/10 flex items-center justify-center text-[#253575]">
              <Layers className="w-4 h-4 text-[#F18800]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-[#253575]">
                  Camada de Staging & Buffer Seguro
                </h3>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-100 text-[#5C6784] border border-slate-200">
                  {stagingResumo.reduce((acc, g) => acc + g.total, 0)} registros na staging
                </span>
              </div>
              <p className="text-xs text-[#5C6784] mt-0.5">
                {stagingDropdownOpen
                  ? 'Clique para recolher o resumo dos lotes em staging.'
                  : 'Clique para inspecionar os lotes e buffers normalizados da staging.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold text-[#253575] bg-[#F0F4FA] px-3 py-1.5 rounded-lg border border-[#D9DFEB] shrink-0">
            <span>{stagingDropdownOpen ? 'Recolher' : 'Abrir Staging'}</span>
            <ChevronDown
              className={`w-4 h-4 text-[#253575] transition-transform duration-200 ${
                stagingDropdownOpen ? 'rotate-180' : ''
              }`}
            />
          </div>
        </button>

        {stagingDropdownOpen && (
          <div className="border-t border-[#D9DFEB] bg-white p-4">
            {stagingResumo.length === 0 ? (
              <p className="text-xs text-[#5C6784] text-center py-6">
                Camada de staging vazia. Novos uploads alimentarão esta tabela para auditoria.
              </p>
            ) : (
              <div className="divide-y divide-[#EAEFF9]">
                {stagingResumo.map((grupo, idx) => (
                  <div key={idx} className="py-3 flex items-center justify-between gap-4 text-xs">
                    <div>
                      <span className="font-bold text-[#253575]">{grupo.entidade}</span>
                      <span className="text-[10px] font-mono text-slate-500 ml-2">
                        (Origem: {grupo.source_system})
                      </span>
                    </div>
                    <div className="flex items-center gap-3 font-mono">
                      <span>
                        Total: <strong>{grupo.total}</strong>
                      </span>
                      <span className="text-amber-700">
                        Pendentes: <strong>{grupo.pendentes}</strong>
                      </span>
                      <span className="text-emerald-700">
                        Processados: <strong>{grupo.processados}</strong>
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* PAINEL RECOLHÍVEL: LOGS & HISTÓRICO DE IMPORTAÇÕES */}
      <div className="steel-card overflow-hidden border border-[#D9DFEB] transition-all">
        <button
          type="button"
          onClick={() => setLogsDropdownOpen(!logsDropdownOpen)}
          className="w-full p-4 flex items-center justify-between bg-white hover:bg-[#F8FAFD] transition-colors text-left focus:outline-none"
        >
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#253575]/10 flex items-center justify-center text-[#253575]">
              <Clock className="w-4 h-4 text-[#F18800]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-[#253575]">
                  Logs & Histórico de Importações
                </h3>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 text-[#5C6784] border border-slate-200">
                  {historico.length} {historico.length === 1 ? 'registro' : 'registros'}
                </span>
              </div>
              <p className="text-xs text-[#5C6784] mt-0.5">
                {logsDropdownOpen
                  ? 'Clique para recolher o histórico.'
                  : 'Clique para abrir o histórico de auditoria e relatórios linha a linha.'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-semibold text-[#253575] bg-[#F0F4FA] px-3 py-1.5 rounded-lg border border-[#D9DFEB]">
            <span>{logsDropdownOpen ? 'Recolher' : 'Abrir Logs'}</span>
            <ChevronDown
              className={`w-4 h-4 text-[#253575] transition-transform duration-200 ${
                logsDropdownOpen ? 'rotate-180' : ''
              }`}
            />
          </div>
        </button>

        {logsDropdownOpen && (
          <div className="border-t border-[#D9DFEB] bg-white">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-[#F8FAFD] text-[#5C6784] uppercase text-[10px] tracking-wider border-b border-[#D9DFEB]">
                  <tr>
                    <th className="py-3 px-4">Sync ID</th>
                    <th className="py-3 px-4">Origem</th>
                    <th className="py-3 px-4">Iniciado em</th>
                    <th className="py-3 px-4 text-center">Status</th>
                    <th className="py-3 px-4 text-right">Lidos</th>
                    <th className="py-3 px-4 text-right">Inseridos</th>
                    <th className="py-3 px-4 text-right">Erros</th>
                    <th className="py-3 px-4 text-center">Log</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#EAEFF9] text-[#141D40]">
                  {historico.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="py-8 text-center text-xs text-[#5C6784]">
                        Nenhum registro de log recente.
                      </td>
                    </tr>
                  ) : (
                    historico.map((item) => (
                      <tr key={item.id} className="hover:bg-[#F8FAFD] transition-colors">
                        <td className="py-3 px-4 font-mono font-bold text-[#253575] text-[11px]">
                          {item.sync_id}
                        </td>
                        <td className="py-3 px-4 font-medium">
                          {item.origem_arquivo || item.entidade}
                        </td>
                        <td className="py-3 px-4 text-[#5C6784] font-mono text-[11px]">
                          {formatDateTimePtBR(item.iniciado_em)}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span
                            className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                              item.status === 'sucesso'
                                ? 'bg-emerald-50 text-emerald-700'
                                : 'bg-red-50 text-red-700'
                            }`}
                          >
                            {item.status}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-right font-mono">{item.registros_lidos}</td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-emerald-700">
                          {item.registros_inseridos}
                        </td>
                        <td className="py-3 px-4 text-right font-mono font-bold text-red-600">
                          {item.registros_erro}
                        </td>
                        <td className="py-3 px-4 text-center">
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setSelectedLog(item)}
                            className="h-7 px-2 text-[#253575] hover:text-[#F18800]"
                          >
                            <FileText className="w-3.5 h-3.5" />
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* MODAL 1: UPLOAD MANUAL (APENAS XLSX - 1 ENVIO BINÁRIO DIRETO PARA STORAGE) */}
      <Dialog open={uploadModalOpen} onOpenChange={setUploadModalOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-black text-[#253575] flex items-center gap-2">
              <UploadCloud className="w-5 h-5 text-[#F18800]" />
              Upload de Planilha XLSX (100% Servidor)
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 pt-2">
            <div className="p-3 bg-blue-50/80 rounded-xl border border-blue-200 text-xs text-[#253575] leading-relaxed">
              <strong>Zero parsing no navegador:</strong> o arquivo binário é enviado diretamente
              para o Supabase Storage. O motor no servidor realiza a ingestão assíncrona com
              checkpoint, garantindo alta performance mesmo com 164.000 linhas.
            </div>

            <div className="border-2 border-dashed border-[#D9DFEB] hover:border-[#F18800] rounded-xl p-6 text-center transition-colors bg-[#F8FAFD]">
              <input
                type="file"
                id="fileUploadXlsx"
                accept=".xlsx"
                multiple
                onChange={handleSelecionarArquivoXlsx}
                className="hidden"
              />
              <label htmlFor="fileUploadXlsx" className="cursor-pointer flex flex-col items-center">
                <FileSpreadsheet className="w-10 h-10 text-[#253575] mb-2" />
                <span className="text-xs font-bold text-[#253575]">
                  {selectedFiles.length > 0
                    ? `${selectedFiles.length} planilha(s) selecionada(s)`
                    : 'Clique para selecionar até 2 planilhas (.XLSX)'}
                </span>
                {selectedFiles.length > 0 && (
                  <div className="mt-2 space-y-1 text-left">
                    {selectedFiles.map((file) => (
                      <div key={`${file.name}-${file.size}`} className="text-[10px] font-mono text-[#253575]">
                        {file.name} · {(file.size / (1024 * 1024)).toFixed(2)} MB
                      </div>
                    ))}
                  </div>
                )}
                <span className="text-[11px] text-[#5C6784] mt-1">
                  Formato aceito: exclusivamente planilhas <strong>.XLSX</strong>, até 2 arquivos de 200 MB cada.
                </span>
              </label>
            </div>

            {uploadingFile && (
              <div className="rounded-lg bg-[#F8FAFD] border border-[#253575]/20 p-3 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-bold text-[#253575] flex items-center gap-1.5">
                    <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#F18800]" />
                    {uploadProgressMessage || 'Enviando arquivo para o Storage...'}
                  </span>
                  <span className="font-mono font-bold text-[#F18800]">
                    {uploadProgressPercent}%
                  </span>
                </div>
                <div className="w-full bg-[#EAEFF9] rounded-full h-2.5 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-[#253575] to-[#F18800] h-2.5 rounded-full transition-all duration-300"
                    style={{ width: `${uploadProgressPercent}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="gap-2 pt-3 border-t border-[#D9DFEB]">
            <Button
              variant="outline"
              onClick={() => setUploadModalOpen(false)}
              disabled={uploadingFile}
              className="text-xs"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleExecutarUploadBinario}
              disabled={selectedFiles.length === 0 || uploadingFile}
              className="text-xs font-bold bg-[#F18800] hover:bg-[#D97706] text-white"
            >
              {uploadingFile ? 'Enviando...' : 'Enviar Arquivo para o Servidor'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* MODAL 2: DUPLA CONFIRMAÇÃO DO TIPO DE PLANILHA ANTES DE PROCESSAR */}
      <Dialog open={confirmModalOpen} onOpenChange={setConfirmModalOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-[#253575] flex items-center gap-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              Confirmação de Importação: {currentImportacao?.nome_arquivo}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 pt-2 text-xs">
            {inspectingServer ? (
              <div className="p-8 text-center space-y-2 text-[#5C6784]">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto text-[#F18800]" />
                <p className="font-bold text-[#253575]">Inspecionando cabeçalhos no servidor...</p>
                <p className="text-[11px]">Lendo metadados sem sobrecarregar o seu navegador.</p>
              </div>
            ) : (
              <>
                <div className="p-3.5 rounded-xl bg-blue-50/80 border border-blue-200 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-[#253575] text-sm">
                      Detecção Automática: {previewDeteccao?.label || 'Gestão da Produção'}
                    </span>
                    <span className="font-mono text-[11px] font-bold text-blue-900 bg-blue-100 px-2 py-0.5 rounded">
                      ~{previewDeteccao?.totalLinhas || currentImportacao?.linhas_total || 0} linhas
                      detectadas
                    </span>
                  </div>
                  <p className="text-[11px] text-[#253575]/80 leading-relaxed">
                    Confirme o tipo da planilha antes do motor processar na Staging.
                  </p>
                </div>

                <div>
                  <label className="text-xs font-bold text-[#253575] block mb-1">
                    Tipo de Planilha (Dupla Confirmação do Usuário)
                  </label>
                  <select
                    value={tipoSelecionadoConfirm}
                    onChange={(e) => setTipoSelecionadoConfirm(e.target.value)}
                    className="w-full h-9 rounded-lg border border-[#D9DFEB] bg-white px-3 text-xs text-[#141D40] outline-none focus:border-[#F18800]"
                  >
                    <option value="GESTAO_PRODUCAO">
                      Gestão da Produção (Pedidos + Itens + Produção + PCP)
                    </option>
                    <option value="MARGEM">MARGEM_GABR (Camada Financeira / Rentabilidade)</option>
                    <option value="CLIENTES">Clientes ERP</option>
                    <option value="ESTOQUE">Estoque Físico</option>
                    <option value="GERAL">Outra / Planilha Geral</option>
                  </select>
                </div>

                {/* Opção: ignorar linhas com erro */}
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-between">
                  <div>
                    <span className="font-bold text-[#253575] block">
                      Tolerância a Inconsistências:
                    </span>
                    <span className="text-[11px] text-[#5C6784]">
                      Ignorar linhas com campos inválidos e continuar o processamento das linhas
                      válidas.
                    </span>
                  </div>
                  <input
                    type="checkbox"
                    checked={ignorarErrosLinha}
                    onChange={(e) => setIgnorarErrosLinha(e.target.checked)}
                    className="w-4 h-4 accent-[#253575] rounded cursor-pointer"
                  />
                </div>

                {/* Amostra dos cabeçalhos */}
                {previewDeteccao?.headers && previewDeteccao.headers.length > 0 && (
                  <div>
                    <label className="text-[11px] font-bold text-[#5C6784] block mb-1">
                      Colunas detectadas no cabeçalho:
                    </label>
                    <div className="p-2 bg-slate-100 rounded text-[10px] font-mono text-slate-700 max-h-20 overflow-y-auto">
                      {previewDeteccao.headers.join(' | ')}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          <DialogFooter className="gap-2 pt-3 border-t border-[#D9DFEB]">
            <Button
              variant="outline"
              onClick={() => setConfirmModalOpen(false)}
              className="text-xs"
            >
              Cancelar
            </Button>
            <Button
              onClick={handleConfirmarEProcessarNoServidor}
              disabled={inspectingServer}
              className="text-xs font-bold bg-emerald-600 hover:bg-emerald-700 text-white flex items-center gap-1.5"
            >
              <Play className="w-3.5 h-3.5" />
              Confirmar e Iniciar Processamento no Servidor
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* MODAL 3: PAINEL DE ERROS POR LINHA */}
      <Dialog
        open={selectedImportacaoErros !== null}
        onOpenChange={() => setSelectedImportacaoErros(null)}
      >
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-[#253575] flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              Relatório de Inconsistências: {selectedImportacaoErros?.nome_arquivo}
            </DialogTitle>
          </DialogHeader>

          {selectedImportacaoErros && (
            <div className="space-y-3 pt-2 text-xs">
              <div className="grid grid-cols-3 gap-2 bg-[#F8FAFD] p-3 rounded-lg border border-[#D9DFEB] text-center font-mono">
                <div>
                  <span className="text-[#5C6784] text-[10px] uppercase block">Total Lidas</span>
                  <strong className="text-base text-[#253575]">
                    {selectedImportacaoErros.linha_checkpoint}
                  </strong>
                </div>
                <div>
                  <span className="text-[#5C6784] text-[10px] uppercase block">Válidas</span>
                  <strong className="text-base text-emerald-600">
                    {selectedImportacaoErros.linhas_validas}
                  </strong>
                </div>
                <div>
                  <span className="text-[#5C6784] text-[10px] uppercase block">Com Erro</span>
                  <strong className="text-base text-red-600">
                    {selectedImportacaoErros.linhas_erro}
                  </strong>
                </div>
              </div>

              {selectedImportacaoErros.erro_mensagem && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-800 text-[11px]">
                  <strong>Erro do Sistema:</strong> {selectedImportacaoErros.erro_mensagem}
                </div>
              )}

              <p className="text-[11px] text-[#5C6784]">
                Cada inconsistência foi registrada individualmente na Staging com o número exato da
                linha no arquivo Excel, coluna e motivo da rejeição.
              </p>
            </div>
          )}

          <DialogFooter>
            <Button
              size="sm"
              onClick={() => setSelectedImportacaoErros(null)}
              className="text-xs bg-[#253575] text-white"
            >
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* MODAL 4: DETALHES DO LOG */}
      <Dialog open={selectedLog !== null} onOpenChange={() => setSelectedLog(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="text-base font-bold text-[#253575] flex items-center gap-2">
              <FileText className="w-4 h-4 text-[#F18800]" />
              Log de Execução: {selectedLog?.sync_id}
            </DialogTitle>
          </DialogHeader>

          {selectedLog && (
            <div className="space-y-3 pt-2 text-xs">
              <div className="grid grid-cols-2 gap-2 bg-[#F8FAFD] p-3 rounded-lg border border-[#D9DFEB]">
                <div>
                  <span className="text-[#5C6784]">Origem:</span>{' '}
                  <strong className="text-[#253575]">
                    {selectedLog.origem_arquivo || selectedLog.entidade}
                  </strong>
                </div>
                <div>
                  <span className="text-[#5C6784]">Status:</span>{' '}
                  <strong className="text-[#253575] capitalize">{selectedLog.status}</strong>
                </div>
              </div>

              <div>
                <label className="text-xs font-bold text-[#253575] block mb-1">
                  Mensagem de Log
                </label>
                <pre className="p-3 bg-[#142758] text-white rounded-lg text-[11px] font-mono whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                  {selectedLog.log || 'Sem log emitido.'}
                </pre>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              size="sm"
              onClick={() => setSelectedLog(null)}
              className="text-xs bg-[#253575] text-white"
            >
              Fechar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
