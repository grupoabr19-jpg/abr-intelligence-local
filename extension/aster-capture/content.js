(() => {
  const script = document.createElement('script')
  script.src = chrome.runtime.getURL('page-hook.js')
  script.onload = () => script.remove()
  ;(document.head || document.documentElement).appendChild(script)

  window.addEventListener('abr-aster-network', (event) => {
    const detail = event.detail
    if (detail && detail.text) chrome.runtime.sendMessage({ type: 'ASTER_NETWORK_CAPTURE', payload: detail })
  })
})()
