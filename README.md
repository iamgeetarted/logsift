# logsift

**Async log analyzer with AI-powered insights and semantic grouping.**

`logsift` reads log files (local or remote), clusters similar lines using vector similarity, and streams an AI-generated diagnosis of what went wrong — all in a live Rich terminal display.

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
