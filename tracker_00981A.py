#!/usr/bin/env python3
"""
ETF 00981A 持股追蹤器
資料來源：統一投信輕鬆理財網（ezmoney.com.tw）
儲存格式：JSON（適合 Git 版控）
"""

import html as html_lib
import json
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / "data"
HISTORY_FILE = DATA_DIR / "history_00981A.json"
LATEST_FILE = DATA_DIR / "latest_00981A.json"

URL = "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"
HEADERS = {
        "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
        ),
}

# ── 載入 / 儲存歷史 ─────────────────────────────────────────────────────────

def load_history() -> list[dict]:
        """載入歷史快照（list of snapshots），檔案不存在就回傳空 list"""
        if HISTORY_FILE.exists():
                    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                                    return json.load(f)
                            return []

    def save_history(history: list[dict]) -> None:
            DATA_DIR.mkdir(exist_ok=True)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                        json.dump(history, f, ensure_ascii=False, indent=2)

        def save_latest(snapshot: dict) -> None:
                """另存一份最新快照，方便前端 fetch"""
                DATA_DIR.mkdir(exist_ok=True)
                with open(LATEST_FILE, "w", encoding="utf-8") as f:
                            json.dump(snapshot, f, ensure_ascii=False, indent=2)

            # ── 爬取資料 ────────────────────────────────────────────────────────────────

