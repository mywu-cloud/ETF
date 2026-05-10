#!/usr/bin/env python3
import sqlite3, json
from pathlib import Path

DB = Path(__file__).parent / "holdings.db"
OUT = Path(__file__).parent / "holdings.html"

conn = sqlite3.connect(DB)
snaps = conn.execute("""
    SELECT id, data_date FROM snapshots
    WHERE id IN (SELECT MAX(id) FROM snapshots GROUP BY data_date)
    ORDER BY data_date
""").fetchall()

all_data = {}
for snap_id, data_date in snaps:
    rows = conn.execute(
        "SELECT ticker, name, weight, shares FROM holdings WHERE snapshot_id=? ORDER BY weight DESC",
        (snap_id,)
    ).fetchall()
    all_data[data_date] = [
        {"ticker": r[0] or "", "name": r[1], "weight": r[2] or 0, "shares": r[3] or 0}
        for r in rows
    ]
conn.close()

dates = list(all_data.keys())
data_js = json.dumps(all_data, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 00981A 持股追蹤</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html {{ font-size: 14px; }}
  body {{ font-family: "PingFang TC", "Microsoft JhengHei", "Segoe UI", Arial, sans-serif;
          background: #f0f2f5; color: #1a1a2e; font-size: 14px; line-height: 1.55; }}
  header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white; padding: 20px 32px; display: flex; align-items: center; gap: 16px; }}
  header h1 {{ font-size: 20px; font-weight: 700; }}
  header span {{ opacity: .6; font-size: 13px; }}
  .container {{ max-width: 1200px; margin: 24px auto; padding: 0 16px; }}

  /* Tab bar */
  .tabs {{ display: flex; gap: 4px; margin-bottom: 20px; }}
  .tab {{ padding: 10px 22px; border-radius: 8px 8px 0 0; border: none; cursor: pointer;
          font-size: 14px; font-weight: 600; background: #dde1ea; color: #555; transition: .2s; }}
  .tab.active {{ background: white; color: #1a1a2e; box-shadow: 0 -2px 8px rgba(0,0,0,.08); }}

  /* Cards */
  .card {{ background: white; border-radius: 12px; padding: 24px;
           box-shadow: 0 2px 12px rgba(0,0,0,.06); margin-bottom: 20px; }}
  .card h2 {{ font-size: 15px; margin-bottom: 16px; color: #16213e; }}

  /* Controls */
  .controls {{ display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 16px; }}
  select, input {{ padding: 8px 12px; border: 1px solid #d0d5dd; border-radius: 8px;
                   font-size: 14px; outline: none; }}
  select:focus, input:focus {{ border-color: #4361ee; box-shadow: 0 0 0 3px rgba(67,97,238,.15); }}
  label {{ font-size: 13px; font-weight: 600; color: #555; }}

  /* Holdings table */
  .tbl-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  thead th {{ background: #f7f8fc; padding: 11px 14px; text-align: left; font-weight: 700;
              border-bottom: 2px solid #e2e8f0; cursor: pointer; user-select: none; white-space: nowrap;
              font-size: 13px; letter-spacing: .02em; }}
  thead th:hover {{ background: #eef0f8; }}
  thead th.sort-asc::after {{ content: " ▲"; opacity: .6; }}
  thead th.sort-desc::after {{ content: " ▼"; opacity: .6; }}
  tbody tr {{ border-bottom: 1px solid #f0f2f5; transition: background .15s; }}
  tbody tr:hover {{ background: #f7f9ff; }}
  td {{ padding: 10px 14px; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.bar-cell {{ width: 120px; }}
  .bar-bg {{ background: #e9ecef; border-radius: 4px; height: 8px; }}
  .bar-fill {{ background: linear-gradient(90deg, #4361ee, #7b97ff); border-radius: 4px; height: 8px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 99px; font-size: 13px; font-weight: 600; }}
  .badge-new {{ background: #fee2e2; color: #991b1b; }}   /* 新增 → 紅 */
  .badge-del {{ background: #d1fae5; color: #065f46; }}   /* 移除 → 綠 */
  .badge-up  {{ background: #fee2e2; color: #991b1b; }}   /* 上漲 → 紅 */
  .badge-dn  {{ background: #d1fae5; color: #065f46; }}   /* 下跌 → 綠 */

  /* Diff table — 台股慣例：漲/增 紅，跌/減 綠 */
  .diff-up {{ color: #dc2626; font-weight: 700; }}
  .diff-dn {{ color: #16a34a; font-weight: 700; }}
  .diff-new {{ background: #fff1f2; }}   /* 新增持股 → 淡紅底 */
  .diff-del {{ background: #f0fdf4; }}   /* 移除持股 → 淡綠底 */

  /* Chart */
  .chart-top {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 700px) {{ .chart-top {{ grid-template-columns: 1fr; }} }}
  #chart-pie {{ max-height: 300px; }}
  #chart-bar-wrap {{ position: relative; height: 560px; width: 100%; }}
  #chart-bar {{ position: absolute; inset: 0; }}

  /* Summary chips */
  .chips {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
  .chip {{ background: white; border-radius: 10px; padding: 14px 20px;
           box-shadow: 0 2px 8px rgba(0,0,0,.06); flex: 1; min-width: 120px; }}
  .chip .val {{ font-size: 22px; font-weight: 800; color: #4361ee; }}
  .chip .lbl {{ font-size: 13px; color: #888; margin-top: 2px; }}

  .panel {{ display: none; }}
  .panel.active {{ display: block; }}
  .empty {{ text-align: center; padding: 40px; color: #aaa; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>ETF 00981A &nbsp;主動統一台股增長</h1>
    <span>持股追蹤儀表板</span>
  </div>
</header>
<div class="container">

  <div class="tabs">
    <button class="tab active" onclick="showPanel('panel-holdings', this)">📋 持股清單</button>
    <button class="tab" onclick="showPanel('panel-chart', this)">📊 圖表分析</button>
    <button class="tab" onclick="showPanel('panel-diff', this)">🔄 差異比較</button>
  </div>

  <!-- ── Panel 1: Holdings ──────────────────────────── -->
  <div id="panel-holdings" class="panel active">
    <div class="controls">
      <div><label>資料日期</label><br>
        <select id="snap-sel" onchange="renderHoldings()">
          {''.join(f'<option value="{d}">{d}</option>' for d in reversed(dates))}
        </select>
      </div>
      <div style="margin-top:auto"><input type="text" id="search" placeholder="🔍 搜尋名稱 / 代碼…" oninput="renderHoldings()" style="width:220px"></div>
    </div>
    <div id="chips" class="chips"></div>
    <div class="card" style="padding:0;overflow:hidden">
      <div class="tbl-wrap">
        <table id="tbl">
          <thead><tr>
            <th onclick="sortBy('rank')">#</th>
            <th onclick="sortBy('name')">股票名稱</th>
            <th onclick="sortBy('ticker')">代碼</th>
            <th onclick="sortBy('weight')">投資比例</th>
            <th class="bar-cell"></th>
            <th onclick="sortBy('shares')">持有股數</th>
            <th onclick="sortBy('prev_shares')">前期股數</th>
            <th onclick="sortBy('delta_shares')">股數差異</th>
          </tr></thead>
          <tbody id="tbl-body"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- ── Panel 2: Charts ───────────────────────────── -->
  <div id="panel-chart" class="panel">
    <div class="controls">
      <div><label>資料日期</label><br>
        <select id="chart-snap-sel" onchange="renderCharts()">
          {''.join(f'<option value="{d}">{d}</option>' for d in reversed(dates))}
        </select>
      </div>
    </div>
    <div class="chart-top">
      <div class="card"><h2>前 10 大持股比例</h2><canvas id="chart-pie"></canvas></div>
      <div class="card" style="display:flex;flex-direction:column;justify-content:center;">
        <p style="font-size:13px;color:#888;text-align:center;padding:8px 0;">選擇日期後載入圖表</p>
      </div>
    </div>
    <div class="card" style="margin-top:0;">
      <h2>前 20 大持股（投資比例 %）</h2>
      <div id="chart-bar-wrap"><canvas id="chart-bar"></canvas></div>
    </div>
  </div>

  <!-- ── Panel 3: Diff ─────────────────────────────── -->
  <div id="panel-diff" class="panel">
    <div class="controls">
      <div><label>舊快照</label><br>
        <select id="diff-old" onchange="renderDiff()">
          {''.join(f'<option value="{d}">{d}</option>' for d in dates)}
        </select>
      </div>
      <div><label>新快照</label><br>
        <select id="diff-new" onchange="renderDiff()">
          {''.join(f'<option value="{d}" {"selected" if i==len(dates)-1 else ""}>{d}</option>' for i, d in enumerate(dates))}
        </select>
      </div>
    </div>
    <div id="diff-chips" class="chips"></div>
    <div id="diff-content"></div>
  </div>
</div>

<script>
const DATA = {data_js};
const DATES = {json.dumps(dates)};

let sortKey = 'weight', sortDir = -1;

function showPanel(id, btn) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
  if (id === 'panel-chart') renderCharts();
  if (id === 'panel-diff') renderDiff();
}}

function fmt(n) {{ return Number(n).toLocaleString('zh-TW'); }}

// ── Holdings ──────────────────────────────────────────
function sortBy(key) {{
  if (sortKey === key) sortDir *= -1; else {{ sortKey = key; sortDir = -1; }}
  document.querySelectorAll('thead th').forEach(th => th.classList.remove('sort-asc','sort-desc'));
  renderHoldings();
}}

function renderHoldings() {{
  const date = document.getElementById('snap-sel').value;
  const q = document.getElementById('search').value.trim().toLowerCase();

  // 前期快照（前一個日期）
  const prevDate = DATES[DATES.indexOf(date) - 1] ?? null;
  const prevMap  = prevDate ? Object.fromEntries(DATA[prevDate].map(h => [h.name, h])) : {{}};

  let rows = DATA[date].map((h, i) => {{
    const prev        = prevMap[h.name] ?? null;
    const prev_shares = prev ? prev.shares : null;
    const delta_shares = prev !== null ? h.shares - prev.shares : null;
    return {{ ...h, rank: i+1, prev_shares, delta_shares }};
  }});
  if (q) rows = rows.filter(h => h.name.includes(q) || h.ticker.toLowerCase().includes(q));

  const keyMap = {{ rank: 'rank', name: 'name', ticker: 'ticker', weight: 'weight',
                   shares: 'shares', prev_shares: 'prev_shares', delta_shares: 'delta_shares' }};
  rows.sort((a, b) => {{
    const va = a[keyMap[sortKey]] ?? -Infinity;
    const vb = b[keyMap[sortKey]] ?? -Infinity;
    if (typeof va === 'string') return va.localeCompare(vb, 'zh-TW') * sortDir;
    return (va - vb) * sortDir;
  }});

  const maxW = Math.max(...rows.map(r => r.weight));
  document.getElementById('tbl-body').innerHTML = rows.map(r => {{
    const deltaColor = r.delta_shares > 0 ? '#dc2626' : r.delta_shares < 0 ? '#16a34a' : '#aaa';
    const deltaSign  = r.delta_shares > 0 ? '+' : '';
    const deltaStr   = r.delta_shares !== null ? `<b style="color:${{deltaColor}}">${{deltaSign}}${{fmt(r.delta_shares)}}</b>` : '─';
    return `<tr>
      <td class="num" style="color:#aaa">${{r.rank}}</td>
      <td><b>${{r.name}}</b></td>
      <td style="color:#4361ee;font-weight:600">${{r.ticker || '─'}}</td>
      <td class="num"><b>${{r.weight.toFixed(2)}}%</b></td>
      <td class="bar-cell">
        <div class="bar-bg"><div class="bar-fill" style="width:${{(r.weight/maxW*100).toFixed(1)}}%"></div></div>
      </td>
      <td class="num">${{fmt(r.shares)}}</td>
      <td class="num" style="color:#888">${{r.prev_shares !== null ? fmt(r.prev_shares) : '─'}}</td>
      <td class="num">${{deltaStr}}</td>
    </tr>`;
  }}).join('');

  // chips
  const total = DATA[date].reduce((s, h) => s + h.weight, 0);
  const top10 = DATA[date].slice(0,10).reduce((s, h) => s + h.weight, 0);
  document.getElementById('chips').innerHTML = `
    <div class="chip"><div class="val">${{DATA[date].length}}</div><div class="lbl">持股支數</div></div>
    <div class="chip"><div class="val">${{total.toFixed(2)}}%</div><div class="lbl">總投資比例</div></div>
    <div class="chip"><div class="val">${{top10.toFixed(2)}}%</div><div class="lbl">前 10 大集中度</div></div>
    <div class="chip"><div class="val">${{DATA[date][0].name}}</div><div class="lbl">最大持股</div></div>`;
}}

// ── Charts ────────────────────────────────────────────
let pieChart, barChart;
const COLORS = ['#4361ee','#7b97ff','#f72585','#3a0ca3','#7209b7','#560bad',
                '#480ca8','#3f37c9','#4895ef','#4cc9f0'];
function renderCharts() {{
  const date = document.getElementById('chart-snap-sel').value;
  const rows = DATA[date];
  const top10 = rows.slice(0,10);
  const top20 = rows.slice(0,20);

  if (pieChart) pieChart.destroy();
  if (barChart) barChart.destroy();

  pieChart = new Chart(document.getElementById('chart-pie'), {{
    type: 'doughnut',
    data: {{
      labels: top10.map(r => r.name),
      datasets: [{{ data: top10.map(r => r.weight), backgroundColor: COLORS }}]
    }},
    options: {{ plugins: {{ legend: {{ position: 'right', labels: {{ font: {{ size: 11 }} }} }} }}, cutout: '55%' }}
  }});

  barChart = new Chart(document.getElementById('chart-bar'), {{
    type: 'bar',
    data: {{
      labels: top20.map(r => r.name),
      datasets: [{{
        label: '投資比例 (%)',
        data: top20.map(r => r.weight),
        backgroundColor: top20.map((_, i) => i < 3 ? '#1a1a2e' : i < 10 ? '#4361ee' : '#7b97ff'),
        borderRadius: 4,
        barThickness: 20
      }}]
    }},
    options: {{
      indexAxis: 'y',
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            label: ctx => ` ${{ctx.parsed.x.toFixed(2)}}%`
          }}
        }},
        datalabels: {{ display: false }}
      }},
      layout: {{ padding: {{ right: 48 }} }},
      scales: {{
        x: {{
          title: {{ display: true, text: '投資比例 (%)', font: {{ size: 13 }} }},
          ticks: {{ font: {{ size: 13 }} }},
          grid: {{ color: '#f0f2f5' }}
        }},
        y: {{
          ticks: {{
            font: {{ size: 14, weight: '600' }},
            color: '#1a1a2e',
            callback: (val, i) => `${{i+1}}. ${{top20[i]?.name ?? val}}`
          }},
          grid: {{ display: false }}
        }}
      }}
    }}
  }});
}}

// ── Diff ──────────────────────────────────────────────
// ── Diff 排序狀態（只作用於「比例/股數變化」區塊）────────────
let diffSortKey = 'deltaW', diffSortDir = -1;
let _changedRows = [];   // 快取，供 diffSortBy 重繪

function diffSortBy(key) {{
  if (diffSortKey === key) diffSortDir *= -1;
  else {{ diffSortKey = key; diffSortDir = -1; }}
  renderChangedSection();
}}

function renderChangedSection() {{
  const cols = ['name','ticker','ow','nw','deltaW','os','ns','deltaS'];
  const sorted = [..._changedRows].sort((a, b) => {{
    const va = a[diffSortKey], vb = b[diffSortKey];
    if (typeof va === 'string') return va.localeCompare(vb, 'zh-TW') * diffSortDir;
    return (va - vb) * diffSortDir;
  }});

  // 更新 header 排序箭頭
  document.querySelectorAll('#diff-changed-tbl th').forEach(th => {{
    th.classList.remove('sort-asc','sort-desc');
    if (th.dataset.key === diffSortKey)
      th.classList.add(diffSortDir === 1 ? 'sort-asc' : 'sort-desc');
  }});

  document.getElementById('diff-changed-body').innerHTML = sorted.map(r => {{
    const wc   = r.deltaW > 0 ? 'diff-up' : r.deltaW < 0 ? 'diff-dn' : '';
    const wSign = r.deltaW > 0 ? '+' : '';
    const sc   = r.deltaS > 0 ? '#dc2626' : r.deltaS < 0 ? '#16a34a' : '#aaa';
    const sSign = r.deltaS > 0 ? '+' : '';
    return `<tr>
      <td><b>${{r.name}}</b></td>
      <td style="color:#4361ee">${{r.ticker||'─'}}</td>
      <td class="num">${{r.ow.toFixed(2)}}%</td>
      <td class="num">${{r.nw.toFixed(2)}}%</td>
      <td class="num ${{wc}}">${{r.deltaW !== 0 ? wSign+r.deltaW.toFixed(2)+'%' : '─'}}</td>
      <td class="num">${{fmt(r.os)}}</td>
      <td class="num">${{fmt(r.ns)}}</td>
      <td class="num"><b style="color:${{sc}}">${{r.deltaS !== 0 ? sSign+fmt(r.deltaS) : '─'}}</b></td>
    </tr>`;
  }}).join('');
}}

function renderDiff() {{
  const oldDate = document.getElementById('diff-old').value;
  const newDate = document.getElementById('diff-new').value;
  const oldMap = Object.fromEntries(DATA[oldDate].map(h => [h.name, h]));
  const newMap = Object.fromEntries(DATA[newDate].map(h => [h.name, h]));
  const allNames = new Set([...Object.keys(oldMap), ...Object.keys(newMap)]);

  const added=[], removed=[], same=[];
  _changedRows = [];

  for (const name of allNames) {{
    const o = oldMap[name], n = newMap[name];
    if (!o) {{ added.push(name); continue; }}
    if (!n) {{ removed.push(name); continue; }}
    const ow = o.weight, nw = n.weight;
    const os = o.shares, ns = n.shares;
    const deltaW = nw - ow, deltaS = ns - os;
    if (deltaW !== 0 || deltaS !== 0)
      _changedRows.push({{ name, ticker: o.ticker||n.ticker||'', ow, nw, deltaW, os, ns, deltaS }});
    else same.push(name);
  }}

  document.getElementById('diff-chips').innerHTML = `
    <div class="chip"><div class="val" style="color:#dc2626">${{added.length}}</div><div class="lbl">新增持股</div></div>
    <div class="chip"><div class="val" style="color:#16a34a">${{removed.length}}</div><div class="lbl">移除持股</div></div>
    <div class="chip"><div class="val" style="color:#1e40af">${{_changedRows.length}}</div><div class="lbl">比例變化</div></div>
    <div class="chip"><div class="val">${{same.length}}</div><div class="lbl">持平</div></div>`;

  // 靜態 section（新增 / 移除）
  const staticRow = (name, cls, o, n) => {{
    const ow = o ? o.weight : 0, nw = n ? n.weight : 0;
    const deltaW = nw - ow;
    const wc = deltaW > 0 ? 'diff-up' : deltaW < 0 ? 'diff-dn' : '';
    const os = o ? o.shares : 0, ns = n ? n.shares : 0;
    const deltaS = ns - os;
    const sc = deltaS > 0 ? '#dc2626' : deltaS < 0 ? '#16a34a' : '#aaa';
    const sSign = deltaS > 0 ? '+' : '';
    const dss = (o && n)
      ? `<b style="color:${{sc}}">${{sSign}}${{fmt(deltaS)}}</b>`
      : (o ? `<b style="color:#16a34a">-${{fmt(os)}}</b>`
           : `<b style="color:#dc2626">+${{fmt(ns)}}</b>`);
    return `<tr class="${{cls}}">
      <td><b>${{name}}</b></td>
      <td style="color:#4361ee">${{(o||n).ticker||'─'}}</td>
      <td class="num">${{o ? ow.toFixed(2)+'%' : '─'}}</td>
      <td class="num">${{n ? nw.toFixed(2)+'%' : '─'}}</td>
      <td class="num ${{wc}}">${{deltaW !== 0 ? (deltaW>0?'+':'')+deltaW.toFixed(2)+'%' : '─'}}</td>
      <td class="num">${{o ? fmt(os) : '─'}}</td>
      <td class="num">${{n ? fmt(ns) : '─'}}</td>
      <td class="num">${{dss}}</td>
    </tr>`;
  }};
  const staticSection = (title, names, cls, getO, getN) => names.length === 0 ? '' : `
    <div class="card"><h2>${{title}}</h2>
      <div class="tbl-wrap"><table>
        <thead><tr><th>股票名稱</th><th>代碼</th><th>舊比例</th><th>新比例</th><th>比例差異</th><th>舊股數</th><th>新股數</th><th>股數差異</th></tr></thead>
        <tbody>${{names.map(n => staticRow(n, cls, getO(n), getN(n))).join('')}}</tbody>
      </table></div>
    </div>`;

  // 可排序的「比例/股數變化」section
  const TH = (label, key) =>
    `<th data-key="${{key}}" onclick="diffSortBy('${{key}}')" style="cursor:pointer">${{label}}</th>`;
  const changedSection = _changedRows.length === 0 ? '' : `
    <div class="card"><h2>🔵 比例 / 股數變化</h2>
      <div class="tbl-wrap"><table id="diff-changed-tbl">
        <thead><tr>
          ${{TH('股票名稱','name')}}
          ${{TH('代碼','ticker')}}
          ${{TH('舊比例','ow')}}
          ${{TH('新比例','nw')}}
          ${{TH('比例差異','deltaW')}}
          ${{TH('舊股數','os')}}
          ${{TH('新股數','ns')}}
          ${{TH('股數差異','deltaS')}}
        </tr></thead>
        <tbody id="diff-changed-body"></tbody>
      </table></div>
    </div>`;

  document.getElementById('diff-content').innerHTML =
    (oldDate === newDate ? '<div class="card"><p class="empty">請選擇不同日期進行比較</p></div>' : '') +
    staticSection('🟢 新增持股', added,   'diff-new', n => null,      n => newMap[n]) +
    staticSection('🔴 移除持股', removed, 'diff-del', n => oldMap[n], n => null     ) +
    changedSection +
    (added.length + removed.length + _changedRows.length === 0
      ? '<div class="card"><p class="empty">兩次快照持股完全相同</p></div>' : '');

  if (_changedRows.length > 0) renderChangedSection();
}}

// init
renderHoldings();
</script>
</body>
</html>
"""

OUT.write_text(html, encoding="utf-8")
print(f"HTML saved: {OUT}")
print(f"File size: {OUT.stat().st_size / 1024:.1f} KB")
