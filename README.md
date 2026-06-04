# Finance News Tracker

Local USD/JPY news tracker that collects fresh items from **Japan** (BOJ, Nikkei Asia, NHK), **US official** (Federal Reserve, US Treasury), and **international FX media** (FXStreet, Investing.com), scores USD/JPY relevance with **DeepSeek API**, and writes an **executive summary** to `summaries/`.

中文注解：本地运行、RSS/HTML 抓取、DeepSeek 打分与汇总；仅使用公开 RSS，不绕过付费墙或反爬。

## Sources

| Source | Method | URL |
|--------|--------|-----|
| Bank of Japan | Official English RSS | `boj.or.jp/en/rss/whatsnew.xml`, `statistics.xml` |
| Nikkei | Nikkei Asia public RSS | `asia.nikkei.com/rss/feed/nar` |
| NHK WORLD | Polite HTML list/tag pages | `nhkworld/en/news/...` |
| Federal Reserve | Official RSS | `federalreserve.gov/feeds/press_monetary.xml`, `speeches.xml` |
| US Treasury | HTML press list (RSS unavailable) | `home.treasury.gov/news/press-releases` |
| FXStreet | Forex news RSS | `fxstreet.com/rss/news` |
| Investing.com | Forex RSS | `investing.com/rss/forex.rss` |

## Requirements

- Python 3.10+
- DeepSeek API key ([platform.deepseek.com](https://platform.deepseek.com/))

## Setup

```powershell
cd Finance-News-Tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
# Edit .env and set DEEPSEEK_API_KEY
```

## Usage

```powershell
# Full pipeline: collect → score → summarize
python -m finance_news_tracker run-once

# Or step by step:
python -m finance_news_tracker collect
python -m finance_news_tracker score
python -m finance_news_tracker summarize
```

Output:

- SQLite DB: `data/tracker.db`
- Markdown summary: `summaries/usdjpy_summary_YYYYMMDD_HHMMSS.md`
- Word summary: `summaries/usdjpy_summary_YYYYMMDD_HHMMSS.docx`
  (page 1 = executive content kept to one page, page 2 = source citations)

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | Required for score/summarize |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model name |
| `RECENCY_HOURS` | `72` | Only keep items within this window |
| `MIN_RELEVANCE_SCORE` | `40` | Minimum score for summary inclusion |
| `MAX_ARTICLES_TO_SCORE` | `25` | Cap DeepSeek calls per run |

## Windows Task Scheduler

1. Open **Task Scheduler** → Create Basic Task.
2. Trigger: every **2–4 hours** (or at market open times).
3. Action: Start a program  
   - Program: `C:\...\Finance-News-Tracker\.venv\Scripts\python.exe`  
   - Arguments: `-m finance_news_tracker run-once`  
   - Start in: `C:\...\Finance-News-Tracker`
4. Ensure `.env` is in the project folder.

## Pipeline

```
BOJ / Nikkei / Fed / Treasury / FXStreet / Investing.com RSS + NHK HTML
  → HTML head backfill (date/excerpt the feed omitted, e.g. Nikkei)
  → RSS HTML stripped from descriptions where needed
  → SQLite (dedupe) → keyword prefilter → DeepSeek score
  → executive summary (Markdown + Word)
```

When a feed omits a field (notably Nikkei Asia RSS, which carries no date), the
article page's **public `<head>` metadata** (`article:published_time`, JSON-LD
`datePublished`, `<meta name="date">`, `og:description`) is read to backfill it.
Only head metadata is parsed — the paywalled article body is never fetched. Each
new article is fetched at most once (already-stored items are skipped).

## Disclaimer

Relevance scores are **narrative FX impact assessments**, not statistical correlation with USD/JPY. For correlation analysis, add market data and backtesting in a future version.

## Development

```powershell
pip install -e ".[dev]"
pytest
```
