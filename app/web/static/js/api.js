// JSON over fetch, with a deadline. An error carries `status` (0: no connection / timeout).

async function call(method, url, body, timeout = 30000) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  try {
    const res = await fetch(url, {
      method,
      headers: body ? { 'content-type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: ctl.signal,
      cache: 'no-store',
    });
    if (!res.ok) {
      const err = new Error(`http ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return await res.json();
  } catch (err) {
    if (err.status == null) err.status = 0;
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

const qs = (params) => new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '')).toString();

// POST /api/turn answers NDJSON: `{"stage": …}` lines while the core works, then `{"answer": …}` or `{"error": …}`.
async function turn(body, onStage, timeout = 90000) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeout);
  const fail = (status) => Object.assign(new Error(`turn ${status}`), { status });
  try {
    const res = await fetch('/api/turn', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    if (!res.ok || !res.body) throw fail(res.status);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut;
      while ((cut = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, cut).trim();
        buffer = buffer.slice(cut + 1);
        if (!line) continue;
        const msg = JSON.parse(line);
        if (msg.stage) onStage(msg.stage);
        else if (msg.answer) return msg.answer;
        else throw fail(500);
      }
    }
    throw fail(0);
  } catch (err) {
    if (err.status == null) err.status = 0;
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  config: () => call('GET', '/api/config'),
  strings: () => call('GET', '/api/strings'),
  turn,
  report: (body) => call('POST', '/api/report', body),
  profile: (id, lang) => call('GET', `/api/profile?${qs({ id, lang })}`),
  profileAction: (body) => call('POST', '/api/profile', body),
  city: (layer, params) => call('GET', `/api/city/${layer}?${qs(params)}`),
  data: (lang) => call('GET', `/api/data?${qs({ lang })}`),
  conditions: (fake) => call('GET', `/api/conditions?${qs({ fake })}`, undefined, 8000),
  exportUrl: (name, params) => `/api/city/export/${name}?${qs(params)}`,
};
