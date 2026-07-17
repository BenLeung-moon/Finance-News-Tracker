# Finance News Tracker / 财经新闻追踪器

A profile-driven intelligence pipeline that collects public news, filters and
deduplicates it, scores relevance, performs deeper business analysis, and
generates Markdown/Word memos plus a persistent Tracker.

这是一个由 **Profile（追踪主题配置）** 驱动的情报流水线：采集公开新闻、过滤和去重、
相关性评分、商业影响分析，并生成 Markdown/Word 报告及可持续更新的 Tracker。

## Profiles / 追踪主题

| Profile | Focus / 主题 | Default lookback / 默认回看窗口 |
|---|---|---|
| `usdjpy` | USD/JPY news: BOJ, Fed, macro and FX media / 美元日元、央行和宏观新闻 | 72 hours / 72 小时 |
| `jp_storage` | Japan BESS: policy, grid, market rules, competitors and financing / 日本储能政策、电网、市场、竞对和融资 | 336 hours / 14 days / 336 小时、14 天 |

Set `TRACKER_PROFILE` in `.env`. Leave `RECENCY_HOURS` empty to use the
profile default; an integer explicitly overrides it.

在 `.env` 中设置 `TRACKER_PROFILE`。`RECENCY_HOURS` 留空时使用 Profile 默认值；
填写整数则全局覆盖该默认值。

## Pipeline / 处理流程

```text
Profile sources / Profile 数据源
  → collect / 采集
  → date enrichment + deduplication / 日期补全和去重
  → keyword prefilter / 关键词预筛
  → Scoring LLM / 相关性评分模型
  → Analysis LLM / 商业影响分析模型
  → profile-specific memo + Tracker / Profile 专属报告和 Tracker
```

- **Scoring** is the high-throughput filter: relevance, basic category, signal,
  confidence and short summary.
  **Scoring** 用于高吞吐筛选：相关性、基础分类、信号、置信度和简短摘要。
- **Analysis** handles the smaller, high-relevance set: entity, impact and
  suggested action; it also synthesizes the memo.
  **Analysis** 处理高相关性文章：实体、业务影响、建议行动，并汇总生成报告。
- Provider/model lineage is saved with scores, analyses and reports. Tracker
  `Owner` and `Status` are human-managed and are preserved on re-analysis.
  每层 provider/model 都会随评分、分析和报告保存；Tracker 的 `Owner` 与 `Status`
  由人工维护，重复分析不会覆盖。

## Requirements / 环境要求

- Python 3.10+
- An API key for DeepSeek, OpenAI or Anthropic for real LLM calls /
  使用真实 LLM 时需要 DeepSeek、OpenAI 或 Anthropic API key
- Docker is optional for server deployment / Docker 仅为服务器部署可选项

## Setup / 本地安装

```powershell
cd Finance-News-Tracker
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
copy .env.example .env
```

Configure at least `TRACKER_PROFILE` and the API key(s) that the selected
provider(s) need. See `.env.example` for every option.

至少配置 `TRACKER_PROFILE` 和所选 provider 所需的 API key。全部配置项见
`.env.example`。

## Commands / 命令

| Command / 命令 | Purpose / 用途 |
|---|---|
| `collect` | Fetch profile sources only / 仅采集当前 Profile 数据源 |
| `score [--provider ...] [--model ...]` | Score unscored articles / 评分尚未处理的文章 |
| `summarize [role options]` | Analyze scored articles and write a memo / 分析已评分文章并生成报告 |
| `run-once [role options]` | Collect → score → analyze → summarize / 全链路运行 |
| `test-llm [--provider ...] [--all]` | Validate provider wiring / 验证 LLM 配置和连接 |
| `collect-scheduled` | Weekday-guarded collection / 工作日保护的仅采集任务 |
| `run-scheduled` | Scheduled production workflow / 生产定时工作流 |
| `test-email` | Send an SMTP test / 发送 SMTP 测试邮件 |
| `send-latest-email` | Send manifest-backed report / 发送 manifest 指向的最新报告 |

### Common workflows / 常用流程

```powershell
# Use configured Profile and model roles / 使用已配置的 Profile 和模型角色
python -m finance_news_tracker run-once

# Separate fast scoring from stronger analysis / 用快速模型评分、强模型分析
python -m finance_news_tracker run-once `
  --scoring-provider deepseek --scoring-model deepseek-v4-flash `
  --analysis-provider openai --analysis-model gpt-5.4-mini

# Run step by step / 分步执行
python -m finance_news_tracker collect
python -m finance_news_tracker score --provider deepseek
python -m finance_news_tracker summarize `
  --scoring-provider deepseek --scoring-model deepseek-v4-flash `
  --analysis-provider openai --analysis-model gpt-5.4-mini `
  --write-latest-manifest
