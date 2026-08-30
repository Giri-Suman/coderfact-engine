"""
Offline test suite — no network, no API keys, no AI calls.

    python test_engine.py

Covers the invariants that are expensive to discover in production: that the
humanizer never mangles code, that JSON extraction survives real LLM output,
that slugs don't collide, and that the mermaid URL is actually fetchable.
"""

import sys
import io
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import humanizer as H
import research_engine as R

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"  — {detail}" if detail and not cond else ""))


SAMPLE = """# Why Your Build Is Slow

It was 1am. The pipeline had been green for six minutes and the repo still had
nothing in it. **Sound familiar?** Yeah. Me too.

## What I Tried First And Why It Failed

In order to debug this, I had to delve into the runner logs. Experts say that
CI caching is a robust solution — but it's not just about caching, but about
knowing when the cache is stale.

```python
import requests  # 2.31.0
# retry — flaky on cold start
def fetch(url):
    return requests.get(url, timeout=10)  # in order to avoid hangs
```

| Approach | Time |
|----------|------|
| Before   | 47s  |
| After    | 3s   |

![diagram](https://example.com/a_b+c/d.png)

Let's dive in. At the end of the day, the real question is whether this
leverages a seamless workflow. I hope this helps!

TAGS: ["python","ci"]
META: How to fix slow builds in order to ship faster.
"""


# ── masking ──────────────────────────────────────────────────────────────────
print("\nmasking")
masked, store = H.mask_protected(SAMPLE)
check("roundtrip is lossless", H.unmask(masked, store) == SAMPLE)
check("code fence is hidden from the scanner", "import requests" not in masked)
check("table row is hidden", "| Before" not in masked)
check("image URL is hidden", "a_b+c" not in masked)
check("TAGS/META hidden", "TAGS:" not in masked and "META:" not in masked)
check("prose survives", "pipeline had been green" in masked)


# ── autofix must never touch protected regions ───────────────────────────────
print("\nautofix safety")
fixed, n = H.autofix(SAMPLE)
check("some fixes applied", n > 0, f"n={n}")
check("code block byte-identical",
      "def fetch(url):\n    return requests.get(url, timeout=10)  # in order to avoid hangs" in fixed)
check("'in order to' inside code untouched", "# in order to avoid hangs" in fixed)
check("'in order to' in prose rewritten", "In order to debug" not in fixed)
check("image URL intact", "https://example.com/a_b+c/d.png" in fixed)
check("table intact", "| Before   | 47s  |" in fixed)
check("no sentinel leaked", "" not in fixed)
check("title-case heading lowered", "## What I tried first and why it failed" in fixed,
      [l for l in fixed.splitlines() if l.startswith("## ")])


# ── detection ────────────────────────────────────────────────────────────────
print("\ndetection")
names = {f.name for f in H.scan(SAMPLE)}
for expect in ("template-leak", "filler-phrases", "vague-attribution",
               "negative-parallelism", "signposting", "authority-tropes",
               "chatbot-artifacts", "ai-vocabulary"):
    check(f"detects {expect}", expect in names, sorted(names))

clean = ("The runner mounts the cache before checkout. That ordering matters: a "
         "cache restored after checkout overwrites the lockfile. I moved the step "
         "up by four lines and the build dropped to nine seconds.\n\n" * 3)
check("clean prose scores higher than slop",
      H.score(clean).score > H.score(SAMPLE).score,
      f"clean={H.score(clean).score} slop={H.score(SAMPLE).score}")
check("score is bounded 0..100", 0 <= H.score(SAMPLE).score <= 100)


# ── humanize loop control flow (stubbed model) ───────────────────────────────
print("\nhumanize loop")

calls = {"n": 0}


def ask_improving(prompt, max_tokens=0):
    """Stub model that actually removes tells, so the loop should keep it."""
    calls["n"] += 1
    body = prompt.split("---", 2)[1] if "---" in prompt else prompt
    out = body
    for bad, good in (("Sound familiar?", "The logs were empty."),
                      ("Yeah. Me too.", "That took a while to notice."),
                      ("It was 1am.", "The clock read 01:04."),
                      ("Let's dive in.", ""), ("I hope this helps!", ""),
                      ("Experts say that", "The GitHub Actions docs say"),
                      ("delve into", "read"), ("robust", "reliable"),
                      ("seamless", "quiet"), ("leverages", "uses"),
                      ("at the end of the day, the real question is",
                       "the question is"),
                      ("At the end of the day, the real question is",
                       "The question is")):
        out = out.replace(bad, good)
    return out.strip()


