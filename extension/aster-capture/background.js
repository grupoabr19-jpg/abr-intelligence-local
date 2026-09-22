const DEFAULTS = { enabled: false, ingestUrl: '', collectorKey: '', fonteId: '', entidade: 'aster_relatorio' }

async function getConfig() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(DEFAULTS)) }
}

function parseJson(text) {
  try { return JSON.parse(text) } catch { return null }
}

function findRows(value, best = []) {
  if (Array.isArray(value)) {
    const objects = value.filter((item) => item && typeof item === 'object' && !Array.isArray(item))
    if (objects.length > best.length) best = objects
    for (const item of value.slice(0, 20)) best = findRows(item, best)
  } else if (value && typeof value === 'object') {
    for (const item of Object.values(value)) best = findRows(item, best)
  }
  return best
}

async function sendCapture(payload) {
  const config = await getConfig()
  if (!config.enabled || !config.ingestUrl || !config.collectorKey || !config.fonteId) return { skipped: true }
  const parsed = parseJson(payload.text)
  if (!parsed) return { skipped: true }
  const rows = findRows(parsed).slice(0, 1000)
  if (!rows.length) return { skipped: true }
  const syncId = `ASTER-${new Date().toISOString().replace(/[-:.TZ]/g, '')}`
  const response = await fetch(config.ingestUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-collector-key': config.collectorKey },
    body: JSON.stringify({
      fonte_id: config.fonteId,
      sync_id: syncId,
      entidade: config.entidade,
      rows,
      metadata: { endpoint: payload.url, method: payload.method, status: payload.status },
    }),
  })
  return { sent: response.ok, rows: rows.length, status: response.status }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== 'ASTER_NETWORK_CAPTURE') return false
  sendCapture(message.payload)
    .then((result) => sendResponse(result))
    .catch((error) => sendResponse({ sent: false, error: error.message }))
  return true
})

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== 'ASTER_GET_CONFIG') {
    if (message?.type === 'ASTER_SET_CONFIG') {
      chrome.storage.local.set({ ...DEFAULTS, ...message.config }).then(() => sendResponse({ ok: true }))
      return true
    }
    return false
  }
  getConfig().then((config) => sendResponse(config))
  return true
})
