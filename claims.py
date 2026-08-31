"""
claims.py — every factual assertion mapped to where it came from.

The strongest idea in learnwithhasan.com's "AI Content Factory" is the claims
map: no claim ships without a receipt. Their Supabase piece carries 49 mapped
claims, and the published guide ends with "23 of 23 facts matched" — re-verified
from committed evidence by script, not by trust.

judge.py already blocks the worst case (a money figure with no source anywhere).
This goes further and inverts the default: instead of scanning for known-bad
patterns, it enumerates EVERY checkable assertion and demands a provenance label
for each. Anything that cannot be labelled is the finding.

Four provenance classes:

  BRAIN      the figure appears in brain/stories.md — the author measured it
  EVIDENCE   the figure or claim traces to a research URL handed to the writer
  SELF       first-person process detail the author is the authority on
             ("the log was empty") — allowed, not externally checkable
  UNSOURCED  none of the above. This is the finding.

Only UNSOURCED blocks. The point is not to ban numbers — it is to make the
unsourced ones visible before publication instead of after.

The map is emitted next to the draft as `<slug>.claims.md`, and `verify()`
re-checks a published piece against it, so a later edit that introduces a new
figure is caught.

Public API:
    extract(article)                      -> list[Claim]
    classify(claims, brain, evidence)     -> list[Claim]  (provenance filled)
    build_map(article, ...)               -> ClaimsMap
    render(map)                           -> str          (the .claims.md file)
    verify(article, map)                  -> (ok, [drift])
"""

import os
import re
import json
from dataclasses import dataclass, field, asdict

import brain as brain_mod

# Figures worth a receipt. Deliberately excludes version numbers, ports, dates
# and years — those are identifiers, not claims, and flagging them buries the
# real findings.
_CLAIM_NUM_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:/month|per month|mrr|arr|/mo|k|m)?\b|"
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:%|x faster|x slower|x|ms|milliseconds|seconds?|secs?|"
    r"minutes?|mins?|hours?|days?|weeks?|months?|MB|GB|KB|TB|req/s|rps|qps|"
    r"lines?(?: of code)?|files?|commits?|users?|customers?|subscribers?|"
    r"downloads?|stars?|calls?|requests?|rows?|records?)\b",
    re.IGNORECASE)

# Assertions about the outside world — these need a URL even with no number.
_EXTERNAL_RE = re.compile(
    r"\b(according to|studies show|research (?:shows|suggests|indicates)|"
    r"a (?:recent )?(?:study|survey|report)|experts? (?:say|agree|argue)|"
    r"(?:is|are) the (?:most|fastest|best|largest|leading)|"
    r"benchmarks? show|documentation says|the docs? (?:say|state)|"
    r"as of \d{4}|industry standard|widely (?:used|adopted|regarded))\b",
    re.IGNORECASE)

# First-person process language — the author is the authority, no URL possible.
_SELF_RE = re.compile(
    r"\b(i|my|me|we|our)\b|\bthe (?:log|error|stack trace|terminal|output|console)\b",
    re.IGNORECASE)

_URL_RE = re.compile(r"https?://[^\s)\]\"'>,]+")

# Identifiers that look like figures but assert nothing.
_IDENTIFIER_RE = re.compile(
    r"\b(?:v?\d+\.\d+(?:\.\d+)?|:\d{2,5}\b|20\d{2}|python\s*3\.\d+|node\s*\d+)",
    re.IGNORECASE)

# A throughput/latency/memory claim is the one a commenter will actually try
# to reproduce, so "22,400 req/s" with no machine or method is a credibility
# liability even when the author did measure it. SELF provenance is not
# enough for these — they also need methodology in the same paragraph.
_PERF_RE = re.compile(
    r"\d[\d,.]*\s*(?:req/s|rps|qps|requests?/s|ops/s|ms|milliseconds?|seconds?|MB|GB|KB|x faster|x slower)\b",
    re.IGNORECASE)