def ask_worse(prompt, max_tokens=0):
    body = prompt.split("---", 2)[1] if "---" in prompt else prompt
    return body.strip() + "\n\nIn conclusion, this is a game-changer. Let's dive in!\n" * 3


out, rep = H.humanize(SAMPLE, ask_improving, target_words=300, samples=[])
check("loop improves the score", rep.after.score > rep.before.score,
      f"{rep.before.score} -> {rep.after.score}")
check("loop called the model", calls["n"] > 0)
check("code block survived the loop", "import requests" in out)
check("report summary renders", "AI-tell score" in rep.summary())

out2, rep2 = H.humanize(SAMPLE, ask_worse, target_words=300, samples=[])
check("a regressing repair is discarded", rep2.after.score >= rep2.before.score,
      f"{rep2.before.score} -> {rep2.after.score}")

out3, rep3 = H.humanize("too short", ask_worse, samples=[])
check("short input is passed through", out3 == "too short" and rep3.rounds == 0)


def ask_raises(prompt, max_tokens=0):
    raise RuntimeError("all providers down")


out4, rep4 = H.humanize(SAMPLE, ask_raises, target_words=300, samples=[])
check("provider failure still returns usable markdown", "import requests" in out4)


# ── voice fingerprint ────────────────────────────────────────────────────────
print("\nvoice fingerprint")
check("no samples -> empty brief", H.voice_fingerprint([]) == "")
fp = H.voice_fingerprint([clean * 2])
check("fingerprint reports sentence length", "Sentence length" in fp)
check("fingerprint reports vocabulary", "Recurring vocabulary" in fp)


# ── agent.py helpers ─────────────────────────────────────────────────────────
print("\nagent helpers")
os.environ.setdefault("SKIP_AGENT_NET", "1")
import agent  # noqa: E402  (import after path setup; module-level code is pure)

check("extract_json: plain", agent.extract_json('{"a": 1}')["a"] == 1)
check("extract_json: fenced", agent.extract_json('```json\n{"a": 2}\n```')["a"] == 2)
check("extract_json: preamble prose",
      agent.extract_json('Here is the JSON:\n```json\n{"a": 3}\n```\nHope that helps')["a"] == 3)
check("extract_json: trailing comma", agent.extract_json('{"a": 4,}')["a"] == 4)
check("extract_json: array", agent.extract_json('[{"a": 5}]', want=list)[0]["a"] == 5)
check("extract_json: literal newline in string",
      agent.extract_json('{"code": "line1\nline2"}')["code"].count("\n") == 1)
try:
    agent.extract_json('{"a": 1}', want=list)
    check("extract_json: type assertion", False)
except ValueError:
    check("extract_json: type assertion", True)
# The specific failure the old .strip("```json") had: it strips CHARACTERS.
check("old strip() bug is gone — leading 'n'/'o' preserved",
      agent.extract_json('```json\n{"note": "ok"}\n```')["note"] == "ok")

long_a = "How I Built A Really Long Article Title That Runs Well Past Sixty Chars Alpha"
long_b = "How I Built A Really Long Article Title That Runs Well Past Sixty Chars Beta"
check("slug: long titles don't collide", agent.draft_slug(long_a) != agent.draft_slug(long_b))
check("slug: short title is clean", agent.draft_slug("Fix CORS in Vite") == "fix-cors-in-vite")
check("slug: empty falls back", agent.draft_slug("!!!") == "draft")

