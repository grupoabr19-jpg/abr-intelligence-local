(() => {
  const shouldCapture = (url, contentType) => {
    try {
      const parsed = new URL(url, location.href)
      if (parsed.origin !== location.origin) return false
      if (/\.(js|css|png|jpg|jpeg|svg|woff2?|ico)(\?|$)/i.test(parsed.pathname)) return false
      return /json|javascript|text\//i.test(contentType || '') || /api|report|query|data|execute/i.test(parsed.pathname)
    } catch {
      return false
    }
  }

  const emit = (event) => window.dispatchEvent(new CustomEvent('abr-aster-network', { detail: event }))
  const originalFetch = window.fetch
  window.fetch = async (...args) => {
    const response = await originalFetch(...args)
    try {
      const request = args[0]
      const init = args[1] || {}
      const url = typeof request === 'string' ? request : request.url
      const method = init.method || (typeof request === 'object' && request.method) || 'GET'
      const contentType = response.headers.get('content-type') || ''
      if (shouldCapture(url, contentType)) {
        const clone = response.clone()
        const text = await clone.text()
        if (text.length <= 8 * 1024 * 1024) emit({ kind: 'fetch', url, method, status: response.status, contentType, text })
      }
    } catch {}
    return response
  }

  const OriginalXHR = window.XMLHttpRequest
  window.XMLHttpRequest = function () {
    const xhr = new OriginalXHR()
    let method = 'GET'
    let url = ''
    const open = xhr.open
    xhr.open = function (m, u, ...rest) {
      method = m
      url = u
      return open.call(xhr, m, u, ...rest)
    }
    xhr.addEventListener('load', () => {
      try {
        const contentType = xhr.getResponseHeader('content-type') || ''
        if (shouldCapture(url, contentType) && typeof xhr.responseText === 'string' && xhr.responseText.length <= 8 * 1024 * 1024) {
          emit({ kind: 'xhr', url, method, status: xhr.status, contentType, text: xhr.responseText })
        }
      } catch {}
    })
    return xhr
  }
  window.XMLHttpRequest.prototype = OriginalXHR.prototype
})()
