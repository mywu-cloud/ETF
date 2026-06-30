export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);
  const dateParam = url.searchParams.get('date');   // YYYYMMDD
  const tickersParam = url.searchParams.get('tickers'); // comma-separated, optional

  if (!dateParam || dateParam.length !== 8) {
    return new Response(JSON.stringify({ error: 'Invalid date' }), {
      status: 400, headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }

  const yyyy = dateParam.substring(0, 4);
  const mm = dateParam.substring(4, 6);
  const dd = dateParam.substring(6, 8);
  const isoDate = yyyy + '-' + mm + '-' + dd;

  const result = {};

  // ── Step 1: TWSE CSV (上市) ────────────────────────────────
  try {
    const twseUrl = 'https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date=' + dateParam;
    const twseResp = await fetch(twseUrl, { headers: { 'User-Agent': 'Mozilla/5.0' } });
    if (twseResp.ok) {
      const text = await twseResp.text();
      const lines = text.trim().split('\n');
      const isCSV = lines[0] && lines[0].includes('日期');
      if (isCSV) {
        for (let i = 1; i < lines.length; i++) {
          const cols = lines[i].split(',').map(c => c.replace(/"/g, '').trim());
          if (cols.length < 10) continue;
          const ticker = cols[1];
          const close = parseFloat(cols[8].replace(/,/g, ''));
          const changeVal = parseFloat(cols[9].replace(/,/g, ''));
          const prevClose = close - changeVal;
          const changeP = prevClose !== 0 ? parseFloat((changeVal / prevClose * 100).toFixed(2)) : 0;
          if (!isNaN(close) && close > 0) {
            result[ticker] = { price: close, change: parseFloat(changeVal.toFixed(2)), changeP };
          }
        }
      }
    }
  } catch (e) {}

  // ── Step 2: FinMind for OTC/missing stocks ───────────────────
  // Determine which tickers still need data
  const requestedTickers = tickersParam ? tickersParam.split(',').filter(Boolean) : [];
  const missingTickers = requestedTickers.length > 0
    ? requestedTickers.filter(t => !result[t])
    : []; // If no specific tickers requested, we only have TWSE data

  if (missingTickers.length > 0) {
    // Calculate date range: last 7 days
    const endDate = new Date(isoDate);
    const startDate = new Date(endDate);
    startDate.setDate(startDate.getDate() - 7);
    const startStr = startDate.toISOString().substring(0, 10);

    // Fetch all missing tickers in parallel from FinMind (server-side, no browser rate limit)
    const finmindBase = 'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&start_date=' + startStr + '&end_date=' + isoDate;
    const fetchResults = await Promise.allSettled(
      missingTickers.map(ticker =>
        fetch(finmindBase + '&data_id=' + ticker, {
          headers: { 'User-Agent': 'Mozilla/5.0 (compatible; ETF-Tracker/1.0)' }
        })
        .then(r => r.json())
        .then(d => ({ ticker, data: d.data }))
      )
    );

    for (const r of fetchResults) {
      if (r.status === 'fulfilled' && r.value.data && r.value.data.length > 0) {
        const rows = r.value.data;
        const latest = rows[rows.length - 1];
        const close = latest.close;
        const changeVal = latest.spread;
        const prevClose = close - changeVal;
        const changeP = prevClose !== 0 ? parseFloat((changeVal / prevClose * 100).toFixed(2)) : 0;
        result[r.value.ticker] = { price: close, change: parseFloat(changeVal.toFixed(2)), changeP };
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
