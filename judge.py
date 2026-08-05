"""
judge.py — editorial review and revision loop for drafted articles.

humanizer.py catches *mechanical* tells (banned vocabulary, em-dash runs,
title-case headings). It cannot tell you that the hook is generic, that the
code would not run, or that a "$4,200 MRR" figure was invented. That needs
judgement, so this module runs an LLM as a reviewer — with two guards, because
an unguarded LLM judge mostly produces praise:

  1. GROUNDING. Everything measurable is computed in Python first (word count,
     keyword placement, code blocks, citation URLs, money figures) and handed to
     the judge as ground truth. It scores against facts, not vibes.
  2. BLOCKING ISSUES. Fabricated citations and invented money figures are
     detected deterministically and cannot be scored away. A draft with one is
     "reject" regardless of what the model thinks of the prose.

The loop mirrors humanizer's: judge -> revise with the actual findings ->
re-judge, and a revision is kept only if the score actually improved.

Public API:
    ground_truth(article, ctx)        -> dict of measured facts
    judge(article, ctx, ask_ai)       -> Verdict
    revise(article, verdict, ask_ai)  -> str
    review_loop(article, ctx, ask_ai) -> (final_article, list[Verdict])
"""

import os
import re
import json
from dataclasses import dataclass, field, asdict

import humanizer

MAX_ROUNDS = int(os.getenv("JUDGE_ROUNDS", "2"))
TARGET_SCORE = float(os.getenv("JUDGE_TARGET", "78"))

# Weights sum to 1.0. Evidence integrity is weighted highest because a
# fabricated number is the only failure here that damages the author's
# credibility permanently.
RUBRIC = {
    "evidence_integrity": (0.22, "Every external claim traces to a real cited URL. No invented revenue, user counts, company names, or 'studies show'. Technical metrics (timings, LOC, error counts) may be the author's own."),
    "hook_specificity":   (0.14, "First 50 words name a real thing — an error string, a version, a file path, a timestamp. Not a scene-setting mood paragraph."),
    "promise_delivery":   (0.14, "The article delivers exactly what the title promised, and does it before the reader would bounce."),
    "technical_depth":    (0.14, "Code is runnable and specific: real imports, real flags, plausible values. A reader could copy it and get somewhere."),
    "reader_payoff":      (0.12, "A working developer finishes with something they can act on today."),
    "structure":          (0.10, "Every H2 earns its place and carries a concrete artifact. No filler section."),
    "voice_authenticity": (0.08, "Reads like one tired engineer wrote it in one sitting. Not a content team, not a LinkedIn post."),
    "seo_execution":      (0.06, "Primary keyword placed naturally in the opening, headings and close — without stuffing."),
}

# Money / audience figures are the fabrication risk. Technical metrics are not:
# the article prompt explicitly allows the author to report their own timings.
# Alternatives are ordered longest-first: Python's re takes the leftmost
# alternative that matches, so "mrr" must be tried before "m" or "$4,200 MRR"
# reports as "$4,200 M".
_MONEY_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:/month|per month|mrr|arr|/mo|k|m)?\b|"
    r"\b\d[\d,]*\s*(?:mrr|arr)\b|"
    r"\b\d[\d,]*\s*(?:paying )?(?:customers|subscribers|users|followers|signups|downloads)\b",
    re.IGNORECASE)

_URL_RE = re.compile(r"https?://[^\s)\]\"'>]+")
_ATTRIB_RE = re.compile(
    r"\b(?:according to|studies show|research shows|a study|survey|report(?:s|ed)? that|"
    r"experts? (?:say|agree|argue))\b", re.IGNORECASE)


def _trim_url(u):
    """A URL at the end of a sentence swallows the punctuation. Report the real
    link, not 'https://example.com/proof.' — these end up in a Telegram message
    someone is expected to click."""
    return u.strip().rstrip(".,;:!?)]}’\"'")


def _norm_url(u):
    u = re.sub(r"^https?://", "", _trim_url(u)).rstrip("/")
    return u.lower()


