const ids = ['enabled', 'ingestUrl', 'collectorKey', 'fonteId', 'entidade']
const status = document.getElementById('status')

chrome.runtime.sendMessage({ type: 'ASTER_GET_CONFIG' }, (config) => {
  if (chrome.runtime.lastError || !config) return
  for (const id of ids) {
    const element = document.getElementById(id)
    if (element.type === 'checkbox') element.checked = Boolean(config[id])
    else element.value = config[id] || ''
  }
})

document.getElementById('save').addEventListener('click', () => {
  const config = Object.fromEntries(ids.map((id) => {
    const element = document.getElementById(id)
    return [id, element.type === 'checkbox' ? element.checked : element.value.trim()]
  }))
  chrome.runtime.sendMessage({ type: 'ASTER_SET_CONFIG', config }, () => {
    status.textContent = 'Configuração salva nesta extensão.'
  })
})
