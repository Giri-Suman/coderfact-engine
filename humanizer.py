"""
humanizer.py — AI-tell detection and repair for CoderFact drafts.

Design borrowed from blader/humanizer (33 patterns from Wikipedia's "Signs of AI
writing"), adapted to this engine's constraints:

  * Everything is FENCE-AWARE. Code blocks, mermaid, pipe tables, image URLs,
    the ```json?chameleon widget and the TAGS:/META: lines are masked out before
    scanning so a regex never mangles working code.
  * Detection is deterministic (regex + structural checks), so the score is
    reproducible and cheap. The LLM is only called for the repair pass.
  * The loop is closed: scan -> repair with the ACTUAL findings -> re-scan.
    agent.py previously ran a humanize pass, printed lint warnings, and shipped
    the draft anyway.

Public API:
    scan(md)                    -> list[Finding]
    score(md, findings)         -> HumanScore
    autofix(md)                 -> (fixed_md, n_applied)
    voice_fingerprint(samples)  -> str  (style brief for the rewrite prompt)
    humanize(md, ask_ai, ...)   -> (final_md, Report)
"""

import os
import re
import glob
import json
import math
from dataclasses import dataclass, field, asdict

# ═══════════════════════════════════════════════════════════════════════════════
# MASKING — protect everything that must survive a rewrite byte-for-byte.
# ═══════════════════════════════════════════════════════════════════════════════

_FENCE_RE = re.compile(r"```.*?\n.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_URL_RE = re.compile(r"\]\([^)]*\)")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)
_META_RE = re.compile(r"^\s*(?:TAGS|META):.*$", re.MULTILINE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# Private-use sentinel: cannot occur in real markdown, survives regex passes.
_SENT = "\ue000"
_MASK = _SENT + "M{}" + _SENT
_MASK_FIND = re.compile(_SENT + r"M(\d+)" + _SENT)


def mask_protected(md):
    """Replace protected regions with opaque sentinels. Returns (masked, store)."""
    store = []

    def _stash(m):
        store.append(m.group(0))
        return _MASK.format(len(store) - 1)

    out = md
    for rx in (
        _FENCE_RE,
        _HTML_COMMENT_RE,
        _TABLE_ROW_RE,
        _META_RE,
        _IMAGE_RE,
        _LINK_URL_RE,
        _INLINE_CODE_RE,
    ):
        out = rx.sub(_stash, out)
    return out, store


def unmask(masked, store):
    """Restore sentinels. Unknown indexes are left alone rather than crashing."""

    def _restore(m):
        i = int(m.group(1))
        return store[i] if 0 <= i < len(store) else m.group(0)

    # Loop: a restored block can never contain a sentinel, so one pass is enough,
    # but guard against pathological input anyway.
    for _ in range(3):
        new = _MASK_FIND.sub(_restore, masked)
        if new == masked:
            break
        masked = new
    return masked


def protected_ratio(md):
    """Fraction of the document that is code/tables/URLs. Used to skip scoring
    documents that are almost entirely code."""
    masked, store = mask_protected(md)
    protected_chars = sum(len(s) for s in store)
    return protected_chars / max(len(md), 1)


# ═══════════════════════════════════════════════════════════════════════════════
# PATTERN REGISTRY — 33 patterns from the humanizer taxonomy, plus this engine's
# own template-leak bans (the phrases older prompt versions taught the model).
#
# severity: "high"   -> always worth a repair pass
#           "medium" -> repair if budget allows
#           "low"    -> advisory only, never triggers a repair on its own
# autofix:  deterministic rewrite is safe (no meaning change)
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Pattern:
    pid: int
    name: str
    severity: str
    fix: str
    rx: "re.Pattern | None" = None
    check: "callable | None" = None  # structural checks get (masked_md) -> [(line, excerpt)]
    autofix: "callable | None" = None
    cap: int = 6  # max findings reported per pattern, keeps reports readable


def _rx(p, flags=re.IGNORECASE):
    return re.compile(p, flags)


AI_VOCAB = [
    "delve", "leverage", "robust", "seamless", "unleash", "empower",
    "groundbreaking", "revolutionize", "game-changer", "synergy", "cutting-edge",
    "supercharge", "paradigm", "tapestry", "myriad", "plethora", "ever-evolving",
    "transformative", "noteworthy", "comprehensive", "intricate", "elevate",
    "embark", "unparalleled", "spearhead", "holistic", "testament", "landscape",
    "realm", "bolster", "streamline", "foster", "facilitate", "utilize",
    "showcase", "underscore", "harness", "pivotal", "multifaceted", "nuanced",
]

FILLER_MAP = {
    r"\bin order to\b": "to",
    r"\bdue to the fact that\b": "because",
    r"\bat this point in time\b": "now",
    r"\bfor the purpose of\b": "for",
    r"\bin the event that\b": "if",
    r"\ba large number of\b": "many",
    r"\bthe majority of\b": "most",
    r"\bin spite of the fact that\b": "although",
    r"\bhas the ability to\b": "can",
    r"\bit is important to note that\b": "",
    r"\bit is worth noting that\b": "",
    r"\bneedless to say,?\s*": "",
}


def _sentences(text):
    """Rough sentence split that ignores decimals and common abbreviations."""
    text = re.sub(r"(\d)\.(\d)", r"\1․\2", text)
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.replace("․", ".").strip() for p in parts if p.strip()]


