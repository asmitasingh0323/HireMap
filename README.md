# HireMap

A fault-tolerant distributed pipeline that collects job postings from several sources in parallel, keeps them current, and uses a local language model to turn each posting into a structured summary.

**Live system:** https://hiremap-dashboard.onrender.com
**API:** https://hiremap-ffey.onrender.com

> The free hosting tier sleeps when idle. Before searching, open
> https://hiremap-ffey.onrender.com/api/health and wait for `{"status":"ok"}`
> (30–50 seconds on the first request).

---

## What It Does

Two things make a job search slow: listings that are already closed, and descriptions that take minutes each to read.

HireMap addresses both. A scheduler crawls six sources continuously, so listings stay current; a lifecycle system tracks whether each posting is still open and hides the ones that aren't; and a language-model worker reads each description and extracts the parts that matter — required skills, nice-to-have skills, seniority, whether the role is genuinely remote, and salary even when it isn't stated.

The result is a dashboard of short structured cards instead of a list of long descriptions.

Underneath, it is a distributed-systems project. Job data is the workload; the engineering is coordinating independent processes through a message broker, guaranteeing correctness under concurrency, recovering from failure, and keeping slow work from blocking fast work.

---

## Architecture

```
                    ┌──────────────┐
   Browser ───────▶ │  Flask API   │ ──── publishes tasks ────┐
                    │ + SocketIO   │                          │
                    └──────┬───────┘                          │
                           │ reads                            ▼
                           │                    ┌─────────────────────────┐
                           │                    │        RabbitMQ         │
                           │                    │                         │
   Scheduler ──────────────┼───── publishes ──▶ │  task_queue             │
   (APScheduler)           │                    │    crawls, freshness    │
                           │                    │                         │
                           │                    │  interpret_queue        │
                           │                    │    model work, liveness │
                           │                    └───────┬──────────┬──────┘
                           │                            │          │
                           │                            ▼          ▼
                           │                    ┌───────────┐  ┌───────────┐
                           │                    │  worker   │  │  worker   │
                           │                    │  (crawl)  │  │(--interpret)
                           │                    └─────┬─────┘  └─────┬─────┘
                           │                          │              │
                           │                          │              ▼
                           │                          │        ┌──────────┐
                           │                          │        │  Ollama  │
                           │                          │        │llama3.2:3b
                           │                          │        └──────────┘
                           ▼                          ▼
                    ┌────────────────────────────────────────┐
                    │              PostgreSQL                │
                    │   jobs (fingerprint UNIQUE), searches,  │
                    │   task_status                           │
                    └────────────────────────────────────────┘
```

### Two queues, not one

This is the most important design decision in the system, and it was made after the single-queue version broke.

Interpretation batches take 50–80 seconds; a crawl takes a few. When both ran on one queue, a user's search sat behind model work and returned zero results from some sources. The queues are now split by latency profile:

| Queue | Work | Character |
|---|---|---|
| `task_queue` | crawls, freshness sweeps | fast, interactive |
| `interpret_queue` | model interpretation, link checks | slow, background |

A worker picks its role at startup:

```bash
python worker.py w1              # consumes task_queue
python worker.py ai-1 --interpret   # consumes interpret_queue
```

Searches now complete in seconds regardless of model load.

### How a posting flows through

1. The **scheduler** publishes a crawl task per source on a recurring interval, spaced to respect each source's rate limit.
2. A **worker** takes the task, calls that source's adapter, and normalizes the results.
3. Results are written to **PostgreSQL**. A `UNIQUE` fingerprint plus `ON CONFLICT` makes the insert idempotent — duplicates across sources collapse to one row, and re-seeing a job refreshes `last_seen`.
4. The **interpretation worker** picks up jobs that have a real description and stores the model's structured answer.
5. The **liveness worker** re-checks stored URLs and expires listings the site reports as gone.
6. The **API** serves only `status = 'active'` rows; the **dashboard** renders them as decoded cards.

---

## Data Sources

Six live sources, each behind one adapter:

| Source | Type | Descriptions |
|---|---|---|
| Adzuna | REST API (key required) | teaser only (~500 chars) — excluded from interpretation |
| RemoteOK | JSON feed | yes |
| WeWorkRemotely | HTML/RSS | no |
| Remotive | JSON API | yes |
| Arbeitnow | JSON API | yes |
| Greenhouse | per-company boards | yes (`content=true`) |

Plus `slow_test`, a synthetic adapter used to exercise deadline and fault behaviour on demand.

Indeed and LinkedIn are deliberately excluded for legal and technical reasons.

### Adding a source

Write one file in `adapters/`. Nothing else changes — `__init_subclass__` registers the class and `pkgutil.iter_modules` imports the package at startup, so the adapter is discovered automatically.