def ground_truth(article, ctx=None):
    """Measured facts. The judge is not allowed to contradict these."""
    ctx = ctx or {}
    prose = humanizer.mask_protected(article)[0]
    prose = humanizer._MASK_FIND.sub(" ", prose)

    words = humanizer.prose_word_count(article)
    target = int(ctx.get("target_words") or 0)
    primary = (ctx.get("primary_keyword") or "").strip().lower()

    h2s = re.findall(r"^##\s+(.+)$", article, re.MULTILINE)
    fences = re.findall(r"```(\w*)\n(.*?)```", article, re.DOTALL)
    code_blocks = [(lang, body) for lang, body in fences
                   if lang.lower() not in ("mermaid", "json?chameleon")]

    # Does each H2 carry a concrete artifact (code / table / diagram / image)?
    sections = re.split(r"^##\s+", article, flags=re.MULTILINE)[1:]
    bare = []
    for s in sections:
        head = s.splitlines()[0].strip() if s.splitlines() else ""
        if not re.search(r"```|^\s*\|.*\|\s*$|!\[", s, re.MULTILINE):
            bare.append(head[:60])

    # Keyword placement
    kw_hits = {}
    if primary:
        paras = [p for p in re.split(r"\n\s*\n", prose) if p.strip()]
        kw_hits = {
            "total": len(re.findall(re.escape(primary), prose, re.IGNORECASE)),
            "in_opening": bool(paras and primary in paras[0].lower()),
            "in_headings": sum(1 for h in h2s if primary in h.lower()),
            "in_closing": bool(paras and primary in paras[-1].lower()),
        }

    # Citation integrity — URLs in the draft that were never supplied as evidence
    allowed = {_norm_url(u) for u in (ctx.get("allowed_urls") or []) if u}
    own = {"coderfact.com", "github.com/" + str(ctx.get("github_user", "")).lower()}
    used = [_trim_url(u) for u in _URL_RE.findall(article)]
    unsourced = []
    for u in used:
        n = _norm_url(u)
        if any(n.startswith(o) or o in n for o in own if o.strip("/")):
            continue
        # image/CDN endpoints the pipeline itself generates are not citations
        if any(h in n for h in ("pollinations.ai", "quickchart.io", "mermaid.ink")):
            continue
        if allowed and not any(n.startswith(a) or a.startswith(n) for a in allowed):
            unsourced.append(u)

    # Money figures with no cited evidence anywhere in the draft
    evidence_blob = " ".join(str(v) for v in (ctx.get("evidence_text") or []))
    money = []
    for m in _MONEY_RE.findall(article):
        tok = m.strip()
        if tok and tok.lower() not in evidence_blob.lower():
            money.append(tok)

    vague = _ATTRIB_RE.findall(article)

    h = humanizer.score(article)
    return {
        "words": words,
        "target_words": target,
        "word_delta_pct": round((words - target) / target * 100, 1) if target else None,
        "h2_count": len(h2s),
        "h2_headings": h2s,
        "h2_without_artifact": bare,
        "code_blocks": len(code_blocks),
        "code_languages": sorted({l for l, _ in code_blocks if l}),
        "code_avg_lines": round(sum(b.count("\n") for _, b in code_blocks) / len(code_blocks), 1) if code_blocks else 0,
        "has_mermaid": "```mermaid" in article,
        "table_count": len(re.findall(r"^\s*\|[-: |]+\|\s*$", article, re.MULTILINE)),
        "image_count": len(re.findall(r"!\[", article)),
        "has_tldr": bool(re.search(r"\*\*TL;DR\*\*|^##?\s*TL;DR", article, re.IGNORECASE | re.MULTILINE)),
        "primary_keyword": primary,
        "keyword_placement": kw_hits,
        "urls_used": used[:20],
        "unsourced_urls": unsourced[:10],
        "unsourced_money_figures": money[:10],
        "vague_attributions": vague[:6],
        "ai_tell_score": h.score,
        "ai_tell_grade": h.grade(),
    }


def blocking_issues(gt):
    """Failures no prose quality can compensate for."""
    out = []
    if gt["unsourced_money_figures"]:
        out.append(f"FABRICATED FIGURES: {', '.join(gt['unsourced_money_figures'][:5])} "
                   f"— money/audience numbers with no cited source. Remove them or "
                   f"attribute them to a real URL from the evidence list.")
    if gt["unsourced_urls"]:
        out.append(f"UNVERIFIED CITATIONS: {', '.join(gt['unsourced_urls'][:3])} "
                   f"— these URLs were not in the research evidence. If the model "
                   f"invented them they are dead links under the author's byline.")
    if gt["vague_attributions"]:
        out.append(f"VAGUE ATTRIBUTION: {', '.join(sorted(set(gt['vague_attributions']))[:3])} "
                   f"— name the source with a URL or cut the claim.")
    if gt["code_blocks"] == 0:
        out.append("NO CODE: a developer tutorial with zero code blocks does not "
                   "deliver on the format.")
    return out