def _paragraphs_with_lines(md):
    """Yield (start_line, paragraph_text) for prose paragraphs."""
    out = []
    line_no = 1
    for block in re.split(r"\n\s*\n", md):
        if block.strip():
            out.append((line_no, block))
        line_no += block.count("\n") + 2
    return out


# ── structural checks ─────────────────────────────────────────────────────────


def _is_list_block(para):
    """A run of bullets is not a paragraph — one em-dash per bullet is normal
    punctuation, not the overuse tell."""
    lines = [l for l in para.splitlines() if l.strip()]
    if not lines:
        return True
    listish = sum(1 for l in lines if re.match(r"^\s*(?:[-*+]\s|\d+[.)]\s|#{1,6}\s|>)", l))
    return listish >= max(2, len(lines) * 0.5)


def _check_emdash(masked):
    hits = []
    for line_no, para in _paragraphs_with_lines(masked):
        if _is_list_block(para):
            continue
        n = para.count("—")
        if n >= 3:
            hits.append((line_no, f"{n} em-dashes in one paragraph"))
    return hits


def _check_boldface(masked):
    bolds = re.findall(r"\*\*[^*\n]{2,60}\*\*", masked)
    # Bolded list headers are counted by their own pattern; don't double-charge.
    inline = [b for b in bolds if not re.search(r"^\s*[-*]\s*" + re.escape(b), masked, re.MULTILINE)]
    if len(inline) > 6:
        return [(0, f"{len(inline)} bold spans in prose")]
    return []


def _check_title_case_headings(masked):
    hits = []
    for i, line in enumerate(masked.splitlines(), 1):
        m = re.match(r"^(#{2,4})\s+(.*\S)\s*$", line)
        if not m:
            continue
        words = [w for w in re.findall(r"[A-Za-z][\w'-]*", m.group(2))]
        if len(words) < 4:
            continue
        # Ignore acronyms and words that are capitalised because they're names.
        capped = sum(1 for w in words[1:] if w[0].isupper() and not w.isupper())
        if capped >= max(3, int(len(words) * 0.6)):
            hits.append((i, m.group(2)[:70]))
    return hits


def _check_staccato(masked):
    hits = []
    for line_no, para in _paragraphs_with_lines(masked):
        if para.lstrip().startswith(("#", ">", "-", "*", "|")):
            continue
        sents = _sentences(para)
        run = 0
        for s in sents:
            if len(s.split()) <= 4:
                run += 1
                if run >= 3:
                    hits.append((line_no, " ".join(sents[:4])[:70]))
                    break
            else:
                run = 0
    return hits


def _check_fragmented_headers(masked):
    """Heading immediately restated by the sentence under it."""
    hits = []
    lines = masked.splitlines()
    stop = {"the", "a", "an", "of", "to", "in", "for", "and", "is", "it", "this",
            "that", "with", "you", "your", "how", "why", "what", "does", "do"}
    for i, line in enumerate(lines):
        m = re.match(r"^#{2,4}\s+(.*\S)\s*$", line)
        if not m:
            continue
        head_words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", m.group(1))} - stop
        if len(head_words) < 3:
            continue
        for nxt in lines[i + 1: i + 4]:
            if not nxt.strip():
                continue
            # Image captions and pull-quotes restate the heading by design.
            if re.match(r"^\s*[*_>|]", nxt) or re.match(r"^\s*\*.*\*\s*$", nxt):
                break
            first = _sentences(nxt)
            if not first:
                break
            body_words = {w.lower() for w in re.findall(r"[A-Za-z]{3,}", first[0])} - stop
            if body_words and len(head_words & body_words) / len(head_words) >= 0.6:
                hits.append((i + 1, first[0][:70]))
            break
    return hits


def _check_rule_of_three(masked):
    triples = re.findall(r"\b[\w'-]+,\s+[\w'-]+,?\s+and\s+[\w'-]+\b", masked)
    if len(triples) >= 4:
        return [(0, f"{len(triples)} three-item groupings — vary the group size")]
    return []


def _check_hedging(masked):
    hedges = r"\b(perhaps|maybe|possibly|potentially|arguably|somewhat|relatively|fairly|quite|generally|typically|often)\b"
    hits = []
    for line_no, para in _paragraphs_with_lines(masked):
        for s in _sentences(para):
            if len(re.findall(hedges, s, re.IGNORECASE)) >= 3:
                hits.append((line_no, s[:70]))
    return hits


def _check_rhetorical_questions(masked):
    qs = [q for q in re.findall(r"[^.\n?]{5,90}\?", masked)
          if not re.match(r"^\s*#{1,6}", q) and "|" not in q]
    if len(qs) > 3:
        return [(0, f"{len(qs)} rhetorical questions — keep at most one")]
    return []


# ── autofixes ─────────────────────────────────────────────────────────────────


def _fix_curly_quotes(md):
    return (md.replace("“", '"').replace("”", '"')
              .replace("‘", "'").replace("’", "'"))


def _fix_emoji_headings(md):
    emoji = "[\U0001F300-\U0001FAFF☀-➿️←-⇿⬀-⯿]"
    md = re.sub(rf"^(#{{1,6}}\s+){emoji}+\s*", r"\1", md, flags=re.MULTILINE)
    md = re.sub(rf"^(\s*[-*]\s+){emoji}+\s*", r"\1", md, flags=re.MULTILINE)
    return md


