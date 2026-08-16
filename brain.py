"""
brain.py — the author's own material, loaded before every draft.

From learnwithhasan.com's "AI Content Factory": the scarce input is not text
generation, it is first-hand evidence. A model with nothing real to work from
will invent a "$4,200 MRR" because the prompt asked for a specific number and
specificity is what it was trained to produce.

judge.py attacks that from the proof side — it blocks a figure with no source.
This module attacks the cause: give the writer real, sourced material up front
so it never needs to reach for a plausible number.

Three files, all hand-written by the author, all optional:

  brain/beliefs.md  positions worth arguing — gives a piece a spine
  brain/stories.md  things that actually happened, WITH numbers and a source
  brain/voice.md    prose rules (complements the measured fingerprint that
                    humanizer.py derives from voice/ samples)

Stories are parsed structurally so their numbers become the *allowed* set for
claims.py: a figure in a story's `numbers:` field is verified, one that appears
from nowhere is not.

Only the `numbers:` field counts. Prose in the body is used for relevance
ranking and never for provenance, because a story legitimately discusses figures
it is arguing against — an entry describing a fabricated "$200 saved" claim must
not certify $200 as verified and launder it into the next article.

Story format — a level-2 heading, a short field block, then prose:

    ## Cut the morning sweep from 9 minutes to 40 seconds
    - when: 2026-03
    - numbers: 9 min -> 40 s, 38 HTTP calls -> 6
    - source: https://github.com/you/repo/commit/abc1234
    - tags: python, automation, github-actions

    Ran every source serially, including fifteen one-at-a-time Hacker News
    item lookups...

Public API:
    load(directory)             -> Brain
    Brain.for_topic(topic)      -> str   (relevance-ranked prompt block)
    Brain.verified_numbers()    -> set[str]
    Brain.verified_urls()       -> set[str]
    seed_entry(...)             -> appends a candidate to brain/inbox.md
"""

import os
import re
import glob
from dataclasses import dataclass, field

BRAIN_DIR = os.getenv("BRAIN_DIR", "brain")
INBOX = "inbox.md"

# Same stopword set shape as research_engine, kept local so brain.py stays
# importable on its own.
_STOP = set("""a an the and or but if of to in on for with at by from as is are was were be
been being it its this that these those you your i my we our they their he she them then
than so not no do does did have has had will would can could should there here what when
where which who how why all any some more most other into out up down over under new best
using use used make made get got just like about has how why can vs versus my me""".split())


def _tokens(text):
    return {w for w in re.findall(r"[a-z][a-z0-9+#.-]{2,}", (text or "").lower())
            if w not in _STOP}


# A "number" for provenance purposes: money, percentages, multipliers, counts
# with units, and bare counts of 3+ digits. Deliberately broad — the cost of an
# extra allowed number is low, the cost of a missed fabrication is high.
_NUM_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s*(?:/month|per month|mrr|arr|/mo|k|m)?|"
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:%|x|ms|s|sec|seconds|min|minutes|hours|days|weeks|"
    r"months|MB|GB|KB|req/s|rps|lines|files|commits|users|customers|stars|calls)\b|"
    r"\b\d{3,}\b",
    re.IGNORECASE)

_URL_RE = re.compile(r"https?://[^\s)\]\"'>,]+")


_BARE_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize_number(tok):
    """'$4,200' and '$4200' are the same claim; '40 s' and '40s' likewise."""
    t = str(tok).strip().lower().replace(",", "")
    t = re.sub(r"\s+", "", t)
    return t.rstrip(".")


def atomize_numbers(blob):
    """Every individual figure in a string, in both unit-bearing and bare form.

    'Cut 9 min to 40 s across 38 HTTP calls' -> {9min, 40s, 9, 40, 38}
    Keeping both forms means a draft saying "40 seconds" and a brain entry
    saying "40 s" agree, and a draft saying plain "38" still matches.
    """
    blob = str(blob or "")
    out = set()
    for m in _NUM_RE.findall(blob):
        out.add(normalize_number(m))
    for m in _BARE_NUM_RE.findall(blob):
        n = normalize_number(m)
        out.add(n)
        # 40.0 and 40 are the same figure
        if n.endswith(".0"):
            out.add(n[:-2])
    return {x for x in out if x}