_METHOD_RE = re.compile(
    # A tool...
    r"\b(?:wrk|apachebench|\bab\b|hyperfine|locust|k6|jmeter|pytest-benchmark|siege|oha)\b"
    # ...or a machine...
    r"|\b\d+\s*(?:-|\s)?(?:core|vcpu|cpu|gb|thread)s?\b"
    r"|\bon (?:a|my|the) [\w\s-]{0,30}?(?:mac|m1|m2|m3|m4|laptop|vm|droplet|instance|box|server|macbook)\b"
    # ...or a sample size / distribution.
    r"|\b(?:over|across) \d+ (?:runs?|iterations?|requests?|samples?)\b"
    r"|\b\d+ connections\b|\b(?:median|average|mean) of\b|\bp9[59]\b"
    r"|\b(?:single process|cold start|all keys warm|warm cache)\b",
    re.IGNORECASE)


BLOCKING = "UNSOURCED"


@dataclass
class Claim:
    text: str = ""            # the sentence the assertion lives in
    figure: str = ""          # the specific number, or "" for a qualitative claim
    kind: str = ""            # number | external | superlative
    line: int = 0
    provenance: str = ""      # BRAIN | EVIDENCE | SELF | UNSOURCED
    receipt: str = ""         # which story/URL backs it

    def as_dict(self):
        return asdict(self)


def _protected_spans(article):
    """Code and asset URLs are not claims — a port number in a config block
    asserts nothing about the world.

    Tables are deliberately NOT protected here, which is the opposite of
    humanizer.py's masking. humanizer masks a table so a rewrite cannot mangle
    it; a before/after table is the most claim-dense element in these articles
    and every figure in it needs a receipt.
    """
    spans = []
    for rx in (re.compile(r"```.*?\n.*?```", re.DOTALL),
               re.compile(r"`[^`\n]+`"),
               re.compile(r"!\[[^\]]*\]\([^)]*\)"),
               re.compile(r"\]\([^)]*\)")):
        spans += [m.span() for m in rx.finditer(article)]
    return spans


_TABLE_ROW_RE = re.compile(r"^[ \t]*\|(.+)\|[ \t]*$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^[ \t]*\|[-: |]+\|[ \t]*$")


def _table_claims(article, spans):
    """One claim per figure per table row, labelled by the row's first cell so
    the map reads 'Project Timeline: 47 minutes' rather than a bare number."""
    out = []
    for m in _TABLE_ROW_RE.finditer(article):
        row = m.group(0)
        if _TABLE_SEP_RE.match(row) or _in_protected(m.start(), spans):
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if not cells:
            continue
        label = cells[0] or "row"
        line = article.count("\n", 0, m.start()) + 1
        scrub = _IDENTIFIER_RE.sub(" ", " | ".join(cells[1:]))
        for fm in _CLAIM_NUM_RE.finditer(scrub):
            fig = fm.group(0).strip()
            if fig:
                out.append(Claim(text=f"[table] {label}: {' vs '.join(cells[1:])}"[:220],
                                 figure=fig, kind="number", line=line))
    return out


def _in_protected(pos, spans):
    return any(a <= pos < b for a, b in spans)


def _sentences_with_pos(text):
    out, start = [], 0
    for m in re.finditer(r"[^.!?\n]+[.!?]|[^\n]+", text):
        s = m.group(0).strip()
        if s:
            out.append((s, m.start()))
        start = m.end()
    return out


def extract(article):
    """Enumerate every checkable assertion in the prose."""
    spans = _protected_spans(article)
    claims = []
    seen = set()

    claims += _table_claims(article, spans)
    seen.update((c.line, c.figure.lower(), c.text[:50].lower()) for c in claims)

    for sent, pos in _sentences_with_pos(article):
        if _in_protected(pos, spans):
            continue
        stripped = sent.lstrip()
        # Table rows are handled above with their row label for context.
        if stripped.startswith(("#", "|", ">", "```", "TAGS:", "META:")):
            continue
        line = article.count("\n", 0, pos) + 1

        # Strip identifiers so "psycopg2 2.9.9" doesn't register as a figure.
        scrub = _IDENTIFIER_RE.sub(" ", sent)

        found_numbers = []
        for m in _CLAIM_NUM_RE.finditer(scrub):
            fig = m.group(0).strip()
            if fig:
                found_numbers.append(fig)

        for fig in found_numbers:
            key = (line, fig.lower(), sent[:50].lower())
            if key in seen:
                continue
            seen.add(key)
            claims.append(Claim(text=re.sub(r"\s+", " ", sent)[:220],
                                figure=fig, kind="number", line=line))

        if _EXTERNAL_RE.search(sent):
            key = (line, "", sent[:50].lower())
            if key not in seen:
                seen.add(key)
                claims.append(Claim(text=re.sub(r"\s+", " ", sent)[:220],
                                    figure="", kind="external", line=line))

    return claims