def _fix_filler(md):
    for rx, repl in FILLER_MAP.items():
        md = re.sub(rx, repl, md, flags=re.IGNORECASE)
    # Collapse the double spaces / orphaned capitals a deletion can leave behind.
    md = re.sub(r"[ \t]{2,}", " ", md)
    md = re.sub(r"(^|\n)\s*([a-z])", lambda m: m.group(1) + m.group(2).upper()
                if m.group(1) else m.group(0), md)
    return md


def _fix_bold_list_headers(md):
    return re.sub(r"^(\s*[-*]\s+)\*\*([^*\n]+?)\*\*(\s*[:—-])", r"\1\2\3",
                  md, flags=re.MULTILINE)


def _fix_title_case_headings(md):
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into",
             "nor", "of", "on", "onto", "or", "over", "so", "the", "to", "up",
             "with", "yet", "is", "it", "that", "this", "when", "why", "how"}

    def _one(m):
        hashes, text = m.group(1), m.group(2)
        words = text.split()
        if len(words) < 4:
            return m.group(0)
        out = []
        for i, w in enumerate(words):
            core = re.sub(r"[^\w'-]", "", w)
            # Leave acronyms, code-ish tokens and hyphenated names alone.
            if not core or core.isupper() or any(c.isdigit() for c in core) or "." in w:
                out.append(w)
            elif i > 0 and core.lower() in small:
                out.append(w.lower())
            elif i > 0 and core[:1].isupper() and core[1:].islower():
                out.append(w[0].lower() + w[1:])
            else:
                out.append(w)
        return f"{hashes}{' '.join(out)}"

    return re.sub(r"^(#{2,6}\s+)(.*\S)\s*$", _one, md, flags=re.MULTILINE)


def _fix_spaced_emdash(md):
    return re.sub(r"\s+—\s+", "—", md)


def _fix_adverb_hyphen(md):
    return re.sub(r"\b(well|highly|fully|widely|newly|poorly|badly|easily|quickly)-(\w+)",
                  r"\1 \2", md, flags=re.IGNORECASE)


