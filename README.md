# logsift

**Async log analyzer with AI-powered insights and semantic grouping.**

`logsift` reads log files (local or remote), clusters similar lines using vector similarity, and streams an AI-generated diagnosis of what went wrong — all in a live Rich terminal display.

## What's New in v1.5.0

### 1. Webhook alerting (`--alert-threshold N --webhook URL`)

POST a JSON payload to a URL whenever the error+critical line count exceeds a threshold. Ideal for CI pipelines and on-call incident detection.

```bash
# Fire a Slack/PagerDuty webhook when > 10 errors
logsift app.log --alert-threshold 10 --webhook https://hooks.slack.com/...
```

The payload includes source name, timestamp, error/warning counts, total line count, and the top error patterns.

### 2. Log sampling (`--sample N`)

Randomly sample N lines before analysis — lets you quickly get a representative diagnosis of massive log files without waiting for full parsing and vectorization.

```bash
# Quickly analyze 1000 lines from a 10M-line log
logsift huge.log --sample 1000
```

### 3. Deduplication (`--dedup`)

Merge consecutive near-identical lines (numbers are normalized for comparison) into a single line with a `[Nx]` count prefix. Eliminates repetitive syslog spam and retry bursts before grouping and AI analysis.

```bash
# Clean up repetitive syslog spam before grouping
logsift syslog --dedup
```

---

## What's New in v1.4.0

### 1. Time range filtering (`--since` / `--until`)

Slice logs to an exact time window — invaluable during incident retrospectives when you only care about the blast radius hour.

```bash
# Only analyze the 08:00–09:00 window
logsift app.log --since "2024-01-15 08:00" --until "2024-01-15 09:00"

# Everything after a known event
logsift app.log --since "2024-01-15 08:30"

# Combine with --level and --grep for surgical analysis
logsift app.log --since "2024-01-15 08:00" --level error --grep 'postgres'
```

Lines without parseable timestamps are always included. ISO 8601 (`2024-01-15T08:00`) and Apache Combined Log Format timestamps are both understood.

### 2. Live colorized tail (`--follow`)

`logsift --follow` streams new log lines in real-time as they are appended to a file — like `tail -f` but with Rich level-colored output. Level filters (`--level`) and grep patterns (`--grep`) apply live to the stream.

```bash
# Watch errors arrive in real-time
logsift app.log --follow --level error

# Tail and filter for auth-related lines
logsift app.log --follow --grep 'auth'
```

```
logsift --follow  app.log  (Ctrl-C to stop)
──────────────────────────────────────────
2024-01-15 08:02  INFO      Listening on :8080
2024-01-15 08:03  ERROR     FAILED to connect to postgres://db:5432
2024-01-15 08:03  WARNING   Retry 1/5 for worker-42
```

### 3. Structured timing observability (`--verbose`)

`--verbose` prints wall-clock timing for each analysis stage — useful for benchmarking large log files and understanding where time is spent.

```bash
logsift app.log --verbose
```

```
  load   0.012s — 1 source(s)
  parse  0.003s — 847 lines
  group  0.089s — 18 groups (threshold=0.45)
  ai     1.243s
```

---

## What's New in v1.3.0

### 1. Regex grep filter (`--grep PATTERN`)

Pre-filter log lines before grouping and AI analysis. Repeat the flag to require multiple patterns simultaneously (AND logic).

```bash
# Only analyze database-related errors
logsift app.log --grep 'database'

# Lines that mention both "timeout" AND "auth"
logsift app.log --grep 'timeout' --grep 'auth'

# Combine with --level for surgical targeting
logsift app.log --grep 'FAILED' --level error
```

The filter runs before vectorization, so the AI analysis and group table reflect exactly the lines you care about.

### 2. Output to file (`--output FILE` / `-o FILE`)

Write JSON, CSV, or Markdown output directly to a file instead of stdout — no shell redirections needed.

