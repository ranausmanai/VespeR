import fs from 'node:fs/promises';
import path from 'node:path';
import pw from '../frontend/node_modules/playwright/index.js';

const { chromium } = pw;
const BASE = process.env.VESPER_BASE || 'http://127.0.0.1:8420';
const outDir = path.resolve('docs/screenshots');
await fs.mkdir(outDir, { recursive: true });

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

let runId = null;
let patternRunId = null;
let sessionId = null;
try {
  const sessions = await fetchJson(`${BASE}/api/sessions`);
  sessionId = sessions.sessions?.[0]?.id || null;
} catch {}

try {
  const runs = await fetchJson(`${BASE}/api/runs`);
  const allRuns = runs.runs || [];
  runId = allRuns[0]?.id || null;
  const pattern = allRuns.find(r => (r.prompt || '').startsWith('[Agent Pattern:'));
  patternRunId = pattern?.id || null;
} catch {}

const pages = [
  { name: '01-dashboard', url: `${BASE}/` },
  { name: '02-sessions', url: `${BASE}/sessions` },
  { name: '03-interactive', url: sessionId ? `${BASE}/interactive?new=1&sessionId=${encodeURIComponent(sessionId)}` : `${BASE}/interactive` },
  { name: '04-agents', url: `${BASE}/agents` },
  { name: '05-patterns', url: `${BASE}/patterns` },
];
if (patternRunId) pages.push({ name: '06-agent-execution', url: `${BASE}/execution/${patternRunId}` });
if (runId) pages.push({ name: '07-run-detail', url: `${BASE}/runs/${runId}` });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

for (const p of pages) {
  await page.goto(p.url, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(1200);
  const file = path.join(outDir, `${p.name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`saved ${file}`);
}

await browser.close();
console.log(JSON.stringify({ runId, patternRunId, sessionId }, null, 2));