@dataclass
class Story:
    title: str = ""
    when: str = ""
    numbers: list = field(default_factory=list)
    source: str = ""
    tags: list = field(default_factory=list)
    body: str = ""

    def relevance(self, topic_tokens):
        mine = _tokens(self.title) | _tokens(" ".join(self.tags)) | _tokens(self.body[:600])
        if not mine or not topic_tokens:
            return 0.0
        return len(mine & topic_tokens) / len(topic_tokens | mine)

    def render(self):
        L = [f"  STORY: {self.title}"]
        if self.when:
            L.append(f"    when: {self.when}")
        if self.numbers:
            L.append(f"    verified numbers: {', '.join(self.numbers)}")
        if self.source:
            L.append(f"    source: {self.source}")
        if self.body:
            L.append(f"    what happened: {re.sub(r'\s+', ' ', self.body)[:400]}")
        return "\n".join(L)


@dataclass
class Brain:
    beliefs: list = field(default_factory=list)
    stories: list = field(default_factory=list)
    voice_rules: list = field(default_factory=list)
    directory: str = BRAIN_DIR

    def __bool__(self):
        return bool(self.beliefs or self.stories or self.voice_rules)

    def verified_numbers(self):
        """Figures from the declared `numbers:` field ONLY — never from prose.

        Two reasons. First, atomisation: a declared 'numbers: 9 min -> 40 s'
        has to yield {9min, 40s, 9, 40}, because the question claims.py asks is
        "does 40 appear in the verified set", never "does the string
        '9 min -> 40 s' appear".

        Second, and the reason prose is excluded: a story body legitimately
        mentions numbers it is *arguing against*. An entry describing a
        fabricated "$200 saved" claim would otherwise certify $200 as verified
        and launder it into every future article. The `numbers:` field is the
        author explicitly asserting "I stand behind these"; the body is
        narrative, and is used for relevance ranking only.
        """
        out = set()
        for s in self.stories:
            for blob in s.numbers:
                out.update(atomize_numbers(blob))
        return out

    def verified_urls(self):
        out = set()
        for s in self.stories:
            if s.source:
                out.add(s.source.strip())
            out.update(_URL_RE.findall(s.body))
        return out

    def for_topic(self, topic, max_stories=4, max_beliefs=5):
        """Relevance-ranked block for the draft prompt. Dumping the whole brain
        wastes context and buries the story that actually fits."""
        if not self:
            return ""
        tk = _tokens(topic)
        L = ["AUTHOR'S OWN MATERIAL — this is the evidence you have. Prefer it over "
             "anything you would otherwise invent."]

        ranked = sorted(self.stories, key=lambda s: -s.relevance(tk))
        picked = [s for s in ranked if s.relevance(tk) > 0][:max_stories] or ranked[:2]
        if picked:
            L.append("\nTHINGS THAT ACTUALLY HAPPENED TO THE AUTHOR (cite these numbers "
                     "freely — they are verified. Do NOT round them or 'improve' them):")
            L += [s.render() for s in picked]

        if self.beliefs:
            rb = sorted(self.beliefs, key=lambda b: -len(_tokens(b) & tk))
            L.append("\nPOSITIONS THE AUTHOR HOLDS (the piece should be consistent with these; "
                     "one of them can be the article's spine):")
            L += [f"  - {b}" for b in rb[:max_beliefs]]

        if self.voice_rules:
            L.append("\nVOICE RULES:\n" + "\n".join(f"  - {r}" for r in self.voice_rules)[:1200])

        return "\n".join(L)

    def summary(self):
        return (f"{len(self.stories)} stor{'y' if len(self.stories) == 1 else 'ies'}, "
                f"{len(self.beliefs)} belief(s), "
                f"{len(self.verified_numbers())} verified number(s)"
                + (", voice rules" if self.voice_rules else ""))


