#!/usr/bin/env python3
"""
ETF 00981A 持股追蹤器
資料來源：統一投信輕鬆理財網（ezmoney.com.tw）
只抓取股票（AssetCode == "ST"）
儲存格式：JSON（適合 Git 版控）
"""

import html as html_lib
import json
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DATA_DIR = Path(__file__).parent / "data"
HISTORY_FILE = DATA_DIR / "history_00981A.json"
LATEST_FILE = DATA_DIR / "latest_00981A.json"

FUND_CODE = "49YTW"  # 統一投信內部代碼，對應 00981A
URL = f"https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode={FUND_CODE}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.ezmoney.com.tw/ETF/Fund/Info",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}


# ── 載入 / 儲存歷史 ─────────────────────────────────────────────────

def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def save_latest(snapshot: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


# ── 建立有重試的 Session ─────────────────────────────────────────────

def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


# ── 爬取資料 ───────────────────────────────────────────────────────

def fetch_holdings() -> tuple[str, list[dict]]:
    """從 ezmoney 抓取 00981A 持股，只回傳股票 (AssetCode == 'ST')。"""
    session = build_session()

    # 先打首頁拿 cookie，再請求資料頁，模擬一般瀏覽流程
    try:
        session.get("https://www.ezmoney.com.tw/", timeout=30)
    except requests.RequestException as e:
        print(f"[warn] warm-up request failed: {e}")

    last_exc = None
    for attempt in range(1, 4):
        try:
            resp = session.get(URL, timeout=30)
            resp.raise_for_status()
            resp.encoding = "utf-8"

            soup = BeautifulSoup(resp.text, "html.parser")
            data_div = soup.find("div", id="DataAsset")
            if data_div is None or not data_div.get("data-content"):
                snippet = resp.text[:400].replace("\n", " ")
                raise RuntimeError(
                    f"找不到 #DataAsset (HTTP {resp.status_code}, len={len(resp.text)})。"
                    f" 開頭片段：{snippet}"
                )

            raw_json = html_lib.unescape(data_div["data-content"])
            asset_groups = json.loads(raw_json)

            stock_group = next(
                (g for g in asset_groups if g.get("AssetCode") == "ST"),
                None,
            )
            if stock_group is None or not stock_group.get("Details"):
                raise RuntimeError("找不到股票資產群組 (AssetCode == 'ST')")

            details = stock_group["Details"]

            tran_date = details[0].get("TranDate", "") or ""
            data_date = tran_date[:10] if tran_date else date.today().isoformat()

            holdings = []
            for d in details:
                name = (d.get("DetailName") or "").strip()
                if not name:
                    continue
                ticker = (d.get("DetailCode") or "").strip() or None
                weight = d.get("NavRate")
                shares = d.get("Share")
                if shares is not None:
                    shares = int(shares)
                holdings.append({
                    "ticker": ticker,
                    "name": name,
                    "weight": float(weight) if weight is not None else None,
                    "shares": shares,
                })

            return data_date, holdings
        except Exception as e:  # noqa: BLE001
            last_exc = e
            print(f"[attempt {attempt}] fetch_holdings failed: {e}")
            time.sleep(2 * attempt)

    raise RuntimeError(f"連續 3 次抓取 00981A 失敗，最後錯誤：{last_exc}")


# ── 加入新快照 ─────────────────────────────────────────────────────

def add_snapshot(history: list[dict], data_date: str, holdings: list[dict]) -> dict:
    snapshot = {
        "data_date": data_date,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "holdings": holdings,
    }

    for i, snap in enumerate(history):
        if snap["data_date"] == data_date:
            history[i] = snapshot
            return snapshot

    history.append(snapshot)
    history.sort(key=lambda s: s["data_date"])
    return snapshot


# ── 主程式 ────────────────────────────────────────────────────────

def main() -> None:
    print("正在抓取 ezmoney 00981A 持股資料…")
    data_date, holdings = fetch_holdings()
    history = load_history()
    snap = add_snapshot(history, data_date, holdings)
    save_history(history)
    save_latest(snap)
    print(f"已儲存快照：資料日期 {data_date}，共 {len(holdings)} 支股票持股")


if __name__ == "__main__":
    main()
