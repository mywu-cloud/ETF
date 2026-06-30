export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);
  const dateParam = url.searchParams.get('date'); // YYYYMMDD format

  if (!dateParam || dateParam.length !== 8) {
    return new Response(JSON.stringify({ error: 'Invalid date' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }

  const yyyy = dateParam.substring(0, 4);
  const mm = dateParam.substring(4, 6);
  const dd = dateParam.substring(6, 8);
  const isoDate = yyyy + '-' + mm + '-' + dd;

  // Try TPEx OpenAPI first (REST endpoint, no bot detection)
  const tpexOpenApiUrl = 'https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes?date=' + isoDate;

  try {
    const resp = await fetch(tpexOpenApiUrl, {
      headers: {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (compatible; ETF-Tracker/1.0)'
      },
      redirect: 'follow'
    });

    if (resp.ok) {
      const data = await resp.json();
      const result = {};

      // TPEx OpenAPI format: array of objects with fields
      for (const item of (Array.isArray(data) ? data : [])) {
        // Fields vary - common ones: SecuritiesCompanyCode, Close, Change, etc.
        const ticker = (item.SecuritiesCompanyCode || item.Code || item['證券代號'] || '').trim();
        if (!ticker || ticker.length < 4) continue;

        const closeStr = (item.Close || item['收盤價'] || item.ClosingPrice || '').replace(/,/g, '');
        const changeStr = (item.Change || item['漲跌'] || item.PriceChange || '').replace(/,/g, '');
        const close = parseFloat(closeStr);
        const changeVal = parseFloat(changeStr) || 0;

        if (!isNaN(close) && close > 0) {
          const prevClose = close - changeVal;
          const changeP = prevClose !== 0 ? parseFloat((changeVal / prevClose * 100).toFixed(2)) : 0;
          result[ticker] = { price: close, change: parseFloat(changeVal.toFixed(2)), changeP };
        }
      }

      if (Object.keys(result).length > 0) {
        return new Response(JSON.stringify(result), {
          status: 200,
          headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Cache-Control': 'public, max-age=1800'
          }
        });
      }
    }

    // Fallback: Try FinMind API (server-side, no browser rate limit issues)
    // FinMind from CF Worker edge is a fresh IP each time, avoiding browser rate limits
    const rocYear = parseInt(yyyy) - 1911;
    const d7ago = new Date(yyyy + '-' + mm + '-' + dd);
    d7ago.setDate(d7ago.getDate() - 7);
    const startDate = d7ago.toISOString().substring(0, 10);

    // Use FinMind to get all Taiwan stocks for the date range
    const finmindUrl = 'https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&start_date=' + startDate + '&end_date=' + isoDate;
    const fResp = await fetch(finmindUrl, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; ETF-Tracker/1.0)' }
    });

    if (fResp.ok) {
      const fData = await fResp.json();
      const result = {};
      const latestByTicker = {};

      for (const row of (fData.data || [])) {
        const ticker = row.stock_id;
        if (!latestByTicker[ticker] || row.date > latestByTicker[ticker].date) {
          latestByTicker[ticker] = row;
        }
      }

      for (const [ticker, row] of Object.entries(latestByTicker)) {
        const close = row.close;
        const changeVal = row.spread;
        const prevClose = close - changeVal;
        const changeP = prevClose !== 0 ? parseFloat((changeVal / prevClose * 100).toFixed(2)) : 0;
        result[ticker] = { price: close, change: parseFloat(changeVal.toFixed(2)), changeP };
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

    return new Response(JSON.stringify({ error: 'All data sources failed', tpexStatus: resp.status }), {
      status: 502,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });

  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }
}