def _parse_stories(text):
    """Split on ## headings; read the '- key: value' block under each."""
    out = []
    chunks = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
    for chunk in chunks:
        lines = chunk.splitlines()
        st = Story(title=lines[0].strip())
        body_lines = []
        for line in lines[1:]:
            # (.*) not (.+): a field left blank — '- source:' with nothing after
            # it, which is the normal case for work done on your own machine —
            # must still be consumed as a field, not fall through into the body.
            m = re.match(r"^\s*[-*]\s*(when|numbers|source|tags)\s*:\s*(.*)$", line, re.IGNORECASE)
            if m:
                key, val = m.group(1).lower(), m.group(2).strip()
                if key == "when":
                    st.when = val
                elif key == "source":
                    st.source = val
                elif key == "numbers":
                    st.numbers = [v.strip() for v in re.split(r"[,;]", val) if v.strip()]
                elif key == "tags":
                    st.tags = [v.strip() for v in re.split(r"[,;]", val) if v.strip()]
            else:
                body_lines.append(line)
        st.body = "\n".join(body_lines).strip()
        if st.title:
            out.append(st)
    return out


def _parse_beliefs(text):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("- ", "* ")):
            s = s[2:].strip()
            if len(s) > 15:
                out.append(s)
    return out


def _read(directory, name):
    path = os.path.join(directory, name)
    if not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except Exception as e:
        print(f"[brain] could not read {path}: {e}")
        return ""


def load(directory=None):
    directory = directory or BRAIN_DIR
    b = Brain(directory=directory)
    if not os.path.isdir(directory):
        return b
    b.stories = _parse_stories(_read(directory, "stories.md"))
    b.beliefs = _parse_beliefs(_read(directory, "beliefs.md"))
    # Bullets only. These files carry explanatory prose for the human editing
    # them, and shipping that preamble to the model as "voice rules" would tell
    # it about humanizer.py instead of about how to write.
    b.voice_rules = _parse_beliefs(_read(directory, "voice.md"))
    return b


# ═══════════════════════════════════════════════════════════════════════════════
# FLYWHEEL — after a piece ships, propose what it taught. Candidates land in
# brain/inbox.md for the author to approve by hand and move into stories.md.
# Nothing is auto-promoted: an unreviewed "fact" in the brain would be laundered
# into every future article as verified.
# ═══════════════════════════════════════════════════════════════════════════════

SEED_PROMPT = """You just finished this article. Propose what should be added to the author's permanent knowledge base.

Only propose entries that are TRUE and SPECIFIC to what this piece established. Do not propose generic writing advice, and do not propose a "story" the article itself invented — if a number in the article had no source, it does not belong here.

ARTICLE TITLE: {title}

ARTICLE:
---
{article}
---

{evidence}

Return ONLY a JSON object:
{{
  "stories": [
    {{
      "title": "what happened, as a headline",
      "numbers": ["only figures that were measured or came from a cited source"],
      "source": "a real URL from the evidence, or empty string if this was the author's own machine",
      "tags": ["3-5 lowercase tags"],
      "body": "2-3 sentences on what happened and what it cost"
    }}
  ],
  "beliefs": ["at most 2 positions this piece demonstrated — each a claim someone could disagree with, not a platitude"]
}}

If the piece established nothing durable, return empty lists. That is a valid answer and better than padding the brain."""


def seed_entry(article, title, ask_ai, evidence_text=None, directory=None):
    """Ask what this piece taught, write candidates to brain/inbox.md."""
    directory = directory or BRAIN_DIR
    ev = ""
    if evidence_text:
        ev = "SOURCES THE WRITER WAS GIVEN:\n" + "\n".join(f"  - {e}" for e in evidence_text[:8])

    import json
    raw = ask_ai(SEED_PROMPT.format(title=title, article=article[:9000], evidence=ev),
                 max_tokens=1200)
    s = re.sub(r"^```(?:json)?\s*", "", str(raw).strip(), flags=re.MULTILINE)
    s = re.sub(r"```\s*$", "", s, flags=re.MULTILINE).strip()
    a, b = s.find("{"), s.rfind("}")
    if a != -1 and b != -1:
        s = s[a:b + 1]
    data = json.loads(s, strict=False)

    stories = [x for x in (data.get("stories") or []) if isinstance(x, dict) and x.get("title")]
    beliefs = [str(x).strip() for x in (data.get("beliefs") or []) if str(x).strip()]
    if not stories and not beliefs:
        return 0

    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, INBOX)
    from datetime import datetime, timezone
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [f"\n<!-- candidates from: {title} ({stamp}) -->"]
    for st in stories:
        lines.append(f"\n## {st.get('title', '').strip()}")
        lines.append(f"- when: {stamp}")
        nums = st.get("numbers") or []
        if nums:
            lines.append(f"- numbers: {', '.join(str(n) for n in nums)}")
        if st.get("source"):
            lines.append(f"- source: {st['source']}")
        tags = st.get("tags") or []
        if tags:
            lines.append(f"- tags: {', '.join(str(t) for t in tags)}")
        lines.append("")
        lines.append(str(st.get("body", "")).strip())
    if beliefs:
        lines.append("\n<!-- candidate beliefs — move to beliefs.md if you agree -->")
        lines += [f"- {b}" for b in beliefs]

    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"[brain] {len(stories)} story + {len(beliefs)} belief candidate(s) -> {path}")
    return len(stories) + len(beliefs)


