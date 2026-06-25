# Finance News Tracker

Multi-profile news tracker that collects fresh items from configurable sources, scores relevance with LLM providers (**DeepSeek**, **OpenAI**, or **Anthropic**), and writes an **executive summary** to `summaries/`.

**Profiles:**
- `usdjpy` (default) — USD/JPY finance news (BOJ, Nikkei Asia, NHK, Fed, US Treasury, FX media)
- `jp_storage` — Japan energy storage ecosystem (ANRE, METI, OCCTO, trading companies, utilities, battery OEMs)

Set `TRACKER_PROFILE=usdjpy` or `TRACKER_PROFILE=jp_storage` in `.env`.

中文注解：核心 pipeline 负责生成报告；邮件发送和 Docker/cron 部署是独立适配层，便于后续功能分支演进。

## Command Overview

| Command | Purpose |
|---------|---------|
| `collect` | Fetch news from all sources |
| `score --provider deepseek\|openai\|anthropic [--model MODEL]` | Score missing articles for one provider/model |
| `summarize --provider deepseek\|openai\|anthropic [--model MODEL]` | Generate a summary for a specific provider/model |
| `run-once [--provider ...] [--model MODEL]` | Collect → score → summarize (generation only, no email) |
| `test-llm` | Validate LLM adapter/config wiring; calls the API only when a key is set |
| `test-email` | Send a test SMTP message to all `EMAIL_TO` recipients |
| `send-latest-email` | Send the manifest-backed latest report |
| `collect-scheduled` | Weekday guarded collection only, no LLM cost |
| `run-scheduled` | Production workflow: weekday guard, lock, generate, optional email |

## Sources

Sources are defined per profile in `src/finance_news_tracker/profiles/`.

| Profile | Sources |
|---------|---------|
| `usdjpy` | BOJ, Nikkei Asia, NHK WORLD, Federal Reserve, US Treasury, FXStreet, Investing.com |
| `jp_storage` | ANRE, METI, OCCTO, major trading companies, power utilities, storage/battery manufacturers (EN/JA only) |

## Requirements

- Python 3.10+
- LLM API key for real scoring/summarizing ([DeepSeek](https://platform.deepseek.com/), OpenAI, or Anthropic)
- Docker (optional, for server deployment)

## Local Setup

```powershell
cd Finance-News-Tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
# Edit .env and set LLM_PROVIDER plus the matching API key for real LLM calls
```

## Local Usage

```powershell
# Full pipeline: collect → score → summarize (no email)
python -m finance_news_tracker run-once

# Override provider/model for the full pipeline:
python -m finance_news_tracker run-once --provider deepseek --model deepseek-v4-flash

# Step by step (writes latest_report.json when using --write-latest-manifest):
python -m finance_news_tracker collect
python -m finance_news_tracker score --provider deepseek
python -m finance_news_tracker summarize --provider deepseek --write-latest-manifest
```

中文注解：`run-once` 始终会写 `summaries/latest_report.json`。分步 `summarize --provider ...` 默认不写 manifest，避免覆盖生产指针；需要 `send-latest-email` 时请显式加 `--write-latest-manifest`。

Development-only model benchmark (not part of the production CLI):

```powershell
python scripts/benchmark_models.py --dry-run
python scripts/benchmark_models.py
```

中文注解：`scripts/benchmark_models.py` 会在同一 frozen article set 上依次对比 DeepSeek、OpenAI、Anthropic；`--dry-run` 只统计计划调用量，不访问 LLM API。

Output:

- SQLite DB: `data/tracker.db`
- Latest manifest: `summaries/latest_report.json`
- Markdown summary: `summaries/<profile>_summary_YYYYMMDD_HHMMSS_provider_model.md`
- Word summary: `summaries/<profile>_summary_YYYYMMDD_HHMMSS_provider_model.docx`

Provider-specific summaries generated via `summarize --provider ...` do not overwrite `summaries/latest_report.json` unless `--write-latest-manifest` is set. `run-once` and `run-scheduled` always write the production manifest. `send-latest-email` continues to use the manifest only.

## LLM Connectivity Self-Test

Run a local adapter/config check before adding API keys:

```powershell
python -m finance_news_tracker test-llm --provider deepseek
python -m finance_news_tracker test-llm --provider openai
python -m finance_news_tracker test-llm --provider anthropic
python -m finance_news_tracker test-llm --all
```

Without an API key, the command returns `status: dry_run`, `missing_api_key: true`, and `network_call: false`. 中文注解：无 key 时只验证 provider 配置、adapter 选择和请求 payload 构造，不代表外部服务真实可达。

After setting the matching API key, the same command sends a minimal JSON request and reports status, latency, provider, model, and parsed response.

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
docker compose run --rm tracker python -m finance_news_tracker collect-scheduled
```

Low-cost cron example (Hong Kong time, Monday–Friday 10:00):

```cron
CRON_TZ=Asia/Hong_Kong
0 10 * * 1-5 cd /opt/finance-news-tracker && flock -n /tmp/finance-news-tracker.lock docker compose run --rm tracker python -m finance_news_tracker collect-scheduled >> logs/cron.log 2>&1
```

See [`deploy/cron.example`](deploy/cron.example) for more examples.

中文注解：
- `CRON_TZ=Asia/Hong_Kong` 保证 cron 按香港时间触发；程序内 `RUN_WEEKDAYS_ONLY` 再做一层工作日判断。
- `flock` 防止上一次任务未完成时重复启动。
- v1 只跳过周六日，不跳过公众假期（`HOLIDAY_GUARD_ENABLED=false`）。

## Configuration (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `deepseek` | Active/default provider when no CLI provider is passed |
| `DEEPSEEK_API_KEY` | — | Required for real DeepSeek calls |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com/v1` | DeepSeek OpenAI-compatible base URL |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | DeepSeek model name |
| `OPENAI_API_KEY` | — | Required for real OpenAI calls |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `OPENAI_MODEL` | `gpt-5.4-mini` | OpenAI model name |
| `ANTHROPIC_API_KEY` | — | Required for real Anthropic calls |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com/v1` | Anthropic base URL |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Anthropic model name |
| `DATA_DIR` | `data` | SQLite and lock files |
| `SUMMARIES_DIR` | `summaries` | Report output directory |
| `LOG_DIR` | `logs` | Daily log files |
| `RECENCY_HOURS` | `72` | Only keep items within this window |
| `MIN_RELEVANCE_SCORE` | `40` | Minimum score for summary inclusion |
| `MAX_ARTICLES_TO_SCORE` | `25` | Cap scoring calls per provider per run |
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
  → SQLite (dedupe) → keyword prefilter → provider/model score
  → executive summary (Markdown + Word + production latest_report.json when enabled)
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
