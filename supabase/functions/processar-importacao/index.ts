import 'jsr:@supabase/functions-js/edge-runtime.d.ts'
import { createClient } from 'npm:@supabase/supabase-js@2'
import * as fflate from 'npm:fflate@0.8.2'
import { corsHeaders } from '../_shared/cors.ts'

const supabaseUrl = Deno.env.get('SUPABASE_URL') ?? ''
const serviceRoleKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? ''

const supabase = createClient(supabaseUrl, serviceRoleKey, {
  auth: { persistSession: false, autoRefreshToken: false },
})

/**
 * Converte índice de coluna Excel ("A", "B", "Z", "AA", "AB"...) para índice 0-based
 */
export function colLettersToIndex(letters: string): number {
  let index = 0
  const upper = letters.toUpperCase()
  for (let i = 0; i < upper.length; i++) {
    index = index * 26 + (upper.charCodeAt(i) - 64)
  }
  return index - 1
}

/**
 * Decodifica entidades XML comuns (&amp;, &lt;, &gt;, &quot;, &apos;, &#...;)
 */
export function decodeXmlEntities(str: string): string {
  if (!str || !str.includes('&')) return str
  return str
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&')
    .replace(/&#(\d+);/g, (_, dec) => {
      try {
        return String.fromCharCode(parseInt(dec, 10))
      } catch {
        return _
      }
    })
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => {
      try {
        return String.fromCharCode(parseInt(hex, 16))
      } catch {
        return _
      }
    })
}

/**
 * Extrai o sharedStrings.xml construindo uma tabela de strings indexadas (0-based)
 * de forma streaming para minimizar uso de memória.
 */
export async function extractSharedStrings(uint8: Uint8Array): Promise<string[]> {
  return new Promise((resolve) => {
    const strings: string[] = []
    let buffer = ''
    let found = false

    const unzipper = new fflate.Unzip()
    unzipper.register(fflate.UnzipInflate)

    unzipper.onfile = (file) => {
      const name = file.name.replace(/\\/g, '/')
      if (name === 'xl/sharedStrings.xml') {
        found = true
        file.ondata = (err, chunk, final) => {
          if (err) return
          if (chunk) {
            buffer += fflate.strFromU8(chunk)

            // Processa cada <si>...</si> incrementalmente
            let siEndIdx: number
            while ((siEndIdx = buffer.indexOf('</si>')) !== -1) {
              const siStartIdx = buffer.indexOf('<si')
              if (siStartIdx !== -1 && siStartIdx < siEndIdx) {
                const siBlock = buffer.substring(siStartIdx, siEndIdx + 5)

                let strVal = ''
                const tRegex = /<t\b[^>]*>([\s\S]*?)<\/t>/gi
                let tMatch: RegExpExecArray | null
                while ((tMatch = tRegex.exec(siBlock)) !== null) {
                  strVal += tMatch[1]
                }
                strings.push(decodeXmlEntities(strVal))
              }
              buffer = buffer.substring(siEndIdx + 5)
            }
          }

          if (final) {
            resolve(strings)
          }
        }
        file.start()
      }
    }

    const CHUNK_SIZE = 512 * 1024
    for (let i = 0; i < uint8.length; i += CHUNK_SIZE) {
      const slice = uint8.subarray(i, Math.min(i + CHUNK_SIZE, uint8.length))
      const isFinal = i + CHUNK_SIZE >= uint8.length
      unzipper.push(slice, isFinal)
    }

    if (!found) {
      resolve([])
    }
  })
}

export interface ParsedRow {
  rowNumber: number // 1-based (Excel row number)
  cells: Record<number, string> // 0-based col index -> string value
  rawValues: string[] // dense array of values
}

/**
 * Extrai células de um bloco XML <row>...</row>
 */