PATTERNS = [
    Pattern(1, "inflated-significance", "high",
            "State the fact. Cut the claim that it matters.",
            rx=_rx(r"\b(pivotal|watershed|marks? a (?:turning point|shift|new era)|"
                   r"cannot be overstated|paradigm shift|broader (?:trend|implication)s?|"
                   r"a testament to|signals? a (?:shift|change))\b")),
    Pattern(2, "notability-padding", "medium",
            "Cut resume padding; keep only what the draft actually sources.",
            rx=_rx(r"\b(featured in (?:several|numerous|various)|widely (?:recognized|regarded|acclaimed)|"
                   r"renowned|prominent figure|has an active presence|industry[- ]leading)\b")),
    Pattern(3, "fake-depth-ing", "high",
            "Delete the trailing -ing clause or make it its own sentence.",
            rx=_rx(r",\s+(symboliz|reflect|highlight|underscor|showcas|emphasiz|demonstrat|"
                   r"solidify|cement|mark|signal|ensur|allow|enabl|cimenting|illustrat)\w*ing\b")),
    Pattern(4, "sales-language", "high",
            "Neutral descriptors only. Drop adjectives you can't source.",
            rx=_rx(r"\b(vibrant|nestled|stunning|breathtaking|must-have|world-class|"
                   r"state-of-the-art|best-in-class|unrivaled|top-notch|blazing[- ]fast|"
                   r"lightning[- ]fast|effortless(?:ly)?)\b")),
    Pattern(5, "vague-attribution", "high",
            "Name the source with a URL, or delete the claim.",
            rx=_rx(r"\b(experts? (?:say|argue|agree|believe|note)|studies (?:show|suggest)|"
                   r"research (?:shows|suggests|indicates)|it is (?:widely )?believed|"
                   r"many (?:developers|engineers|people) (?:say|believe|agree)|"
                   r"industry reports|observers note|some argue|surveys show)\b")),
    Pattern(6, "formula-sections", "medium",
            "Cut the scaffolding sentence; keep the concrete problem.",
            rx=_rx(r"\b(despite (?:these |the |its )?(?:challenges|limitations|drawbacks)|"
                   r"while (?:there are|it has) (?:some )?(?:challenges|limitations)|"
                   r"that said,\s+(?:it|the|there))\b")),
    Pattern(7, "ai-vocabulary", "high",
            "Swap for the plainest word that means the same thing.",
            rx=_rx(r"\b(" + "|".join(re.escape(w) for w in AI_VOCAB) + r")\b"),
            cap=10),
    Pattern(8, "copula-avoidance", "medium",
            'Use "is" / "has". The fancy verb adds nothing.',
            rx=_rx(r"\b(serves as|acts as|stands as|boasts|represents a|constitutes|"
                   r"functions as|is characterized by|comes equipped with)\b")),
    Pattern(9, "negative-parallelism", "high",
            'Drop the "not X but Y" frame; assert Y directly.',
            rx=_rx(r"\b(?:it'?s |this is |that'?s )?not (?:just|only|merely|simply)\b"
                   r"[^.\n]{0,90}\bbut\b")),
    Pattern(10, "rule-of-three", "low",
            "Vary group size — two or four items instead of three.",
            check=_check_rule_of_three),
    Pattern(11, "elegant-variation", "low",
            "Reuse the same noun instead of cycling synonyms.",
            rx=_rx(r"\b(the (?:aforementioned|latter|former)|said (?:tool|library|approach|method))\b")),
    # Endpoints containing a digit are a real measured range ("from 500ms to
    # 200ms", "from 3 workers to 12"), which is the specificity this engine is
    # trying to produce. Only fire when BOTH endpoints are non-numeric, which is
    # the fake-spectrum case ("from startups to enterprises").
    Pattern(12, "false-ranges", "medium",
            "List the items; drop the fake spectrum.",
            rx=_rx(r"\b(?:anything |everything )?(?:ranging )?from\s+"
                   r"(?![\w'-]*\d)[\w'-]{3,20}\s+to\s+(?![\w'-]*\d)[\w'-]{3,20}\b")),
    Pattern(13, "passive-voice", "medium",
            "Name the actor. Active voice.",
            rx=_rx(r"\b(?:is|are|was|were|been|being)\s+\w+(?:ed|en)\s+by\b|"
                   r"\bit (?:is|was) (?:believed|thought|considered|found|noted|observed|assumed)\b"),
            cap=8),
    Pattern(14, "em-dash-overuse", "high",
            "At most one em-dash per paragraph; use periods or commas.",
            check=_check_emdash, autofix=_fix_spaced_emdash),
    Pattern(15, "excessive-boldface", "medium",
            "Bold is structure, not emphasis. Strip decorative bold.",
            check=_check_boldface),
    Pattern(16, "bolded-list-headers", "medium",
            "Drop the bold from the lead term in bullets.",
            rx=_rx(r"^\s*[-*]\s+\*\*[^*\n]{2,60}\*\*\s*[:—-]", re.MULTILINE),
            autofix=_fix_bold_list_headers),
    Pattern(17, "title-case-headings", "medium",
            "Sentence case headings.",
            check=_check_title_case_headings, autofix=_fix_title_case_headings),
    Pattern(18, "emoji-decoration", "medium",
            "No emoji in headings or bullet leads.",
            rx=re.compile(r"^(?:#{1,6}|\s*[-*])\s+"
                          r"[\U0001F300-\U0001FAFF☀-➿️]", re.MULTILINE),
            autofix=_fix_emoji_headings),
    Pattern(19, "curly-quotes", "low",
            "Straight quotes.",
            rx=re.compile(r"[“”‘’]"), autofix=_fix_curly_quotes, cap=2),
    Pattern(20, "chatbot-artifacts", "high",
            "Delete. This is assistant voice, not author voice.",
            rx=_rx(r"\b(i hope this helps|let me know if you|feel free to (?:ask|reach|explore)|"
                   r"would you like me to|happy to help|great question|as an ai)\b")),
    Pattern(21, "cutoff-disclaimers", "high",
            "Say what you know. Cut the hedge about knowledge limits.",
            rx=_rx(r"\b(as of my (?:last )?(?:training|knowledge|update)|"
                   r"i don'?t have (?:access to )?real-?time|my training data|"
                   r"at the time of writing, i)\b")),
    Pattern(22, "sycophantic-tone", "medium",
            "Neutral register.",
            rx=_rx(r"\b(excellent point|that'?s a (?:great|fantastic|brilliant)|"
                   r"you'?re (?:absolutely )?right|absolutely!|incredible(?:ly)? powerful)\b")),
    Pattern(23, "filler-phrases", "medium",
            "Condense to the core word.",
            rx=_rx("|".join(FILLER_MAP.keys())), autofix=_fix_filler, cap=8),
    Pattern(24, "over-hedging", "medium",
            "One qualifier per sentence, or none.",
            check=_check_hedging),
    Pattern(25, "generic-conclusions", "high",
            "End on the last concrete fact. No send-off.",
            rx=_rx(r"\b(exciting times|bright future|the future (?:is|looks|of)|"
                   r"only time will tell|possibilities are endless|happy coding|"
                   r"the journey (?:continues|doesn'?t end)|go forth and)\b")),
    Pattern(26, "adverb-hyphen-misuse", "low",
            "No hyphen after an -ly/degree adverb.",
            rx=_rx(r"\b(well|highly|fully|widely|newly|poorly|badly|easily|quickly)-\w+"),
            autofix=_fix_adverb_hyphen),
    Pattern(27, "authority-tropes", "high",
            "Cut the ceremony; state the point.",
            rx=_rx(r"\b(the real question is|at its core|what (?:really )?matters is|"
                   r"here'?s the thing|the truth is|make no mistake|let'?s be (?:honest|clear)|"
                   r"the bottom line|at the end of the day)\b")),
    Pattern(28, "signposting", "high",
            "Delete the announcement; deliver the content.",
            rx=_rx(r"\b(let'?s dive in|dive deep(?:er)? into|here'?s what you need to know|"
                   r"in this (?:article|post|guide|tutorial),?\s+(?:we|i)'?(?:ll| will)|"
                   r"buckle up|without further ado|let'?s get started|by the end of this|"
                   r"we'?ll (?:explore|cover|walk through))\b")),
    Pattern(29, "fragmented-headers", "medium",
            "The heading already said it. Cut the restatement.",
            check=_check_fragmented_headers),
    Pattern(30, "diff-anchored", "low",
            "Describe what it is, not what it replaced.",
            rx=_rx(r"\b(?:was|has been) (?:added|removed|replaced|renamed|deprecated) "
                   r"(?:to|in|from|with)\b|\bused to be (?:called|named)\b")),
    Pattern(31, "staccato-drama", "high",
            "Manufactured drama. Merge into full sentences.",
            check=_check_staccato),
    Pattern(32, "aphorism-formulas", "high",
            "Replace with the concrete claim and its consequence.",
            rx=_rx(r"\b\w+ is the \w+ of \w+\b|"
                   r"\b\w+ becomes? (?:a|the) (?:trap|crutch|liability|bottleneck)\b|"
                   r"\bthat'?s not \w+[.,] that'?s \w+\b")),
    Pattern(33, "rhetorical-openers", "high",
            "Start with the point.",
            rx=_rx(r"(?:^|\n)\s*(honestly|look|truth is|real talk|spoiler|here'?s the kicker)"
                   r"\s*[,.:?]", re.IGNORECASE)),
    # ── engine-specific: phrases earlier prompt versions taught the model ──
    Pattern(34, "template-leak", "high",
            "Verbatim phrase from an older prompt. Rewrite specific to this topic.",
            rx=_rx(r"\bI spent three hours on this\b|\bTHREE hours\b|\bSound familiar\??|"
                   r"\bYeah\.\s*Me too\.|\bIt was 1am\b|\bthe clap button\b|\btap that clap\b|"
                   r"\bdrop a comment below\b|\bsmash that\b")),
    Pattern(35, "transition-openers", "high",
            "Delete the connective; the sentence stands alone.",
            rx=_rx(r"(?:^|\n)\s*(furthermore|moreover|additionally|in conclusion|in summary|"
                   r"to summarize|in essence|as we can see|as mentioned|as discussed)\s*,",
                   re.IGNORECASE)),
    Pattern(36, "excess-rhetorical-questions", "medium",
            "Keep one question, make it topic-specific.",
            check=_check_rhetorical_questions),
]

