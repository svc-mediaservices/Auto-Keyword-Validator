"""
Weekly LLM visibility checker (ChatGPT, Claude, Perplexity).

Reads keywords from the "rankings" tab (column A) and maintains one tab
per LLM: llm_chatgpt, llm_claude, llm_perplexity. Tabs are auto-created.

Tab layout (same rolling model as the SERP tracker):
  A: keyword
  B-O: last 14 checks, newest first (header = check date)
       "C2" = cited, 2nd source | "M" = mentioned in text, not cited
       "-"  = absent            | blank = errored/skipped that run
  P: Cited (Yes/No, latest check)
  Q: Cited URL (latest check)

Env: SHEET_ID, TARGET_DOMAIN, GOOGLE_CREDENTIALS
     + any of PERPLEXITY_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
     LLM_MAX_QUERIES (optional cost guard, per LLM per run; 0 = no cap)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from llm_providers import LLM_PROVIDERS

MAX_HISTORY = 14
SUMMARY_HEADERS = ["Cited", "Cited URL"]
MAX_QUERIES = int(os.environ.get("LLM_MAX_QUERIES", "0"))


def get_sheet():
    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_CREDENTIALS"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return gspread.authorize(creds).open_by_key(os.environ["SHEET_ID"])


def run_tab(sheet, tab: str, fn, keywords: list[str]):
    try:
        ws = sheet.worksheet(tab)
        grid = ws.get_all_values()
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(tab, rows=len(keywords) + 10,
                                 cols=1 + MAX_HISTORY + len(SUMMARY_HEADERS))
        grid = []

    old_header = grid[0] if grid else ["keyword"]
    old_dates = [h for h in old_header[1:] if h not in SUMMARY_HEADERS][:MAX_HISTORY]
    old_rows = {r[0].strip(): r for r in grid[1:] if r and r[0].strip()}

    today = datetime.now(timezone.utc).strftime("%m/%d")
    new_header = ["keyword", today] + old_dates[:MAX_HISTORY - 1] + SUMMARY_HEADERS

    out, cited_count, done = [], 0, 0
    for kw in keywords:
        r = old_rows.get(kw, [kw])
        old_hist = [r[i] if i < len(r) else "" for i in range(1, len(old_dates) + 1)]
        s_off = 1 + len(old_dates)
        prev_summary = [r[i] if i < len(r) else "" for i in range(s_off, s_off + 2)]

        if MAX_QUERIES and done >= MAX_QUERIES:
            out.append([kw, ""] + old_hist[:MAX_HISTORY - 1] + prev_summary)
            continue
        try:
            pos, url, mentioned = fn(kw)
            done += 1
            if pos:
                val, summary = f"C{pos}", ["Yes", url or ""]
                cited_count += 1
            elif mentioned:
                val, summary = "M", ["No", ""]
            else:
                val, summary = "-", ["No", ""]
        except Exception as e:
            print(f"  {tab} failed on '{kw}': {e}")
            val, summary = "", prev_summary
        out.append([kw, val] + old_hist[:MAX_HISTORY - 1] + summary)
        time.sleep(1)

    ws.update([new_header] + out, "A1")
    print(f"{tab}: {done} queried | cited: {cited_count}/{len(keywords)}")


def main():
    sheet = get_sheet()
    keywords = [k.strip() for k in sheet.worksheet("rankings").col_values(1)[1:]
                if k.strip()]
    if not keywords:
        sys.exit("No keywords in 'rankings' tab")

    active = {tab: fn for tab, (env, fn) in LLM_PROVIDERS.items()
              if os.environ.get(env)}
    if not active:
        sys.exit("No LLM API keys configured")

    print(f"Keywords: {len(keywords)} | LLMs: {', '.join(active)}")
    for tab, fn in active.items():
        run_tab(sheet, tab, fn, keywords)


if __name__ == "__main__":
    main()