```python
from .base import SourceAdapter

class MySource(SourceAdapter):
    name = "mysource"
    requests_per_minute = 20

    def fetch(self, keyword, location, limit):
        # return a list of raw dicts from the source
        ...
```

The base class handles the rest: field normalization, mojibake repair, location cleanup (every spelling of "remote" collapses to one value), salary parsing (`$120,000` and `95k` both become numbers, reversed ranges are swapped), HTML-to-text for descriptions, fingerprinting, keyword matching, and the US-only and English-only filters.

---

## The Interpretation Layer

`interpreter.py` sends a description to a local model and stores structured fields.

The model is **`llama3.2:3b` running through Ollama** — no account, no API key, no per-request cost, and no posting data leaves the machine.

Extracted per job: `required skills`, `preferred skills`, `seniority`, `work arrangement`, `salary_min`, `salary_max`, and `salary_basis` (whether the figure was stated in the posting or estimated).

**The parser assumes the model will misbehave.** `parse_answer()` finds JSON inside prose or code fences, accepts a comma-separated string where a list was requested, clamps any value outside the allowed set to `unknown`, converts hourly rates to yearly at 2,080 hours, and rejects figures outside a believable range. A malformed answer produces empty or unknown fields — it can never break the worker.

Only jobs with at least 800 characters of description are interpreted. Short teasers produced confident nonsense, so they are skipped rather than guessed at.

### Seniority comes from a rule, not the model

The model consistently read titles like *Director of Engineering* and answered `senior`, because those descriptions are full of hands-on engineering work. Two prompt rewrites changed nothing — a 3B model does not follow that instruction reliably.

Seniority is therefore decided in `title_rules.py`, and the model is only consulted when the title names no level. The rule handles the cases that need care: a *Product* Manager manages a product, not people, and is not a lead.

```bash
python title_rules.py   # runs the rule against its test cases
```

This is the general principle the project settled on: **rules where rules are reliable, the model where they are not.**

---

## Measuring Quality

Hand-checking model output was too slow to iterate on, so `score_interpretation.py` scores every interpreted job automatically against independent keyword rules.

```bash
python score_interpretation.py        # score everything interpreted
python score_interpretation.py 100    # score a random 100
```

Current results on 64 interpreted jobs:

| Measure | Result |
|---|---|
| Skill grounding — extracted skills that appear in the description | **92%** (399/432) |
| Jobs producing skills at all | **100%** (64/64) |
| Seniority set correctly by the title rule | **100%** (39/39) |
| Seniority agreement where the model decided | **70%** (7/10) |
| Work arrangement agreement | **91%** (10/11) |

Skill grounding is the number that matters most — it measures whether the model is inventing skills that aren't in the posting. It rose from 75% to 92% over the term.

The scorer reports rule-decided and model-decided jobs **separately**, so the seniority figure still measures the model rather than the title rule agreeing with itself.

`eval_interpretation.py` provides hand-checked sampling when a true accuracy figure is needed; results append to `interpretation_eval.csv`.

---

## Freshness and Lifecycle

Every job carries `first_seen`, `last_seen`, and `status`.

- A crawl that sees a job again refreshes `last_seen`.
- `expire_stale_jobs()` marks anything a source has stopped returning as expired.
- `liveness.py` re-checks stored URLs directly: HEAD, falling back to GET on 403/405/501, spaced by each source's own rate limit.

**Only 404 and 410 expire a listing.** Blocks, redirects and timeouts are recorded as unknown, because a site refusing automated requests must never be mistaken for a closed job. Expired rows are marked, not deleted, so history is preserved.

Every API query filters on `status = 'active'`.

---

## Fault Tolerance

Inherited from Term 1 and extended:

- **Task level** — a worker killed mid-task never acknowledged its message, so RabbitMQ requeues it and another worker completes it. No task lost, no duplicate created.
- **Process level** — `monitor.py` detects missed heartbeats and spawns a replacement worker.
- **Source isolation** — one source failing does not affect the others. Demonstrated with a deliberately failing adapter: it failed every assigned task while five healthy sources completed 80 tasks uninterrupted.
- **Visible failure** — failures are recorded in `task_status` with the error text, so a dead source shows as failed rather than leaving the dashboard waiting forever. Error strings are redacted before storage (an API key once appeared in a logged URL).
- **Self-migrating schema** — `ensure_schema()` runs the base schema plus an ordered list of additive updates at every startup, so local and cloud environments catch themselves up. This exists because columns added locally were silently missing in production.

---

## Tech Stack

| Piece | Technology |
|---|---|
| Workers | Python, Requests, BeautifulSoup4 |
| Broker | RabbitMQ |
| Storage | PostgreSQL |
| Containers | Docker Compose |
| API | Flask + Flask-SocketIO |
| Frontend | React + Vite + Recharts |
| Scheduling | APScheduler |
| Analytics | Pandas |
| Model | Ollama (`llama3.2:3b`) |