PATTERNS_BY_ID = {p.pid: p for p in PATTERNS}
SEVERITY_WEIGHT = {"high": 3.0, "medium": 1.5, "low": 0.5}


# ═══════════════════════════════════════════════════════════════════════════════
# SCANNING
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Finding:
    pid: int
    name: str
    severity: str
    line: int
    excerpt: str
    fix: str


@dataclass
class HumanScore:
    score: int                     # 0-100, higher = more human
    per_1k: float                  # weighted findings per 1000 prose words
    counts: dict = field(default_factory=dict)   # severity -> n
    words: int = 0

    def grade(self):
        if self.score >= 85:
            return "ship"
        if self.score >= 70:
            return "ok"
        if self.score >= 50:
            return "needs-work"
        return "reject"


def _line_of(masked, pos):
    return masked.count("\n", 0, pos) + 1


def _clean_excerpt(text):
    """Findings are quoted from masked text, so a sentinel can land inside an
    excerpt. Render it as a readable placeholder — it must never reach a
    terminal or a Telegram message."""
    text = _MASK_FIND.sub("[code]", text)
    return text.replace(_SENT, "").strip()


def scan(md):
    """Return findings for prose only. Code, tables and URLs are masked out."""
    if not md:
        return []
    masked, _ = mask_protected(md)
    findings = []

    for p in PATTERNS:
        hits = []
        if p.rx is not None:
            for m in p.rx.finditer(masked):
                text = m.group(0).strip()
                if not text:
                    continue
                start = max(m.start() - 30, 0)
                excerpt = re.sub(r"\s+", " ", masked[start:m.end() + 40])
                hits.append((_line_of(masked, m.start()), _clean_excerpt(excerpt)[:100]))
        if p.check is not None:
            hits.extend((line, _clean_excerpt(str(ex))) for line, ex in p.check(masked))

        # De-dupe identical excerpts, then cap.
        seen, deduped = set(), []
        for line, excerpt in hits:
            key = excerpt.lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            deduped.append((line, excerpt))

        for line, excerpt in deduped[: p.cap]:
            findings.append(Finding(p.pid, p.name, p.severity, line, excerpt, p.fix))

    findings.sort(key=lambda f: (-SEVERITY_WEIGHT[f.severity], f.line))
    return findings


def prose_word_count(md):
    masked, _ = mask_protected(md)
    masked = _MASK_FIND.sub(" ", masked)
    return len(re.findall(r"[A-Za-z][\w'-]*", masked))


def score(md, findings=None):
    """Density-based score so long articles aren't punished for length."""
    findings = scan(md) if findings is None else findings
    words = prose_word_count(md)
    counts = {"high": 0, "medium": 0, "low": 0}
    weighted = 0.0
    for f in findings:
        counts[f.severity] += 1
        weighted += SEVERITY_WEIGHT[f.severity]
    per_1k = weighted / max(words, 1) * 1000
    # Exponential decay, calibrated against this repo's own draft corpus, where
    # untreated LLM output measures 20-70 weighted tells per 1k prose words.
    # A linear curve pinned every real draft to 0 and made the score useless.
    #   per_1k  0 -> 100 |  3 -> 85 (ship) |  6 -> 72 (ok)
    #          12 -> 51  | 20 -> 33        | 70 ->  2
    raw = 100 * math.exp(-per_1k / 18.0)
    return HumanScore(int(max(0, min(100, round(raw)))), round(per_1k, 2), counts, words)


