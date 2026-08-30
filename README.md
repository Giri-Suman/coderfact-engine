# coderfact-engine

An automated content pipeline: sweep developer platforms for what's actually
getting engagement, propose three scored topics over Telegram, and draft the one
you pick into a Dev.to draft plus a Markdown file in this repo.

The pipeline is written down in [PIPELINE.md](PIPELINE.md) — every stage, both
human checkpoints, and the rules that were added after something went wrong.

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
python agent.py judge <file.md>        # editorial review; --fix applies findings
python agent.py claims <file.md>       # map every claim to its receipt
python agent.py brain init|list|check  # the author's own sourced material
python agent.py promo <file.md> [url]  # LinkedIn + X posts from a finished article

python humanizer.py <file.md> [--fix] [--json]   # audit prose, no AI calls
python judge.py --dry <file.md>                  # grounded facts only, no AI calls
python claims.py [--write] <file.md>             # claims map, no AI calls
python brain.py list|check <topic>               # what a draft would be given
python promo.py <file.md> --facts                # what the promo writer sees
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
| `judge.py` | Editorial rubric, fabrication detection, critique → revise loop |
| `claims.py` | Every factual claim mapped to its receipt (no AI calls) |
| `brain.py` | The author's beliefs, sourced stories and voice rules |
| `PIPELINE.md` | The contract — every stage and rule in plain English |
| `promo.py` | LinkedIn + X posts generated from a finished article |
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

### Editorial review

The humanizer catches mechanical tells. It cannot tell you the hook is generic
or that a revenue figure was invented, so `judge.py` runs a second loop:

```
article ──► measure facts in Python ──► rubric review (8 weighted dimensions)
                    │                              │
                    │                              ├─ ship ──────────► publish
                    └─ blocking issues ────────►   └─ revise with the actual
                       (fabricated figures,           findings ──► re-judge
                        unverified URLs,              (keep only if the score
                        vague attribution,             improved, max 2 rounds)
                        zero code blocks)
```

An LLM asked to review its own output mostly produces praise, so two guards
apply. Everything measurable — word count, keyword placement, code blocks,
citation URLs, money figures — is computed in Python first and handed to the
reviewer as ground truth it may not contradict. And **fabrication is detected
deterministically**: a money or audience figure with no cited source, or a URL
that was never in the research evidence, forces a `reject` regardless of what
the model thinks of the prose. Technical metrics the author measured themselves
(timings, LOC, memory) are explicitly allowed.

```bash
python judge.py --dry medium_drafts/*.md   # grounded facts, no API key needed
```

### Promotion

`promo.py` writes the LinkedIn post and X thread **from the finished article**,
not from the topic — so the posts quote the real error string and the real
before/after number instead of inventing a second, worse article. Platform
limits are enforced in Python rather than requested in the prompt: 280 chars per
X post (the model is asked to cut, truncation at a word boundary is the
fallback), and the LinkedIn hook is checked against the ~210-char fold, which is
the only line most people read. Both drafts go through the humanizer first.

### Why a draft can come back at 70 words

Gemini 3.x Flash has thinking **on by default**, and thinking shares the
`maxOutputTokens` budget with the visible answer. A 900-word article requested
with a 2,760-token budget came back as 70 words and `finishReason=MAX_TOKENS` —
reasoning had spent the budget before the prose started.