def fetch_holdings() -> tuple[str, list[dict]]:
        """從統一投信官網抓取 00981A 持股，回傳 (data_date, holdings_list)"""
        resp = requests.get(URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")
    data_div = soup.find("div", id="DataAsset")
    if data_div is None or not data_div.get("data-content"):
                raise RuntimeError("找不到 #DataAsset，統一投信頁面結構可能已變更")

    raw_json = html_lib.unescape(data_div["data-content"])
    asset_groups = json.loads(raw_json)

    stock_group = next((g for g in asset_groups if g.get("AssetCode") == "ST"), None)
    if stock_group is None or not stock_group.get("Details"):
                raise RuntimeError("找不到股票資產群組")

    details = stock_group["Details"]

    tran_date = details[0].get("TranDate", "")
    data_date = tran_date[:10] if tran_date else date.today().isoformat()

    holdings = []
    for d in details:
                ticker = (d.get("DetailCode") or "").strip() or None
                name = (d.get("DetailName") or "").strip()
                weight = d.get("NavRate")
                shares = d.get("Share")
                if shares is not None:
                                shares = int(shares)
                            if name:
                                            holdings.append({
                                                                "ticker": ticker,
                                                                "name": name,
                                                                "weight": float(weight) if weight is not None else None,
                                                                "shares": shares,
                                            })

    return data_date, holdings

# ── 加入新快照 ─────────────────────────────────────────────────────────────

def add_snapshot(history: list[dict], data_date: str, holdings: list[dict]) -> dict:
        """把新的快照加入歷史；若同一個 data_date 已存在則覆蓋"""
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

# ── 比較最近兩次快照 ─────────────────────────────────────────────────────────

def compare_latest_two(history: list[dict]) -> None:
        if len(history) < 2:
                    print("(尚無前次快照可比較，這是第一筆資料)")
                    return

    new_snap = history[-1]
    old_snap = history[-2]

    new_date = new_snap["data_date"]
    old_date = old_snap["data_date"]

    print(f"\n比較：{old_date} → {new_date}\n{'─'*55}")

    def to_dict(holdings):
                return {h["name"]: h for h in holdings}

    old_h = to_dict(old_snap["holdings"])
    new_h = to_dict(new_snap["holdings"])

    added = set(new_h) - set(old_h)
    removed = set(old_h) - set(new_h)
    common = set(new_h) & set(old_h)

    changed = [
                (name,
                          old_h[name].get("weight"), new_h[name].get("weight"),
                          old_h[name].get("shares"), new_h[name].get("shares"))
                for name in common
                if old_h[name].get("weight") != new_h[name].get("weight")
                or old_h[name].get("shares") != new_h[name].get("shares")
    ]
    changed.sort(key=lambda x: abs((x[2] or 0) - (x[1] or 0)), reverse=True)

    if added:
                print(f"\n【新增持股】{len(added)} 支")
        for name in sorted(added):
                        h = new_h[name]
                        print(f"  + {name:15s} {h.get('weight') or 0:6.2f}% {h.get('shares') or 0:>12,} 股")

    if removed:
                print(f"\n【移除持股】{len(removed)} 支")
        for name in sorted(removed):
                        h = old_h[name]
                        print(f"  - {name:15s} {h.get('weight') or 0:6.2f}% {h.get('shares') or 0:>12,} 股")

    if changed:
                print(f"\n【比例/股數變化】{len(changed)} 支")
        print(f"  {'名稱':15s} {'舊比例':>7} {'新比例':>7} {'變化':>7} {'舊股數':>12} {'新股數':>12}")
        print(f"  {'─'*15} {'─'*7} {'─'*7} {'─'*7} {'─'*12} {'─'*12}")
        for name, ow, nw, os_, ns in changed:
                        delta = (nw or 0) - (ow or 0)
                        print(
                            f"  {name:15s} {ow or 0:6.2f}% {nw or 0:6.2f}% "
                            f"{delta:+6.2f}% {os_ or 0:>12,} {ns or 0:>12,}"
                        )

    if not added and not removed and not changed:
                print("  (本次持股與前次完全相同)")

# ── 列印目前持股 ─────────────────────────────────────────────────────────────

def print_latest(history: list[dict]) -> None:
        if not history:
                    return

    snap = history[-1]
    print(f"\n【最新持股】資料日期：{snap['data_date']}\n{'─'*55}")
    print(f"  {'名稱':15s} {'代碼':>6} {'比例':>7} {'持股數':>12}")
    print(f"  {'─'*15} {'─'*6} {'─'*7} {'─'*12}")

    holdings = sorted(snap["holdings"], key=lambda h: h.get("weight") or 0, reverse=True)
    for h in holdings:
                ticker_str = h.get("ticker") or "─"
        print(
                        f"  {h['name']:15s} {ticker_str:>6} "
                        f"{h.get('weight') or 0:6.2f}% {h.get('shares') or 0:>12,}"
        )

# ── 歷史快照清單 ─────────────────────────────────────────────────────────────

def list_snapshots(history: list[dict]) -> None:
        print(f"\n{'#':>4} {'資料日期':>10} {'抓取時間':>20} {'持股數':>6}")
    print(f"{'─'*4} {'─'*10} {'─'*20} {'─'*6}")
    for i, snap in enumerate(history, 1):
                print(
                    f"{i:>4} {snap['data_date']:>10} "
                    f"{snap['fetched_at']:>20} {len(snap['holdings']):>6}"
    )

# ── 主程式 ──────────────────────────────────────────────────────────────────

def main() -> None:
        import argparse

    parser = argparse.ArgumentParser(description="ETF 00981A 持股追蹤器")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("fetch", help="抓取最新持股並存入歷史")
    sub.add_parser("show", help="顯示最新快照持股清單")
    sub.add_parser("diff", help="比較最近兩次快照的差異")
    sub.add_parser("list", help="列出所有歷史快照")

    args = parser.parse_args()

    history = load_history()

    if args.cmd == "fetch" or args.cmd is None:
                print("正在抓取統一投信 00981A 持股資料…")
        data_date, holdings = fetch_holdings()
        snap = add_snapshot(history, data_date, holdings)
        save_history(history)
        save_latest(snap)
        print(f"已儲存快照：資料日期 {data_date}，共 {len(holdings)} 支持股")
        compare_latest_two(history)

elif args.cmd == "show":
        print_latest(history)

elif args.cmd == "diff":
        compare_latest_two(history)

elif args.cmd == "list":
        list_snapshots(history)

if __name__ == "__main__":
        main()
