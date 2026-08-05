"""
promo.py — LinkedIn and X posts generated FROM a finished article.

agent.py already had social_media_single(topic), which writes posts from a topic
string. That produces plausible-sounding copy about a subject. This module works
from the finished article instead, so the posts quote details that actually
exist in it — the real error string, the real before/after number, the real
snippet — which is the difference between promotion and a second, worse article.

Platform rules are enforced in Python, not requested in the prompt:
  * X: 280 characters per post, hard. Over-length posts are sent back to the
    model for a rewrite, then truncated at a word boundary as a last resort.
  * LinkedIn: 3000 char limit, but the fold is at ~210 characters — the hook has
    to land before "…see more". That is the only line most people read.
  * Both drafts go through humanizer. A LinkedIn post is the single most
    slop-prone format there is, and it is the one with the author's face on it.

Public API:
    extract_facts(article, title)          -> dict of citable details
    build_promo(article, title, ...)       -> PromoPack
    render_markdown(pack)                  -> str
"""

import os
import re
import json
from dataclasses import dataclass, field, asdict

import humanizer

X_LIMIT = 280
LI_LIMIT = 3000
LI_FOLD = 210          # LinkedIn collapses after roughly this many characters
THREAD_LEN = int(os.getenv("PROMO_THREAD_LEN", "6"))

_URL_RE = re.compile(r"https?://[^\s)\]\"'>]+")


def strip_seo_block(article):
    """Committed drafts in medium_drafts/ carry an editor-only header that ends
    with a 'cut this before publishing' marker. The pipeline passes the clean
    body, but the CLI reads the file from disk — without this the promo writer
    treats the thumbnail prompt as the article's opening line."""
    m = re.search(r"CUT THE ABOVE BLOCK[^\n]*\n", article)
    return article[m.end():].lstrip() if m else article


def extract_facts(article, title=""):
    """Pull the concrete, quotable material out of the finished draft, so the
    post writer works from evidence instead of from the title alone."""
    body = strip_seo_block(article)

    tldr = ""
    m = re.search(r"\*\*TL;DR\*\*(.*?)(?=\n##|\Z)", body, re.DOTALL)
    if m:
        tldr = re.sub(r"\s+", " ", re.sub(r"[*\-]", " ", m.group(1))).strip()[:400]

    h2s = re.findall(r"^##\s+(.+)$", body, re.MULTILINE)

    # Longest real code block — the most shareable artifact.
    snippets = [(lang, code.strip()) for lang, code in
                re.findall(r"```(\w*)\n(.*?)```", body, re.DOTALL)
                if lang.lower() not in ("mermaid", "json?chameleon", "")]
    snippets.sort(key=lambda lc: -len(lc[1]))
    best_snippet = snippets[0] if snippets else ("", "")
    # Trim to something that fits in a tweet image / LinkedIn code block.
    snippet_lines = best_snippet[1].splitlines()[:12]

    # Numbers that read like a result, with their surrounding clause.
    metrics = []
    for mm in re.finditer(r"[^.\n]{0,70}\b\d[\d,.]*\s*(?:ms|s|sec|seconds|min|minutes|hours|"
                          r"x|%|MB|GB|req/s|lines)\b[^.\n]{0,50}", body, re.IGNORECASE):
        frag = re.sub(r"\s+", " ", mm.group(0)).strip(" -|*#")
        if frag and not frag.startswith("!") and len(frag) > 12:
            metrics.append(frag[:140])

    tables = re.findall(r"((?:^\s*\|.*\|\s*$\n?){3,})", body, re.MULTILINE)

    urls = [u for u in _URL_RE.findall(body)
            if not any(h in u for h in ("pollinations.ai", "quickchart.io", "mermaid.ink"))]

    # First real paragraph = the hook the article itself opens with.
    prose = humanizer.mask_protected(body)[0]
    prose = humanizer._MASK_FIND.sub(" ", prose)
    paras = [p.strip() for p in re.split(r"\n\s*\n", prose)
             if p.strip() and not p.strip().startswith(("#", ">", "|", "-", "*"))]

    return {
        "title": title or (h2s[0] if h2s else ""),
        "opening": (paras[0][:400] if paras else ""),
        "closing": (paras[-1][:300] if paras else ""),
        "tldr": tldr,
        "h2s": h2s[:6],
        "snippet_lang": best_snippet[0],
        "snippet": "\n".join(snippet_lines),
        "metrics": metrics[:6],
        "has_table": bool(tables),
        "urls": urls[:6],
        "word_count": humanizer.prose_word_count(body),
    }