def autofix(md):
    """Apply only the deterministic, meaning-preserving fixes. Fence-aware."""
    masked, store = mask_protected(md)
    applied = 0
    for p in PATTERNS:
        if p.autofix is None:
            continue
        before = masked
        masked = p.autofix(masked)
        if masked != before:
            applied += 1
    return unmask(masked, store), applied


def format_findings(findings, limit=24):
    """Compact, LLM-readable findings block for the repair prompt."""
    if not findings:
        return "(none)"
    lines = []
    for f in findings[:limit]:
        lines.append(f"[{f.severity.upper()}] #{f.pid} {f.name} (line ~{f.line})\n"
                     f"    found: {f.excerpt}\n"
                     f"    fix:   {f.fix}")
    if len(findings) > limit:
        lines.append(f"... and {len(findings) - limit} more")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# VOICE CALIBRATION — fingerprint real writing samples instead of asserting a
# generic "casual dev voice". Drop .md/.txt files in voice/ to activate.
# ═══════════════════════════════════════════════════════════════════════════════

VOICE_DIR = os.getenv("VOICE_SAMPLES_DIR", "voice")


def load_voice_samples(directory=None):
    directory = directory or VOICE_DIR
    if not os.path.isdir(directory):
        return []
    out = []
    for path in sorted(glob.glob(os.path.join(directory, "*.md"))
                       + glob.glob(os.path.join(directory, "*.txt")))[:5]:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read().strip()
            if len(text) > 300:
                out.append(text)
        except Exception as e:
            print(f"[voice] Could not read {path}: {e}")
    return out


def voice_fingerprint(samples):
    """Measurable style facts from the author's own writing. Empty string if no
    samples — the caller then falls back to the persona description."""
    if not samples:
        return ""
    joined = "\n\n".join(samples)
    masked, _ = mask_protected(joined)
    masked = _MASK_FIND.sub(" ", masked)

    sents = _sentences(masked)
    lengths = [len(s.split()) for s in sents if s.split()]
    if not lengths:
        return ""
    avg = sum(lengths) / len(lengths)
    shortest = min(lengths)
    longest = max(lengths)
    variance = sum((x - avg) ** 2 for x in lengths) / len(lengths)

    words = re.findall(r"[a-z][\w'-]*", masked.lower())
    total = max(len(words), 1)
    contractions = len(re.findall(r"\b\w+'(?:s|t|re|ll|ve|d|m)\b", masked, re.IGNORECASE))
    first_person = len(re.findall(r"\bI\b", masked))
    parentheticals = masked.count("(")
    emdashes = masked.count("—")
    semicolons = masked.count(";")
    frag_ratio = sum(1 for l in lengths if l <= 5) / len(lengths)

    # Words the author uses that a generic model wouldn't — high-frequency,
    # non-stopword terms from their own corpus.
    stop = set("""the a an and or but if of to in on for with at by from as is are was were be been
                  it its this that these those you your i my we our they their he she them then than
                  so not no do does did have has had will would can could should there here what
                  when where which who how why all any some more most other into out up down over""".split())
    freq = {}
    for w in words:
        if len(w) > 3 and w not in stop:
            freq[w] = freq.get(w, 0) + 1
    signature = [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])[:12]]

    return f"""MEASURED VOICE FINGERPRINT (from {len(samples)} sample(s) of the author's real writing —
match these numbers, do not imitate the samples' topics):
- Sentence length: average {avg:.0f} words, range {shortest}-{longest}, variance {variance:.0f}
  (high variance means: mix a 4-word sentence with a 30-word one; do not level them out)
- Short-sentence ratio: {frag_ratio:.0%} of sentences are <=5 words
- Contractions: {contractions / total * 1000:.1f} per 1000 words {'(uses them freely)' if contractions / total * 1000 > 8 else '(uses them sparingly)'}
- First-person "I": {first_person / total * 1000:.1f} per 1000 words
- Punctuation habits per 1000 words: parentheses {parentheticals / total * 1000:.1f}, em-dash {emdashes / total * 1000:.1f}, semicolon {semicolons / total * 1000:.1f}
  (pick the ONE the author actually uses; ignore the others)
- Recurring vocabulary: {', '.join(signature)}"""


# ═══════════════════════════════════════════════════════════════════════════════
# REWRITE + REPAIR LOOP
# ═══════════════════════════════════════════════════════════════════════════════

PRESERVE_BLOCK = """WHAT TO PRESERVE EXACTLY — copy these through byte-for-byte:
- every ## / ### heading's position in the document (you may reword, never reorder or drop)
- every ``` fenced block and its contents (code, mermaid, json?chameleon widget)
- every pipe table
- every image ![alt](url) and every link URL
- every TAGS: and META: line
Rewrite ONLY the prose paragraphs between those elements."""


def _strip_preamble(text):
    """Models like to open with 'Here is the rewritten article:'."""
    text = text.strip()
    first_nl = text.find("\n")
    head = text[: first_nl if first_nl != -1 else len(text)]
    if re.match(r"^\s*(here'?s?|here is|below is|sure|certainly|rewritten|revised|final)"
                r"[^.\n]{0,80}[:.]?\s*$", head, re.IGNORECASE):
        text = text[first_nl + 1:] if first_nl != -1 else ""
    return text.strip()


def _sane_length(new, old, floor=0.55):
    return bool(new) and len(new) >= int(len(old) * floor)


