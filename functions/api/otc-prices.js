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
  const rocYear = parseInt(yyyy) - 1911;
  const rocDate = rocYear + '/' + mm + '/' + dd;

  const tpexUrl =
    'https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php' +
    '?l=zh-tw&d=' + rocDate + '&se=AL&s=0,asc,0';

  try {
    const resp = await fetch(tpexUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (compatible; ETF-Tracker)',
        'Referer': 'https://www.tpex.org.tw/'
      }
    });

    if (!resp.ok) {
      return new Response(JSON.stringify({ error: 'TPEx API error', status: resp.status }), {
        status: 502,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    }

    const data = await resp.json();
    const result = {};

    for (const row of (data.aaData || [])) {
      const ticker = (row[0] || '').trim();
      if (!ticker || ticker.length < 4) continue;

      // TPEx columns: [0]代號 [1]名稱 [2]收盤 [3]漲跌 [4]開盤 [5]最高 [6]最低 ...
      const closeStr = (row[2] || '').replace(/,/g, '');
      const changeStr = (row[3] || '').replace(/,/g, '')
        .replace(/\u25b3|\u25b2|△|▲/g, '+')   // up arrow → +
        .replace(/\u25bd|\u25bc|▽|▼/g, '-');   // down arrow → -
      const close = parseFloat(closeStr);
      const changeVal = parseFloat(changeStr) || 0;

      if (!isNaN(close) && close > 0) {
        const prevClose = close - changeVal;
        const changeP = prevClose !== 0
          ? parseFloat((changeVal / prevClose * 100).toFixed(2))
          : 0;
        result[ticker] = {
          price: close,
          change: parseFloat(changeVal.toFixed(2)),
          changeP
        };
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
  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), {
      status: 500,
      headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
    });
  }
}
