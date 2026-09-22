import 'jsr:@supabase/functions-js/edge-runtime.d.ts'
import { createClient } from 'npm:@supabase/supabase-js@2'
import { corsHeaders } from '../_shared/cors.ts'

const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? ''
const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? Deno.env.get('SUPABASE_SECRET_KEY') ?? ''
const collectorKey = Deno.env.get('ABR_COLLECTOR_KEY') ?? Deno.env.get('ASTER_COLLECTOR_INGEST_KEY') ?? ''

const supabase = createClient(supabaseUrl, serviceRoleKey, {
  auth: { persistSession: false, autoRefreshToken: false },
})

type IngestPayload = {
  fonte_id: string
  sync_id?: string
  entidade?: string
  rows: Record<string, unknown>[]
  metadata?: Record<string, unknown>
}

function jsonResponse(body: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders },
  })
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`
  const obj = value as Record<string, unknown>
  return `{${Object.keys(obj)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(obj[key])}`)
    .join(',')}}`
}

async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('')
}

function sourceIdFromRow(row: Record<string, unknown>, fallback: string): string {
  const keys = [
    'id',
    'Id',
    'ID',
    'docEntry',
    'DocEntry',
    'pedido',
    'Pedido',
    'numero',
    'Numero',
    'codigo',
    'Código',
    'Codigo',
  ]
  for (const key of keys) {
    const value = row[key]
    if (value !== undefined && value !== null && String(value).trim()) return String(value).trim()
  }
  return fallback
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: corsHeaders })
  if (req.method !== 'POST') return jsonResponse({ sucesso: false, erro: 'Metodo nao permitido.' }, 405)

  if (!collectorKey) {
    return jsonResponse({ sucesso: false, erro: 'ABR_COLLECTOR_KEY nao configurada na Edge Function.' }, 500)
  }

  const providedKey = req.headers.get('x-collector-key') || ''
  if (providedKey !== collectorKey) {
    return jsonResponse({ sucesso: false, erro: 'Chave do coletor invalida.' }, 401)
  }

  let body: IngestPayload
  try {
    body = await req.json()
  } catch {
    return jsonResponse({ sucesso: false, erro: 'Payload JSON invalido.' }, 400)
  }

  if (!body.fonte_id) return jsonResponse({ sucesso: false, erro: 'fonte_id e obrigatorio.' }, 400)
  if (!Array.isArray(body.rows) || body.rows.length === 0) {
    return jsonResponse({ sucesso: false, erro: 'rows deve conter ao menos um objeto.' }, 400)
  }

  const rows = body.rows.filter((row) => row && typeof row === 'object' && !Array.isArray(row)).slice(0, 1000)
  if (!rows.length) return jsonResponse({ sucesso: false, erro: 'Nenhuma linha valida para ingestao.' }, 400)

  const syncId =
    body.sync_id ||
    `ASTER-${new Date().toISOString().replace(/[-:.TZ]/g, '')}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`
  const entidade = body.entidade || 'aster_relatorio'
  const metadata = body.metadata || {}

  const stagingRows = []
  for (let index = 0; index < rows.length; index++) {
    const row = rows[index]
    const hash = await sha256Hex(`${body.fonte_id}|${entidade}|${stableStringify(row)}`)
    stagingRows.push({
      fonte_id: body.fonte_id,
      source_system: 'ASTER_CHROME',
      source_id: sourceIdFromRow(row, `row-${index + 1}`),
      entidade,
      payload_original: row,
      dados_transformados: row,
      sync_id: syncId,
      hash_registro: hash,
      status_validacao: 'pendente',
      erro_validacao: null,
      tabela_destino: null,
      coleta_metadata: metadata,
      ativo: true,
    })
  }

  const { error } = await supabase
    .from('staging_dados')
    .upsert(stagingRows, { onConflict: 'fonte_id,hash_registro', ignoreDuplicates: true })

  if (error) {
    return jsonResponse({ sucesso: false, erro: `Falha ao gravar staging: ${error.message}` }, 500)
  }

  const { data: historicoAtual } = await supabase
    .from('historico_importacoes')
    .select('registros_lidos, registros_inseridos, registros_atualizados, registros_erro')
    .eq('sync_id', syncId)
    .maybeSingle()

  const registrosLidos = Number(historicoAtual?.registros_lidos || 0) + rows.length
  const registrosInseridos = Number(historicoAtual?.registros_inseridos || 0) + rows.length
  const registrosAtualizados = Number(historicoAtual?.registros_atualizados || 0)
  const registrosErro = Number(historicoAtual?.registros_erro || 0)

  const historicoPayload: Record<string, unknown> = {
    sync_id: syncId,
    fonte_id: body.fonte_id,
    entidade,
    status: 'sucesso',
    registros_lidos: registrosLidos,
    registros_inseridos: registrosInseridos,
    registros_atualizados: registrosAtualizados,
    registros_erro: registrosErro,
    origem_arquivo: 'ASTER_CHROME',
    log: `Ingestao Aster acumulada com ${registrosLidos} registros recebidos.`,
    finalizado_em: new Date().toISOString(),
  }
  if (!historicoAtual) historicoPayload.iniciado_em = new Date().toISOString()

  await supabase.from('historico_importacoes').upsert(historicoPayload, { onConflict: 'sync_id' })

  return jsonResponse({ sucesso: true, sync_id: syncId, recebidos: rows.length, recebidos_acumulado: registrosLidos })
})