```

`--provider/--model` remains a backward-compatible shorthand that applies to
both roles if role-specific flags are omitted. `run-once` always writes
`summaries/latest_report.json`; manual `summarize` only writes it with
`--write-latest-manifest`.

若未指定角色专属参数，旧的 `--provider/--model` 会同时应用给 Scoring 和 Analysis。
`run-once` 始终更新 `summaries/latest_report.json`；手动 `summarize` 只有带
`--write-latest-manifest` 才更新它。

### Japan storage example / 日本储能示例

```powershell
$env:TRACKER_PROFILE = "jp_storage"
Remove-Item Env:RECENCY_HOURS -ErrorAction SilentlyContinue
python -m finance_news_tracker collect
```

This uses the 14-day `jp_storage` default. For a one-off 7-day lookback, set
`$env:RECENCY_HOURS = "168"` before the command.

此命令使用 `jp_storage` 的 14 天默认窗口。若要临时改为 7 天，请先设置
`$env:RECENCY_HOURS = "168"`。

## Outputs / 输出

- SQLite database / SQLite 数据库: `data/tracker.db`
- Latest report manifest / 最新报告索引: `summaries/latest_report.json`
- Markdown memo / Markdown 报告: `summaries/<profile>_summary_*.md`
- Word memo / Word 报告: `summaries/<profile>_summary_*.docx`
- Logs / 日志: `logs/`

The manifest prevents email delivery from guessing the newest file by timestamp.
`send-latest-email` uses the manifest unless explicitly given a path.

manifest 防止邮件任务只按文件时间猜测“最新报告”；`send-latest-email` 默认读取
manifest，除非明确指定文件路径。

## Add or modify sources / 添加或修改数据源

Sources belong to a profile's `SOURCES` list. Existing examples are in:

- `src/finance_news_tracker/profiles/usdjpy.py`
- `src/finance_news_tracker/profiles/jp_storage.py`

数据源定义在各 Profile 的 `SOURCES` 列表中。可直接参考上述两个现有文件。

### SourceConfig fields / 关键字段

| Field / 字段 | Use / 用途 |
|---|---|
| `id` | Stable, unique source identifier. Never reuse it for another source / 稳定且唯一的来源 ID；不要复用。 |
| `name` | Display name in reports / 报告展示名称。 |
| `kind` | `rss`, `html`, or a registered custom collector kind / `rss`、`html` 或已注册的自定义 collector。 |
| `url`, `extra_urls` | Feed/list URLs; HTML collector checks all of them / RSS 或列表页；HTML 会逐一检查。 |
| `languages` | Source languages, normally `["en"]` and/or `["ja"]` / 来源语言。 |
| `link_patterns` | Include links containing at least one pattern / 至少命中一个模式的链接才保留。 |
| `exclude_patterns` | Drop matching links; `.pdf` remains excluded unless `allow_pdf=True` / 排除匹配链接；`.pdf` 需设置 `allow_pdf=True` 才可保留。 |
| `allowed_domains` | Extra domains permitted for HTML links / HTML 链接允许跨到的额外域名。 |
| `priority_tier` | Ranking priority; higher is more important / 排序优先级，数值越高越优先。 |
| `is_noisy` | Marks high-volume feeds for per-source caps / 标记高噪声来源以应用单源限额。 |
| `url_year_templated` | Replaces `{year}` with the current year / 将 URL 中 `{year}` 替换为当前年份。 |
| `allow_http_statuses` | Expected non-200 list-page statuses, e.g. `[404]` / 可容忍的非 200 列表页状态码。 |

All dated articles are filtered by the active `RECENCY_HOURS` window. RSS
entries without a date are retained as newly seen; undated HTML links are
dropped to avoid evergreen content.

所有有日期的文章都会根据当前 `RECENCY_HOURS` 过滤。没有日期的 RSS 项目会作为最新发现
保留；没有日期的 HTML 链接会被丢弃，以避免抓到长期存在的页面。

### Add an RSS source / 添加 RSS 数据源

```python
from finance_news_tracker.profiles.base import SourceConfig