SCAFFOLD = {
    "beliefs.md": """# Beliefs

Positions you actually hold. Each one should be something a competent engineer
could disagree with — that is what makes a piece worth reading. Delete these
examples and write your own.

- Most "AI agent" tutorials are architecture diagrams with no working orchestration, which is why they rank but do not help.
- A tool that needs a README longer than its source is a tool with the wrong interface.
- Publishing a benchmark without the machine spec is publishing a vibe.
""",
    "stories.md": """# Stories

Things that actually happened to you, with numbers you can defend. Anything not
here (and not in the research evidence) gets flagged by `python agent.py claims`.

Only the `numbers:` field is treated as verified. The prose body is for context
and relevance ranking — write freely there about figures you are arguing
against, they will not be certified.

Rule of thumb: if you cannot re-run something and get the number back, leave it
out. Delete this example and write your own.

## Cut the morning research sweep from 9 minutes to 40 seconds
- when: 2026-08
- numbers: 9 min -> 40 s, 38 HTTP calls -> 6, 15 sequential lookups
- source:
- tags: python, automation, concurrency, github-actions

Every source ran serially, including fifteen one-at-a-time Hacker News item
lookups. Moving the sweep to a thread pool with per-source timeouts took the
whole run under a minute. The slow part was never the model.
""",
    "voice.md": """# Voice rules

Prose rules that are specific to you. humanizer.py already measures sentence
length, contraction density and punctuation habits from the samples in `voice/`
— this file is for things a measurement cannot capture.

- Name the version. "psycopg2 2.9.9", not "the Postgres driver".
- Never open with weather, coffee, or the time of day unless it is load-bearing.
- If a paragraph could appear in any article on any topic, cut it.
- Admit the thing that is still broken. End on it if it is interesting.
""",
}


def scaffold(directory=None):
    """Create the three files with worked examples if they do not exist."""
    directory = directory or BRAIN_DIR
    os.makedirs(directory, exist_ok=True)
    made = []
    for name, content in SCAFFOLD.items():
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            made.append(name)
    return made


# ═══════════════════════════════════════════════════════════════════════════════
# CLI:
#   python brain.py init          create brain/ with worked examples
#   python brain.py list          show what is loaded
#   python brain.py check <topic> preview the block a draft on <topic> would get
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "init":
        made = scaffold()
        print(f"created: {', '.join(made)}" if made else
              f"{BRAIN_DIR}/ already set up — nothing overwritten")

    elif cmd == "list":
        b = load()
        if not b:
            print(f"No brain at {BRAIN_DIR}/. Run: python brain.py init")
            sys.exit(0)
        print(b.summary())
        print(f"\nSTORIES ({len(b.stories)}):")
        for s in b.stories:
            src = s.source or "(own machine)"
            print(f"  - {s.title}\n      numbers: {', '.join(s.numbers) or 'none'}\n      source: {src}")
        print(f"\nBELIEFS ({len(b.beliefs)}):")
        for x in b.beliefs:
            print(f"  - {x}")
        nums = sorted(b.verified_numbers())
        print(f"\nVERIFIED NUMBERS ({len(nums)}): {', '.join(nums[:25])}")

    elif cmd == "check":
        topic = " ".join(sys.argv[2:]) or "python automation"
        block = load().for_topic(topic)
        print(block or f"(empty brain — run: python brain.py init)")

    else:
        print(__doc__)
        print("Usage: python brain.py init | list | check <topic>")
