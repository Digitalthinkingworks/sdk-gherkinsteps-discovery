/* ==========================================================================
   SDK Step Discovery — app.js
   All UI logic: chat, API calls, result card rendering, scaffold loading.
   ========================================================================== */

const API = 'http://localhost:8002';   // same origin — FastAPI serves both /ui and /query
let isLoading = false;

// ── DOM refs (resolved after DOMContentLoaded) ────────────────────────────
let msgsEl, inputEl, sendBtn, resultEl, emptyEl, sdkSel, dotEl, statusTxt;

document.addEventListener('DOMContentLoaded', () => {
  msgsEl    = document.getElementById('messages');
  inputEl   = document.getElementById('queryInput');
  sendBtn   = document.getElementById('sendBtn');
  resultEl  = document.getElementById('resultPanel');
  emptyEl   = document.getElementById('emptyState');
  sdkSel    = document.getElementById('sdkFilter');
  dotEl     = document.getElementById('statusDot');
  statusTxt = document.getElementById('statusText');

  inputEl.addEventListener('input', autoResize);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(); }
  });
  sendBtn.addEventListener('click', sendQuery);

  checkHealth();
});

// ── Health check ──────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const r = await fetch(`${API}/health`);
    const d = await r.json();
    if (d.status === 'ok') {
      dotEl.classList.add('on');
      statusTxt.textContent = 'Service online';
      loadSdkOptions();
    } else {
      dotEl.classList.remove('on');
      statusTxt.textContent = 'Service starting…';
      setTimeout(checkHealth, 3000);
    }
  } catch {
    dotEl.classList.remove('on');
    statusTxt.textContent = 'Service offline';
    setTimeout(checkHealth, 4000);
  }
}

// ── SDK filter dropdown ───────────────────────────────────────────────────
async function loadSdkOptions() {
  try {
    const r = await fetch(`${API}/query`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ query: 'inventory steps' }),
    });
    const d   = await r.json();
    const sdk = d.type === 'result' ? d.data?.sdk_name : d.data?.[0]?.sdk_name;
    if (sdk) {
      const opt = document.createElement('option');
      opt.value = sdk;
      opt.textContent = sdk;
      sdkSel.appendChild(opt);
    }
  } catch { /* silently ignore — dropdown stays at "All SDKs" */ }
}

// ── Send query ────────────────────────────────────────────────────────────
async function sendQuery() {
  const query = inputEl.value.trim();
  if (!query || isLoading) return;

  const sdkFilter = sdkSel.value || null;
  isLoading = true;
  sendBtn.style.opacity = '0.5';
  inputEl.value = '';
  autoResize();

  appendUserMsg(query);
  const typingEl = appendBotTyping();

  try {
    const r = await fetch(`${API}/query`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ query, sdk_filter: sdkFilter }),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    typingEl.remove();

    if (data.type === 'result') {
      handleResult(data, query);
    } else {
      handleClarification(data);
    }
  } catch (err) {
    typingEl.remove();
    appendBotMsg(`Error: ${esc(err.message)}`);
  } finally {
    isLoading = false;
    sendBtn.style.opacity = '1';
    inputEl.focus();
  }
}

// ── Result handler ────────────────────────────────────────────────────────
function handleResult(data, query) {
  const card = data.data;
  const pct  = Math.round((card.confidence || 0) * 100);
  appendBotMsg(
    `Match in <strong>${esc(card.sdk_name)}</strong> — <strong>${esc(card.class_name)}</strong><br>` +
    `<span style="color:var(--muted);font-size:11.5px;">Confidence ${pct}% · ${data.latency_ms}ms</span>`
  );
  renderResultCard(card);
  loadScaffold(card);   // async — non-blocking
}