# A model handed a truncated or confusing draft often answers ABOUT the draft
# instead of rewriting it — "the content cuts off mid-sentence, send the full
# text and I will rewrite it". That reply is prose of a plausible length, so
# every length check passes and the commentary gets saved as the article. It
# has to be recognised by what it is, not how long it is.
_META_REPLY_PATTERNS = [
    r"\bwhat you (?:pasted|provided|shared|sent)\b",
    r"\bthe (?:rest|remainder) of the (?:draft|article|text)\b",
    r"\bi can only (?:rewrite|work with|see|process)\b",
    r"\b(?:send|share|provide|paste) (?:me )?the (?:full|complete|rest)\b",
    r"\bi(?:'d| would) need the (?:full|complete|entire)\b",
    r"\b(?:content|text|draft) (?:cuts|is cut) off\b",
    r"\bcuts off mid-?sentence\b",
    r"\bwell short of the\b.{0,30}\btarget\b",
    r"\bthe draft (?:appears|seems) to be\b",
    r"\b(?:please|kindly) (?:provide|share|paste)\b",
    r"\bis missing from\b",
    r"\bonce you (?:send|provide|share)\b",
    r"\bi (?:cannot|can't|am unable to) (?:rewrite|complete|proceed)\b",
]
# Named _META_REPLY_RE, not _META_RE: that name is already taken above by the
# TAGS:/META: line masker, and shadowing it silently stopped those lines
# being protected from rewrites.
_META_REPLY_RE = re.compile("|".join(_META_REPLY_PATTERNS), re.IGNORECASE)


def looks_like_meta_response(text, original=""):
    """True when the model talked about the task instead of doing it.

    Two signals, either is enough:
      * an explicit meta phrase ("send the full text")
      * the reply is far shorter than the input AND addresses the reader as
        "you" — a rewrite has no reason to do either.
    """
    if not text:
        return True
    head = text[:1200]
    if _META_REPLY_RE.search(head):
        return True
    if original and len(text) < len(original) * 0.5:
        if re.search(r"\byou (?:pasted|sent|provided|need|would|can)\b", head, re.IGNORECASE):
            return True
    return False


def rewrite_pass(md, ask_ai, voice_context, voice_brief, target_words):
    """First pass: rewrite for voice. Observations about real writing, not
    tricks to insert."""
    banned = ", ".join(AI_VOCAB[:24])
    prompt = f"""You are a line editor at a technical magazine. Your only job is to make this draft stop sounding generated. You do not add ideas, facts, numbers, names, or citations that are not already in the draft.

DRAFT:
---
{md}
---

{PRESERVE_BLOCK}

HOW TO REWRITE — these describe how real writing behaves. They are not devices to insert:

1. Real writers accidentally repeat themselves and move on. Leave one repetition in; don't polish it out.
2. Real writers have exactly ONE verbal tic per piece. Pick one — parentheticals, or em-dashes, or fragments — and use only that one. Mixing several tics is itself the AI signature.
3. Real writers ask the reader at most one rhetorical question per article, and it's specific to the topic.
4. Real writers rarely write "I". They show it by what they noticed. "The error log was empty" carries more first person than "I noticed the error log was empty."
5. Real writers are not funny on purpose. Cut any polished wisecrack. One flat, tired observation beats three jokes.
6. Real writers commit to verbs. "It really is" becomes "it is". "Actually started" becomes "started".
7. Real writers do not conclude. The last paragraph just stops. Do not add a wrap-up.
8. Sentence length is uneven. A four-word sentence next to a thirty-word one. If every sentence is 15-20 words, you have failed.

{voice_brief if voice_brief else f"VOICE CONTEXT: {voice_context}"}

DELETE ON SIGHT:
- Any sentence containing: {banned}
- Any sentence opening with Furthermore, Moreover, Additionally, In conclusion, In summary, In essence, It is worth noting, As we can see, As mentioned.
- Signposting: "let's dive in", "in this article we'll", "buckle up", "by the end of this".
- Authority ceremony: "at its core", "the real question is", "here's the thing", "the truth is", "at the end of the day".
- Chatbot voice: "I hope this helps", "feel free to", "let me know".
- Closing send-offs: "exciting times", "the future of", "happy coding".
- Emoji in headings. Bold used for emphasis rather than structure. Title Case Headings.

DO NOT INVENT: no new dollar amounts, user counts, company names, dates, benchmarks, or citations. If a claim in the draft has no source, make it vaguer, never more specific.

WORD TARGET: about {target_words}. If the result runs short, leave it short. Padding is worse.

Output the rewritten article only. No preamble, no commentary."""
    out = ask_ai(prompt, max_tokens=int(target_words * 2.2) + 600)
    out = _strip_preamble(out)
    if looks_like_meta_response(out, md):
        print("[humanize] rewrite returned commentary, not a rewrite — keeping input")
        return md
    if not _sane_length(out, md):
        print(f"[humanize] rewrite too short ({len(out)} vs {len(md)}) — keeping input")
        return md
    return out