@dataclass
class Verdict:
    scores: dict = field(default_factory=dict)
    weighted: float = 0.0
    verdict: str = "revise"          # ship | revise | reject
    findings: list = field(default_factory=list)   # {severity, dimension, quote, problem, fix}
    strengths: list = field(default_factory=list)
    blocking: list = field(default_factory=list)
    ground: dict = field(default_factory=dict)
    error: str = ""

    def summary(self):
        worst = sorted(self.scores.items(), key=lambda kv: kv[1])[:3]
        worst_s = ", ".join(f"{k} {v}/10" for k, v in worst)
        return (f"editorial {self.weighted:.0f}/100 ({self.verdict})"
                + (f" | blocking: {len(self.blocking)}" if self.blocking else "")
                + (f" | weakest: {worst_s}" if worst_s else ""))

    def as_dict(self):
        return asdict(self)


def _fmt_ground(gt):
    kw = gt.get("keyword_placement") or {}
    lines = [
        f"- prose words: {gt['words']}" + (f" (target {gt['target_words']}, {gt['word_delta_pct']:+}%)"
                                           if gt.get("target_words") else ""),
        f"- H2 sections: {gt['h2_count']}",
        f"- H2s with NO code/table/diagram/image: {gt['h2_without_artifact'] or 'none'}",
        f"- code blocks: {gt['code_blocks']} ({', '.join(gt['code_languages']) or 'no language tags'}), "
        f"avg {gt['code_avg_lines']} lines",
        f"- tables: {gt['table_count']} | mermaid: {gt['has_mermaid']} | images: {gt['image_count']} | TL;DR: {gt['has_tldr']}",
        f"- mechanical AI-tell score: {gt['ai_tell_score']}/100 ({gt['ai_tell_grade']})",
    ]
    if kw:
        lines.append(f"- primary keyword '{gt['primary_keyword']}': {kw['total']}x total, "
                     f"opening={kw['in_opening']}, headings={kw['in_headings']}, closing={kw['in_closing']}")
    if gt["unsourced_money_figures"]:
        lines.append(f"- MONEY FIGURES WITH NO SOURCE: {gt['unsourced_money_figures']}")
    if gt["unsourced_urls"]:
        lines.append(f"- URLS NOT IN THE EVIDENCE LIST: {gt['unsourced_urls']}")
    if gt["vague_attributions"]:
        lines.append(f"- VAGUE ATTRIBUTIONS: {gt['vague_attributions']}")
    return "\n".join(lines)