// ── Clarification handler ─────────────────────────────────────────────────
function handleClarification(data) {
  const opts = data.data;
  const msg  = document.createElement('div');
  msg.className = 'msg bot';

  const inner = document.createElement('div');
  inner.className = 'bubble';
  inner.innerHTML =
    `Found ${opts.length} possible matches — which did you mean?
    <div class="clarify-options" style="margin-top:8px;">
      ${opts.map((o, i) => `
        <button class="clarify-btn" data-idx="${i}">
          <span style="color:var(--amber);font-size:11px;font-family:var(--font-mono)">${esc(o.keyword)}</span>
          ${esc(o.step_text)}<br>
          <span style="color:var(--muted);font-size:11px;">${esc(o.class_name)} · ${Math.round(o.confidence * 100)}%</span>
        </button>`).join('')}
    </div>`;

  // Wire clarify buttons after innerHTML is parsed
  setTimeout(() => {
    inner.querySelectorAll('.clarify-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const opt = opts[+btn.dataset.idx];
        inner.querySelectorAll('.clarify-btn').forEach(b => b.disabled = true);
        inputEl.value = opt.step_text;
        sendQuery();
      });
    });
  }, 0);

  const t = document.createElement('span');
  t.className = 'msg-time';
  t.textContent = now();

  msg.appendChild(inner);
  msg.appendChild(t);
  msgsEl.appendChild(msg);
  scrollBottom();
}

// ── Result card renderer ──────────────────────────────────────────────────
function renderResultCard(card) {
  emptyEl.style.display = 'none';

  // Remove previous card
  const prev = resultEl.querySelector('.result-card');
  if (prev) prev.remove();

  const conf      = card.confidence || 0;
  const pct       = Math.round(conf * 100);
  const confColor = conf >= 0.6 ? 'var(--green)' : conf >= 0.4 ? 'var(--amber)' : 'var(--red)';
  const kwCls     = `badge-${(card.keyword || '').toLowerCase()}`;
  const isLocal   = (card.github_url || '').startsWith('local://');

  const el = document.createElement('div');
  el.className = 'result-card';
  el.innerHTML = `
    <div class="card-header">
      <div class="card-header-left">
        <div class="card-step-text">${esc(card.keyword)} ${esc(card.step_text)}</div>
        <div class="card-meta">
          <span class="badge ${kwCls}">${esc(card.keyword)}</span>
          <span class="chip">${esc(card.class_name)}</span>
          <span class="chip">${esc(card.sdk_name)} v${esc(card.sdk_version)}</span>
          <span class="conf-badge" style="color:${confColor};background:${confColor}18;border:1px solid ${confColor}30;">${pct}%</span>
        </div>
      </div>
    </div>

    <div class="card-grid">
      <div class="grid-cell">
        <div class="cell-label">Method</div>
        <div class="cell-value">
          <span class="method" style="font-family:var(--font-mono);font-size:12px;">${esc(card.method_name)}()</span>
        </div>
      </div>
      <div class="grid-cell">
        <div class="cell-label">Class</div>
        <div class="cell-value">
          <span class="class-nm" style="font-family:var(--font-mono);font-size:12px;">${esc(card.class_name)}</span>
        </div>
      </div>
      <div class="grid-cell">
        <div class="cell-label">File</div>
        <div class="cell-value mono">${esc(card.step_definition_file)}</div>
      </div>
      <div class="grid-cell">
        <div class="cell-label">Confidence</div>
        <div class="conf-row">
          <div class="conf-track">
            <div class="conf-fill" style="width:${pct}%;background:${confColor};"></div>
          </div>
          <span style="font-size:12px;font-weight:600;color:${confColor};min-width:30px;text-align:right;">${pct}%</span>
        </div>
      </div>
      ${!isLocal ? `
      <div class="grid-cell" style="grid-column:1/-1;border-bottom:none;">
        <div class="cell-label">Source</div>
        <div class="cell-value">
          <a href="${escAttr(card.github_url)}" target="_blank" rel="noopener">View on GitHub ↗</a>
        </div>
      </div>` : ''}
    </div>

    <div class="hint-row">
      <div class="section-label">Usage hint</div>
      <div class="hint-content" style="margin-top:6px;">${esc(card.usage_hint)}</div>
    </div>

    <div class="gherkin-row">
      <div class="section-label">
        Gherkin scaffold
        <span id="scaffoldStatus" style="font-size:10px;color:var(--muted);margin-left:8px;font-weight:400;text-transform:none;letter-spacing:0;">generating…</span>
      </div>
      <div class="gherkin-block" id="gherkinBlock">
        <div style="display:flex;align-items:center;gap:8px;padding:8px 0;color:var(--muted);font-size:12px;font-family:var(--font-mono);">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2.5"
               style="animation:spin 1s linear infinite;flex-shrink:0;">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          Asking LLM to generate scenario…
        </div>
      </div>
    </div>

    <div class="maven-row">
      <div class="section-label">Maven dependency</div>
      <div class="maven-block">
        <button class="copy-btn" id="copyMaven">
          <svg viewBox="0 0 24 24">
            <rect x="9" y="9" width="13" height="13" rx="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          Copy
        </button>
        <pre>${highlightMaven(card.maven_coords)}</pre>
      </div>
    </div>`;

  resultEl.insertBefore(el, resultEl.firstChild);
  resultEl.scrollTop = 0;

  // Wire Maven copy — button exists immediately in the static HTML above
  // Gherkin copy is wired inside loadScaffold() after the LLM responds
  el.querySelector('#copyMaven').addEventListener('click', function () {
    copyText(card.maven_coords, this);
  });
}