```bash
# Save JSON report
logsift app.log --format json -o report.json

# Save Markdown for GitHub Issues
logsift app.log --format markdown -o incident-report.md

# Save CSV for pandas
logsift app.log --format csv -o groups.csv
```

A confirmation line is printed to the terminal when the file is written.

### 3. Event timeline histogram (`--timeline`)

Show a time-bucketed bar chart of log volume alongside the main summary table. Each bucket is colored by severity: red if errors dominate, yellow for warnings, green for clean periods. Instantly reveals burst patterns and quiet windows.

```bash
logsift app.log --timeline
```

```
╭──────────────────────────── Event Timeline ─────────────────────────────────╮
│ Time Bucket          │ Count │ Distribution                │ Levels          │
│ 2024-01-15 08:00     │    42 │ ████████████████████████    │ E:28  W:6  I:8  │
│ 2024-01-15 09:00     │    12 │ ███████                     │ W:4   I:8       │
│ 2024-01-15 10:00     │   187 │ ██████████████████████████  │ I:187           │
╰─────────────────────────────────────────────────────────────────────────────╯
```

Only displayed when logs contain parseable timestamps (ISO 8601 or Apache Combined Log Format).

---

## What's New in v1.2.0

### `--watch` mode — continuous re-analysis
Tail any log file in watch mode: logsift re-analyzes it every N seconds in-place, giving you a live updating view of an evolving log.

```bash
# Re-analyze app.log every 10 seconds
logsift app.log --watch 10
```

### Markdown export (`--format markdown`)
Generate a shareable Markdown report — perfect for pasting into GitHub Issues, Confluence, or Slack code blocks. Includes level-breakdown table, top pattern table, and AI diagnosis.

```bash
logsift app.log --format markdown > report.md
logsift app.log --format markdown --no-ai >> INCIDENT.md
```

### CSV export (`--format csv`)
Dump every group as a CSV row: source, count, level, sample, first timestamp. Pipe it to `csvkit`, open it in a spreadsheet, or load it into pandas.

```bash
logsift app.log --format csv > groups.csv
logsift *.log --format csv | grep ERROR | sort -t, -k2 -rn
```

### Config file (`~/.logsift.toml`)
Persist your preferred defaults so you don't need to repeat flags on every run.

```toml
# ~/.logsift.toml
[defaults]
threshold = 0.5
format    = "table"
no_ai     = false
top       = 30
timeout   = 60.0
watch     = 15      # enable watch mode by default
```

## Install

```bash
pip install logsift
# or from source:
git clone https://github.com/iamgeetarted/logsift
cd logsift && pip install -e .
```

## Usage

```bash
# Analyze a local log file
logsift app.log

# Analyze multiple files
logsift *.log

# Fetch and analyze a remote log (async HTTP)
logsift --url https://ci.example.com/build/42/output.log

# Pipe from stdin
cat /var/log/nginx/error.log | logsift

# Filter to errors and above only
logsift app.log --level error

# Tighter grouping (fewer, more-similar groups)
logsift app.log --threshold 0.6

# Skip AI analysis (no ANTHROPIC_API_KEY needed)
logsift app.log --no-ai

# Structured JSON output (for piping to jq, etc.)
logsift app.log --format json | jq '.[] | select(.count > 5)'

# Markdown report
logsift app.log --format markdown > report.md

# CSV export
logsift app.log --format csv > groups.csv

# Watch mode (re-analyze every 30 seconds)
logsift app.log --watch 30
```

## Features

### Semantic log grouping
Lines are vectorized using TF-IDF bag-of-words and clustered by cosine similarity with `numpy`. Similar error messages (same error, different hostnames/ports/timestamps) land in the same group. Adjust sensitivity with `--threshold`.

### Full async architecture
`asyncio.TaskGroup` fetches multiple log sources concurrently — local files via thread pool, remote URLs via `httpx.AsyncClient`. Multiple `--url` flags resolve in parallel with proper timeout and cancellation.