SOURCES.append(
    SourceConfig(
        id="example_rss",
        name="Example Energy RSS",
        kind="rss",
        url="https://example.com/news/feed.xml",
        languages=["en"],
        link_patterns=["/news/", "/press/"],
        exclude_patterns=["/events/", "/podcast/"],
        priority_tier=3,
    )
)
```

RSS source links are filtered by `link_patterns` and `exclude_patterns`.
Confirm that the feed exposes publication dates; otherwise it is kept as a
fresh RSS item each collection run.

RSS 链接会受 `link_patterns` 和 `exclude_patterns` 过滤。应确认 feed 提供发布日期；
否则系统会把它当作新 RSS 项目保留。

### Add an HTML source / 添加 HTML 数据源

```python
SOURCES.append(
    SourceConfig(
        id="example_press",
        name="Example Utility Press Releases",
        kind="html",
        url="https://example.com/news/",
        extra_urls=["https://example.com/energy/news/"],
        languages=["ja", "en"],
        link_patterns=["/news/", "/press/"],
        exclude_patterns=["/archive/", "/events/", ".pdf"],
        allowed_domains=["media.example.com"],
        priority_tier=3,
    )
)
```

Start with restrictive `link_patterns`; broad patterns can collect navigation,
category and evergreen pages. Add `allowed_domains` only when article links
genuinely redirect to a related host. Use `url_year_templated=True` only for
URLs that contain `{year}`.

建议先使用严格的 `link_patterns`；过宽会抓到导航、分类和长期页面。仅当文章真实跳转到
关联域名时添加 `allowed_domains`。只有 URL 包含 `{year}` 时才设置
`url_year_templated=True`。

### Add a custom collector / 添加自定义 collector

Use a custom collector when RSS/HTML parsing cannot represent a source, such
as a JSON API, POST-based archive, or authenticated internal feed. The existing
`sumitomo_archive` collector is the reference implementation.

当 RSS/HTML 无法描述来源时，例如 JSON API、POST 归档接口或内部 feed，可新增自定义
collector。现有 `sumitomo_archive` 是参考实现。

1. Add `collect_<kind>(source, settings) -> list[Article]` under
   `src/finance_news_tracker/collectors/`.
2. Import it in `src/finance_news_tracker/collectors/base.py`.
3. Add a `source.kind == "<kind>"` branch beside the existing `rss`, `html`,
   and `sumitomo_archive` dispatch.
4. Use `SourceConfig(kind="<kind>", ...)` in the Profile.
5. Add collector tests, then run `collect` using the target Profile.

自定义 collector 的步骤：在 `collectors/` 新增 `collect_<kind>`；在
`collectors/base.py` 导入并注册分发；最后在 Profile 中用相同的 `kind` 配置来源，
并为该 collector 添加测试。

### Create a new Profile / 新建完整 Profile

1. Create `src/finance_news_tracker/profiles/<profile_id>.py`.
2. Define `SOURCES`, `keyword_tiers`, `ScoringSchema`, scoring prompt, analysis
   prompt/schema, report labels, and `default_recency_hours`.
3. Use the base summary style or mount a custom `SummaryProfile` for sections
   and labels. `jp_storage.py` demonstrates a custom BESS memo layout.
4. Export `PROFILE = TrackerProfile(...)`.
5. Import and register it in `src/finance_news_tracker/profiles/__init__.py`
   in `_PROFILES`.
6. Set `TRACKER_PROFILE=<profile_id>` in `.env`.

新建 Profile 时：创建对应 Python 文件，定义来源、关键词、Scoring/Analysis schema 和
prompt、报告标签、默认窗口；按需使用基础或自定义 `SummaryProfile`；导出
`PROFILE`，然后在 `profiles/__init__.py` 的 `_PROFILES` 注册，最后在 `.env` 选择它。

### Verify a changed source/Profile / 验证新增来源或 Profile

```powershell
# Check collection without LLM cost / 先无 LLM 成本验证采集
$env:TRACKER_PROFILE = "your_profile_id"
python -m finance_news_tracker collect

# Inspect logs and SQLite, then score / 检查日志和 SQLite 后再评分
python -m finance_news_tracker score --dry-run
python -m finance_news_tracker score --provider deepseek
python -m finance_news_tracker summarize --provider deepseek

