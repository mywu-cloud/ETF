#!/usr/bin/env python3
"""
ETF 00992A 持股追蹤器
資料來源：MoneyDJ
"""

import sqlite3
import re
from datetime import date, datetime
from pathlib import Path

import urllib3
import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DB_PATH = Path(__file__).parent / "holdings_00992A.db"
URL = "https://www.moneydj.com/etf/x/basic/basic0007B.xdjhtm?etfid=00992A.TW"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.moneydj.com/",
}


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            data_date TEXT NOT NULL,
            fetched_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS holdings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
            ticker      TEXT,
            name        TEXT NOT NULL,
            weight      REAL,
            shares      INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_holdings_snapshot ON holdings(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_snapshots_date    ON snapshots(data_date);
    """)
    conn.commit()


def fetch_holdings() -> tuple[str, list[dict]]:
    resp = requests.get(URL, headers=HEADERS, timeout=30, verify=False)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    soup = BeautifulSoup(resp.text, "html.parser")

    data_date = date.today().isoformat()
    date_pattern = re.compile(r"資料日期[：:]\s*(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})")
    for text_node in soup.find_all(string=date_pattern):
        m = date_pattern.search(text_node)
        if m:
            data_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            break

    table = soup.find("table", class_="datalist")
    if table is None:
        raise RuntimeError("找不到持股表格，MoneyDJ 頁面結構可能已變更")

    holdings = []
    ticker_re = re.compile(r"\((\d{4,6}(?:\.\w+)?)\)")

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue

        raw_name = cells[0].get_text(strip=True)
        m = ticker_re.search(raw_name)
        ticker = m.group(1).replace(".TW", "").replace(".tw", "") if m else None
        name = ticker_re.sub("", raw_name).strip()

        try:
            weight = float(cells[1].get_text(strip=True).replace(",", ""))
        except ValueError:
            weight = None

        shares = None
        if len(cells) >= 3:
            try:
                shares = int(cells[2].get_text(strip=True).replace(",", ""))
            except ValueError:
                pass

        if name:
            holdings.append({"ticker": ticker, "name": name, "weight": weight, "shares": shares})

    return data_date, holdings


def save_snapshot(conn: sqlite3.Connection, data_date: str, holdings: list[dict]) -> int:
    cur = conn.execute(
        "INSERT INTO snapshots (data_date, fetched_at) VALUES (?, ?)",
        (data_date, datetime.now().isoformat(timespec="seconds")),
    )
    snapshot_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO holdings (snapshot_id, ticker, name, weight, shares) VALUES (?, ?, ?, ?, ?)",
        [(snapshot_id, h["ticker"], h["name"], h["weight"], h["shares"]) for h in holdings],
    )
    conn.commit()
    return snapshot_id


def compare_latest_two(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, data_date, fetched_at FROM snapshots ORDER BY id DESC LIMIT 2"
    ).fetchall()

    if len(rows) < 2:
        print("(尚無前次快照可比較，這是第一筆資料)")
        return

    new_id, new_date, _ = rows[0]
    old_id, old_date, _ = rows[1]

    print(f"\n比較：{old_date} → {new_date}\n{'─'*55}")

    def get_holdings(snap_id):
        return {
            row[0]: {"weight": row[1], "shares": row[2]}
            for row in conn.execute(
                "SELECT name, weight, shares FROM holdings WHERE snapshot_id=?", (snap_id,)
            )
        }

    old_h = get_holdings(old_id)
    new_h = get_holdings(new_id)

    added   = set(new_h) - set(old_h)
    removed = set(old_h) - set(new_h)
    common  = set(new_h) & set(old_h)

    changed = [
        (name, old_h[name]["weight"], new_h[name]["weight"],
         old_h[name]["shares"], new_h[name]["shares"])
        for name in common
        if old_h[name]["weight"] != new_h[name]["weight"]
        or old_h[name]["shares"] != new_h[name]["shares"]
    ]
    changed.sort(key=lambda x: abs((x[2] or 0) - (x[1] or 0)), reverse=True)

    if added:
        print(f"\n【新增持股】{len(added)} 支")
        for name in sorted(added):
            h = new_h[name]
            print(f"  + {name:15s}  {h['weight'] or 0:6.2f}%  {h['shares'] or 0:>12,} 股")

    if removed:
        print(f"\n【移除持股】{len(removed)} 支")
        for name in sorted(removed):
            h = old_h[name]
            print(f"  - {name:15s}  {h['weight'] or 0:6.2f}%  {h['shares'] or 0:>12,} 股")

    if changed:
        print(f"\n【比例/股數變化】{len(changed)} 支")
        print(f"  {'名稱':15s}  {'舊比例':>7}  {'新比例':>7}  {'變化':>7}  {'舊股數':>12}  {'新股數':>12}")
        print(f"  {'─'*15}  {'─'*7}  {'─'*7}  {'─'*7}  {'─'*12}  {'─'*12}")
        for name, ow, nw, os_, ns in changed:
            delta = (nw or 0) - (ow or 0)
            print(
                f"  {name:15s}  {ow or 0:6.2f}%  {nw or 0:6.2f}%  "
                f"{delta:+6.2f}%  {os_ or 0:>12,}  {ns or 0:>12,}"
            )

    if not added and not removed and not changed:
        print("  (本次持股與前次完全相同)")


def print_latest(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT id, data_date FROM snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return

    snap_id, data_date = row
    print(f"\n【最新持股】資料日期：{data_date}\n{'─'*55}")
    print(f"  {'名稱':15s}  {'代碼':>6}  {'比例':>7}  {'持股數':>12}")
    print(f"  {'─'*15}  {'─'*6}  {'─'*7}  {'─'*12}")
    for name, ticker, weight, shares in conn.execute(
        "SELECT name, ticker, weight, shares FROM holdings "
        "WHERE snapshot_id=? ORDER BY weight DESC NULLS LAST",
        (snap_id,),
    ):
        ticker_str = ticker or "─"
        print(f"  {name:15s}  {ticker_str:>6}  {weight or 0:6.2f}%  {shares or 0:>12,}")


def list_snapshots(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT s.id, s.data_date, s.fetched_at, COUNT(h.id) "
        "FROM snapshots s JOIN holdings h ON h.snapshot_id=s.id "
        "GROUP BY s.id ORDER BY s.id DESC"
    ).fetchall()
    print(f"\n{'ID':>4}  {'資料日期':>10}  {'抓取時間':>20}  {'持股數':>6}")
    print(f"{'─'*4}  {'─'*10}  {'─'*20}  {'─'*6}")
    for snap_id, data_date, fetched_at, cnt in rows:
        print(f"{snap_id:>4}  {data_date:>10}  {fetched_at:>20}  {cnt:>6}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="ETF 00992A 持股追蹤器")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("fetch", help="抓取最新持股並存入資料庫")
    sub.add_parser("show",  help="顯示最新快照持股清單")
    sub.add_parser("diff",  help="比較最近兩次快照的差異")
    sub.add_parser("list",  help="列出所有歷史快照")

    args = parser.parse_args()

    with sqlite3.connect(DB_PATH) as conn:
        init_db(conn)

        if args.cmd == "fetch" or args.cmd is None:
            print("正在抓取 MoneyDJ 00992A 持股資料…")
            data_date, holdings = fetch_holdings()
            snap_id = save_snapshot(conn, data_date, holdings)
            print(f"已儲存快照 #{snap_id}：資料日期 {data_date}，共 {len(holdings)} 支持股")
            compare_latest_two(conn)

        elif args.cmd == "show":
            print_latest(conn)

        elif args.cmd == "diff":
            compare_latest_two(conn)

        elif args.cmd == "list":
            list_snapshots(conn)


if __name__ == "__main__":
    main()