def judge(article, ctx, ask_ai):
    """Score the draft against the rubric, grounded in measured facts."""
    ctx = ctx or {}
    gt = ground_truth(article, ctx)
    block = blocking_issues(gt)

    rubric_block = "\n".join(
        f"  {name} (weight {w:.2f}): {desc}" for name, (w, desc) in RUBRIC.items())

    prompt = f"""You are a hostile but fair editor reviewing a draft before it goes out under a real engineer's name. Your job is to find what is wrong. A draft you pass that later embarrasses the author is a failure on your part.

You are NOT writing encouragement. Do not list strengths you had to search for. If the draft is mediocre, say so and score it in the 40s.

ARTICLE TITLE: {ctx.get('title', '(untitled)')}
ARTICLE FORMAT: {ctx.get('article_format', 'Code Tutorial')}

MEASURED FACTS (computed in Python — you may NOT contradict these, and you must
account for any listed problem in your scoring):
{_fmt_ground(gt)}

{"DETERMINISTIC BLOCKING ISSUES ALREADY FOUND — reflect these in evidence_integrity and set verdict to reject unless they are trivial:" + chr(10) + chr(10).join('  ! ' + b for b in block) if block else "No deterministic blocking issues found."}

EVIDENCE THE WRITER WAS GIVEN (the only external sources they were allowed to cite):
{chr(10).join('  - ' + e for e in (ctx.get('evidence_text') or ['(none — the article must be entirely first-person with no external claims)'])[:10])}

RUBRIC — score each 0-10:
{rubric_block}

SCORING ANCHORS: 9-10 = better than the best post on this topic today. 7-8 = publishable, a reader would bookmark it. 5-6 = competent but forgettable. 3-4 = generic, would not survive the first paragraph. 0-2 = broken or dishonest.

ARTICLE:
---
{article[:14000]}
---

Return ONLY a JSON object, no markdown fences:
{{
  "scores": {{ {', '.join(f'"{k}": 0' for k in RUBRIC)} }},
  "verdict": "ship" | "revise" | "reject",
  "strengths": ["at most 2, only if genuinely above average — omit rather than pad"],
  "findings": [
    {{
      "severity": "high" | "medium" | "low",
      "dimension": "one of the rubric keys",
      "quote": "the exact phrase or sentence from the article that is the problem, verbatim, max 120 chars",
      "problem": "what is wrong with it in one sentence",
      "fix": "the specific change to make — an instruction the writer can act on without re-reading your review"
    }}
  ]
}}

Rules for findings: quote real text from the article, never paraphrase. Order by severity. At most 10. Every finding must name a fix that is concrete enough to apply directly. "Make the hook stronger" is a useless finding; "Replace the weather-and-coffee opening with the actual psycopg2 OperationalError string and the time it fired" is a usable one."""

    v = Verdict(ground=gt, blocking=block)
    try:
        raw = ask_ai(prompt, max_tokens=2600)
        data = _extract_json(raw)
        scores = {k: _clamp(data.get("scores", {}).get(k)) for k in RUBRIC}
        v.scores = scores
        v.weighted = round(sum(scores[k] * w for k, (w, _) in RUBRIC.items()) * 10, 1)
        v.strengths = [str(s) for s in (data.get("strengths") or [])][:2]
        v.findings = [f for f in (data.get("findings") or []) if isinstance(f, dict)][:10]
        v.verdict = str(data.get("verdict", "revise")).lower().strip()
    except Exception as e:
        v.error = str(e)[:200]
        # Fall back to the deterministic signal rather than silently passing.
        v.weighted = float(gt["ai_tell_score"])
        v.verdict = "reject" if block else "revise"
        print(f"[judge] scoring failed: {e} — falling back to mechanical score")

    if block:
        v.verdict = "reject"
        v.weighted = min(v.weighted, 45.0)
    elif v.verdict not in ("ship", "revise", "reject"):
        v.verdict = "revise"
    return v


def _clamp(x):
    try:
        return max(0, min(10, int(round(float(x)))))
    except (TypeError, ValueError):
        return 5


def _extract_json(raw):
    s = str(raw).strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"```\s*$", "", s, flags=re.MULTILINE).strip()
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1:
        s = s[a:b + 1]
    try:
        return json.loads(s, strict=False)
    except json.JSONDecodeError:
        return json.loads(re.sub(r",(\s*[}\]])", r"\1", s), strict=False)


def format_findings(v, limit=10):
    if not v.findings and not v.blocking:
        return "(no findings)"
    out = []
    for b in v.blocking:
        out.append(f"[BLOCKING] {b}")
    for f in v.findings[:limit]:
        out.append(
            f"[{str(f.get('severity', 'medium')).upper()}] {f.get('dimension', '')}\n"
            f"    quote:   \"{str(f.get('quote', ''))[:120]}\"\n"
            f"    problem: {f.get('problem', '')}\n"
            f"    fix:     {f.get('fix', '')}")
    return "\n".join(out)


def revise(article, v, ask_ai, ctx=None):
    """Apply the reviewer's findings. Same contract as humanizer.repair_pass:
    fix what was flagged, touch nothing else."""
    ctx = ctx or {}
    actionable = [f for f in v.findings if str(f.get("severity", "")).lower() in ("high", "medium")]
    if not actionable and not v.blocking:
        return article

    prompt = f"""An editor reviewed this article and returned the findings below. Apply every one of them. Change nothing the editor did not flag.

ARTICLE:
---
{article}
---

EDITOR'S FINDINGS:
{format_findings(v)}

{humanizer.PRESERVE_BLOCK}

HOW TO APPLY:
- Work finding by finding. Locate the quoted text and rewrite the sentence or paragraph around it so the problem is gone.
- A finding that says to cut something means cut it. Do not replace it with a softer version of the same thing.
- Do not add new facts, numbers, company names, URLs, or citations while revising. If a finding says a number is unsourced, DELETE the number or make the sentence qualitative — never swap in a different number.
- Do not add transitions or summary sentences to paper over a deletion. An abrupt paragraph is the correct outcome.
- Do not rewrite paragraphs that were not flagged, and do not "improve" the prose generally.
- Keep the length near {ctx.get('target_words') or humanizer.prose_word_count(article)} words.

{"THE ONLY EXTERNAL SOURCES YOU MAY CITE:" + chr(10) + chr(10).join('  - ' + e for e in (ctx.get('evidence_text') or [])[:10]) if ctx.get('evidence_text') else "You may not cite any external source. Write first-person only."}

Output the corrected article only. No preamble, no changelog."""

    out = ask_ai(prompt, max_tokens=int(len(article) / 3) + 1200)
    out = humanizer._strip_preamble(out)
    if not out or len(out) < len(article) * 0.6:
        print(f"[judge] revision too short ({len(out) if out else 0} vs {len(article)}) — keeping previous")
        return article
    return out


