# coderfact-engine

An automated content pipeline: sweep developer platforms for what's actually
getting engagement, propose three scored topics over Telegram, and draft the one
you pick into a Dev.to draft plus a Markdown file in this repo.

```
morning_research.yml   08:00 IST   agent.py research   -> Telegram brief with 3 scored topics
telegram_listener.yml  every 15m   agent.py draft      -> reads your reply, writes the article
educational_drops.yml  19:30 IST   agent.py educational-> short-form hooks/tips/steps drop
tests.yml              on push     test_engine.py      -> offline suite, no keys needed
```

## Commands

```bash
python agent.py doctor                 # probe every source + key, publish nothing
python agent.py research               # score today's topics, send the Telegram brief
python agent.py draft                  # read the Telegram reply, write the article(s)
python agent.py educational <topic>    # short-form drop
python agent.py social <topic>         # per-platform social pack
python agent.py humanize <file.md>     # rerun the rewrite/repair loop on a draft

python humanizer.py <file.md> [--fix] [--json]   # audit prose, no AI calls
python research_engine.py doctor|scan|search <q> # sources + offline library
python test_engine.py                            # offline test suite
```

Start with `doctor`. It reports which API keys are set, whether voice
calibration is active, and which signal sources are actually returning data —
without calling an AI provider or publishing anything.

## Layout

| File | Role |
|---|---|
| `agent.py` | Orchestration, prompts, Telegram, Dev.to and GitHub publishing |
| `research_engine.py` | Parallel source sweep, clustering, ranking, research library |
| `humanizer.py` | AI-tell detection, scoring, repair loop, voice fingerprint (stdlib only) |
| `test_engine.py` | Offline suite — no network, no keys |
| `state.json` | Today's topics, title history, Telegram cursor |
| `research/library.jsonl` | Append-only archive of every research run |
| `voice/` | Your own writing samples for voice calibration (gitignored) |

## How the writing pipeline works

`draft_single()` runs five model passes: complexity classification, keyword
research, outline, article, then visual planning. Between the article and the
visuals sits the humanizer:

```
draft ──► rewrite for voice ──► scan (regex + structural, fence-aware)
                                  │
                                  ├─ score >= 85 ──────────────► ship
                                  └─ below ──► repair with the actual
                                               findings ──► re-scan
                                               (keep only if the score improved,
                                                max 2 rounds)
                                  │
                                  └──► deterministic autofix ──► final score
```

The score is density-based (weighted tells per 1000 prose words) so long
articles aren't punished for length, and it is reported to Telegram whenever a
draft lands in `needs-work` or `reject`.

Detection covers the 33 patterns from Wikipedia's "Signs of AI writing" —
inflated significance, copula avoidance, negative parallelism, false ranges,
title-case headings, staccato drama, aphorism formulas, and so on — plus
template phrases that earlier versions of this repo's own prompts taught the
model to repeat.

**Everything is fence-aware.** Code blocks, mermaid, pipe tables, image URLs,
the `json?chameleon` widget and the `TAGS:`/`META:` lines are masked out before
any regex runs, so a rewrite can never mangle working code. `test_engine.py`
asserts this byte-for-byte.

Calibration against this repo's own corpus: untreated drafts in `medium_drafts/`
score 3–33; hand-written technical prose scores in the mid-50s. Treat the score
as a relative signal, not an AI-detector verdict.

### Voice calibration

Put your own writing in `voice/*.md` and the rewrite prompt gets measured facts
about your style — sentence-length distribution, contraction density, which
punctuation habit is actually yours — instead of an adjective like "casual dev
voice". See [voice/README.md](voice/README.md).

## How topic selection works

`research_engine.py` sweeps every source in parallel with per-source timeouts,
then ranks in Python rather than asking the model to eyeball a flat list:

1. **Within-source normalisation** — 400 HN points, 2k Reddit upvotes and 90
   Dev.to reactions aren't comparable, so each item becomes a percentile rank
   inside its own source.
2. **Clustering** — greedy title-token Jaccard, so the same story on HN,
   Reddit and TechCrunch becomes one cluster.
3. **Composite score** — `0.34·engagement + 0.30·breadth + 0.16·volume +
   0.20·recency`, plus a bonus for clusters containing a citable indie-builder
   post. Breadth counts distinct *platforms*, so an HN story echoed by
   `hnrss.org` doesn't fake cross-source corroboration.
4. **Health reporting** — every source reports ok/empty/failed with a reason. A
   broken scraper looks like a broken scraper, not like a quiet news day.

Each run appends to `research/library.jsonl`, and proposed titles are checked
for novelty against that whole archive:

```bash
python research_engine.py search "ai agents"
```

## Configuration

Secrets (GitHub → Settings → Secrets):
`OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `DEVTO_API_KEY`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

Variables (GitHub → Settings → Variables):
`AUTHOR_NAME`, `AUTHOR_CONTEXT`, `AUTHOR_VIBE`.

Tuning (all optional):

| Variable | Default | Effect |
|---|---|---|
| `HUMANIZE_ROUNDS` | `2` | Max repair rounds per article |
| `HUMANIZE_TARGET` | `85` | Score at which repair stops early |
| `VOICE_SAMPLES_DIR` | `voice` | Where voice samples live |
| `SOURCE_TIMEOUT` | `45` | Per-source seconds before a source is degraded |
| `REDDIT_BUDGET` | `40` | Total seconds for the Reddit leg |
| `SHOW_HN_WINDOW_DAYS` | `30` | Recency window for Show HN launches |
| `RESEARCH_LIBRARY_DIR` | `research` | Where the archive is written |

AI providers are tried in order — OpenRouter Llama 3.3 70B, Gemini 2.0 Flash,
DeepSeek R1, Groq, Gemma, OpenRouter auto — and any one of them is enough.

## Telegram replies

| Reply | Effect |
|---|---|
| `1` / `2` / `3` | Draft that topic |
| `1 2`, `1 2 3` | Draft several |
| `0` | Skip today |
| free text (10+ chars) | Draft your own topic |
| `edu: <topic>` | Educational drop instead |
| `social: <topic>` | Social pack instead |

## Notes

- Reddit blocks unauthenticated `.json` with a 403 from most hosts. The engine
  tries JSON once, then uses the RSS path for the rest of the run. RSS carries
  no score, so those items rank on recency and corroboration only.
- Reddit requests are serialised behind a lock and paced; parallel subreddit
  fetches get rate-limited.
- `pytrends` is optional. Without it, Google Trends reports as degraded and the
  sweep continues.