// ── Scaffold loader (async, non-blocking) ─────────────────────────────────
async function loadScaffold(card) {
  // Capture DOM refs BEFORE the first await.
  // After await, the card may have been replaced by a new query.
  const block  = document.getElementById('gherkinBlock');
  const status = document.getElementById('scaffoldStatus');
  if (!block || !status) return;

  try {
    const r = await fetch(`${API}/scaffold`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sdk_name:             card.sdk_name,
        class_name:           card.class_name,
        method_name:          card.method_name,
        keyword:              card.keyword,
        step_text:            card.step_text,
        step_definition_file: card.step_definition_file,
        sdk_version:          card.sdk_version,
        section:              card.section    || '',
        usage_hint:           card.usage_hint || '',
      }),
    });

    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();

    // Guard: user may have sent another query, replacing this card
    if (!document.contains(block)) return;

    const plainText = data.gherkin;

    // Build DOM nodes directly — NEVER use innerHTML then querySelector.
    // innerHTML is async-parsed by the browser; querySelector on freshly
    // set innerHTML can return null before parsing completes.
    block.innerHTML = '';  // clear spinner

    const svgNS   = 'http://www.w3.org/2000/svg';
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn';
    copyBtn.style.cssText = 'position:absolute;top:8px;right:8px;';

    const svg  = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '11');
    svg.setAttribute('height', '11');
    svg.style.cssText = 'stroke:currentColor;fill:none;stroke-width:2;vertical-align:middle;margin-right:3px;';

    const rect = document.createElementNS(svgNS, 'rect');
    rect.setAttribute('x', '9'); rect.setAttribute('y', '9');
    rect.setAttribute('width', '13'); rect.setAttribute('height', '13'); rect.setAttribute('rx', '2');

    const path = document.createElementNS(svgNS, 'path');
    path.setAttribute('d', 'M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1');

    svg.appendChild(rect);
    svg.appendChild(path);
    copyBtn.appendChild(svg);
    copyBtn.appendChild(document.createTextNode('Copy'));

    // Listener on the element reference directly — no querySelector needed
    copyBtn.addEventListener('click', () => copyText(plainText, copyBtn));

    const pre = document.createElement('pre');
    pre.innerHTML = highlightGherkin(plainText);

    block.style.position = 'relative';
    block.appendChild(copyBtn);
    block.appendChild(pre);

    status.textContent = `generated in ${data.latency_ms}ms`;
    status.style.color = 'var(--green)';

  } catch (err) {
    if (!document.contains(block)) return;

    block.innerHTML = '';
    const pre = document.createElement('pre');
    pre.style.cssText = 'color:var(--muted);font-size:12px;';
    pre.textContent =
      err.message.includes('404') || err.message.includes('502')
        ? '# LLM not reachable — check Ollama is running: ollama serve'
        : err.message.includes('504') || err.message.includes('timeout')
        ? '# LLM took too long — increase timeout_seconds in sdk_discovery.yml'
        : `# Generation failed: ${err.message}`;
    block.appendChild(pre);

    status.textContent = 'failed';
    status.style.color = 'var(--red)';
  }
}

