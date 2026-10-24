// har2spy.js — In-browser network interceptor for HAR capture
// Inject via execute_js, then read window.__har2spy_exportHAR()

(function () {
  'use strict';

  if (window.__har2spy_installed) {
    // Already injected; return existing export function
    return { reinit: false };
  }
  window.__har2spy_installed = true;

  const PAGE_START = performance.now();
  const pageUrl = window.location.href || '';
  const pageTitle = document.title || '';

  // ─── Storage ───────────────────────────────────────────────
  const entries = [];          // array of HAR entry objects
  let entryId = 0;

  // Use sessionStorage as a safety net so data survives page reloads
  // (we also copy to the live `entries` array)
  const STORAGE_KEY = '__har2spy_entries__';
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed)) {
        entries.push(...parsed);
        entryId = Math.max(...parsed.map(e => +e._id || 0)) + 1;
      }
    }
  } catch (e) { /* ignore */ }

  function _persist() {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch (e) { /* quota exceeded — keep live copy only */ }
  }

  // ─── Helpers ───────────────────────────────────────────────

  function safeHeaders(obj) {
    const out = [];
    if (!obj) return out;
    if (obj instanceof Headers) {
      obj.forEach((v, k) => out.push({ name: k, value: v }));
    } else if (typeof obj === 'object' && !(obj instanceof String)) {
      for (const [k, v] of Object.entries(obj)) {
        out.push({ name: k, value: Array.isArray(v) ? v.join(', ') : String(v) });
      }
    } else if (typeof obj === 'string') {
      // "Header-Name: value\r\n..."
      obj.split('\n').forEach(line => {
        line = line.trim();
        if (!line) return;
        const idx = line.indexOf(':');
        if (idx > 0) {
          out.push({ name: line.slice(0, idx).trim(), value: line.slice(idx + 1).trim() });
        }
      });
    }
    return out;
  }

  function safeBody(body) {
    if (body == null) return null;
    if (typeof body === 'string') return body;
    if (body instanceof URLSearchParams) return body.toString();
    if (body instanceof Blob) return '[Blob size=' + body.size + ' type=' + body.type + ']';
    if (body instanceof FormData) {
      const parts = [];
      for (const [k, v] of body.entries()) {
        parts.push(k + '=' + (v instanceof File ? '[File ' + v.name + ']' : v));
      }
      return parts.join('&');
    }
    try { return JSON.stringify(body); } catch (e) { return String(body); }
  }

  function toHAR(time, startedDateTime, timeMillis, method, url, reqHeaders, reqBody,
                 statusCode, respHeaders, respBody, connInfo) {
    const end = performance.now();
    return {
      _id: entryId++,
      // --- HAR 1.2 structure ---
      startedDateTime: new Date(startedDateTime).toISOString(),
      time: Math.round(timeMillis),
      request: {
        method: method,
        url: url,
        httpVersion: connInfo.httpVersion || 'HTTP/1.1',
        cookies: [],
        headers: reqHeaders || [],
        queryString: [],
        headersSize: -1,
        bodySize: reqBody != null ? (typeof reqBody === 'string' ? reqBody.length : -1) : 0,
        content: { size: -1, mimeType: '' }
      } ,
      response: {
        status: statusCode || 0,
        statusText: '',
        httpVersion: connInfo.httpVersion || 'HTTP/1.1',
        cookies: [],
        headers: respHeaders || [],
        headersSize: -1,
        bodySize: respBody != null ? (typeof respBody === 'string' ? respBody.length : -1) : -1,
        content: {
          size: respBody != null ? (typeof respBody === 'string' ? respBody.length : -1) : -1,
          mimeType: connInfo.mimeType || 'text/plain',
          text: respBody != null ? respBody : undefined
        }
      },
      cache: {},
      timings: {
        send: 0,
        wait: Math.round(timeMillis / 2),
        receive: Math.round(timeMillis / 2)
      },
      serverIPAddress: connInfo.serverIP || '',
      connection: String(connInfo.connId || ''),
      pageref: 'page_1'
    };
  }

  // ─── fetch() interception ──────────────────────────────────

  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    const start = performance.now();
    const started = Date.now();
    const url = typeof input === 'string' ? input : input.url || '';
    const method = (init && init.method) || (input.method) || 'GET';
    const reqHeaders = safeHeaders(init && init.headers);
    const reqBody = safeBody(init && init.body);

    const entry = {
      _id: entryId++,
      startedDateTime: new Date(started).toISOString(),
      request: { method, url, httpVersion: 'HTTP/1.1', cookies: [], headers: reqHeaders, queryString: [], bodySize: -1, headersSize: -1, content: { size: -1, mimeType: '' } },
      response: { status: 0, statusText: '', httpVersion: 'HTTP/1.1', cookies: [], headers: [], headersSize: -1, bodySize: -1, content: { size: -1, mimeType: '', text: undefined } },
      cache: {}, timings: { send: 0, wait: 0, receive: 0 },
      serverIPAddress: '', connection: '', pageref: 'page_1'
    };

    // Attach request body size
    entry.request.bodySize = reqBody != null ? (typeof reqBody === 'string' ? reqBody.length : -1) : 0;

    entries.push(entry);
    _persist();

    // Build entry with response later
    const entryIndex = entries.length - 1;

    return origFetch.apply(this, arguments).then(async resp => {
      const elapsed = Math.round(performance.now() - start);

      // Clone because we need to read the body
      const clone = resp.clone();
      let respBody = null;
      let respText = null;
      try {
        const ct = clone.headers.get('content-type') || '';
        if (ct.includes('application/json') || ct.includes('text/')) {
          respText = await clone.text();
          respBody = respText;
        } else {
          const buf = await clone.arrayBuffer();
          if (buf.byteLength < 10 * 1024 * 1024) {
            respText = new TextDecoder().decode(new Uint8Array(buf));
            respBody = respText;
          } else {
            respBody = '[binary ' + buf.byteLength + ' bytes]';
          }
        }
      } catch (e) {
        respBody = '[error reading body: ' + e.message + ']';
      }

      const respHeaders = safeHeaders(clone.headers);
      const finalEntry = toHAR(
        resp.status, started, elapsed, method, url,
        reqHeaders, reqBody,
        resp.status, respHeaders, respBody,
        { httpVersion: 'HTTP/1.1', mimeType: clone.headers.get('content-type') || 'text/plain', serverIP: '' }
      );
      // Replace the placeholder entry
      entries[entryIndex] = finalEntry;
      _persist();

      return resp;
    }).catch(err => {
      const elapsed = Math.round(performance.now() - start);
      entries[entryIndex].response.status = -1;
      entries[entryIndex].response.statusText = err.message || String(err);
      entries[entryIndex].response.content.text = err.message;
      entries[entryIndex].time = elapsed;
      entries[entryIndex]._error = err.message;
      _persist();
      throw err;
    });
  };
  // Preserve a reference for restoration if needed
  window.fetch._har2spy_orig = origFetch;

  // ─── XMLHttpRequest interception ───────────────────────────

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, async, user, password) {
    this._har2spy = {
      method: method || 'GET',
      url: url || '',
      headers: {},
      body: null,
      startTime: Date.now()
    };
    return origOpen.apply(this, arguments);
  };

  const origSetRequestHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    if (this._har2spy) {
      this._har2spy.headers[name] = value;
    }
    return origSetRequestHeader.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function (body) {
    const h = this._har2spy;
    if (h) {
      h.body = safeBody(body);
      h.startTime = Date.now();
      h.async = arguments.length >= 3 ? arguments[2] : true;
    }

    const entry = {
      _id: entryId++,
      startedDateTime: new Date(h ? h.startTime : Date.now()).toISOString(),
      request: {
        method: h ? h.method : 'GET',
        url: h ? h.url : '',
        httpVersion: 'HTTP/1.1',
        cookies: [],
        headers: Object.entries(h ? h.headers : {}).map(([k, v]) => ({ name: k, value: v })),
        queryString: [],
        bodySize: h && h.body != null ? (typeof h.body === 'string' ? h.body.length : -1) : 0,
        headersSize: -1,
        content: { size: -1, mimeType: '' }
      },
      response: {
        status: 0,
        statusText: '',
        httpVersion: 'HTTP/1.1',
        cookies: [],
        headers: [],
        headersSize: -1,
        bodySize: -1,
        content: { size: -1, mimeType: '', text: undefined }
      },
      cache: {},
      timings: { send: 0, wait: 0, receive: 0 },
      serverIPAddress: '',
      connection: '',
      pageref: 'page_1'
    };
    entries.push(entry);
    _persist();

    const entryIndex = entries.length - 1;

    const self = this;
    const originalOnReady = this.onreadystatechange ? this.onreadystatechange : null;
    if (originalOnReady) {
      // Don't override — wrap via setTimeout polling instead
    }

    // Also listen globally
    if (h) {
      h.entryIndex = entryIndex;
    }

    this.onreadystatechange = function () {
      if (self.readyState === 4) {
        const elapsed = Math.round(performance.now() - (h ? h.startTime : performance.now()));

        let respHeaders = [];
        try {
          const rh = self.getAllResponseHeaders();
          respHeaders = safeHeaders(rh);
        } catch (e) { /* security */ }

        let respBody = null;
        try {
          if (typeof self.responseText === 'string') {
            respBody = self.responseText;
          }
        } catch (e) {
          respBody = '[error: ' + e.message + ']';
        }

        entries[entryIndex].response.status = self.status || 0;
        entries[entryIndex].response.statusText = self.statusText || '';
        entries[entryIndex].response.headers = respHeaders;
        entries[entryIndex].response.content.mimeType = (respHeaders.find(h => h.name.toLowerCase() === 'content-type') || { value: 'text/plain' }).value || 'text/plain';
        entries[entryIndex].response.content.text = respBody;
        entries[entryIndex].response.content.size = respBody != null ? (typeof respBody === 'string' ? respBody.length : -1) : -1;
        entries[entryIndex].response.bodySize = respBody != null ? (typeof respBody === 'string' ? respBody.length : -1) : -1;
        entries[entryIndex].time = elapsed;
        entries[entryIndex]._xhr = true;
        _persist();
      }
      if (originalOnReady) originalOnReady.apply(this, arguments);
    };

    return origSend.apply(this, arguments);
  };

  // ─── Form submission interception ──────────────────────────

  // We can't easily intercept form submissions that cause navigation
  // (data is lost), but we can intercept forms that use XHR/fetch.
  // For traditional form submits, we'll rely on the browser's navigation
  // and then use performance API to capture what we can.

  // ─── Export functions ──────────────────────────────────────

  window.__har2spy_exportHAR = function (options) {
    options = options || {};
    _persist();

    const creator = options.creator || 'har2spy';
    const created = options.created || new Date().toISOString();

    // Filter entries
    let filtered = entries.slice();
    if (options.onlyXHR) {
      filtered = filtered.filter(e => e._xhr || e.request.method.toUpperCase() === 'GET' || e.request.method.toUpperCase() === 'POST');
      // Further filter: keep only XHR-like requests (no document navigations)
      filtered = filtered.filter(e => {
        const url = e.request.url;
        if (!url) return false;
        // Exclude common non-API requests
        const skipPatterns = [
          /favicon\.ico$/, /\.css$/, /(?:\.min\.)?js$/, /\.png$/, /\.jpg$/, /\.gif$/, /\.webp$/, /\.woff/, /\.ico$/, /\.svg$/
        ];
        return !skipPatterns.some(p => p.test(url));
      });
    }
    if (options.urlContains) {
      filtered = filtered.filter(e => e.request.url.includes(options.urlContains));
    }
    if (options.method) {
      const m = options.method.toUpperCase();
      filtered = filtered.filter(e => e.request.method.toUpperCase() === m);
    }
    if (options.minTime) {
      filtered = filtered.filter(e => (e.time || 0) >= options.minTime);
    }
    if (options.afterMs) {
      filtered = filtered.filter(e => (e._id || 0) > (options.afterMs || 0)); // rough: use _id as marker
    }

    // Clean internal fields
    filtered = filtered.map(e => {
      // Build a proper HAR entry without internal fields
      const clean = {
        startedDateTime: e.startedDateTime,
        time: e.time,
        request: e.request,
        response: e.response,
        cache: e.cache,
        timings: e.timings,
        serverIPAddress: e.serverIPAddress,
        connection: e.connection,
        pageref: e.pageref
      };
      // Mark XHR entries for analysis
      Object.defineProperty(clean, '_xhr', { value: !!e._xhr, enumerable: true });
      Object.defineProperty(clean, '_error', { value: e._error, enumerable: !!e._error });
      return clean;
    });

    const har = {
      log: {
        version: '1.2',
        creator: { name: creator, comment: creator + ' via har2spy' },
        pages: [{
          id: 'page_1',
          startedDateTime: new Date(PAGE_START).toISOString(),
          pageTimings: { onLoad: 0, onContentEvent: -1 }
        }],
        entries: filtered
      }
    };

    return JSON.stringify(har);
  };

  window.__har2spy_count = function () { return entries.length; };
  window.__har2spy_clear = function () {
    entries.length = 0;
    entryId = 0;
    try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) { /* */ }
  };
  window.__har2spy_entriesRaw = function () { return entries.slice(); };
  window.__har2spy_setPageRef = function (ref) {
    entries.forEach(e => e.pageref = ref);
    _persist();
  };
  window.__har2spy_marker = function (name) {
    // Returns current entry count — caller can use this to later
    // extract only entries captured AFTER this point.
    window.__har2spy_marker_id = entryId;
    return entryId;
  };

  // ─── Intercept fetch/XHR error logging ─────────────────────

  // Catch unhandled rejection from fetch (don't interfere)
  // We already handle errors in our wrappers.

  return "har2spy:installed";
})();
