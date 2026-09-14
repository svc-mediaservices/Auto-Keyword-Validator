"""
Twice-weekly Google first-page rank checker.
Provider rotation + rolling 14-check history + latest-check summary columns,
all in Google Sheets.

Sheet layout, tab "rankings":
  A: keyword
  B-O: last 14 checks, newest first (header = check date)
       "3" = position 3, "-" = not on page 1, "~5" = approximate (Tavily),
       blank = quota ran out that run
  P: On Page 1 (Yes/No, latest check)
  Q: Ranking URL (which page of your site ranked, latest check)

Tab "usage": provider | period | used   (period = "2026-09" or "lifetime")

Required secrets/env:
  SHEET_ID, TARGET_DOMAIN, GOOGLE_CREDENTIALS (service account JSON)
  Plus at least one provider key: BRIGHTDATA_KEY, SERPAPI_KEY,
  SCRAPERAPI_KEY, TAVILY_KEY, SERPER_KEY
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from providers import PROVIDERS

MAX_HISTORY = 14
SUMMARY_HEADERS = ["On Page 1", "Ranking URL"]
SHEET_ID = os.environ["SHEET_ID"]


def get_sheet():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds).open_by_key(SHEET_ID)


def load_usage(ws) -> dict:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    usage = {}
    for row in ws.get_all_records():
        p, period = row.get("provider"), str(row.get("period"))
        if p and (period == month or period == "lifetime"):
            usage[p] = usage.get(p, 0) + int(row.get("used", 0))
    return usage


def save_usage(ws, spent: dict):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = []
    for p in PROVIDERS:
        n = spent.get(p["name"], 0)
        if n:
            period = "lifetime" if p["reset"] == "one_time" else month
            rows.append([p["name"], period, n])
    if rows:
        ws.append_rows(rows)


def build_rotation(usage: dict) -> list:
    active = []
    for p in PROVIDERS:
        if not os.environ.get(p["env"]):
            continue
        remaining = p["quota"] - usage.get(p["name"], 0)
        if remaining > 0:
            active.append({**p, "remaining": remaining})
    return active


def main():
    sheet = get_sheet()
    rankings = sheet.worksheet("rankings")
    try:
        usage_ws = sheet.worksheet("usage")
    except gspread.WorksheetNotFound:
        usage_ws = sheet.add_worksheet("usage", rows=2000, cols=3)
        usage_ws.append_row(["provider", "period", "used"])

    grid = rankings.get_all_values()
    if len(grid) < 2:
        sys.exit("No keywords found in 'rankings' tab")

    old_header = grid[0]
    # Old history date headers = everything between col A and the summary block
    old_dates = [h for h in old_header[1:] if h not in SUMMARY_HEADERS][:MAX_HISTORY]

    rotation = build_rotation(load_usage(usage_ws))
    if not rotation:
        sys.exit("No provider has remaining free quota this period")

    budget = sum(p["remaining"] for p in rotation)
    rows = [r for r in grid[1:] if r and r[0].strip()]
    print(f"Keywords: {len(rows)} | Free budget available: {budget}")
    for p in rotation:
        print(f"  {p['name']}: {p['remaining']} left ({p['reset']})")

    today = datetime.now(timezone.utc).strftime("%m/%d")
    new_header = (["keyword", today] + old_dates[:MAX_HISTORY - 1]
                  + SUMMARY_HEADERS)

    spent = {}
    out_rows = []
    idx = 0
    checked = on_page = 0

    for r in rows:
        kw = r[0].strip()
        old_hist = [r[i] if i < len(r) else "" for i in range(1, len(old_dates) + 1)]
        # previous summary values (preserved if this run skips the keyword)
        s_off = 1 + len(old_dates)
        prev_summary = [r[i] if i < len(r) else "" for i in range(s_off, s_off + 2)]

        while idx < len(rotation) and rotation[idx]["remaining"] <= 0:
            idx += 1

        if idx >= len(rotation):
            out_rows.append([kw, ""] + old_hist[:MAX_HISTORY - 1] + prev_summary)
            continue

        p = rotation[idx]
        try:
            pos, url = p["fn"](kw)
            if pos:
                val = f"~{pos}" if p["approximate"] else str(pos)
                summary = ["Yes", url or ""]
                on_page += 1
            else:
                val = "-"
                summary = ["No", ""]
            checked += 1
        except Exception as e:
            print(f"  {p['name']} failed on '{kw}': {e}")
            val, summary = "", prev_summary

        p["remaining"] -= 1
        spent[p["name"]] = spent.get(p["name"], 0) + 1
        out_rows.append([kw, val] + old_hist[:MAX_HISTORY - 1] + summary)
        time.sleep(0.5)

    rankings.update([new_header] + out_rows, "A1")
    save_usage(usage_ws, spent)

    print(f"\nChecked {checked}/{len(rows)} | On page 1: {on_page}")


if __name__ == "__main__":
    main()
