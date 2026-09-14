# Weekly Rank Tracker (Google Sheets + free API rotation)

Checks 500 keywords weekly against Google page 1, rotating across free API tiers, with a rolling 14-check history per keyword in Google Sheets.

## Free tier facts (Sep 2026)

| Provider | Free searches | Resets? | Priority |
|---|---|---|---|
| **Bright Data** | **5,000/month, no card required** | **Monthly (1st)** | **1 — covers everything alone** |
| SerpAPI | 250/month | Monthly | 2 (fallback) |
| ScraperAPI | 40/month (Google = 25 credits each) | Monthly, no rollover | 3 (fallback) |
| Tavily | 1,000/month | Monthly | 4 (approximate, marked `~`) |
| Serper.dev | 2,500 ONE-TIME | Never | 5 (last-resort buffer) |

250 keywords × 2 runs/week ≈ 2,166 searches/month. Bright Data's 5,000 covers it alone with headroom (capped at 4,800 in config as a safety margin). Other providers are automatic fallback only. The `usage` tab shows exactly where you stand.

### Bright Data setup (5 min)
1. Sign up at brightdata.com (no card needed for the free tier).
2. Control Panel → add a **SERP API** zone. Default expected zone name: `serp_api1` (or change `BRIGHTDATA_ZONE` in the workflow).
3. Account settings → copy your API key → save as `BRIGHTDATA_KEY` repo secret.

**Tavily caveat:** it ranks by its own relevance, not real Google position. Its results are prefixed `~` in the sheet.

## Google Sheet setup

1. Create a sheet, name the first tab **rankings**.
2. Put `keyword` in A1, your 500 keywords in A2 down.
3. Google Cloud Console: create a project → enable Google Sheets API → create a Service Account → create a JSON key → download it.
4. Share the sheet with the service account email (Editor access).

## GitHub setup

Push these files to a repo, then add secrets (Settings → Secrets → Actions):

| Secret | Value |
|---|---|
| `SHEET_ID` | from the sheet URL: `docs.google.com/spreadsheets/d/THIS_PART/edit` |
| `TARGET_DOMAIN` | e.g. `jamesvasquezlaw.com` |
| `GOOGLE_CREDENTIALS` | full contents of the service account JSON file |
| `SERPAPI_KEY` / `SCRAPERAPI_KEY` / `TAVILY_KEY` / `SERPER_KEY` | whichever you have; missing ones are skipped |

Runs Mondays 8 AM ET. Manual: Actions tab → Weekly Rank Check → Run workflow.

## How to read the sheet

Columns B-O hold the last 14 checks, newest first (header = check date; oldest drops off automatically). Then two summary columns always show the latest check:
- **P: On Page 1** - Yes/No
- **Q: Ranking URL** - which page of your site ranked (catches page cannibalization)

History cell values: `3` = position 3 on page 1
- `-` = not on page 1
- `~5` = approximate position 5 (Tavily)
- blank = free quota ran out before this keyword was reached

Conditional formatting tip: color scale on B2:O501 (green low, red high) gives instant per-keyword trend visibility.