def _facts_block(f):
    lines = [f"TITLE: {f['title']}"]
    if f["tldr"]:
        lines.append(f"TL;DR FROM THE ARTICLE: {f['tldr']}")
    if f["opening"]:
        lines.append(f"HOW THE ARTICLE OPENS: {f['opening']}")
    if f["h2s"]:
        lines.append("SECTIONS:\n" + "\n".join(f"  - {h}" for h in f["h2s"]))
    if f["metrics"]:
        lines.append("REAL NUMBERS IN THE ARTICLE (the only figures you may quote):\n"
                     + "\n".join(f"  - {m}" for m in f["metrics"]))
    if f["snippet"]:
        lines.append(f"LONGEST CODE BLOCK ({f['snippet_lang']}):\n{f['snippet']}")
    if f["urls"]:
        lines.append("URLS CITED IN THE ARTICLE:\n" + "\n".join(f"  - {u}" for u in f["urls"]))
    return "\n\n".join(lines)


@dataclass
class PromoPack:
    title: str = ""
    article_url: str = ""
    linkedin: str = ""
    linkedin_hook: str = ""
    x_thread: list = field(default_factory=list)
    x_single: str = ""
    hashtags_li: list = field(default_factory=list)
    hashtags_x: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    human_scores: dict = field(default_factory=dict)

    def as_dict(self):
        return asdict(self)


def _clean_post(s):
    """Strip the packaging models add to social copy."""
    s = str(s or "").strip()
    s = re.sub(r"^(?:tweet\s*\d+\s*[:.\-–]\s*|\d+[/.]\s*|post\s*[:.]\s*)", "", s,
               flags=re.IGNORECASE)
    s = re.sub(r'^["“](.*)["”]$', r"\1", s.strip(), flags=re.DOTALL)
    return s.strip()


def _fit_x(post, ask_ai=None, url=""):
    """Enforce 280 chars. Ask the model to cut first; truncate only as a
    last resort, and never mid-word."""
    post = _clean_post(post)
    reserved = len(url) + 1 if url and url not in post else 0
    budget = X_LIMIT - reserved
    if len(post) <= budget:
        return post, None

    if ask_ai is not None:
        try:
            shorter = _clean_post(ask_ai(
                f"Cut this to under {budget} characters. Keep the specific detail — "
                f"the number, the tool name, the error. Drop adjectives and framing, "
                f"not facts. No hashtags, no emoji, no quotation marks around it.\n\n{post}",
                max_tokens=200))
            if shorter and len(shorter) <= budget:
                return shorter, None
        except Exception:
            pass

    cut = post[:budget]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,.;:—-") + "…", f"X post truncated from {len(post)} chars"


