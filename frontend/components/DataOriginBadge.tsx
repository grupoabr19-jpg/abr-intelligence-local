import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CentralDadosService } from '@/services/centralDadosService'
import { ShieldAlert, CheckCircle2, Database, HelpCircle } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

interface DataOriginBadgeProps {
  modulo?: string
  className?: string
  compact?: boolean
}

export function DataOriginBadge({ modulo, className = '', compact = false }: DataOriginBadgeProps) {
  const [origemInfo, setOrigemInfo] = useState<{
    erpAtivo: boolean
    isBaseVazia?: boolean
    fontesAtivasCount: number
    nomeFontePrincipal: string
    isBaseMista?: boolean
    detalhesContagem?: {
      clientesReais: number
      pedidosReais: number
      materiaisReais: number
      estoqueReal: number
      totalGeral?: number
      stagingPendentes?: number
    }
  }>({
    erpAtivo: false,
    isBaseVazia: true,
    fontesAtivasCount: 1,
    nomeFontePrincipal: 'Demonstração ABR',
  })

  useEffect(() => {
    CentralDadosService.checarStatusOrigemReal().then(setOrigemInfo)
  }, [])

  const isReal = origemInfo.erpAtivo
  const isVazia =
    (origemInfo as any).isBaseVazia ??
    (!origemInfo.erpAtivo && (origemInfo.detalhesContagem?.totalGeral ?? 0) === 0)
  const counts = origemInfo.detalhesContagem

  if (compact) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold border transition-colors cursor-help ${
              isReal
                ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                : isVazia
                  ? 'bg-slate-100 text-slate-700 border-slate-300'
                  : 'bg-amber-50 text-amber-800 border-amber-300'
            } ${className}`}
          >
            {isReal ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span>Base Real ({origemInfo.nomeFontePrincipal})</span>
              </>
            ) : isVazia ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                <span>Base vazia — aguardando importação</span>
              </>
            ) : (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
                <span>Dados de demonstração</span>
              </>
            )}
          </span>
        </TooltipTrigger>
        <TooltipContent
          side="bottom"
          className="max-w-xs text-xs bg-[#142758] text-white border-[#253575]"
        >
          <p className="font-bold text-[#F18800] mb-1">
            {isReal
              ? 'Origem Auditada: Base Real'
              : isVazia
                ? 'Base Limpa: Aguardando Primeira Importação'
                : 'Transparência de Abastecimento'}
          </p>
          <p className="text-[11px] text-white/90 leading-relaxed">
            {isReal
              ? `Registros reais detectados nas tabelas principais: ${counts ? `${counts.clientesReais} clientes, ${counts.pedidosReais} pedidos, ${counts.materiaisReais} materiais.` : 'promovidos da staging.'}`
              : isVazia
                ? 'A base foi zerada com sucesso. Nenhuma planilha ou dado demo carregado. Faça o primeiro upload na Central de Dados para ativar os dashboards.'
                : 'Nenhum dado fictício se passa por real. As tabelas principais contêm dados de demonstração. Promova os registros da Central de Dados para ativar a Base Real.'}
          </p>
        </TooltipContent>
      </Tooltip>
    )
  }

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-lg border text-xs font-semibold ${
        isReal
          ? 'bg-emerald-50/80 text-emerald-800 border-emerald-200'
          : isVazia
            ? 'bg-slate-50 text-slate-800 border-slate-300'
            : 'bg-amber-50/90 text-amber-900 border-amber-200'
      } ${className}`}
    >
      <div className="flex items-center gap-1.5">
        {isReal ? (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
        ) : isVazia ? (
          <Database className="w-3.5 h-3.5 text-slate-500 shrink-0" />
        ) : (
          <ShieldAlert className="w-3.5 h-3.5 text-amber-600 shrink-0" />
        )}
        <span className="text-[11px] font-bold">
          {isReal
            ? 'Origem: Base Real'
            : isVazia
              ? 'Base vazia — aguardando primeira importação'
              : 'Origem: Dados de demonstração'}
        </span>
      </div>

      <span className="text-[10px] text-[#5C6784] hidden sm:inline">|</span>

      <span className="text-[10px] text-[#5C6784] hidden sm:inline">
        {isReal
          ? origemInfo.nomeFontePrincipal
          : isVazia
            ? 'Central de Dados pronta para novas planilhas'
            : 'ERP Aster (captura assistida pela extensão)'}
      </span>

      <Link
        to="/central-dados"
        className="text-[10px] font-bold text-[#F18800] hover:underline flex items-center gap-0.5 ml-1"
        title="Gerenciar conexões e staging na Central de Dados"
      >
        <Database className="w-3 h-3" />
        Central
      </Link>
    </div>
  )
}