def _norm_url(u):
    return re.sub(r"^https?://", "", str(u).strip().rstrip(".,;:!?)]}\"'")).rstrip("/").lower()


def classify(claims, brain=None, evidence_urls=None, evidence_text=None, article=""):
    """Attach provenance to each claim."""
    brain = brain if brain is not None else brain_mod.Brain()
    verified_nums = brain.verified_numbers()
    brain_urls = {_norm_url(u) for u in brain.verified_urls()}
    ev_urls = {_norm_url(u) for u in (evidence_urls or []) if u}
    ev_blob = " ".join(str(t) for t in (evidence_text or [])).lower()

    for c in claims:
        if c.kind == "external":
            # An external assertion needs a URL in the same sentence, or in the
            # evidence the writer was handed.
            urls_here = [_norm_url(u) for u in _URL_RE.findall(c.text)]
            hit = next((u for u in urls_here if u in ev_urls or u in brain_urls), "")
            if hit:
                c.provenance, c.receipt = "EVIDENCE", hit
            elif urls_here:
                c.provenance, c.receipt = "UNSOURCED", f"cites {urls_here[0]}, not in evidence"
            else:
                c.provenance, c.receipt = "UNSOURCED", "no URL"
            continue

        atoms = brain_mod.atomize_numbers(c.figure)
        if atoms & verified_nums:
            c.provenance = "BRAIN"
            c.receipt = next((s.title for s in brain.stories
                              if brain_mod.atomize_numbers(
                                  " ".join(s.numbers) + " " + s.body) & atoms), "brain")
            continue

        norm = brain_mod.normalize_number(c.figure)
        if norm and norm in ev_blob.replace(",", "").replace(" ", ""):
            c.provenance, c.receipt = "EVIDENCE", "appears in research evidence"
            continue

        # Money and audience counts are never self-evidenced — the author cannot
        # be the sole authority on somebody's revenue.
        money = re.search(r"\$|mrr|arr|customers?|subscribers?|users?|followers?|downloads?",
                          c.figure, re.IGNORECASE)
        if not money and _PERF_RE.search(c.figure):
            if _METHOD_RE.search(c.text):
                c.provenance, c.receipt = "SELF", "measured, methodology stated"
            else:
                c.provenance = "NEEDS_METHOD"
                c.receipt = ("throughput/latency/memory claim with no machine, tool "
                             "or sample size — this is the number a commenter will "
                             "try to reproduce")
            continue

        if not money and _SELF_RE.search(c.text):
            c.provenance = "SELF"
            c.receipt = "first-person process detail"
            continue

        c.provenance = "UNSOURCED"
        c.receipt = "no receipt"

    return claims


@dataclass
class ClaimsMap:
    title: str = ""
    slug: str = ""
    claims: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)

    @property
    def unsourced(self):
        return [c for c in self.claims if c.provenance == BLOCKING]

    @property
    def coverage(self):
        if not self.claims:
            return 1.0
        return 1.0 - len(self.unsourced) / len(self.claims)

    def summary(self):
        return (f"{len(self.claims)} claim(s), {self.coverage:.0%} sourced "
                f"({self.counts.get('BRAIN', 0)} brain, {self.counts.get('EVIDENCE', 0)} evidence, "
                f"{self.counts.get('SELF', 0)} first-person, "
                f"{self.counts.get('NEEDS_METHOD', 0)} need methodology, "
                f"{len(self.unsourced)} unsourced)")

    def as_dict(self):
        return {"title": self.title, "slug": self.slug,
                "counts": self.counts, "coverage": round(self.coverage, 3),
                "claims": [c.as_dict() for c in self.claims]}


def build_map(article, title="", slug="", brain=None, evidence_urls=None,
              evidence_text=None):
    claims = classify(extract(article), brain=brain, evidence_urls=evidence_urls,
                      evidence_text=evidence_text, article=article)
    counts = {}
    for c in claims:
        counts[c.provenance] = counts.get(c.provenance, 0) + 1
    return ClaimsMap(title=title, slug=slug, claims=claims, counts=counts)