def review_loop(article, ctx, ask_ai, max_rounds=None, target=None):
    """judge -> revise -> re-judge. A revision is kept only if it scores higher.

    Returns (final_article, [Verdict, ...]) — one verdict per round, so the
    caller can report the trajectory.
    """
    max_rounds = MAX_ROUNDS if max_rounds is None else max_rounds
    target = TARGET_SCORE if target is None else target

    history = []
    current = article
    v = judge(current, ctx, ask_ai)
    history.append(v)
    print(f"[judge] round 0 — {v.summary()}")

    for i in range(1, max_rounds + 1):
        if v.verdict == "ship" and v.weighted >= target and not v.blocking:
            break
        if not v.findings and not v.blocking:
            break
        try:
            candidate = revise(current, v, ask_ai, ctx)
        except Exception as e:
            print(f"[judge] revision {i} failed: {e}")
            break
        if candidate == current:
            break

        cv = judge(candidate, ctx, ask_ai)
        print(f"[judge] round {i} — {cv.summary()}")
        # Keep only a real improvement, and never accept a revision that
        # introduces a blocking issue the previous draft did not have.
        if cv.weighted > v.weighted and len(cv.blocking) <= len(v.blocking):
            current, v = candidate, cv
            history.append(cv)
        else:
            print(f"[judge] round {i} did not improve "
                  f"({cv.weighted:.0f} vs {v.weighted:.0f}) — discarded")
            history.append(cv)
            break

    return current, history


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — review any draft on disk:
#   python judge.py medium_drafts/some-post.md
#   python judge.py --json medium_drafts/some-post.md
#   python judge.py --fix medium_drafts/some-post.md   (writes the revision back)
#
# Needs an AI provider key; the grounded facts alone work offline via --dry.
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import glob as _glob

    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        print("Usage: python judge.py [--json] [--fix] [--dry] <file.md> ...")
        sys.exit(0)

    paths = []
    for a in args:
        paths.extend(sorted(_glob.glob(a)) or [a])

    results = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()

        title = next((l.lstrip("# ").strip() for l in text.splitlines()
                      if l.startswith("# ")), os.path.basename(path))
        ctx = {"title": title,
               "allowed_urls": _URL_RE.findall(text),  # CLI: trust what's there
               "evidence_text": []}

        if "--dry" in flags:
            gt = ground_truth(text, ctx)
            block = blocking_issues(gt)
            if "--json" in flags:
                results.append({"file": path, "ground": gt, "blocking": block})
            else:
                print(f"\n{'=' * 72}\n{path}\n{'=' * 72}")
                print(_fmt_ground(gt))
                for b in block:
                    print(f"  ! {b}")
            continue

        from agent import ask_ai as _ask   # provider chain lives in agent.py

        if "--fix" in flags:
            fixed, hist = review_loop(text, ctx, _ask)
            if fixed != text:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(fixed)
                print(f"[judge] wrote revision to {path}")
            v = hist[-1]
        else:
            v = judge(text, ctx, _ask)

        results.append({"file": path, "verdict": v.as_dict()})
        if "--json" not in flags:
            print(f"\n{'=' * 72}\n{path}\n{'=' * 72}")
            print(v.summary())
            for k, s in sorted(v.scores.items(), key=lambda kv: kv[1]):
                print(f"  {s:2d}/10  {k}")
            print()
            print(format_findings(v))

    if "--json" in flags:
        print(json.dumps(results, indent=2, default=str))
