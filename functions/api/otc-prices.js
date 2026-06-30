export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);
  const dateParam = url.searchParams.get('date');     // YYYYMMDD
  const tickersParam = url.searchParams.get('tickers'); // comma-separated list

  if (!dateParam || dateParam.length !== 8) {
    return new Response(JSON.stringify({ error: 'Invalid date' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }

  const result = {};
  const requestedTickers = tickersParam
    ? tickersParam.split(',').map(t => t.trim()).filter(Boolean)
    : [];

  // ── Step 1: TWSE STOCK_DAY_ALL CSV (上市股，日收盤) ────────
  try {
    const twseUrl = 'https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date=' + dateParam;
    const twseResp = await fetch(twseUrl, {
      headers: { 'User-Agent': 'Mozilla/5.0', 'Accept': '*/*' }
    });
    if (twseResp.ok) {
      const text = await twseResp.text();
      const lines = text.trim().split('\n');
      const tickerSet = requestedTickers.length > 0 ? new Set(requestedTickers) : null;
      if (lines[0] && lines[0].includes('日期')) {
        for (let i = 1; i < lines.length; i++) {
          const cols = lines[i].split(',').map(c => c.replace(/"/g, '').trim());
          if (cols.length < 10) continue;
          const ticker = cols[1];
          if (tickerSet && !tickerSet.has(ticker)) continue;
          const close = parseFloat(cols[8].replace(/,/g, ''));
          const changeVal = parseFloat(cols[9].replace(/,/g, ''));
          if (!isNaN(close) && close > 0) {
            const prevClose = close - changeVal;
            const changeP = prevClose !== 0 ? parseFloat((changeVal / prevClose * 100).toFixed(2)) : 0;
            result[ticker] = { price: close, change: parseFloat(changeVal.toFixed(2)), changeP };
          }
        }
      }
    }
  } catch (e) {}

  // ── Step 2: TWSE MIS API (上市+上櫃即時/收盤報價) ───────────
  // MIS supports both tse_ (listed) and otc_ (OTC) in a single batch request.
  // Use this to fill in any missing tickers (especially OTC stocks).
  const missingTickers = requestedTickers.length > 0
    ? requestedTickers.filter(t => !result[t])
    : [];

  if (missingTickers.length > 0) {
    try {
      // Build ex_ch: try otc_ prefix first for unknown tickers, also tse_ as fallback
      // MIS silently ignores invalid tickers, so we can safely try both prefixes
      const exChParts = [];
      for (const t of missingTickers) {
        exChParts.push('otc_' + t + '.tw');
        exChParts.push('tse_' + t + '.tw');
      }
      const exCh = exChParts.join('%7C'); // URL-encoded |

      const misUrl = 'https://mis.twse.com.tw/stock/api/getStockInfo.jsp' +
        '?ex_ch=' + exCh + '&json=1&delay=0&_=' + Date.now();

      const misResp = await fetch(misUrl, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
          'Referer': 'https://mis.twse.com.tw/',
          'Accept': 'application/json, text/javascript, */*'
        }
      });

      if (misResp.ok) {
        const misData = await misResp.json();
        for (const item of (misData.msgArray || [])) {
          const ticker = (item.c || '').trim();
          if (!ticker) continue;
          // z = 最近成交價, y = 昨收
          const priceStr = (item.z || item.y || '').replace(/,/g, '');
          const prevStr = (item.y || '').replace(/,/g, '');
          const price = parseFloat(priceStr);
          const prevClose = parseFloat(prevStr);
          if (!isNaN(price) && price > 0 && !isNaN(prevClose)) {
            const changeVal = parseFloat((price - prevClose).toFixed(2));
            const changeP = prevClose !== 0 ? parseFloat((changeVal / prevClose * 100).toFixed(2)) : 0;
            result[ticker] = { price, change: changeVal, changeP };
          }
        }
      }
    } catch (e) {}
  }

  // ── Step 3: FinMind fallback (for any still-missing OTC stocks) ─
  const stillMissing = requestedTickers.filter(t => !result[t]);
  if (stillMissing.length > 0) {
    const today = new Date();
    const startD = new Date(today); startD.setDate(startD.getDate() - 7);
    const startDate = startD.toISOString().substring(0, 10);
    const isoDate = dateParam.substring(0,4) + '-' + dateParam.substring(4,6) + '-' + dateParam.substring(6,8);
    const base = 'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&start_date=' + startDate + '&end_date=' + isoDate;

    const fetches = await Promise.allSettled(
      stillMissing.map(t =>
        fetch(base + '&data_id=' + t, { headers: { 'User-Agent': 'Mozilla/5.0' } })
          .then(r => r.json())
          .then(d => ({ t, rows: d.data }))
      )
    );
    for (const r of fetches) {
      if (r.status === 'fulfilled' && r.value.rows?.length > 0) {
        const row = r.value.rows[r.value.rows.length - 1];
        const close = row.close, changeVal = row.spread;
        const prevClose = close - changeVal;
        const changeP = prevClose !== 0 ? parseFloat((changeVal / prevClose * 100).toFixed(2)) : 0;
        result[r.value.t] = { price: close, change: parseFloat(changeVal.toFixed(2)), changeP };
      }
    }
  }

  return new Response(JSON.stringify(result), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'public, max-age=1800'
    }
  });
}