### Live Rich terminal UI
A `Rich` table shows groups ranked by frequency with level-colored status indicators. Stats panel shows level distribution at a glance.

### AI-powered diagnosis (streaming)
Set `ANTHROPIC_API_KEY` and `logsift` streams a concise technical analysis: what's happening, likely root cause, and recommended action — using `claude-haiku-4-5-20251001` for fast, cheap responses.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
logsift app.log
```

### Watch mode
Re-analyze a file every N seconds. The display clears and refreshes in place — useful for monitoring a growing log during an incident.

### Multi-format export
| Flag | Output |
|------|--------|
| `--format table` | Rich terminal table (default) |
| `--format json` | JSON array for `jq` / scripting |
| `--format csv` | CSV rows for spreadsheets / pandas |
| `--format markdown` | Markdown report for GitHub Issues / Confluence |

### Config file
Drop a `~/.logsift.toml` to set persistent defaults — no more repeating the same flags.

## Sample Output

```
  Total lines: 847   ERROR: 34  WARNING: 12  INFO: 801  Groups: 18

╭──────────────────────────────────────────── app.log ────────────────────────────────────────────╮
│ Count │  Level  │ Pattern / Sample                                          │ First Seen         │
├───────┼─────────┼───────────────────────────────────────────────────────────┼────────────────────┤
│   28  │  ERROR  │ FAILED to connect to postgres://db:5432 — conn refused    │ 2024-01-15 08:02   │
│    6  │ WARNING │ WARN retry 3/5 for job worker-42 backoff 30s              │ 2024-01-15 08:04   │
│    4  │  ERROR  │ ERROR OOM killer invoked on pid 1847 rss=2.1GB            │ 2024-01-15 08:06   │
╰───────────────────────────────────────────────────────────────────────────────────────────────────╯

╭─ AI Analysis ──────────────────────────────────────────────────────────────────────────────────╮
The primary issue is a database connectivity failure — 28 repeated "connection refused" errors    │
to postgres on port 5432 suggest the database service crashed or was never started. The OOM      │
events indicate the application or database ran out of memory, likely triggering the crash.      │
Immediate actions: restart the postgres service, increase container memory limits, and check    │
for runaway queries with pg_stat_activity.                                                      │
╰────────────────────────────────────────────────────────────────────────────────────────────────╯

  ↻ watch mode — refreshing in 10s (Ctrl-C to stop)
```

## Options

```
  FILE                  Log files to analyze
  --url URL             Fetch log from URL (repeatable, concurrent)
  --no-ai               Skip AI analysis
  --level LEVEL         Filter: debug | info | warning | error | critical
  --threshold FLOAT     Grouping similarity 0–1 (default: 0.45)
  --top N               Show top N groups (default: 20)
  --format              table | json | csv | markdown (default: table)
  --timeout SECONDS     HTTP fetch timeout (default: 30s)
  --watch SECS          Re-analyze every SECS seconds (watch mode)
```

## Architecture

```
logsift/
├── cli.py        # argparse entry point, asyncio.run() orchestration, watch loop
├── config.py     # ~/.logsift.toml config loader
├── fetcher.py    # async file + HTTP loading with asyncio.TaskGroup
├── parser.py     # log line parsing: level detection, timestamp, tokenization
├── grouper.py    # TF-IDF vectors + cosine similarity clustering (numpy)
├── analyzer.py   # Anthropic streaming API integration
├── exporter.py   # Markdown + CSV serializers
└── display.py    # Rich tables, panels, progress bars
```

## Requirements

- Python 3.11+
- `rich` — terminal UI
- `httpx` — async HTTP for remote log fetching
- `numpy` — vector math for semantic grouping
- `anthropic` — AI analysis (optional, needs `ANTHROPIC_API_KEY`)

## License

MIT