export function parseRowXml(rowXml: string, sharedStrings: string[]): ParsedRow {
  const rowMatch = rowXml.match(/<row\b[^>]*\br=["']?(\d+)["']?[^>]*>/i)
  const rowNumber = rowMatch ? parseInt(rowMatch[1], 10) : 0

  const cells: Record<number, string> = {}
  const rawValues: string[] = []

  const cRegex = /<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/gi
  let cMatch: RegExpExecArray | null

  while ((cMatch = cRegex.exec(rowXml)) !== null) {
    const cAttrs = cMatch[1] || ''
    const cBody = cMatch[2] || ''

    const rMatch = cAttrs.match(/\br=["']?([A-Za-z]+)(\d+)?["']?/i)
    let colIdx = -1
    if (rMatch) {
      colIdx = colLettersToIndex(rMatch[1])
    }

    const tMatch = cAttrs.match(/\bt=["']?([a-z]+)["']?/i)
    const cellType = tMatch ? tMatch[1] : 'n'

    let val = ''

    if (cellType === 's') {
      const vMatch = cBody.match(/<v\b[^>]*>([\s\S]*?)<\/v>/i)
      if (vMatch) {
        const sstIdx = parseInt(vMatch[1].trim(), 10)
        if (!isNaN(sstIdx) && sstIdx >= 0 && sstIdx < sharedStrings.length) {
          val = sharedStrings[sstIdx]
        }
      }
    } else if (cellType === 'inlineStr') {
      const tInsideMatch = cBody.match(/<t\b[^>]*>([\s\S]*?)<\/t>/i)
      if (tInsideMatch) {
        val = decodeXmlEntities(tInsideMatch[1])
      }
    } else {
      const vMatch = cBody.match(/<v\b[^>]*>([\s\S]*?)<\/v>/i)
      if (vMatch) {
        val = decodeXmlEntities(vMatch[1].trim())
      }
    }

    if (colIdx >= 0) {
      cells[colIdx] = val
      rawValues[colIdx] = val
    }
  }

  for (let i = 0; i < rawValues.length; i++) {
    if (rawValues[i] === undefined) {
      rawValues[i] = ''
    }
  }

  return { rowNumber, cells, rawValues }
}

/**
 * Extrai o texto de uma entrada pequena do ZIP XLSX (workbook.xml ou relações).
 */
export async function extractZipEntryText(uint8: Uint8Array, entryName: string): Promise<string> {
  return new Promise((resolve) => {
    let result = ''
    let found = false
    const unzipper = new fflate.Unzip()
    unzipper.register(fflate.UnzipInflate)
    unzipper.onfile = (file) => {
      if (file.name.replace(/\\/g, '/') !== entryName) return
      found = true
      file.ondata = (err, chunk, final) => {
        if (err) {
          resolve('')
          return
        }
        if (chunk) result += fflate.strFromU8(chunk)
        if (final) resolve(result)
      }
      file.start()
    }
    const CHUNK_SIZE = 512 * 1024
    for (let i = 0; i < uint8.length; i += CHUNK_SIZE) {
      unzipper.push(uint8.subarray(i, Math.min(i + CHUNK_SIZE, uint8.length)), i + CHUNK_SIZE >= uint8.length)
    }
    if (!found) resolve('')
  })
}

/**
 * Resolve os arquivos XML das abas na ordem do workbook.xml.
 */
export async function discoverWorksheetPaths(uint8: Uint8Array): Promise<string[]> {
  const workbookXml = await extractZipEntryText(uint8, 'xl/workbook.xml')
  const relsXml = await extractZipEntryText(uint8, 'xl/_rels/workbook.xml.rels')
  const relationMap = new Map<string, string>()
  for (const match of relsXml.matchAll(/<Relationship\b[^>]*\bId="([^"]+)"[^>]*\bTarget="([^"]+)"/g)) {
    relationMap.set(match[1], match[2])
  }
  const paths: string[] = []
  for (const match of workbookXml.matchAll(/<sheet\b([^>]*)\br:id="([^"]+)"[^>]*\/?>(?:<\/sheet>)?/g)) {
    const target = relationMap.get(match[2])
    if (!target || !target.includes('worksheet')) continue
    const normalized = target.replace(/^\//, '').replace(/^xl\//, '')
    paths.push(`xl/${normalized}`)
  }
  return paths.length > 0 ? paths : ['xl/worksheets/sheet1.xml']
}

async function scanWorksheetMetadata(
  uint8: Uint8Array,
  sharedStrings: string[],
  sheetPath: string,
): Promise<{
  headers: string[]
  totalRowsEstimate: number
  sampleRows: ParsedRow[]
}> {
  return new Promise((resolve) => {
    let headers: string[] = []
    let totalRowsEstimate = 0
    const sampleRows: ParsedRow[] = []
    let xmlBuffer = ''
    let foundSheet = false
    let isTerminated = false
    const unzipper = new fflate.Unzip()
    unzipper.register(fflate.UnzipInflate)
    unzipper.onfile = (file) => {
      if (file.name.replace(/\\/g, '/') !== sheetPath) return
      foundSheet = true
      file.ondata = (err, chunk, final) => {
        if (err || isTerminated) return
        if (chunk) {
          xmlBuffer += fflate.strFromU8(chunk)
          if (totalRowsEstimate === 0) {
            const dimMatch = xmlBuffer.match(/<dimension\b[^>]*\bref="[A-Za-z]+\d+:([A-Za-z]+)(\d+)"/i)
            if (dimMatch) totalRowsEstimate = Math.max(0, parseInt(dimMatch[2], 10) - 1)
          }
          let rowEndIdx: number
          while ((rowEndIdx = xmlBuffer.indexOf('</row>')) !== -1) {
            const rowStartIdx = xmlBuffer.indexOf('<row')
            if (rowStartIdx !== -1 && rowStartIdx < rowEndIdx) {
              const parsed = parseRowXml(xmlBuffer.substring(rowStartIdx, rowEndIdx + 6), sharedStrings)
              if (headers.length === 0 && parsed.rawValues.length > 0) {
                headers = parsed.rawValues.map((v) => String(v || '').trim())
              } else if (sampleRows.length < 5) {
                sampleRows.push(parsed)
              }
            }
            xmlBuffer = xmlBuffer.substring(rowEndIdx + 6)
          }
          if (headers.length > 0 && sampleRows.length >= 5 && totalRowsEstimate > 0) {
            isTerminated = true
            resolve({ headers, totalRowsEstimate, sampleRows })
            return
          }
        }
        if (final) {
          if (totalRowsEstimate === 0) totalRowsEstimate = Math.max(0, sampleRows.length)
          isTerminated = true
          resolve({ headers, totalRowsEstimate, sampleRows })
        }
      }
      file.start()
    }
    const CHUNK_SIZE = 512 * 1024
    for (let i = 0; i < uint8.length && !isTerminated; i += CHUNK_SIZE) {
      unzipper.push(uint8.subarray(i, Math.min(i + CHUNK_SIZE, uint8.length)), i + CHUNK_SIZE >= uint8.length)
    }
    if (!foundSheet && !isTerminated) resolve({ headers: [], totalRowsEstimate: 0, sampleRows: [] })
  })
}

/**
 * Lê a aba tabular correta. Planilhas de margem podem ter abas de resumo/pivô
 * antes da aba BD/BD_Meta; por isso a seleção não pode ficar presa a sheet1.xml.
 */
export async function extractHeadersAndMetadata(
  uint8: Uint8Array,
  requestedSheetPath?: string,
): Promise<{
  headers: string[]
  totalRowsEstimate: number
  sampleRows: ParsedRow[]
  sharedStrings: string[]
  sheetPath: string
}> {
  const sharedStrings = await extractSharedStrings(uint8)
  const candidates = requestedSheetPath ? [requestedSheetPath] : await discoverWorksheetPaths(uint8)
  let best = { headers: [] as string[], totalRowsEstimate: 0, sampleRows: [] as ParsedRow[], sheetPath: candidates[0] }
  for (const candidate of candidates) {
    const result = await scanWorksheetMetadata(uint8, sharedStrings, candidate)
    const textHeaders = result.headers.filter((h) => /[A-Za-zÀ-ÿ]/.test(h)).length
    const score = textHeaders * 1000000 + result.headers.filter(Boolean).length * 1000 + result.totalRowsEstimate
    const bestTextHeaders = best.headers.filter((h) => /[A-Za-zÀ-ÿ]/.test(h)).length
    const bestScore = bestTextHeaders * 1000000 + best.headers.filter(Boolean).length * 1000 + best.totalRowsEstimate
    if (score > bestScore) best = { ...result, sheetPath: candidate }
  }
  return best
}

/**
 * Extrai UMA FATIA de linhas de dados em streaming incremental
 */
export async function streamSheetChunk(
  uint8: Uint8Array,
  params: {
    startRow1Based: number
    maxRowsToCollect: number
    maxWorkTimeMs: number
    sharedStrings: string[]
    sheetPath?: string
  },
  onRow: (row: ParsedRow) => Promise<boolean | void> | boolean | void,
): Promise<{
  rowsProcessed: number
  lastRowProcessed: number
  totalRowsEncountered: number
  reachedTimeLimit: boolean
  reachedMaxRows: boolean
  endOfFile: boolean
}> {
  const {
    startRow1Based,
    maxRowsToCollect,
    maxWorkTimeMs,
    sharedStrings,
    sheetPath = 'xl/worksheets/sheet1.xml',
  } = params

  const startTime = Date.now()

  return new Promise((resolve, reject) => {
    let rowsProcessed = 0
    let lastRowProcessed = startRow1Based - 1
    let totalRowsEncountered = 0
    let reachedTimeLimit = false
    let reachedMaxRows = false
    let endOfFile = false
    let shouldStop = false

    let xmlBuffer = ''
    let isTerminated = false

    const unzipper = new fflate.Unzip()
    unzipper.register(fflate.UnzipInflate)

    unzipper.onfile = (file) => {
      const name = file.name.replace(/\\/g, '/')
      if (name === sheetPath) {
        file.ondata = (err, chunk, final) => {
          if (err || isTerminated) return

          if (chunk && !shouldStop) {
            xmlBuffer += fflate.strFromU8(chunk)

            let rowEndIdx: number
            while (!shouldStop && (rowEndIdx = xmlBuffer.indexOf('</row>')) !== -1) {
              const rowStartIdx = xmlBuffer.indexOf('<row')
              if (rowStartIdx !== -1 && rowStartIdx < rowEndIdx) {
                const rowXml = xmlBuffer.substring(rowStartIdx, rowEndIdx + 6)
                const parsed = parseRowXml(rowXml, sharedStrings)
                totalRowsEncountered++

                if (parsed.rowNumber >= startRow1Based) {
                  rowsProcessed++
                  lastRowProcessed = parsed.rowNumber

                  const stopSignal = onRow(parsed)
                  if (stopSignal === false) {
                    shouldStop = true
                  }

                  if (rowsProcessed >= maxRowsToCollect) {
                    reachedMaxRows = true
                    shouldStop = true
                  }

                  if (Date.now() - startTime >= maxWorkTimeMs) {
                    reachedTimeLimit = true
                    shouldStop = true
                  }
                }
              }
              xmlBuffer = xmlBuffer.substring(rowEndIdx + 6)
            }
          }

          if (final || shouldStop) {
            if (final && !shouldStop) {
              endOfFile = true
            }
            isTerminated = true
            resolve({
              rowsProcessed,
              lastRowProcessed,
              totalRowsEncountered,
              reachedTimeLimit,
              reachedMaxRows,
              endOfFile,
            })
          }
        }
        file.start()
      }
    }

    try {
      const CHUNK_SIZE = 512 * 1024
      for (let i = 0; i < uint8.length && !isTerminated; i += CHUNK_SIZE) {
        const slice = uint8.subarray(i, Math.min(i + CHUNK_SIZE, uint8.length))
        const isFinal = i + CHUNK_SIZE >= uint8.length
        unzipper.push(slice, isFinal)
      }
    } catch (pushErr) {
      if (!isTerminated) {
        reject(pushErr)
      }
    }
  })
}

/**
 * Normaliza datas: serial Excel, DD/MM/AAAA, AAAA-MM-DD ou ISO
 */
export function sanitizeIsoDate(val: unknown): string | null {
  if (val === null || val === undefined || val === '') return null

  if (val instanceof Date) {
    if (isNaN(val.getTime())) return null
    return val.toISOString().slice(0, 10)
  }

  if (typeof val === 'number' || (typeof val === 'string' && /^\d+(\.\d+)?$/.test(val.trim()))) {
    const num = Number(val)
    if (num >= 1 && num <= 100000) {
      try {
        const msPerDay = 86400000
        const wholeDays = Math.floor(num)
        const excelEpochMs = Date.UTC(1899, 11, 30)
        const dateUtc = new Date(excelEpochMs + wholeDays * msPerDay)
        if (!isNaN(dateUtc.getTime())) {
          return dateUtc.toISOString().slice(0, 10)
        }
      } catch {
        // Fallback
      }
    }
  }

  const str = String(val).trim()
  if (!str) return null

  if (/^\d{4}-\d{2}-\d{2}/.test(str)) {
    return str.slice(0, 10)
  }

  const ddmmyyyy = /^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})/
  const match = str.match(ddmmyyyy)
  if (match) {
    const d = match[1].padStart(2, '0')
    const m = match[2].padStart(2, '0')
    const y = match[3]
    return `${y}-${m}-${d}`
  }

  try {
    const d = new Date(str)
    if (!isNaN(d.getTime())) {
      return d.toISOString().slice(0, 10)
    }
  } catch {
    // null
  }

  return null
}

/**
 * Converte strings numéricas em pt-BR ("1.234,56" ou "- 12,34") ou number para float JS
 */
export function parsePtBrNumber(val: unknown, fallback = 0): number {
  if (val === null || val === undefined || val === '') return fallback
  if (typeof val === 'number') return isNaN(val) ? fallback : val

  const str = String(val).trim()
  if (!str) return fallback

  const clean = str.replace(/\s/g, '').replace(/R\$/gi, '').replace(/\./g, '').replace(',', '.')
  const num = parseFloat(clean)
  return isNaN(num) ? fallback : num
}

/**
 * HASH DETERMINÍSTICO ANTI-DUPLICAÇÃO REAL
 */
export function generateDeterministicHash(
  entidade: string,
  linhaNormalizada: Record<string, unknown>,
): string {
  const sortedKeys = Object.keys(linhaNormalizada).sort()
  const contentParts: string[] = [entidade]

  for (const k of sortedKeys) {
    const v = linhaNormalizada[k]
    if (v !== undefined && v !== null && String(v).trim() !== '') {
      contentParts.push(`${k}:${String(v).trim()}`)
    }
  }

  const rawStr = contentParts.join('|')
  let hash1 = 5381
  let hash2 = 52711

  for (let i = 0; i < rawStr.length; i++) {
    const char = rawStr.charCodeAt(i)
    hash1 = (hash1 * 33) ^ char
    hash2 = (hash2 * 33) ^ char
  }

  const h1 = (hash1 >>> 0).toString(16).padStart(8, '0')
  const h2 = (hash2 >>> 0).toString(16).padStart(8, '0')
  return `h_${h1}${h2}`
}

/**
 * Detecta o tipo da planilha e entidade com base no cabeçalho
 */
export function detectarTipoPlanilha(headers: string[]): {
  tipo: 'GESTAO_PRODUCAO' | 'MARGEM' | 'CLIENTES' | 'ESTOQUE' | 'GERAL'
  entidade: string
  tabelaDestino: string
  label: string
} {
  const norm = headers.map((h) =>
    String(h || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim(),
  )

  const has = (sub: string) => norm.some((h) => h.includes(sub))

  const hasPedido = has('pedido')
  const hasGestaoSign =
    has('nf') ||
    has('fat r$') ||
    has('status da linha') ||
    has('status') ||
    has('op') ||
    has('picking') ||
    has('romaneio') ||
    has('cod mp') ||
    has('pa')

  if (hasPedido && hasGestaoSign) {
    return {
      tipo: 'GESTAO_PRODUCAO',
      entidade: 'GESTAO_PRODUCAO_ITEM',
      tabelaDestino: 'pedidos_venda',
      label: 'Gestão da Produção (Pedidos + Itens + PCP)',
    }
  }

  const hasMargem =
    has('receita bruta') ||
    has('receita liquida') ||
    has('mcii') ||
    has('pv/kg') ||
    has('margem') ||
    has('ggf')

  if (hasMargem) {
    return {
      tipo: 'MARGEM',
      entidade: 'MARGEM',
      tabelaDestino: 'pedidos_venda',
      label: 'Margem Financeira (MARGEM_GABR)',
    }
  }

  const hasClientes = has('razao_social') || has('razao social') || has('cnpj') || has('cnpj_cpf')
  if (hasClientes && !hasPedido) {
    return {
      tipo: 'CLIENTES',
      entidade: 'CLIENTES',
      tabelaDestino: 'clientes',
      label: 'Clientes ERP',
    }
  }

  const hasEstoque = has('estoque') || has('deposito') || has('qtd disponivel')
  if (hasEstoque) {
    return {
      tipo: 'ESTOQUE',
      entidade: 'ESTOQUE',
      tabelaDestino: 'estoque',
      label: 'Estoque Físico',
    }
  }

  return {
    tipo: 'GERAL',
    entidade: 'GERAL',
    tabelaDestino: 'pedidos_venda',
    label: 'Planilha Geral',
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders })
  }

  const startTime = Date.now()
  let importacaoId: string | null = null

  try {
    let body: Record<string, unknown> = {}
    try {
      body = await req.json()
    } catch (jsonErr: any) {
      console.error('[processar-importacao] Erro ao parsear JSON de requisição:', jsonErr)
      return new Response(
        JSON.stringify({ sucesso: false, erro: 'Payload JSON inválido: ' + jsonErr.message }),
        { status: 400, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
      )
    }

    importacaoId = (body.importacao_id as string) || null
    const modoDeteccaoSomente = Boolean(body.modo_deteccao_somente)
    const tipoConfirmadoUsuario = (body.confirmar_tipo as string) || null
    const userMaxLinhas =
      typeof body.max_linhas_por_invocacao === 'number' ? body.max_linhas_por_invocacao : null

    if (!importacaoId) {
      return new Response(
        JSON.stringify({ sucesso: false, erro: 'Parâmetro importacao_id é obrigatório.' }),
        { status: 400, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
      )
    }

    console.log(
      `[processar-importacao] Executando importacao_id=${importacaoId}, modoDeteccao=${modoDeteccaoSomente}`,
    )

    // 1. Busca registro na tabela de controle 'importacoes'
    const { data: importacao, error: importacaoErr } = await supabase
      .from('importacoes')
      .select('*')
      .eq('id', importacaoId)
      .single()

    if (importacaoErr || !importacao) {
      const msg = `Importação ${importacaoId} não encontrada: ${importacaoErr?.message || 'registro inexistente'}`
      console.error(`[processar-importacao] ${msg}`)
      return new Response(JSON.stringify({ sucesso: false, erro: msg }), {
        status: 404,
        headers: { 'Content-Type': 'application/json', ...corsHeaders },
      })
    }

    // 2. Baixa o arquivo XLSX do bucket privado 'imports'
    const storagePath = importacao.storage_path
    console.log(`[processar-importacao] Baixando do storage: imports/${storagePath}`)

    const { data: fileBlob, error: downloadErr } = await supabase.storage
      .from('imports')
      .download(storagePath)

    if (downloadErr || !fileBlob) {
      const msg = `Falha ao baixar arquivo XLSX do Storage (${storagePath}): ${downloadErr?.message || 'arquivo vazio'}`
      console.error(`[processar-importacao] ${msg}`)
      await supabase
        .from('importacoes')
        .update({
          status: 'erro',
          erro_mensagem: msg,
          atualizado_em: new Date().toISOString(),
        })
        .eq('id', importacaoId)

      return new Response(JSON.stringify({ sucesso: false, erro: msg }), {
        status: 500,
        headers: { 'Content-Type': 'application/json', ...corsHeaders },
      })
    }

    // 3. Obtém o buffer Uint8Array
    const arrayBuffer = await fileBlob.arrayBuffer()
    const uint8 = new Uint8Array(arrayBuffer)
    console.log(
      `[processar-importacao] Arquivo baixado: ${(uint8.length / (1024 * 1024)).toFixed(2)} MB`,
    )

    // 4. Inspeciona cabeçalhos e metadados de forma streaming
    const { headers, totalRowsEstimate, sampleRows, sharedStrings, sheetPath } =
      await extractHeadersAndMetadata(uint8, importacao.sheet_path || undefined)
    const validHeadersCount = headers.filter((h) => h.length > 0).length

    console.log(
      `[processar-importacao] Metadados extraídos: ${headers.length} colunas (${validHeadersCount} válidas), estimativa total de linhas: ${totalRowsEstimate}`,
    )

    if (validHeadersCount === 0) {
      const msg = 'A planilha está vazia ou não contém cabeçalhos válidos na primeira linha.'
      await supabase
        .from('importacoes')
        .update({ status: 'erro', erro_mensagem: msg, atualizado_em: new Date().toISOString() })
        .eq('id', importacaoId)

      return new Response(JSON.stringify({ sucesso: false, erro: msg }), {
        status: 400,
        headers: { 'Content-Type': 'application/json', ...corsHeaders },
      })
    }

    // 5. Detecção automática do tipo de planilha
    const deteccao = detectarTipoPlanilha(headers)
    const tipoFinal =
      tipoConfirmadoUsuario ||
      (importacao.tipo_planilha !== 'desconhecido' ? importacao.tipo_planilha : deteccao.tipo)
    const entidadeFinal = deteccao.entidade
    const tabelaDestinoFinal = deteccao.tabelaDestino

    console.log(
      `[processar-importacao] Detecção de tipo: ${deteccao.tipo} (${deteccao.label}), tipoFinal: ${tipoFinal}`,
    )

    // Se for apenas modo de detecção:
    if (modoDeteccaoSomente) {
      const amostraPreview: Record<string, unknown>[] = []
      for (const sample of sampleRows) {
        const rowObj: Record<string, unknown> = {}
        headers.forEach((h, colIdx) => {
          if (h) {
            rowObj[h] = sample.cells[colIdx] ?? sample.rawValues[colIdx] ?? ''
          }
        })
        amostraPreview.push(rowObj)
      }

      await supabase
        .from('importacoes')
        .update({
          tipo_planilha: deteccao.tipo,
          tipo_confirmado: true,
          sheet_path: sheetPath,
          linhas_total: totalRowsEstimate,
          entidade: entidadeFinal,
          atualizado_em: new Date().toISOString(),
        })
        .eq('id', importacaoId)

      return new Response(
        JSON.stringify({
          sucesso: true,
          modoDeteccao: true,
          importacaoId,
          deteccao,
          totalLinhas: totalRowsEstimate,
          headers: headers.filter((h) => h.length > 0),
          amostra: amostraPreview,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
      )
    }

    // 6. Ingestão incremental na STAGING com Checkpoint
    const checkpoint = importacao.linha_checkpoint || 0
    const syncId = importacao.sync_id || `SYNC-IMP-${importacaoId.slice(0, 8)}`

    // Atualiza status para 'processando', salvando tipo e total de linhas
    await supabase
      .from('importacoes')
      .update({
        status: 'processando',
        tipo_planilha: tipoFinal,
        tipo_confirmado: true,
        sheet_path: sheetPath,
        linhas_total: totalRowsEstimate > 0 ? totalRowsEstimate : importacao.linhas_total,
        entidade: entidadeFinal,
        sync_id: syncId,
        erro_mensagem: null,
        atualizado_em: new Date().toISOString(),
      })
      .eq('id', importacaoId)

    // Se o checkpoint já atingiu ou ultrapassou o total conhecido (>0), finaliza
    if (totalRowsEstimate > 0 && checkpoint >= totalRowsEstimate) {
      await supabase
        .from('importacoes')
        .update({
          status: 'aguardando_aprovacao',
          linha_checkpoint: totalRowsEstimate,
          linhas_total: totalRowsEstimate,
          atualizado_em: new Date().toISOString(),
        })
        .eq('id', importacaoId)

      return new Response(
        JSON.stringify({
          sucesso: true,
          importacaoId,
          finalizou: true,
          status: 'aguardando_aprovacao',
          checkpoint: totalRowsEstimate,
          totalLinhas: totalRowsEstimate,
          linhasLote: 0,
          linhasValidas: importacao.linhas_validas || 0,
          linhasErro: importacao.linhas_erro || 0,
          linhasDuplicadas: importacao.linhas_duplicadas || 0,
          duracaoMs: Date.now() - startTime,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
      )
    }

    // Configuração de fatias seguras
    // Fatias padrão de 3.000 linhas ou até 40 segundos de trabalho por invocação
    const MAX_LINHAS_INVOCACAO = userMaxLinhas || 3000
    const MAX_WORK_TIME_MS = 40000
    const SUB_BATCH_SIZE = 500

    const startRowExcel = 2 + checkpoint

    console.log(
      `[processar-importacao] Iniciando fatia streaming a partir da linha Excel ${startRowExcel} (checkpoint=${checkpoint})`,
    )

    let linhasProcessadasLote = 0
    let linhasValidasLote = 0
    let linhasErroLote = 0
    let linhasDuplicadasLote = 0

    const errosDetalhados: Array<{
      linha: number
      coluna: string
      valor: unknown
      motivo: string
    }> = []
    let stagingSubBatch: Array<Record<string, unknown>> = []

    const flushStagingSubBatch = async () => {
      if (stagingSubBatch.length === 0) return

      const currentToInsert = stagingSubBatch
      stagingSubBatch = []

      const hashes = currentToInsert.map((s) => s.hash_registro as string)
      const { data: existingHashes } = await supabase
        .from('staging_dados')
        .select('hash_registro')
        .in('hash_registro', hashes)

      const existingSet = new Set((existingHashes || []).map((x: any) => x.hash_registro))

      const toInsert = currentToInsert.filter((item) => {
        if (existingSet.has(item.hash_registro as string)) {
          linhasDuplicadasLote++
          return false
        }
        return true
      })

      if (toInsert.length > 0) {
        const { error: insertErr } = await supabase.from('staging_dados').insert(toInsert)
        if (insertErr) {
          console.warn(
            `[processar-importacao] Inserção de lote com aviso: ${insertErr.message}. Tentando por item individual...`,
          )
          for (const item of toInsert) {
            await supabase
              .from('staging_dados')
              .insert(item)
              .catch(() => {})
          }
        }
      }
    }

    // Processa a fatia com o streaming parser
    const streamResult = await streamSheetChunk(
      uint8,
      {
        startRow1Based: startRowExcel,
        maxRowsToCollect: MAX_LINHAS_INVOCACAO,
        maxWorkTimeMs: MAX_WORK_TIME_MS,
        sharedStrings,
        sheetPath,
      },
      async (row: ParsedRow) => {
        const numeroLinhaExcel = row.rowNumber
        const payloadOriginal: Record<string, unknown> = {}
        const dadosTransformados: Record<string, unknown> = {}
        let temConteudo = false

        headers.forEach((h, colIdx) => {
          if (!h) return
          const rawVal = row.cells[colIdx] ?? row.rawValues[colIdx] ?? ''
          if (rawVal !== undefined && rawVal !== null && String(rawVal).trim() !== '') {
            temConteudo = true
          }
          payloadOriginal[h] = rawVal

          const hNorm = h.toLowerCase().trim()
          let valNormalizado: unknown = rawVal

          if (
            hNorm.includes('data') ||
            hNorm.includes('dt_') ||
            hNorm === 'emissao' ||
            hNorm === 'entrega'
          ) {
            valNormalizado = sanitizeIsoDate(rawVal)
          } else if (
            hNorm.includes('peso') ||
            hNorm.includes('qtd') ||
            hNorm.includes('quantidade') ||
            hNorm.includes('preco') ||
            hNorm.includes('preço') ||
            hNorm.includes('total') ||
            hNorm.includes('fat r$') ||
            hNorm.includes('valor') ||
            hNorm.includes('mcii') ||
            hNorm.includes('receita')
          ) {
            valNormalizado = parsePtBrNumber(rawVal)
          } else if (typeof rawVal === 'string') {
            valNormalizado = rawVal.trim()
          }

          dadosTransformados[hNorm] = valNormalizado
        })

        linhasProcessadasLote++

        if (!temConteudo) {
          return
        }

        let motivoErro: string | null = null
        let colunaComErro: string | null = null
        let valorComErro: unknown = null

        if (tipoFinal === 'GESTAO_PRODUCAO') {
          const pedidoVal =
            dadosTransformados['pedido'] ?? payloadOriginal['Pedido'] ?? payloadOriginal['pedido']

          if (!pedidoVal || String(pedidoVal).trim() === '') {
            motivoErro = 'Número do Pedido ausente ou em branco na linha.'
            colunaComErro = 'Pedido'
            valorComErro = pedidoVal
          }
        }

        const hashRegistro = generateDeterministicHash(entidadeFinal, dadosTransformados)

        const rawSourceId =
          dadosTransformados['pedido'] ||
          dadosTransformados['item do pa'] ||
          dadosTransformados['codigo_erp'] ||
          dadosTransformados['codigo'] ||
          `L-${numeroLinhaExcel}`

        if (motivoErro) {
          linhasErroLote++
          errosDetalhados.push({
            linha: numeroLinhaExcel,
            coluna: colunaComErro || 'Geral',
            valor: valorComErro,
            motivo: motivoErro,
          })

          stagingSubBatch.push({
            fonte_id: importacao.fonte_id || null,
            source_system: 'UPLOAD_MANUAL',
            source_id: String(rawSourceId).trim(),
            entidade: entidadeFinal,
            payload_original: payloadOriginal,
            dados_transformados: dadosTransformados,
            sync_id: syncId,
            hash_registro: hashRegistro,
            status_validacao: 'invalido',
            erro_validacao: `Linha ${numeroLinhaExcel} [${colunaComErro}]: ${motivoErro}`,
            tabela_destino: tabelaDestinoFinal,
            ativo: true,
          })
        } else {
          linhasValidasLote++
          stagingSubBatch.push({
            fonte_id: importacao.fonte_id || null,
            source_system: 'UPLOAD_MANUAL',
            source_id: String(rawSourceId).trim(),
            entidade: entidadeFinal,
            payload_original: payloadOriginal,
            dados_transformados: dadosTransformados,
            sync_id: syncId,
            hash_registro: hashRegistro,
            status_validacao: 'valido',
            erro_validacao: null,
            tabela_destino: tabelaDestinoFinal,
            ativo: true,
          })
        }

        if (stagingSubBatch.length >= SUB_BATCH_SIZE) {
          await flushStagingSubBatch()
        }
      },
    )

    // Descarrega o sub-lote restante
    await flushStagingSubBatch()

    const novoCheckpoint = checkpoint + streamResult.rowsProcessed
    const totalLinhasReal = totalRowsEstimate > 0 ? totalRowsEstimate : novoCheckpoint
    const finalizou =
      streamResult.endOfFile || (totalRowsEstimate > 0 && novoCheckpoint >= totalRowsEstimate)
    const statusProximo = finalizou ? 'aguardando_aprovacao' : 'processando'

    const totalValidas = (importacao.linhas_validas || 0) + linhasValidasLote
    const totalErros = (importacao.linhas_erro || 0) + linhasErroLote
    const totalDuplicadas = (importacao.linhas_duplicadas || 0) + linhasDuplicadasLote

    console.log(
      `[processar-importacao] Fatia concluída: processadas=${streamResult.rowsProcessed}, checkpoint=${novoCheckpoint}/${totalLinhasReal}, válidasLote=${linhasValidasLote}, errosLote=${linhasErroLote}, duplicadasLote=${linhasDuplicadasLote}, finalizou=${finalizou}`,
    )

    // Atualiza importacoes
    await supabase
      .from('importacoes')
      .update({
        linha_checkpoint: novoCheckpoint,
        linhas_total: totalLinhasReal,
        linhas_validas: totalValidas,
        linhas_erro: totalErros,
        linhas_duplicadas: totalDuplicadas,
        status: statusProximo,
        erro_mensagem: null,
        atualizado_em: new Date().toISOString(),
      })
      .eq('id', importacaoId)

    // Atualiza histórico de importações
    try {
      await supabase.from('historico_importacoes').upsert(
        {
          sync_id: syncId,
          fonte_id: importacao.fonte_id || null,
          entidade: entidadeFinal,
          iniciado_em: new Date(startTime).toISOString(),
          finalizado_em: finalizou ? new Date().toISOString() : null,
          status: finalizou ? (totalErros > 0 ? 'parcial' : 'sucesso') : 'processando',
          registros_lidos: novoCheckpoint,
          registros_inseridos: totalValidas,
          registros_atualizados: totalDuplicadas,
          registros_erro: totalErros,
          origem_arquivo: importacao.nome_arquivo,
          log: finalizou
            ? `Processamento finalizado na staging: ${totalValidas} linhas válidas, ${totalDuplicadas} duplicatas, ${totalErros} erros. Aguardando aprovação.`
            : `Processando fatias no servidor: ${novoCheckpoint}/${totalLinhasReal} linhas lidas...`,
          duracao_ms: Date.now() - startTime,
        },
        { onConflict: 'sync_id' },
      )
    } catch (hErr) {
      console.warn('[processar-importacao] Aviso ao atualizar historico:', hErr)
    }

    return new Response(
      JSON.stringify({
        sucesso: true,
        importacaoId,
        finalizou,
        status: statusProximo,
        checkpoint: novoCheckpoint,
        totalLinhas: totalLinhasReal,
        linhasLote: streamResult.rowsProcessed,
        linhasValidas: totalValidas,
        linhasErro: totalErros,
        linhasDuplicadas: totalDuplicadas,
        errosDetalhadosLote: errosDetalhados.slice(0, 50),
        duracaoMs: Date.now() - startTime,
      }),
      { status: 200, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    )
  } catch (fatalErr: any) {
    const errorMsg = fatalErr?.message || String(fatalErr)
    console.error(`[processar-importacao] ERRO FATAL: ${errorMsg}`, fatalErr?.stack)

    if (importacaoId) {
      try {
        await supabase
          .from('importacoes')
          .update({
            status: 'erro',
            erro_mensagem: `Falha no processamento: ${errorMsg}`,
            atualizado_em: new Date().toISOString(),
          })
          .eq('id', importacaoId)
      } catch {
        // ignora
      }
    }

    return new Response(
      JSON.stringify({
        sucesso: false,
        erro: `Falha na Edge Function processar-importacao: ${errorMsg}`,
      }),
      { status: 500, headers: { 'Content-Type': 'application/json', ...corsHeaders } },
    )
  }
})
