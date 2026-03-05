/**
 * PoE Price Lookup — poe.ninja API
 * Usage: node poe-price.js [league]
 * Then open http://localhost:3000 in your browser
 */

const http = require("http");
const https = require("https");
const url = require("url");

const PORT = 3000;
const DEFAULT_LEAGUE = process.argv[2] || "Standard";

// ─── poe.ninja fetch helpers ────────────────────────────────────────────────

function httpsGet(apiUrl, redirects = 5) {
  return new Promise((resolve, reject) => {
    const opts = {
      ...url.parse(apiUrl),
      headers: { "User-Agent": "poe-price-lookup/1.0" },
    };
    https.get(opts, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
        if (redirects <= 0) return reject(new Error("Too many redirects"));
        const next = new URL(res.headers.location, apiUrl).toString();
        res.resume();
        return httpsGet(next, redirects - 1).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode} for ${apiUrl}`));
      }
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(new Error(`JSON parse error for ${apiUrl}: ${data.slice(0, 120)}`)); }
      });
    }).on("error", reject);
  });
}

async function fetchCategory(league, type, isCurrency) {
  const kind = isCurrency ? "currencyoverview" : "itemoverview";
  const apiUrl = `https://poe.ninja/api/data/${kind}?league=${encodeURIComponent(league)}&type=${type}`;
  try {
    const data = await httpsGet(apiUrl);
    const lines = data.lines || [];
    return lines.map((l) => ({
      name: isCurrency ? l.currencyTypeName : l.name,
      chaos: isCurrency ? (l.chaosEquivalent ?? 1) : (l.chaosValue ?? 0),
      divine: isCurrency ? (l.divineEquivalent ?? null) : (l.divineValue ?? null),
      type,
      icon: l.icon ?? null,
    }));
  } catch (e) {
    console.error(`  Failed to fetch ${type}: ${e.message}`);
    return [];
  }
}

// ─── Data cache ──────────────────────────────────────────────────────────────

let cache = { league: null, items: [], fetchedAt: null };

async function loadData(league) {
  if (cache.league === league && cache.fetchedAt && Date.now() - cache.fetchedAt < 5 * 60 * 1000) {
    return; // use cached (5-minute TTL)
  }

  console.log(`\nFetching poe.ninja data for league: ${league} …`);

  const CATEGORIES = [
    ["Currency",        true],
    ["Fragment",        true],
    ["DivinationCard",  false],
    ["SkillGem",        false],
    ["UniqueWeapon",    false],
    ["UniqueArmour",    false],
    ["UniqueAccessory", false],
    ["UniqueFlask",     false],
    ["UniqueJewel",     false],
    ["Map",             false],
    ["UniqueMap",       false],
    ["Scarab",          false],
    ["Essence",         false],
    ["Fossil",          false],
  ];

  const results = await Promise.all(CATEGORIES.map(([t, c]) => fetchCategory(league, t, c)));
  cache.items = results.flat();
  cache.league = league;
  cache.fetchedAt = Date.now();
  console.log(`  Loaded ${cache.items.length} items.\n`);
}

// ─── Search ──────────────────────────────────────────────────────────────────

function search(query, items) {
  if (!query || query.length < 2) return [];
  const q = query.toLowerCase();
  const exact = [], starts = [], contains = [];
  for (const item of items) {
    const n = item.name.toLowerCase();
    if (n === q) exact.push(item);
    else if (n.startsWith(q)) starts.push(item);
    else if (n.includes(q)) contains.push(item);
  }
  return [...exact, ...starts, ...contains].slice(0, 30);
}

// ─── HTML page ───────────────────────────────────────────────────────────────

const HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>PoE Price Lookup</title>
<style>
  :root { --bg:#0e0e0e; --card:#1a1a1a; --border:#2a2a2a; --accent:#c8a45a; --text:#e0d8cc; --sub:#888; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--text); font:14px/1.5 'Segoe UI',sans-serif; display:flex; flex-direction:column; align-items:center; padding:32px 16px; min-height:100vh; }
  h1 { color:var(--accent); font-size:1.4rem; margin-bottom:4px; letter-spacing:1px; }
  p.sub { color:var(--sub); font-size:.85rem; margin-bottom:24px; }
  .controls { display:flex; gap:10px; width:100%; max-width:640px; margin-bottom:20px; }
  input { flex:1; background:var(--card); border:1px solid var(--border); color:var(--text); padding:10px 14px; border-radius:6px; font-size:1rem; outline:none; }
  input:focus { border-color:var(--accent); }
  select { background:var(--card); border:1px solid var(--border); color:var(--text); padding:10px 10px; border-radius:6px; font-size:.9rem; cursor:pointer; }
  #status { color:var(--sub); font-size:.8rem; height:18px; margin-bottom:8px; }
  #results { width:100%; max-width:640px; display:flex; flex-direction:column; gap:6px; }
  .item { display:flex; align-items:center; gap:12px; background:var(--card); border:1px solid var(--border); border-radius:6px; padding:10px 14px; }
  .item img { width:36px; height:36px; object-fit:contain; flex-shrink:0; }
  .item .no-icon { width:36px; height:36px; flex-shrink:0; }
  .item .info { flex:1; min-width:0; }
  .item .name { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .item .type { color:var(--sub); font-size:.78rem; }
  .item .price { text-align:right; flex-shrink:0; }
  .item .chaos { color:#e8c96a; font-size:1rem; font-weight:700; }
  .item .divine { color:#9bb5e8; font-size:.78rem; margin-top:2px; }
  .chaos-icon { display:inline-block; width:14px; height:14px; background:url('https://web.poecdn.com/gen/image/WzI1LDE0LHsiZiI6IjJESXRlbXMvQ3VycmVuY3kvQ3VycmVuY3lSZXJvbGxTb2NrZXRzIiwidyI6MSwiaCI6MSwic2NhbGUiOjF9XQ/ded7230aa7/CurrencyRerollSockets.png') center/contain no-repeat; vertical-align:middle; margin-right:2px; }
</style>
</head>
<body>
<h1>PoE Price Lookup</h1>
<p class="sub">Prices from poe.ninja — updated every 5 minutes</p>

<div class="controls">
  <input id="q" type="text" placeholder="Search item name…" autocomplete="off" autofocus/>
  <select id="league">
    <option value="Standard">Standard</option>
    <option value="Hardcore">Hardcore</option>
  </select>
</div>
<div id="status"></div>
<div id="results"></div>

<script>
const qEl = document.getElementById('q');
const leagueEl = document.getElementById('league');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
let timer = null;

function fmt(n) {
  if (n === null || n === undefined) return null;
  if (n >= 1000) return (n/1000).toFixed(1) + 'k';
  if (n >= 10) return Math.round(n).toString();
  return n.toFixed(1);
}

function render(items) {
  if (!items.length) { resultsEl.innerHTML = ''; return; }
  resultsEl.innerHTML = items.map(it => {
    const icon = it.icon ? \`<img src="\${it.icon}" alt="" loading="lazy"/>\` : '<div class="no-icon"></div>';
    const divine = it.divine != null && it.divine >= 0.1
      ? \`<div class="divine">\${fmt(it.divine)} div</div>\` : '';
    return \`
    <div class="item">
      \${icon}
      <div class="info">
        <div class="name">\${it.name}</div>
        <div class="type">\${it.type}</div>
      </div>
      <div class="price">
        <div class="chaos"><span class="chaos-icon"></span>\${fmt(it.chaos)}c</div>
        \${divine}
      </div>
    </div>\`;
  }).join('');
}

async function doSearch() {
  const q = qEl.value.trim();
  const league = leagueEl.value;
  if (q.length < 2) { resultsEl.innerHTML = ''; statusEl.textContent = ''; return; }
  statusEl.textContent = 'Searching…';
  try {
    const res = await fetch(\`/api/search?q=\${encodeURIComponent(q)}&league=\${encodeURIComponent(league)}\`);
    const data = await res.json();
    if (data.error) { statusEl.textContent = 'Error: ' + data.error; return; }
    statusEl.textContent = data.items.length ? \`\${data.items.length} results (league: \${data.league})\` : 'No results';
    render(data.items);
  } catch(e) {
    statusEl.textContent = 'Request failed';
  }
}

qEl.addEventListener('input', () => {
  clearTimeout(timer);
  timer = setTimeout(doSearch, 250);
});
leagueEl.addEventListener('change', doSearch);
</script>
</body>
</html>`;

// ─── HTTP server ──────────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  const parsed = url.parse(req.url, true);

  if (parsed.pathname === "/") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    return res.end(HTML);
  }

  if (parsed.pathname === "/api/search") {
    const q = (parsed.query.q || "").trim();
    const league = (parsed.query.league || DEFAULT_LEAGUE).trim();
    res.writeHead(200, { "Content-Type": "application/json" });

    try {
      await loadData(league);
      const items = search(q, cache.items);
      res.end(JSON.stringify({ league, items }));
    } catch (e) {
      res.end(JSON.stringify({ error: e.message, items: [] }));
    }
    return;
  }

  res.writeHead(404);
  res.end("Not found");
});

server.listen(PORT, () => {
  console.log(`PoE Price Lookup running at http://localhost:${PORT}`);
  console.log(`Default league: ${DEFAULT_LEAGUE}`);
  console.log(`Override: node poe-price.js "Settlers"`);
  console.log(`\nData will be fetched on first search request.`);
});