def render(cmap):
    """The .claims.md file that ships beside the draft."""
    L = [f"# Claims map — {cmap.title}", "",
         cmap.summary(), ""]
    if cmap.unsourced:
        L += ["## Unsourced — fix before publishing", ""]
        for c in cmap.unsourced:
            fig = f"`{c.figure}` " if c.figure else ""
            L += [f"- **line {c.line}** {fig}({c.receipt})",
                  f"  > {c.text}", ""]
    else:
        L += ["Every checkable claim has a receipt.", ""]

    needs = [c for c in cmap.claims if c.provenance == "NEEDS_METHOD"]
    if needs:
        L += ["## Performance claims missing methodology", "",
              "These will be fact-checked in the comments. State the machine, the",
              "tool and the sample size in the same paragraph, or hedge the number.", ""]
        for c in needs:
            L += [f"- **line {c.line}** `{c.figure}`", f"  > {c.text}", ""]

    for label, heading in (("BRAIN", "Backed by the author's own measurements"),
                           ("EVIDENCE", "Backed by cited research"),
                           ("SELF", "Measured by the author, methodology stated")):
        group = [c for c in cmap.claims if c.provenance == label]
        if not group:
            continue
        L += [f"## {heading} ({len(group)})", ""]
        for c in group:
            fig = f"`{c.figure}` — " if c.figure else ""
            L.append(f"- line {c.line}: {fig}{c.text[:130]}")
            if c.receipt and label != "SELF":
                L.append(f"  receipt: {c.receipt}")
        L.append("")

    L += ["---", "*Generated by claims.py. Re-check with "
          "`python agent.py claims <draft.md>` after any edit.*"]
    return "\n".join(L)


def verify(article, cmap):
    """Re-extract from the article and compare against a stored map.

    Hasan's piece ends with '23 of 23 facts matched'. This is that check: an
    edit that introduces a figure the map never approved shows up as drift.
    """
    current = {(c.figure.lower(), c.line) for c in extract(article) if c.figure}
    known = {(c.figure.lower(), c.line) for c in cmap.claims if c.figure}
    new = current - known
    gone = known - current
    drift = ([f"new unmapped figure: {f} (line {l})" for f, l in sorted(new)]
             + [f"mapped figure no longer present: {f} (line {l})" for f, l in sorted(gone)])
    matched = len(current & known)
    return (not new), drift, matched, len(current)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — offline, no API key:
#   python claims.py medium_drafts/some-post.md
#   python claims.py --json medium_drafts/*.md
#   python claims.py --write medium_drafts/some-post.md   (emit .claims.md)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import glob as _glob

    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        print("Usage: python claims.py [--json] [--write] <file.md> ...")
        sys.exit(0)

    paths = []
    for a in args:
        paths.extend(sorted(_glob.glob(a)) or [a])

    b = brain_mod.load()
    results, worst = [], 1.0
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        title = next((l.lstrip("# ").strip() for l in text.splitlines()
                      if l.startswith("# ")), os.path.basename(path))
        slug = os.path.splitext(os.path.basename(path))[0]
        # A draft's own cited URLs count as its evidence at the CLI — there is no
        # research context on disk to compare against.
        cmap = build_map(text, title=title, slug=slug, brain=b,
                         evidence_urls=_URL_RE.findall(text))
        worst = min(worst, cmap.coverage)
        results.append(cmap)

        if "--write" in flags:
            out = os.path.join(os.path.dirname(path), slug + ".claims.md")
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(render(cmap))
            print(f"wrote {out}")

        if "--json" not in flags:
            print(f"\n{'=' * 72}\n{path}\n{'=' * 72}")
            print(cmap.summary())
            for c in cmap.unsourced[:12]:
                fig = f"`{c.figure}` " if c.figure else ""
                print(f"  UNSOURCED line {c.line}: {fig}{c.text[:100]}")

    if "--json" in flags:
        print(json.dumps([c.as_dict() for c in results], indent=2))
    elif len(results) > 1:
        print(f"\n{'=' * 72}\nSUMMARY (by claim coverage)")
        for cmap in sorted(results, key=lambda m: m.coverage):
            print(f"  {cmap.coverage:6.0%}  {len(cmap.unsourced):3d} unsourced  {cmap.slug}")