That truncated stub then flowed into the humanizer, which replied *about* the
draft ("the content cuts off mid-sentence, send the full text and I will rewrite
it"), and because that reply was plausible prose of a reasonable length, every
length check passed and the commentary was saved as the article.

Four guards now, at each level it could have been caught:

1. `GEMINI_TOKEN_HEADROOM` (3x) and `GEMINI_THINKING=low` give reasoning room.
   The thinking field is dropped and retried automatically if the API rejects it.
2. A `MAX_TOKENS` / `SAFETY` / `RECITATION` finish reason raises, so the chain
   falls through to the next provider instead of returning a fragment. The error
   reports the token split so you can see thinking-vs-output.
3. `looks_like_meta_response()` rejects a reply that discusses the draft rather
   than being it — in `rewrite_pass`, `repair_pass` and `judge.revise`.
4. An article under `ARTICLE_MIN_RATIO` of its target, or ending mid-sentence,
   fails the draft instead of continuing down the pipeline.

### Claims map

Borrowed from learnwithhasan.com's "AI Content Factory": no claim ships without
a receipt. Where `judge.py` scans for known-bad patterns, `claims.py` inverts
the default — it enumerates **every** checkable figure and demands a provenance
label for each:

| Label | Meaning |
|---|---|
| `BRAIN` | the figure appears in `brain/stories.md` — you measured it |
| `EVIDENCE` | traces to a research URL the writer was handed |
| `SELF` | first-person process detail you're the authority on |
| `UNSOURCED` | **the finding** |

Money and audience numbers can never be `SELF` — you are not the authority on
someone else's revenue. Versions, ports and years are excluded as identifiers,
not claims. Code blocks are excluded; **tables are not** — a before/after table
is the most claim-dense element in these articles, so each figure is extracted
with its row label.

The map ships beside the draft as `<slug>.claims.md`, and `verify()` re-checks a
published piece against it, so an edit that introduces a new figure is caught.

```bash
python claims.py medium_drafts/*.md   # coverage per draft, no API key needed
```

### The brain

The claims map proves what was used; the brain supplies what to use. Three
hand-written files loaded into the draft prompt, ranked by relevance to the
topic:

- `brain/beliefs.md` — positions worth arguing, so a piece has a spine
- `brain/stories.md` — things that happened, **with numbers and a source**
- `brain/voice.md` — prose rules a measurement can't capture

A model with nothing real to hand invents a `$4,200 MRR`, because the prompt
asked for a specific number and specificity is what it was trained to produce.
Stories are parsed structurally, so the figures in each entry's `numbers:` field
become the *allowed* set the claims map validates against.

**Only the `numbers:` field counts.** Prose in a story body is used for relevance
ranking and never for provenance — a story legitimately discusses figures it is
arguing against, and an entry describing a fabricated "$200 saved" claim must not
certify `$200` as verified for the next article.

```bash
python agent.py brain init      # scaffold with worked examples
python brain.py check "docker"  # what a draft on that topic would receive
```

After each piece, S10 proposes new entries into `brain/inbox.md`. Nothing is
auto-promoted — an unreviewed "fact" would be laundered into every future
article as verified.

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
| `JUDGE_ROUNDS` | `2` | Max editorial revise rounds per article |
| `JUDGE_TARGET` | `78` | Editorial score at which review stops early |
| `BRAIN_DIR` | `brain` | Where beliefs/stories/voice rules live |
| `GEMINI_MODELS` | `gemini-3.7-flash,gemini-3.5-flash` | Gemini chain, in order |
| `OPENROUTER_MODELS` | 4 `:free` slugs | OpenRouter chain, in order |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model |
| `OPENROUTER_ALLOW_PAID` | unset | Enable `openrouter/auto` (can bill) |
| `GEMINI_THINKING` | `low` | Thinking level; empty string sends no field |
| `GEMINI_TOKEN_HEADROOM` | `3.0` | Multiplier on the output-token budget |
| `ARTICLE_MIN_RATIO` | `0.45` | Min share of target words before a draft is rejected |
| `PROMO_THREAD_LEN` | `6` | Posts in the generated X thread |
| `VOICE_SAMPLES_DIR` | `voice` | Where voice samples live |
| `SOURCE_TIMEOUT` | `45` | Per-source seconds before a source is degraded |
| `REDDIT_BUDGET` | `40` | Total seconds for the Reddit leg |
| `SHOW_HN_WINDOW_DAYS` | `30` | Recency window for Show HN launches |
| `RESEARCH_LIBRARY_DIR` | `research` | Where the archive is written |

AI providers are tried in order — **Gemini 3.7 Flash, Gemini 3.5 Flash** (direct
API), Groq, then OpenRouter's free models. Any one of them is enough.

Gemini goes first because the **direct API is the only genuinely free path to a
Flash model**. OpenRouter carries every Gemini tier but none of them free —
`google/gemini-3.5-flash` bills $1.50/$9.00 per million tokens there.

Model IDs rot, silently. A retired slug returns 404, the chain falls through, and
a run "succeeds" on a worse model. Three of the four OpenRouter slugs originally
hardcoded here had been removed from the catalogue, and `gemini-2.0-flash` had
been shut down by Google — so two thirds of the fallback chain was dead with no
symptom. Check any time:

```bash
python agent.py models   # resolves every configured ID against the live catalogue
```

Override without touching code: `GEMINI_MODELS`, `OPENROUTER_MODELS`, `GROQ_MODEL`.

`openrouter/auto` is **off by default** — its pricing is variable, so it can route
to a paid model and bill you. Set `OPENROUTER_ALLOW_PAID=1` if a run completing
matters more than the run being free.

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