# Run tests / 运行测试
python -m pytest
```

Check source-specific counts and errors in `logs/`, and inspect stored article
URLs/dates before enabling scheduled execution.

在启用定时任务前，检查 `logs/` 中各来源的数量和错误，并检查 SQLite 内文章 URL 与日期。

## Configuration / 配置

| Variable / 变量 | Default / 默认值 | Description / 说明 |
|---|---|---|
| `TRACKER_PROFILE` | `usdjpy` | Active Profile / 当前 Profile |
| `LLM_PROVIDER` | `deepseek` | Fallback provider for both roles / 两个角色的兜底 provider |
| `SCORING_LLM_PROVIDER`, `SCORING_LLM_MODEL` | empty / 空 | Scoring role override / Scoring 覆盖配置 |
| `ANALYSIS_LLM_PROVIDER`, `ANALYSIS_LLM_MODEL` | empty / 空 | Analysis and memo override / Analysis 和报告覆盖配置 |
| `DEEPSEEK_*`, `OPENAI_*`, `ANTHROPIC_*` | see `.env.example` / 见示例 | Provider credentials, base URLs and models / Provider 凭证、地址和模型 |
| `RECENCY_HOURS` | empty / 空 | Global override; otherwise Profile default / 全局覆盖；否则使用 Profile 默认 |
| `MIN_RELEVANCE_SCORE` | `40` | Minimum score for memo input / 进入报告的最低分数 |
| `MAX_ARTICLES_TO_SCORE` | `25` | Per-run scoring cap / 单次评分上限 |
| `DATA_DIR`, `SUMMARIES_DIR`, `LOG_DIR` | `data`, `summaries`, `logs` | Runtime directories / 运行目录 |
| `EMAIL_ENABLED`, `EMAIL_*` | disabled / 关闭 | SMTP delivery settings / SMTP 发送配置 |

Run `python -m finance_news_tracker test-llm --all` before production. Without
an API key it performs a local dry run; with a key it sends a minimal request.

生产前运行 `python -m finance_news_tracker test-llm --all`。无 API key 时只进行本地
dry run；有 key 时会发送最小请求。

## Scheduling and email / 定时任务与邮件

`collect-scheduled` performs weekday-guarded collection only. `run-scheduled`
uses the production workflow and sends email only when `EMAIL_ENABLED=true`.
See [`deploy/cron.example`](deploy/cron.example) for cron examples.

`collect-scheduled` 仅在工作日采集；`run-scheduled` 执行生产工作流，且仅在
`EMAIL_ENABLED=true` 时发送邮件。cron 示例见 [`deploy/cron.example`](deploy/cron.example)。

For Windows Task Scheduler, point the program to
`C:\...\Finance-News-Tracker\.venv\Scripts\python.exe`, use
`-m finance_news_tracker run-once` as arguments, and use the repository as
the Start in directory.

Windows Task Scheduler 中，程序指向
`C:\...\Finance-News-Tracker\.venv\Scripts\python.exe`，参数为
`-m finance_news_tracker run-once`，Start in 设置为项目根目录。

## Handover checklist / 交接清单

1. Copy `.env.example` to `.env`; select a Profile and configure API keys.
2. Keep `RECENCY_HOURS=` empty unless a global override is intended.
3. Run `test-llm --all`, then `collect`, before enabling full automation.
4. Review `summaries/`, `logs/`, and `data/tracker.db` after every first run
   of a new Profile/source.
5. Run `python -m pytest` before deployment or after collector/Profile changes.
6. Treat source changes as code changes: review dates, URLs, duplicates and
   relevance before scheduled delivery.

1. 从 `.env.example` 创建 `.env`，选择 Profile 并配置 API key。
2. 除非要全局覆盖，否则保持 `RECENCY_HOURS=` 为空。
3. 启用自动化前，运行 `test-llm --all`，再运行 `collect`。
4. 每次新增 Profile/来源首次运行后，检查 `summaries/`、`logs/` 和 `data/tracker.db`。
5. 部署前或修改 collector/Profile 后运行 `python -m pytest`。
6. 数据源修改应视为代码修改：定时发送前确认日期、URL、去重和相关性结果。

## Development / 开发

```powershell
pip install -e ".[dev]"
python -m pytest
```

## Disclaimer / 免责声明

Outputs are automated research aids, not investment, trading, legal, regulatory
or operational advice. Scores and analysis are narrative model judgments, not
statistical predictions or verified facts; review original sources before making
decisions.

本项目输出仅作为自动化研究辅助，不构成投资、交易、法律、监管或运营建议。评分和分析是
模型的叙事性判断，不是统计预测或经核实的事实；作出决策前必须核对原始来源。