def build_promo(article, title, ask_ai, article_url="", author="", voice_context="",
                humanize=True):
    """Generate the LinkedIn post and X thread, grounded in the article."""
    facts = extract_facts(article, title)
    pack = PromoPack(title=title, article_url=article_url)

    prompt = f"""You are writing the promotion posts for an article that is already finished. You are NOT summarising it and you are NOT writing a second version of it. You are giving a developer a reason to click.

Everything you write must come from the material below. Do not invent a number, a tool, a company, a result, or a story beat that is not here.

{_facts_block(facts)}

AUTHOR: {author or 'the author'}{(' — ' + voice_context) if voice_context else ''}
ARTICLE URL: {article_url or '(link will be added separately — do not write a placeholder)'}

Write two things.

1. LINKEDIN POST
   - The first line is everything. LinkedIn hides everything after ~{LI_FOLD} characters behind "see more", so the first line must carry a specific fact — a number, an error name, a tool version — that makes the fold worth opening. Never open with a question. Never open with "I'm excited to share".
   - 4-6 short paragraphs, one line break between each. No paragraph over 3 sentences.
   - Tell what actually happened, in order: what broke, what was tried, what worked, what the number was.
   - One concrete takeaway a reader can use without clicking. Give something away.
   - Close with a plain sentence pointing at the article. No "link in comments", no "thoughts?", no "let me know below".
   - No emoji. No bold. No bullet-point lists of "key takeaways". Under {LI_LIMIT} characters.

2. X THREAD — exactly {THREAD_LEN} posts
   - Post 1 stands alone as a complete thought and must work as a quote-tweetable line. It contains the most specific fact you have.
   - Posts 2 to {THREAD_LEN - 1} each carry ONE idea: the failed attempt, the actual cause, the fix, the measured result. One of them should contain a code line or a command, written inline.
   - Final post points to the article in one plain sentence.
   - Every post under 265 characters. Count them.
   - No thread emoji, no "🧵", no numbering — the client adds that. No hashtags inside the posts.

Return ONLY a JSON object, no markdown fences:
{{
  "linkedin": "the full post with \\n between paragraphs",
  "linkedin_hook": "the first line only, under {LI_FOLD} characters",
  "x_thread": ["post 1", "post 2", "..."],
  "x_single": "a standalone version of the whole thing in one post under 265 chars, for when a thread is too much",
  "hashtags_linkedin": ["3 to 4, no # symbol, lowercase"],
  "hashtags_x": ["2 to 3, no # symbol, lowercase"]
}}"""

    raw = ask_ai(prompt, max_tokens=2200)
    try:
        data = _extract_json(raw)
    except Exception as e:
        pack.warnings.append(f"promo JSON parse failed: {str(e)[:120]}")
        return pack

    pack.linkedin = _clean_post(data.get("linkedin"))
    pack.linkedin_hook = _clean_post(data.get("linkedin_hook")) or \
        (pack.linkedin.split("\n", 1)[0] if pack.linkedin else "")
    pack.x_single = _clean_post(data.get("x_single"))
    thread = [_clean_post(t) for t in (data.get("x_thread") or []) if _clean_post(t)]
    pack.hashtags_li = [str(h).lstrip("#").lower() for h in (data.get("hashtags_linkedin") or [])][:4]
    pack.hashtags_x = [str(h).lstrip("#").lower() for h in (data.get("hashtags_x") or [])][:3]

    # ── humanize before validating length: the rewrite changes the count ──
    if humanize and pack.linkedin:
        try:
            fixed, rep = humanizer.humanize(
                pack.linkedin, ask_ai, voice_context=voice_context,
                target_words=max(humanizer.prose_word_count(pack.linkedin), 120),
                max_rounds=1, do_rewrite=True)
            if fixed and len(fixed) > len(pack.linkedin) * 0.5:
                pack.linkedin = fixed.strip()
                pack.human_scores["linkedin"] = rep.after.score
                if rep.after.grade() in ("needs-work", "reject"):
                    pack.warnings.append(
                        f"LinkedIn post AI-tell score {rep.after.score}/100 ({rep.after.grade()})")
        except Exception as e:
            pack.warnings.append(f"LinkedIn humanize skipped: {str(e)[:100]}")

    # Short posts get the deterministic autofix only — a full rewrite pass on a
    # 240-character tweet costs a model call and usually makes it blander.
    fixed_thread = []
    for t in thread[:THREAD_LEN]:
        t = humanizer.autofix(t)[0].strip()
        fitted, warn = _fit_x(t, ask_ai, url="")
        if warn:
            pack.warnings.append(warn)
        fixed_thread.append(fitted)

    # The last post carries the link, so it needs the URL budget reserved.
    if fixed_thread and article_url:
        last, warn = _fit_x(fixed_thread[-1], ask_ai, url=article_url)
        if warn:
            pack.warnings.append(warn)
        fixed_thread[-1] = f"{last}\n\n{article_url}"
    pack.x_thread = fixed_thread

    if pack.x_single:
        pack.x_single = _fit_x(humanizer.autofix(pack.x_single)[0], ask_ai,
                               url=article_url)[0]
        pack.human_scores["x"] = humanizer.score("\n\n".join(pack.x_thread)).score

    # ── deterministic platform validation ──
    if len(pack.linkedin) > LI_LIMIT:
        pack.linkedin = pack.linkedin[:LI_LIMIT].rsplit(" ", 1)[0] + "…"
        pack.warnings.append(f"LinkedIn post exceeded {LI_LIMIT} chars — truncated")
    if pack.linkedin_hook and len(pack.linkedin_hook) > LI_FOLD:
        pack.warnings.append(
            f"LinkedIn hook is {len(pack.linkedin_hook)} chars — the fold cuts it at ~{LI_FOLD}")
    if not pack.linkedin:
        pack.warnings.append("LinkedIn post came back empty")
    if len(pack.x_thread) < 3:
        pack.warnings.append(f"X thread has only {len(pack.x_thread)} posts")
    over = [i + 1 for i, t in enumerate(pack.x_thread) if len(t) > X_LIMIT]
    if over:
        pack.warnings.append(f"X posts still over {X_LIMIT} chars: {over}")

    return pack


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


