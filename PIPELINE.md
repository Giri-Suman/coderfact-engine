# The contract

What this engine does, stage by stage, in plain English. Written down because a
pipeline that only exists as code cannot be argued with — and every rule below
was added after something went wrong.

Adapted from the "AI Content Factory" structure (learnwithhasan.com), minus the
ephemeral-server Lab: this repo publishes written developer content, and renting
infrastructure per piece would add cost, credentials and blast radius for
evidence that keyword research and the author's own machine already provide.

## Stages

| # | Stage | Runs | Output |
|---|---|---|---|
| S0 | **Sweep** | `agent.py research`, 08:00 IST | 8 sources in parallel, ranked clusters |
| S1 | **Score** | same run | cross-source corroboration computed in Python |
| S2 | **Propose** | same run | 3 titles, novelty-checked against the library |
| — | **CHECKPOINT 1 — human picks the topic** | Telegram | reply `1`/`2`/`3`, or type your own |
| S3 | **Plan** | `agent.py draft` | complexity, keywords, outline, snippet + diagram plan |
| S4 | **Brain pull** | same run | relevant stories, beliefs, voice rules loaded |
| S5 | **Draft** | same run | article written against the brain and the evidence |
| S6 | **Humanize** | same run | rewrite → scan → repair, keep only if score improves |
| S7 | **Review** | same run | rubric judge → revise, keep only if score improves |
| S8 | **Claims map** | same run | every figure labelled with its receipt |
| S9 | **Ship** | same run | Dev.to **draft** + `medium_drafts/*.md` + `*.claims.md` |
| S10 | **Seed** | same run | brain candidates → `brain/inbox.md` |
| S11 | **Promote** | same run | LinkedIn post + X thread from the finished piece |
| — | **CHECKPOINT 2 — human reads it before publishing** | Dev.to | nothing auto-publishes |

## Rules

**Nothing publishes itself.** Dev.to receives `published: false`. Every stage
after S9 produces material for review, never a live post. The two checkpoints
are not optional and not delegable.

**No claim ships without a receipt.** Every figure in a draft is labelled
`BRAIN` (the author measured it), `EVIDENCE` (traces to a research URL), `SELF`
(first-person process detail), or `UNSOURCED`. Unsourced figures are listed in
the claims map and pushed to Telegram. Money and audience numbers can never be
`SELF` — you are not the authority on someone else's revenue.

**Loops keep a result only if it scored better.** Both the humanizer and the
judge re-score after revising and discard a pass that made things worse. A loop
that can only improve is a loop that ran twice for nothing.

**Detection is deterministic where it can be.** Regex and structural checks are
reproducible and free; the model is called for judgement, not for measurement.
Anything the judge could be sycophantic about is computed in Python first and
handed to it as ground truth it may not contradict.

**Nothing enters the brain unreviewed.** S10 proposes; a human promotes. An
unreviewed entry would be laundered into every future article as verified fact.

**A broken source looks broken.** Every sweep reports per-source ok/empty/failed
with a reason. Silence is never reported as "no news today".

## Where the guards live

```
brain/stories.md ──► supplies real numbers ──► draft (S5)
                                                 │
                                                 ▼
                                    humanizer.py  mechanical tells   (S6)
                                                 │
                                                 ▼
                                    judge.py      editorial rubric   (S7)
                                                 │  blocking: fabricated
                                                 │  figures, unverified URLs
                                                 ▼
                                    claims.py     receipt per figure (S8)
                                                 │
                                                 ▼
                                             human read
```

The brain and the claims map are the same fix from both ends: give the writer
real material so it never needs to invent, then prove what it used.

## Cost

No paid infrastructure. Free tiers only — OpenRouter/Gemini/Groq for models
(Gemini Flash is free-of-charge on the free tier; `GEMINI_MODELS` lists two so
the quota buckets are independent),
public APIs and RSS for research, GitHub Actions for scheduling. The only paid
key that could be added is a SERP API for prior-art analysis, which S3 currently
approximates with Dev.to, Hacker News and Reddit search.

## When something goes wrong

Add the rule here first, then the code. A rule that only exists in a regex is a
rule nobody can find.