def repair_pass(md, findings, ask_ai, target_words, round_no=1):
    """Second pass: hand the model its OWN detected tells and make it fix those
    specific lines. This is the loop the old ai_lint never closed."""
    high_med = [f for f in findings if f.severity in ("high", "medium")]
    if not high_med:
        return md
    prompt = f"""A regex linter scanned this article and found the AI-writing tells listed below. Fix exactly these. Change nothing else.

ARTICLE:
---
{md}
---

LINTER FINDINGS ({len(high_med)} to fix, repair round {round_no}):
{format_findings(high_med)}

{PRESERVE_BLOCK}

RULES FOR THIS PASS:
- Fix each finding at the line indicated. Rewrite the sentence around it so the phrasing disappears; do not just delete the word and leave a stub.
- Do not introduce new facts, numbers, names, links, or citations while fixing.
- Do not rewrite paragraphs the linter did not flag.
- Do not add transitions, summaries, or conclusions to smooth over a deletion. A slightly abrupt paragraph is correct.
- Keep the word count near {target_words}; deletions do not need replacing.

Output the corrected article only. No preamble, no list of what you changed."""
    out = ask_ai(prompt, max_tokens=int(target_words * 2.2) + 600)
    out = _strip_preamble(out)
    if looks_like_meta_response(out, md):
        print(f"[humanize] repair round {round_no} returned commentary — keeping previous")
        return md
    if not _sane_length(out, md, floor=0.7):
        print(f"[humanize] repair round {round_no} too short — keeping previous")
        return md
    return out


@dataclass
class Report:
    before: HumanScore
    after: HumanScore
    rounds: int
    autofixes: int
    remaining: list = field(default_factory=list)

    def summary(self):
        return (f"AI-tell score {self.before.score} -> {self.after.score}/100 "
                f"({self.after.grade()}) | {self.rounds} repair round(s), "
                f"{self.autofixes} autofix group(s) | "
                f"remaining: {self.after.counts.get('high', 0)} high, "
                f"{self.after.counts.get('medium', 0)} medium")

    def as_dict(self):
        return {
            "before": asdict(self.before),
            "after": asdict(self.after),
            "grade": self.after.grade(),
            "rounds": self.rounds,
            "autofixes": self.autofixes,
            "remaining": [asdict(f) for f in self.remaining[:20]],
        }


def humanize(md, ask_ai, voice_context="", target_words=1100,
             max_rounds=2, target_score=85, do_rewrite=True, samples=None):
    """Full loop: rewrite -> scan -> repair (until score clears) -> autofix.

    ask_ai(prompt, max_tokens) -> str is injected so this module stays free of
    provider code and is testable offline.
    """
    original = md or ""
    before = score(original)
    if len(original) < 400:
        return original, Report(before, before, 0, 0, scan(original))

    samples = load_voice_samples() if samples is None else samples
    voice_brief = voice_fingerprint(samples)
    if voice_brief:
        print(f"[humanize] voice fingerprint from {len(samples)} sample(s)")

    current = original
    if do_rewrite:
        try:
            current = rewrite_pass(current, ask_ai, voice_context, voice_brief, target_words)
        except Exception as e:
            print(f"[humanize] rewrite failed: {e} — continuing with original")

    rounds = 0
    findings = scan(current)
    for i in range(1, max_rounds + 1):
        s = score(current, findings)
        if s.score >= target_score:
            break
        if not [f for f in findings if f.severity in ("high", "medium")]:
            break
        try:
            candidate = repair_pass(current, findings, ask_ai, target_words, i)
        except Exception as e:
            print(f"[humanize] repair round {i} failed: {e}")
            break
        rounds = i
        cand_findings = scan(candidate)
        # Only keep the repair if it actually improved the score.
        if score(candidate, cand_findings).score > s.score:
            current, findings = candidate, cand_findings
        else:
            print(f"[humanize] repair round {i} did not improve — discarded")
            break

    current, n_autofix = autofix(current)
    final_findings = scan(current)
    after = score(current, final_findings)
    return current, Report(before, after, rounds, n_autofix, final_findings)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — audit any markdown file without touching the publishing pipeline:
#   python humanizer.py medium_drafts/some-post.md
#   python humanizer.py --json medium_drafts/*.md
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    # Windows consoles default to cp1252 and choke on the box-drawing / em-dash
    # characters these reports contain.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    fix_in_place = "--fix" in sys.argv

    if not args:
        print(__doc__)
        print("Usage: python humanizer.py [--json] [--fix] <file.md> [more.md ...]")
        sys.exit(0)

    paths = []
    for a in args:
        paths.extend(sorted(glob.glob(a)) or [a])

    results = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except Exception as e:
            print(f"!! {path}: {e}")
            continue

        if fix_in_place:
            text, n = autofix(text)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)

        f = scan(text)
        s = score(text, f)
        results.append({"file": path, "score": s.score, "grade": s.grade(),
                        "per_1k": s.per_1k, "counts": s.counts, "words": s.words,
                        "findings": [asdict(x) for x in f[:30]]})

        if not as_json:
            print(f"\n{'=' * 72}\n{path}\n{'=' * 72}")
            print(f"score {s.score}/100 ({s.grade()})  |  {s.words} prose words  |  "
                  f"{s.per_1k} weighted tells / 1k words")
            print(f"high {s.counts['high']}  medium {s.counts['medium']}  low {s.counts['low']}")
            if fix_in_place:
                print(f"autofixed in place ({n} groups applied)")
            if f:
                print()
                print(format_findings(f, limit=20))

    if as_json:
        print(json.dumps(results, indent=2))
    elif len(results) > 1:
        print(f"\n{'=' * 72}\nSUMMARY")
        for r in sorted(results, key=lambda r: r["score"]):
            print(f"  {r['score']:3d}/100  {r['grade']:<11} {r['file']}")