def render_markdown(pack, author=""):
    """Copy-paste ready. Character counts inline so nothing needs re-checking
    before posting."""
    L = [f"# Promo pack — {pack.title}", ""]
    if pack.article_url:
        L += [f"Article: {pack.article_url}", ""]
    if pack.warnings:
        L += ["> **Check before posting**"] + [f"> - {w}" for w in pack.warnings] + [""]

    L += ["## LinkedIn", ""]
    if pack.linkedin_hook:
        fold = "fits" if len(pack.linkedin_hook) <= LI_FOLD else "PAST THE FOLD"
        L += [f"_Hook ({len(pack.linkedin_hook)} chars — {fold}):_ {pack.linkedin_hook}", ""]
    L += [f"_Full post — {len(pack.linkedin)} / {LI_LIMIT} chars_", "", "```text",
          pack.linkedin, "```", ""]
    if pack.hashtags_li:
        L += ["Hashtags: " + " ".join(f"#{h}" for h in pack.hashtags_li), ""]

    L += ["## X / Twitter thread", ""]
    for i, t in enumerate(pack.x_thread, 1):
        flag = "" if len(t) <= X_LIMIT else f"  ⚠️ OVER BY {len(t) - X_LIMIT}"
        L += [f"**{i}/{len(pack.x_thread)}** _({len(t)}/{X_LIMIT}){flag}_", "",
              "```text", t, "```", ""]
    if pack.hashtags_x:
        L += ["Hashtags: " + " ".join(f"#{h}" for h in pack.hashtags_x), ""]

    if pack.x_single:
        L += ["## X — single post version", "",
              f"_{len(pack.x_single)}/{X_LIMIT} chars_", "",
              "```text", pack.x_single, "```", ""]

    if pack.human_scores:
        L += ["---", "AI-tell scores: " + ", ".join(
            f"{k} {v}/100" for k, v in pack.human_scores.items()), ""]
    L += ["---", f"*Promo pack for {author or 'CoderFact'}, generated from the finished article.*"]
    return "\n".join(L)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI:  python promo.py medium_drafts/some-post.md [--url https://...]
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import glob as _glob

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    url = ""
    for a in sys.argv[1:]:
        if a.startswith("--url="):
            url = a.split("=", 1)[1]

    if not args:
        print(__doc__)
        print("Usage: python promo.py <file.md> [--url=https://...] [--facts]")
        sys.exit(0)

    paths = []
    for a in args:
        paths.extend(sorted(_glob.glob(a)) or [a])

    for path in paths:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        title = next((l.lstrip("# ").strip() for l in text.splitlines()
                      if l.startswith("# ")), os.path.basename(path))

        if "--facts" in sys.argv:      # offline: show what the writer would get
            print(json.dumps(extract_facts(text, title), indent=2)[:4000])
            continue

        from agent import ask_ai as _ask, AUTHOR_NAME, AUTHOR_CONTEXT

        pack = build_promo(text, title, _ask, article_url=url, author=AUTHOR_NAME,
                           voice_context=AUTHOR_CONTEXT)
        out = os.path.join("social", os.path.splitext(os.path.basename(path))[0] + "-promo.md")
        os.makedirs("social", exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(pack, AUTHOR_NAME))
        print(render_markdown(pack, AUTHOR_NAME))
        print(f"\n[promo] wrote {out}")
