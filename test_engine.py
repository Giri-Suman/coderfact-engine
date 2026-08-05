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


# ── summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 62)
print(f"{len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    for f in FAIL:
        print("  FAILED:", f)
    sys.exit(1)
print("all green")