md = agent.convert_mermaid_for_medium("```mermaid\ngraph TD\n A[Start] --> B{Ok?}\n B -->|yes| C[Ship]\n```")
url = md[md.find("(") + 1:md.find(")")]
payload = url.split("/img/")[1].split("?")[0]
check("mermaid URL has no '/' in the payload", "/" not in payload, payload)
check("mermaid URL has no '+' in the payload", "+" not in payload, payload)
import base64 as _b64
check("mermaid payload decodes back to the diagram",
      b"graph TD" in _b64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


# ── research engine (pure functions only — no network) ───────────────────────
print("\nresearch engine")
items = [
    R.Item("hackernews", "DeepSeek V4 Flash runs on a single AMD MI300X", "u1", 400, 3),
    R.Item("reddit", "DeepSeek V4 Flash on a single MI300X card", "u2", 900, 5, detail="r/LocalLLaMA"),
    R.Item("rss", "DeepSeek V4 Flash on a single AMD MI300X", "u3", 0, 8, detail="TechCrunch AI"),
    R.Item("rss", "Totally unrelated post about garden sheds", "u4", 0, 40, detail="HN RSS"),
    R.Item("hackernews", "Totally unrelated post about garden sheds", "u5", 10, 40),
]
R.normalize(items)
check("normalize assigns percentiles", all("norm" in i.meta for i in items))
cl = R.score_clusters(R.cluster(items))
top = cl[0]
check("cross-source story clusters together", len(top.items) == 3, [c.title for c in cl])
check("cluster counts 3 platforms", len(top.platforms) == 3, top.platforms)
shed = [c for c in cl if "shed" in c.title.lower()][0]
check("hnrss collapses into hackernews", shed.platforms == {"hackernews"}, shed.platforms)
check("corroborated cluster outranks single-platform", cl[0] is top)
check("platform_of maps medium feeds",
      R.platform_of(R.Item("rss", "x", detail="Better Programming")) == "medium")

with tempfile.TemporaryDirectory() as td:
    R.LIBRARY_PATH = os.path.join(td, "library.jsonl")
    R.LIBRARY_DIR = td
    R.library_append({"date": "x", "titles": ["Building a research agent with LangGraph"]})
    check("library persists", len(R.library_read()) == 1)
    check("library search finds it", len(R.library_search("langgraph research agent")) >= 1)
    fresh, closest, sim = R.novelty("Why my Postgres index was ignored")
    check("novel title passes", fresh)
    dup, closest2, sim2 = R.novelty("Building a research agent with LangGraph")
    check("near-duplicate is caught", not dup, f"sim={sim2} closest={closest2}")

check("tokens drops stopwords", "the" not in R.tokens("the agent and the tool"))

# A measured before/after is the specificity the engine exists to produce.
# Flagging "from 500ms to 200ms" as a fake range trained the writer away from it.
for _txt, _want in [("Response time went from 500ms to 200ms.", False),
                    ("Scaled from 3 workers to 12 workers.", False),
                    ("Used by everyone from startups to enterprises.", True),
                    ("anything from debugging to deployment", True)]:
    check(f"false-ranges {'flags' if _want else 'ignores'}: {_txt[:38]}",
          any(f.pid == 12 for f in H.scan(_txt)) == _want)

# Show HN regressions. Algolia's default sort is relevance across ALL TIME, and
# this source used to hardcode age_hours=72 — so a 14-year-old post arrived
# labelled as three-day-fresh signal. It also filtered launches by income
# keywords in the title, which dropped 39 of every 40 Show HN posts.
_now = __import__("time").time()
_captured = {}


def _fake_show_hn_get(url, **kw):
    _captured["params"] = kw.get("params", {})

    class _R:
        @staticmethod
        def json():
            return {"hits": [
                # a launch with no income keyword anywhere — must survive
                {"title": "Show HN: I made an open-source laptop from scratch",
                 "points": 3237, "num_comments": 400, "objectID": "1",
                 "created_at_i": int(_now - 5 * 86400), "story_text": ""},
                # an income-angle launch — must be flagged
                {"title": "Show HN: I replaced a $120k system with $1,600 of ESP32",
                 "points": 2935, "num_comments": 300, "objectID": "2",
                 "created_at_i": int(_now - 17 * 86400), "story_text": "made $4k MRR"},
            ]}
    return _R()


_real_get = R._get
try:
    R._get = _fake_show_hn_get
    _items = R.src_show_hn()
finally:
    R._get = _real_get

check("show_hn keeps launches without income keywords", len(_items) == 2,
      f"got {len(_items)}")
check("show_hn constrains the window server-side",
      f"created_at_i>" in str(_captured["params"].get("numericFilters", "")),
      str(_captured["params"]))
check("show_hn uses real age, not a hardcoded 72h",
      abs(_items[0].age_hours - 5 * 24) < 2, f"{_items[0].age_hours}h")
check("show_hn flags the income angle",
      _items[1].meta.get("income_angle") and not _items[0].meta.get("income_angle"))
# Snippets go straight into the model's prompt; HN returns them as raw HTML.
_dirty = "I&#x27;m Sasha.<p>A black hole &amp; it&#x27;s live<br>in your browser"
check("snippet HTML is stripped and entities decoded",
      R._clean_text(_dirty) == "I'm Sasha. A black hole & it's live in your browser",
      repr(R._clean_text(_dirty)))
check("_clean_text handles None/empty", R._clean_text(None) == "" and R._clean_text("") == "")
check("_age_hours falls back when the timestamp is junk",
      R._age_hours(None) == 48.0 and R._age_hours("nope") == 48.0)
check("_age_hours floors at 0.5h", R._age_hours(_now + 10_000) == 0.5)

# Income-angle stories sort ahead of higher-engagement generic ones, because
# that block exists so the writer cites a real number instead of inventing one.
_generic = R.Item("show_hn", "Show HN: A neat CLI", url="https://x/1",
                  meta={"story": True, "norm": 0.99, "income_angle": False})
_money = R.Item("show_hn", "Show HN: $4k MRR from a script", url="https://x/2",
                meta={"story": True, "norm": 0.10, "income_angle": True})
_block = R.format_stories([R.Cluster("k", items=[_generic, _money])])
check("income-angle story is listed first",
      _block.index("$4k MRR") < _block.index("A neat CLI"))


import judge as J
import promo as P

print("\njudge — grounding and blocking")

_FAB = """# How I Made Money

I built this in a weekend and it now does $4,200 MRR with 1,300 paying customers.
According to a study, most devs never ship. Research shows this is common.
Proof at https://totally-invented-source.com/proof.

## What I did
Prose with no code at all.
"""
_gt_fab = J.ground_truth(_FAB, {"title": "x",
                                "allowed_urls": ["https://news.ycombinator.com/item?id=1"],
                                "evidence_text": []})
check("money figures are captured whole, not truncated at 'M'",
      "$4,200 MRR" in _gt_fab["unsourced_money_figures"], _gt_fab["unsourced_money_figures"])
check("audience counts flagged",
      any("1,300" in m for m in _gt_fab["unsourced_money_figures"]))
check("url outside the evidence list flagged",
      _gt_fab["unsourced_urls"] == ["https://totally-invented-source.com/proof"])
check("vague attribution flagged", len(_gt_fab["vague_attributions"]) >= 2)
check("missing code flagged", _gt_fab["code_blocks"] == 0)
check("fabrication produces blocking issues", len(J.blocking_issues(_gt_fab)) >= 3)

# The author's own technical measurements are explicitly allowed — flagging
# them would make the judge unusable on exactly the articles this engine writes.
_CLEAN = """# Fixing a slow query

The psycopg2 OperationalError fired at 02:14. The query took 4200ms, now 180ms.
Cut 340 lines. Memory dropped from 512MB to 90MB.

```python
import psycopg2  # 2.9.9
conn = psycopg2.connect(host="db", port=5432)
```

| metric | before | after |
|---|---|---|
| latency | 4200ms | 180ms |
"""
_gt_clean = J.ground_truth(_CLEAN, {"primary_keyword": "psycopg2", "target_words": 60})
check("technical metrics are not treated as money", _gt_clean["unsourced_money_figures"] == [],
      _gt_clean["unsourced_money_figures"])
check("pipeline's own image hosts aren't treated as citations",
      J.ground_truth("![x](https://image.pollinations.ai/prompt/y)\n\n```py\na=1\n```",
                     {"allowed_urls": ["https://example.com"]})["unsourced_urls"] == [])
check("clean draft has no blocking issues", J.blocking_issues(_gt_clean) == [])
check("artifact-free H2s are named",
      "What I did" in " ".join(_gt_fab["h2_without_artifact"]))
check("rubric weights sum to 1.0", abs(sum(w for w, _ in J.RUBRIC.values()) - 1.0) < 1e-9)

# A judge that can't parse its own model output must not silently pass a draft.
_v = J.judge(_CLEAN, {"title": "t"}, lambda p, max_tokens=0: "not json at all")
check("judge falls back to revise/reject when scoring fails",
      _v.verdict in ("revise", "reject") and _v.error)

# review_loop must not accept a revision that scores worse.
_calls = {"n": 0}


def _degrading_ai(prompt, max_tokens=0):
    _calls["n"] += 1
    if "EDITOR'S FINDINGS" in prompt:
        return _CLEAN + "\n\nAccording to a study, this is common.\n"
    return json.dumps({
        "scores": {k: (9 if _calls["n"] == 1 else 3) for k in J.RUBRIC},
        "verdict": "revise", "strengths": [],
        "findings": [{"severity": "high", "dimension": "structure",
                      "quote": "Cut 340 lines.", "problem": "vague", "fix": "name the file"}],
    })


_final, _hist = J.review_loop(_CLEAN, {"title": "t"}, _degrading_ai, max_rounds=1)
check("a worse revision is discarded", _final == _CLEAN, "kept the degraded revision")
check("review_loop records every round", len(_hist) >= 2)

print("\npromo — platform limits and grounding")

check("SEO header is stripped before facts are read",
      not P.strip_seo_block("---\nTAGS: x\n---\nCUT THE ABOVE BLOCK HERE ✂️\n\nReal opening."
                            ).startswith("---"))
_facts = P.extract_facts(_CLEAN, "Fixing a slow query")
check("facts pull the real code snippet", "psycopg2" in _facts["snippet"])
check("facts pull real metrics", any("4200ms" in m or "180ms" in m for m in _facts["metrics"]))
check("facts detect the comparison table", _facts["has_table"])

_long = "x " * 400
_fitted, _warn = P._fit_x(_long, ask_ai=None)
check("over-length X post is truncated to the limit", len(_fitted) <= P.X_LIMIT, len(_fitted))
check("truncation is flagged as a warning", bool(_warn))
check("truncation lands on a word boundary", "  " not in _fitted.rstrip("…"))
_short = "A short post."
check("short X post is left alone", P._fit_x(_short, ask_ai=None)[0] == _short)
check("model rewrite is preferred over truncation",
      P._fit_x("y " * 300, ask_ai=lambda p, max_tokens=0: "concise version")[0]
      == "concise version")
check("tweet numbering prefixes are stripped", P._clean_post('2/ "Real text"') == "Real text")


import brain as B
import claims as C

print("\nbrain — parsing and verified numbers")

_STORIES = """# Stories

## Cut the sweep from 9 minutes to 40 seconds
- when: 2026-08
- numbers: 9 min -> 40 s, 38 HTTP calls -> 6
- source:
- tags: python, concurrency

Ran serially, including 15 sequential lookups. Thread pool fixed it.

## Dropped the Docker image from 1.2 GB to 180 MB
- when: 2026-07
- numbers: 1.2 GB -> 180 MB
- source: https://github.com/example/repo/pull/12
- tags: docker

Multi-stage build.
"""
with tempfile.TemporaryDirectory() as _td:
    with open(os.path.join(_td, "stories.md"), "w", encoding="utf-8") as fh:
        fh.write(_STORIES)
    with open(os.path.join(_td, "beliefs.md"), "w", encoding="utf-8") as fh:
        fh.write("# Beliefs\n\nSome prose that is not a belief.\n\n- Benchmarks without a machine spec are vibes.\n")
    with open(os.path.join(_td, "voice.md"), "w", encoding="utf-8") as fh:
        fh.write("# Voice\n\nExplanatory preamble the model must never receive.\n\n- Name the version.\n")
    _b = B.load(_td)

    check("brain parses both stories", len(_b.stories) == 2)
    # '- source:' with nothing after it is the normal case for work on your own
    # machine; it must be consumed as a field, not fall into the prose body.
    check("empty field does not leak into the body",
          "source:" not in _b.stories[0].body, _b.stories[0].body[:60])
    check("beliefs take bullets only, not prose", _b.beliefs == ["Benchmarks without a machine spec are vibes."])
    check("voice.md preamble is not fed to the model",
          _b.voice_rules == ["Name the version."], _b.voice_rules)
    _nums = _b.verified_numbers()
    check("compound number field is atomised", {"9", "40", "38", "6"} <= _nums, sorted(_nums))
    check("unit forms are kept too", "40s" in _nums or "9min" in _nums, sorted(_nums))
    # Prose is NOT a source of verified figures. A story body legitimately
    # discusses numbers it argues against — an entry describing a fabricated
    # "$200 saved" claim must never certify $200 as verified.
    check("prose numbers do not become verified", "15" not in _nums, sorted(_nums))
    _poison = B.Brain(stories=[B.Story(title="t", numbers=["40 s"],
                                       body="The draft claimed $200 saved. It was invented.")])
    check("a story arguing against a figure does not verify it",
          "200" not in _poison.verified_numbers() and "$200" not in _poison.verified_numbers(),
          sorted(_poison.verified_numbers()))
    check("story source URL is verified", "https://github.com/example/repo/pull/12" in _b.verified_urls())
    # A topic-specific pull must lead with the story that fits and is allowed to
    # drop the one that does not — dumping the whole brain buries the match.
    _blk = _b.for_topic("docker image size")
    check("for_topic includes the relevant story", "180 MB" in _blk)
    check("for_topic drops or trails the irrelevant one",
          "40 seconds" not in _blk or _blk.index("180 MB") < _blk.index("40 seconds"))
    check("for_topic falls back when nothing matches",
          bool(_b.for_topic("underwater basket weaving").strip()))
    check("empty brain is falsy", not B.load(os.path.join(_td, "nope")))

check("atomize splits a range", {"9min", "40s", "9", "40"} <= B.atomize_numbers("9 min -> 40 s"))
check("normalize_number is comma/space insensitive",
      B.normalize_number("$ 4,200 ") == B.normalize_number("$4200"))

print("\nclaims — receipts")

_ART = """# Cutting the sweep

The sweep took 9 minutes before I touched it. I got it to 40 seconds.

According to a study, most pipelines are IO bound.

We now push $9,400 MRR from this.

| stage | before | after |
|---|---|---|
| sweep | 9 minutes | 40 seconds |

```python
PORT = 8787   # not a claim
TIMEOUT = 4500
```

Runs on Python 3.11 with psycopg2 2.9.9 on port 5432.
"""
with tempfile.TemporaryDirectory() as _td2:
    with open(os.path.join(_td2, "stories.md"), "w", encoding="utf-8") as fh:
        fh.write(_STORIES)
    _b2 = B.load(_td2)

_cm = C.build_map(_ART, title="t", brain=_b2)
_figs = {c.figure.lower() for c in _cm.claims}

check("code block figures are not claims",
      not any("8787" in f or "4500" in f for f in _figs), sorted(_figs))
check("versions and ports are not claims",
      not any(f.startswith(("3.11", "2.9.9", "5432")) for f in _figs), sorted(_figs))
# A before/after table is the most claim-dense element in these articles.
# humanizer masks tables so a rewrite cannot mangle them; claims must NOT.
check("table figures are extracted",
      any(c.text.startswith("[table]") for c in _cm.claims),
      [c.text[:40] for c in _cm.claims])
check("table claim carries its row label",
      any("sweep" in c.text.lower() and c.text.startswith("[table]") for c in _cm.claims))
_prov = {c.figure.lower(): c.provenance for c in _cm.claims}
check("a figure in the brain is BRAIN",
      any(v == "BRAIN" for k, v in _prov.items() if "9 minutes" in k or "40 seconds" in k), _prov)
check("an unsourced money figure is UNSOURCED",
      any(v == "UNSOURCED" for k, v in _prov.items() if "9,400" in k or "9400" in k), _prov)
check("vague attribution becomes an external claim",
      any(c.kind == "external" and c.provenance == "UNSOURCED" for c in _cm.claims))
check("coverage is a fraction of all claims", 0.0 <= _cm.coverage <= 1.0)

# Money is never self-evidenced: the author is not the authority on revenue.
_money = C.classify([C.Claim(text="I make $9,400 MRR from it.", figure="$9,400", kind="number")],
                    brain=B.Brain())
check("first-person does not launder a money claim", _money[0].provenance == "UNSOURCED")
_timing = C.classify([C.Claim(text="I measured 250 ms on my laptop.", figure="250 ms", kind="number")],
                     brain=B.Brain())
check("first-person timing is allowed as SELF", _timing[0].provenance == "SELF")

_ok, _drift, _matched, _total = C.verify(_ART, _cm)
check("an unedited article verifies clean", _ok and not _drift, _drift)
_edited = _ART.replace("40 seconds.", "40 seconds. It also saved 12 hours.")
_ok2, _drift2, _, _ = C.verify(_edited, _cm)
check("a figure added after mapping is caught as drift", not _ok2 and _drift2, _drift2)
check("render lists the unsourced section",
      "Unsourced" in C.render(_cm) or not _cm.unsourced)


# ── Python 3.11 f-string compatibility ───────────────────────────────────────
# CI runs 3.11, where a backslash inside an f-string EXPRESSION is a
# SyntaxError; PEP 701 only lifted that in 3.12. Dev machines on 3.12+ compile
# such a line happily and the break only shows up in Actions, so scan for it
# here. ast.parse(feature_version=(3,11)) does NOT catch this — it was a
# tokenizer restriction, not a grammar feature.
print("\npython 3.11 compatibility")

import re
import glob as _glob2

_FSTR = re.compile(r"(?:rf|fr|f|F)(\"\"\"|'''|\"|')(.*?)\1", re.DOTALL)


def _fstring_backslash_offenders(src):
    # Drop {{ and }} first: those are literal braces in an f-string (JSON in a
    # prompt template), not expressions.
    src = src.replace("{{", "\x00").replace("}}", "\x01")
    out = []
    for m in _FSTR.finditer(src):
        for expr in re.findall(r"\{([^{}]*)\}", m.group(2)):
            if "\\" in expr:
                out.append((src.count("\n", 0, m.start()) + 1, expr[:60]))
    return out


# test_engine.py is skipped: the two checks below deliberately embed a bad
# line as a fixture, and CI's compileall covers this file anyway.
_offenders = []
for _f in sorted(f for f in _glob2.glob("*.py") if f != "test_engine.py"):
    with open(_f, encoding="utf-8") as _fh:
        _offenders += [(_f, ln, ex) for ln, ex in _fstring_backslash_offenders(_fh.read())]

check("no backslash inside an f-string expression (breaks Python 3.11)",
      not _offenders,
      "; ".join(f"{f}:{ln} {{{ex}}}" for f, ln, ex in _offenders[:4]))

# The detector must actually detect — a guard that silently passes is worse
# than no guard.
check("the 3.11 detector catches a known-bad line",
      len(_fstring_backslash_offenders("""x = f"a {re.sub(r'\\s+', ' ', b)} c" """)) == 1)
check("the 3.11 detector ignores {{ }} escaped braces",
      not _fstring_backslash_offenders('x = f"""{{ "k": "v\\n" }}"""'))


print("\ntruncation + meta-response guards")

# The exact failure that shipped: a truncated draft made the model answer ABOUT
# the draft, and that commentary was saved as the article.
_REFUSAL = """The rest of the draft is missing from what you pasted - the content
cuts off mid-sentence after "successfully." I can only rewrite what is actually
here, and what is here is roughly 70 words, well short of the 900-word target.

To produce a full article, I would need the complete draft. Send the full text
and I will rewrite it against the voice fingerprint."""

_REAL = """The webhook fired at 02:14 and came back 400. Stripe signs every payload
with a timestamped HMAC, and the raw body has to reach the verifier byte for
byte. Next.js 14 parses JSON before the handler runs, so the signature never
matched. Setting the route to accept the raw body fixed it."""

check("refusal is recognised as commentary", H.looks_like_meta_response(_REFUSAL))
check("real prose is not flagged", not H.looks_like_meta_response(_REAL, _REAL))
check("empty output counts as meta", H.looks_like_meta_response(""))
for _p in ("send the full text", "I can only rewrite", "what you pasted",
           "the content cuts off", "I would need the complete"):
    check("meta phrase caught: " + _p, H.looks_like_meta_response("Sure. " + _p + " and I will help."))

_kept = H.rewrite_pass(_REAL, lambda p, max_tokens=0: _REFUSAL, "v", "", 900)
check("rewrite_pass discards a commentary reply", _kept == _REAL)
_kept2 = H.repair_pass(_REAL, [H.Finding(1, "x", "high", 1, "e", "f")],
                       lambda p, max_tokens=0: _REFUSAL, 900)
check("repair_pass discards a commentary reply", _kept2 == _REAL)

_better = _REAL.replace("came back 400", "returned 400")
check("a genuine rewrite is accepted",
      H.rewrite_pass(_REAL, lambda p, max_tokens=0: _better, "v", "", 900) == _better)

_v = J.Verdict(findings=[{"severity": "high", "dimension": "structure",
                          "quote": "x", "problem": "y", "fix": "z"}])
check("judge.revise discards a commentary reply",
      J.revise(_REAL, _v, lambda p, max_tokens=0: _REFUSAL) == _REAL)

# Mid-sentence truncation: the published break ended on "and successfully".
_END_RE = re.compile(r"[.!?)\]`\"\u2019]\s*$")
for _txt, _complete in [("A full sentence.", True), ("ends with code `x`", True),
                        ("a list item)", True), ("and successfully", False),
                        ("The model was steered toward", False)]:
    check(("complete: " if _complete else "truncated: ") + _txt[:28],
          bool(_END_RE.search(_txt.strip())) == _complete)


# ── summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 62)
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
    sys.exit(1)
print("all green")