---

## Getting Started

### Prerequisites

- Docker Desktop
- Python 3.10+
- Node.js 18+ (for the dashboard)
- [Ollama](https://ollama.com) (for the interpretation layer)

### Setup

```bash
# 1. Clone and enter the project
git clone https://github.com/asmitasingh0323/HireMap.git
cd HireMap/HireMap_Project

# 2. Start PostgreSQL and RabbitMQ
docker compose up -d

# 3. Create a virtual environment and install dependencies
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

# 4. Create the schema (also runs automatically at startup)
python -c "from db_utils import ensure_schema; ensure_schema()"

# 5. Pull the model
ollama pull llama3.2:3b

# 6. Install dashboard dependencies
cd dashboard && npm install && cd ..
```

### `.env`

```ini
# Database
DB_HOST=localhost
DB_PORT=5433
DB_NAME=hiremap_db
DB_USER=hiremap
DB_PASSWORD=hiremap_pass

# Broker
RABBIT_HOST=localhost
RABBIT_PORT=5673
RABBIT_USER=hiremap
RABBIT_PASS=hiremap_pass

# Adzuna (free tier: https://developer.adzuna.com)
ADZUNA_APP_ID=your_app_id
ADZUNA_APP_KEY=your_app_key

# Model
MODEL_BACKEND=ollama
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b
MAX_PROMPT_CHARS=8000

# Filtering
US_ONLY=true
```

In cloud deployment, `DATABASE_URL` and `RABBITMQ_URL` override the individual settings above.

### Running

Each of these goes in its own terminal:

```bash
python worker.py w1                  # crawl worker
python worker.py ai-1 --interpret    # interpretation worker
python scheduler.py                  # continuous crawling
python api.py                        # API on :5000
cd dashboard && npm run dev          # dashboard on :5173
```

Open http://localhost:5173.

### Running one task at a time

The scheduler also works as a one-shot publisher, which is how most development is done:

```bash
python scheduler.py --once           # one crawl of every source
python scheduler.py --once --interpret   # one batch of model work
python scheduler.py --once --liveness    # one round of link checks
python scheduler.py --once --freshness   # one expiry sweep
```

---

## Tuning

All optional, all read from `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `CRAWL_INTERVAL_MINUTES` | 15 | how often each source is crawled |
| `FRESHNESS_INTERVAL_MINUTES` | 60 | how often stale jobs are expired |
| `INTERPRET_INTERVAL_MINUTES` | 10 | how often model batches are published |
| `INTERPRET_BATCH` | 5 | jobs per model batch |
| `LIVENESS_INTERVAL_MINUTES` | 20 | how often URLs are re-checked |
| `LIVENESS_BATCH` | 5 | URLs per check round |
| `MAX_PROMPT_CHARS` | 8000 | how much of a description the model reads |
| `US_ONLY` | true | drop non-US postings at the adapter layer |

The scheduler never crawls faster than a source allows: the gap between tasks is `max(preferred interval, number_of_crawls × 60 / requests_per_minute)`.

---

## Scripts

| Script | Purpose |
|---|---|
| `score_interpretation.py` | automatic quality score across all interpreted jobs |
| `eval_interpretation.py` | hand-checked sampling into `interpretation_eval.csv` |
| `title_rules.py` | the seniority rule, runnable as its own test |
| `backfill_seniority.py` | reapply the title rule to already-interpreted rows |
| `cleanup_non_us.py` | apply current US/English filters to stored rows |
| `market.py` | the Pandas market summary, runnable directly |
| `interpreter.py N` | interpret N stored jobs and print the result |
| `monitor.py` | worker heartbeat monitor |

Most take `--apply` or a limit; run them with no arguments first to preview.

---

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{"status":"ok"}` |
| `POST /api/search` | publishes a search, streams results over SocketIO |
| `GET /api/results` | active jobs with interpreted fields |
| `GET /api/market` | market summary (skills, seniority mix, hiring activity, pay by level, top companies) |

---

## Project Status

**Term 1 (complete)** — distributed worker-queue pipeline, cross-source deduplication, fault recovery at task and process level, deadline enforcement, cloud deployment.

**Term 2 / Phase 2 (complete)** — pluggable adapters, continuous scheduled crawling with per-source rate limits, three new sources, lifecycle tracking and liveness checking, the interpretation layer, decoded job cards, the market summary view, and automatic quality measurement.

**Not yet done** — automated pytest suite, Lever and USAJobs adapters, resume-based matching, and a larger liveness sample.

**Next** — embedding-based semantic search (so "ML engineer" also matches "machine learning specialist"), resume matching against the structured fields, richer dashboard filtering and saved searches, per-company hiring trends, autoscaling workers by queue depth, and proper metrics.

---

## Author

Asmita Singh — Binghamton University