// ── Gherkin syntax highlighter ────────────────────────────────────────────
function highlightGherkin(plain) {
  return plain.split('\n').map(line => {
    const t      = line.trimStart();
    const indent = line.match(/^(\s*)/)[1];

    if (t.startsWith('@'))
      return `${indent}<span class="g-tag">${esc(t)}</span>`;

    const featureKws = ['Feature:', 'Scenario Outline:', 'Scenario:', 'Background:', 'Examples:', 'Rule:'];
    for (const kw of featureKws) {
      if (t.startsWith(kw)) {
        const rest = t.slice(kw.length);
        return `${indent}<span class="g-keyword">${esc(kw)}</span><span class="g-text">${esc(rest)}</span>`;
      }
    }

    const stepKws = ['Given ', 'When ', 'Then ', 'And ', 'But '];
    for (const kw of stepKws) {
      if (t.startsWith(kw)) {
        const rest      = t.slice(kw.length);
        const restClean = esc(rest).replace(/&quot;([^&]*)&quot;/g,
          (_, v) => `<span class="g-param">"${v}"</span>`);
        return `${indent}<span class="g-step-kw">${esc(kw.trim())}</span> <span class="g-text">${restClean}</span>`;
      }
    }

    if (t.startsWith('|')) {
      const cells     = t.split('|').filter(c => c !== '');
      const isHeader  = cells.every(c => !/\d/.test(c.trim()) || c.trim().length < 4);
      const cellClass = isHeader ? 'g-table-hd' : 'g-table-vl';
      const rendered  = cells.map(c =>
        `<span class="${cellClass}">| ${esc(c.trim())} </span>`
      ).join('') + '<span class="g-table-hd">|</span>';
      return `${indent}${rendered}`;
    }

    if (t.startsWith('#'))
      return `${indent}<span class="g-comment">${esc(t)}</span>`;

    return esc(line);
  }).join('\n');
}

// ── Maven syntax highlighter ──────────────────────────────────────────────
function highlightMaven(src) {
  return esc(src)
    .replace(/(&lt;\/?)([a-zA-Z]+)(&gt;)/g,
      (_, open, tag, close) => `<span class="kw">${open}${tag}${close}</span>`)
    .replace(/(&gt;)([^&\n<]+)(&lt;)/g,
      (_, gt, val, lt)      => `${gt}<span class="val">${val}</span>${lt}`);
}

// ── Chat helpers ──────────────────────────────────────────────────────────
function appendUserMsg(text) {
  const el = document.createElement('div');
  el.className = 'msg user';
  el.innerHTML = `<div class="bubble">${esc(text)}</div><span class="msg-time">${now()}</span>`;
  msgsEl.appendChild(el);
  scrollBottom();
}

function appendBotMsg(html) {
  const el = document.createElement('div');
  el.className = 'msg bot';
  el.innerHTML = `<div class="bubble">${html}</div><span class="msg-time">${now()}</span>`;
  msgsEl.appendChild(el);
  scrollBottom();
  return el;
}

function appendBotTyping() {
  const el = document.createElement('div');
  el.className = 'msg bot';
  el.innerHTML = `<div class="bubble typing">Searching SDK library…</div>`;
  msgsEl.appendChild(el);
  scrollBottom();
  return el;
}

// ── Textarea auto-resize ──────────────────────────────────────────────────
function autoResize() {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 110) + 'px';
}

// ── Copy to clipboard ─────────────────────────────────────────────────────
function copyText(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = `<svg viewBox="0 0 24 24" style="width:11px;height:11px;stroke:currentColor;fill:none;stroke-width:2;">
      <polyline points="20 6 9 17 4 12"/>
    </svg> Copied!`;
    btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('copied'); }, 2000);
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────
function scrollBottom() { msgsEl.scrollTop = msgsEl.scrollHeight; }

function now() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escAttr(s) {
  return String(s ?? '').replace(/"/g, '&quot;');
}
