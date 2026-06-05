# Finance News Tracker

USD/JPY news tracker that collects fresh items from **Japan** (BOJ, Nikkei Asia, NHK), **US official** (Federal Reserve, US Treasury), and **international FX media** (FXStreet, Investing.com), scores USD/JPY relevance with **DeepSeek API**, and writes an **executive summary** to `summaries/`.

中文注解：核心 pipeline 负责生成报告；邮件发送和 Docker/cron 部署是独立适配层，便于后续功能分支演进。

## Command Overview

| Command | Purpose |
|---------|---------|
| `run-once` | Collect → score → summarize (generation only, no email) |
| `test-email` | Send a test SMTP message to all `EMAIL_TO` recipients |
| `send-latest-email` | Send the manifest-backed latest report |
| `run-scheduled` | Production workflow: weekday guard, lock, generate, optional email |

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
- Docker (optional, for server deployment)

## Local Setup

```powershell
cd Finance-News-Tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
# Edit .env and set DEEPSEEK_API_KEY
```

## Local Usage

```powershell
# Full pipeline: collect → score → summarize (no email)
python -m finance_news_tracker run-once

# Step by step:
python -m finance_news_tracker collect
python -m finance_news_tracker score
python -m finance_news_tracker summarize
```

Output:

- SQLite DB: `data/tracker.db`
- Latest manifest: `summaries/latest_report.json`
- Markdown summary: `summaries/usdjpy_summary_YYYYMMDD_HHMMSS.md`
- Word summary: `summaries/usdjpy_summary_YYYYMMDD_HHMMSS.docx`

## Email Setup

1. Copy `.env.example` to `.env` and configure SMTP:

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your.name@nexaracapital.com
SMTP_PASSWORD=your_app_password_here
SMTP_USE_TLS=true
EMAIL_FROM=your.name@nexaracapital.com
EMAIL_TO=your.name@nexaracapital.com,recipient2@nexaracapital.com
EMAIL_SUBJECT_PREFIX=[TEST] Finance News Tracker
EMAIL_ATTACH_DOCX=true
```

2. Test SMTP before enabling cron:

```powershell
python -m finance_news_tracker test-email
```

3. After a successful `run-once`, send the latest report:

```powershell
python -m finance_news_tracker send-latest-email
```

`send-latest-email` reads `summaries/latest_report.json` (written by `run-once`) so it does not accidentally email an older file when generation fails.

## Server Deployment (Docker + cron)

Recommended server layout:

```
/opt/finance-news-tracker/
  ├── data/
  ├── summaries/
  ├── logs/
  ├── .env
  ├── docker-compose.yml
  └── deploy/
```

Build and run:

```bash
cd /opt/finance-news-tracker
docker compose build
docker compose run --rm tracker python -m finance_news_tracker test-email
docker compose run --rm tracker python -m finance_news_tracker run-scheduled
```

Cron example (Hong Kong time, Monday–Friday 10:00):

```cron
CRON_TZ=Asia/Hong_Kong
0 10 * * 1-5 cd /opt/finance-news-tracker && flock -n /tmp/finance-news-tracker.lock docker compose run --rm tracker python -m finance_news_tracker run-scheduled >> logs/cron.log 2>&1
```

See [`deploy/cron.example`](deploy/cron.example) for more examples.

中文注解：
- `CRON_TZ=Asia/Hong_Kong` 保证 cron 按香港时间触发；程序内 `RUN_WEEKDAYS_ONLY` 再做一层工作日判断。
- `flock` 防止上一次任务未完成时重复启动。
- v1 只跳过周六日，不跳过公众假期（`HOLIDAY_GUARD_ENABLED=false`）。

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | Required for score/summarize |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model name |
| `DATA_DIR` | `data` | SQLite and lock files |
| `SUMMARIES_DIR` | `summaries` | Report output directory |
| `LOG_DIR` | `logs` | Daily log files |
| `RECENCY_HOURS` | `72` | Only keep items within this window |
| `MIN_RELEVANCE_SCORE` | `40` | Minimum score for summary inclusion |
| `MAX_ARTICLES_TO_SCORE` | `25` | Cap DeepSeek calls per run |
| `RUN_TIMEZONE` | `Asia/Hong_Kong` | Timezone for scheduling guard |
| `RUN_WEEKDAYS_ONLY` | `true` | Skip Saturday/Sunday in `run-scheduled` |
| `HOLIDAY_GUARD_ENABLED` | `false` | Future holiday calendar support |
| `REPORT_RETENTION_DAYS` | `90` | Delete old report files after N days |
| `EMAIL_ENABLED` | `false` | Send email in `run-scheduled` |
| `EMAIL_TO` | — | Comma-separated recipient list |

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
  → executive summary (Markdown + Word + latest_report.json)
```

Optional delivery layer (separate commands):

```
run-once → latest_report.json
send-latest-email / run-scheduled → SMTP email with Markdown body + .docx attachment
```

## Run History

Scheduled runs are recorded in SQLite table `run_history` (`data/tracker.db`), including status, report paths, email recipients, and error messages.

## Disclaimer

Relevance scores are **narrative FX impact assessments**, not statistical correlation with USD/JPY. For correlation analysis, add market data and backtesting in a future version.

## Development

```powershell
pip install -e ".[dev]"
pytest
```
