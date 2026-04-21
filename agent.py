import os, sys, json, base64, requests, feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

DEVTO_KEY      = os.getenv("DEVTO_API_KEY")
TELEGRAM_BOT   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY")
GROQ_KEY       = os.getenv("GROQ_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
GITHUB_REPO    = os.getenv("GITHUB_REPOSITORY")
STATE_FILE     = "state.json"

# ── AI: OpenRouter Llama → OpenRouter DeepSeek → OpenRouter Gemma → Gemini → Groq ──
def ask_ai(prompt: str, max_tokens: int = 4000) -> str:
    """
    5-provider fallback chain — all free tiers.
    Order: OpenRouter Llama 3.3 70B → OpenRouter DeepSeek R1 →
           OpenRouter Gemma 3 27B  → Gemini 2.0 Flash → Groq Llama 3.3 70B
    """
    errors = []

    def _call_openai_compat(url, headers, model, prompt, max_tokens, name):
        r = requests.post(
            url, headers=headers,
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.7, "max_tokens": max_tokens},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        if "choices" not in data: raise ValueError(f"No choices: {data}")
        text = data["choices"][0]["message"]["content"].strip()
        if len(text) < 50: raise ValueError(f"Too short ({len(text)} chars)")
        print(f"[AI] {name} ✅")
        return text

    # 1–3. OpenRouter free models
    if OPENROUTER_KEY:
        or_headers = {
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type":  "application/json",
            "HTTP-Referer":  "https://coderfact.com",
            "X-Title":       "CoderFact Content Engine",
        }
        or_models = [
            ("meta-llama/llama-3.3-70b-instruct:free", "OpenRouter Llama 3.3 70B"),
            ("deepseek/deepseek-r1:free",               "OpenRouter DeepSeek R1"),
            ("google/gemma-3-27b-it:free",              "OpenRouter Gemma 3 27B"),
        ]
        for model_id, name in or_models:
            try:
                return _call_openai_compat(
                    "https://openrouter.ai/api/v1/chat/completions",
                    or_headers, model_id, prompt, max_tokens, name
                )
            except Exception as e:
                errors.append(f"{name}: {e}")
                print(f"[AI] {name} failed → {e}")

    # 4. Gemini 2.0 Flash
    if GEMINI_KEY:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}},
                timeout=45,
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if len(text) < 50: raise ValueError(f"Too short ({len(text)} chars)")
            print("[AI] Gemini 2.0 Flash ✅")
            return text
        except Exception as e:
            errors.append(f"Gemini: {e}")
            print(f"[AI] Gemini failed → {e}")

    # 5. Groq Llama 3.3 70B (last resort)
    if GROQ_KEY:
        try:
            return _call_openai_compat(
                "https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                "llama-3.3-70b-versatile", prompt, max_tokens, "Groq Llama 3.3 70B"
            )
        except Exception as e:
            errors.append(f"Groq: {e}")
            print(f"[AI] Groq failed → {e}")

    raise RuntimeError("All AI providers failed:\n" + "\n".join(errors))


# ── State: load / save / commit to GitHub ────────────────────────────────────
def load_state():
    return json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}

def save_state(data):
    json.dump(data, open(STATE_FILE, "w"), indent=2)
    if not (GITHUB_TOKEN and GITHUB_REPO): return
    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    hdrs = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = requests.get(api, headers=hdrs).json().get("sha")
    body = {"message": "chore: update state", "content": base64.b64encode(json.dumps(data, indent=2).encode()).decode()}
    if sha: body["sha"] = sha
    requests.put(api, headers=hdrs, json=body)

# ── Telegram ─────────────────────────────────────────────────────────────────
def send_tg(msg):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
                  json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown"})

def get_reply():
    """
    Returns a list of chosen topic numbers (e.g. ['1'], ['1','3'], ['1','2','3']).
    Accepts inputs like: '1', '1 2', '1 2 3', '12', '123', '0' (skip).
    Returns None if no valid reply found today.
    """
    state   = load_state()
    last_id = state.get("last_update_id", 0)
    print(f"[get_reply] last_update_id={last_id}")

    res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT}/getUpdates",
                       params={"offset": last_id + 1, "limit": 20}, timeout=10).json()

    updates = res.get("result", [])
    print(f"[get_reply] {len(updates)} new updates found")

    today = datetime.now(timezone.utc).date()
    # Also accept IST "today" — Suman is in Kolkata (UTC+5:30)
    # A reply at 00:30 IST = 19:00 prev UTC, so check both UTC and IST dates
    ist_offset = timedelta(hours=5, minutes=30)
    today_ist  = (datetime.now(timezone.utc) + ist_offset).date()
    for u in reversed(updates):
        msg     = u.get("message", {})
        text    = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        date    = datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc).date()
        print(f"[get_reply] update_id={u.get('update_id')} chat={chat_id} text='{text}' date={date} today={today}")

        if chat_id != str(TELEGRAM_CHAT) or date not in (today, today_ist):
            continue

        # Parse: "0", "1", "2", "3", "1 2", "1 3", "2 3", "1 2 3", "12", "123" etc.
        digits = [c for c in text.replace(" ", "") if c in "0123"]
        if not digits or len(digits) != len(text.replace(" ", "")):
            continue  # contains invalid characters

        choices = list(dict.fromkeys(digits))  # deduplicate, preserve order

        if "0" in choices:
            save_state({**state, "last_update_id": u["update_id"]})
            return ["0"]

        valid = [c for c in choices if c in ("1", "2", "3")]
        if valid:
            print(f"[get_reply] ✅ Valid choices: {valid}")
            save_state({**state, "last_update_id": u["update_id"]})
            return valid

    print("[get_reply] No valid reply found.")
    return None

# ── Multi-Source Trend Aggregator (8 sources) ────────────────────────────────
def fetch_trends():
    """
    Pulls real-time signals from 8 sources:
    1. GitHub Trending        — what devs are building right now
    2. HackerNews API         — top upvoted tech discussions
    3. Reddit                 — r/programming, r/MachineLearning, r/webdev, r/artificial
    4. Dev.to Trending        — what's getting read on our publish platform
    5. ProductHunt            — new tools launching today
    6. Stack Overflow Blog    — what devs are asking about
    7. AI/Tech RSS feeds      — TechCrunch AI, The Batch, import AI
    8. pytrends               — real Google search trending for coding/AI keywords
    """
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoderFact-Bot/1.0)"}
    signals = {}

    # 1. GitHub Trending (scrape)
    try:
        r = requests.get("https://github.com/trending", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        repos = []
        for article in soup.find_all("article", class_="Box-row")[:10]:
            name_tag  = article.find("h2")
            desc_tag  = article.find("p")
            lang_tag  = article.find("span", itemprop="programmingLanguage")
            stars_tag = article.find("a", href=lambda h: h and "stargazers" in h)
            if name_tag:
                repos.append({
                    "repo":  name_tag.get_text(strip=True).replace("\n","").replace(" ",""),
                    "desc":  desc_tag.get_text(strip=True) if desc_tag else "",
                    "lang":  lang_tag.get_text(strip=True) if lang_tag else "",
                    "stars": stars_tag.get_text(strip=True) if stars_tag else "",
                })
        signals["github"] = repos
        print(f"[trends] GitHub: {len(repos)} repos")
    except Exception as e:
        print(f"[trends] GitHub failed: {e}")
        signals["github"] = []

    # 2. HackerNews top stories
    try:
        top_ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=8).json()[:15]
        hn = []
        for sid in top_ids:
            item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5).json()
            if item and item.get("type") == "story":
                hn.append({"title": item.get("title",""), "score": item.get("score",0), "comments": item.get("descendants",0)})
        signals["hackernews"] = sorted(hn, key=lambda x: x["score"], reverse=True)[:8]
        print(f"[trends] HN: {len(signals['hackernews'])} stories")
    except Exception as e:
        print(f"[trends] HN failed: {e}")
        signals["hackernews"] = []

    # 3. Reddit — 4 subs
    reddit_posts = []
    for sub in ["programming", "MachineLearning", "webdev", "artificial"]:
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=8",
                             headers={**HEADERS,"Accept":"application/json"}, timeout=8)
            for p in r.json()["data"]["children"]:
                d = p["data"]
                if not d.get("stickied"):
                    reddit_posts.append({"title": d.get("title",""), "upvotes": d.get("ups",0),
                                         "comments": d.get("num_comments",0), "sub": sub})
        except Exception as e:
            print(f"[trends] Reddit r/{sub} failed: {e}")
    signals["reddit"] = sorted(reddit_posts, key=lambda x: x["upvotes"], reverse=True)[:12]
    print(f"[trends] Reddit: {len(signals['reddit'])} posts")

    # 4. Dev.to trending
    try:
        articles = requests.get("https://dev.to/api/articles?top=7&per_page=10", headers=HEADERS, timeout=8).json()
        signals["devto"] = [{"title": a.get("title",""), "tags": a.get("tag_list",[]),
                              "reactions": a.get("positive_reactions_count",0)} for a in articles[:8]]
        print(f"[trends] Dev.to: {len(signals['devto'])} articles")
    except Exception as e:
        print(f"[trends] Dev.to failed: {e}")
        signals["devto"] = []

    # 5. ProductHunt — today's top tech launches
    try:
        r = requests.get("https://www.producthunt.com/feed", headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.find_all("item")[:8]
        ph = []
        for item in items:
            title = item.find("title")
            desc  = item.find("description")
            ph.append({
                "title": title.get_text(strip=True) if title else "",
                "desc":  BeautifulSoup(desc.get_text(), "html.parser").get_text()[:120] if desc else "",
            })
        signals["producthunt"] = ph
        print(f"[trends] ProductHunt: {len(ph)} launches")
    except Exception as e:
        print(f"[trends] ProductHunt failed: {e}")
        signals["producthunt"] = []

    # 6. Tech/AI RSS feeds — TechCrunch AI + The Verge Tech + MIT Tech Review
    rss_items = []
    rss_feeds = [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://www.technologyreview.com/feed/",
    ]
    for url in rss_feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:4]:
                rss_items.append(entry.title)
        except Exception:
            pass
    signals["rss_news"] = rss_items[:12]
    print(f"[trends] RSS news: {len(rss_items)} items")

    # 7. Stack Overflow — trending questions via blog RSS
    try:
        feed = feedparser.parse("https://stackoverflow.blog/feed/")
        signals["stackoverflow"] = [e.title for e in feed.entries[:6]]
        print(f"[trends] StackOverflow blog: {len(signals['stackoverflow'])} items")
    except Exception as e:
        print(f"[trends] StackOverflow failed: {e}")
        signals["stackoverflow"] = []

    # 8. Google Trends via pytrends — rising queries for coding/AI keywords
    google_rising = []
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=330, timeout=(10, 25), retries=2, backoff_factor=0.5)
        # Check rising related queries for core topic seeds
        for seed in ["python automation", "AI coding", "machine learning"]:
            try:
                pt.build_payload([seed], timeframe="now 7-d", geo="")
                related = pt.related_queries()
                rising = related.get(seed, {}).get("rising")
                if rising is not None and not rising.empty:
                    google_rising += rising["query"].tolist()[:4]
            except Exception:
                pass
        signals["google_trends"] = list(dict.fromkeys(google_rising))[:12]
        print(f"[trends] Google Trends: {len(signals['google_trends'])} rising queries")
    except ImportError:
        print("[trends] pytrends not installed — skipping Google Trends")
        signals["google_trends"] = []
    except Exception as e:
        print(f"[trends] Google Trends failed: {e}")
        signals["google_trends"] = []

    return signals


def format_signals(signals: dict) -> str:
    lines = []

    if signals.get("google_trends"):
        lines.append("🔍 GOOGLE TRENDS RISING QUERIES (people actively searching these RIGHT NOW):")
        for q in signals["google_trends"][:8]:
            lines.append(f"  • {q}")

    if signals.get("github"):
        lines.append("\n🔥 GITHUB TRENDING (what devs are building):")
        for r in signals["github"][:6]:
            lang = f" [{r['lang']}]" if r["lang"] else ""
            lines.append(f"  • {r['repo']}{lang} — {r['desc'][:80]}")

    if signals.get("hackernews"):
        lines.append("\n📈 HACKER NEWS TOP (score = community interest):")
        for s in signals["hackernews"][:6]:
            lines.append(f"  • [{s['score']}pts, {s['comments']} comments] {s['title']}")

    if signals.get("reddit"):
        lines.append("\n💬 REDDIT HOT:")
        for p in signals["reddit"][:6]:
            lines.append(f"  • [r/{p['sub']}, {p['upvotes']} upvotes] {p['title']}")

    if signals.get("producthunt"):
        lines.append("\n🚀 PRODUCTHUNT (new tools launching today):")
        for p in signals["producthunt"][:4]:
            lines.append(f"  • {p['title']} — {p['desc'][:70]}")

    if signals.get("rss_news"):
        lines.append("\n📰 TECH/AI NEWS (TechCrunch, The Verge, MIT Tech Review):")
        for item in signals["rss_news"][:6]:
            lines.append(f"  • {item}")

    if signals.get("devto"):
        lines.append("\n📝 DEV.TO TRENDING:")
        for a in signals["devto"][:5]:
            tags = ", ".join(a["tags"][:3])
            lines.append(f"  • [{a['reactions']}❤️] {a['title']} ({tags})")

    if signals.get("stackoverflow"):
        lines.append("\n🛠 STACK OVERFLOW BLOG:")
        for s in signals["stackoverflow"][:4]:
            lines.append(f"  • {s}")

    return "\n".join(lines)


# ── PHASE 1: Morning Researcher ───────────────────────────────────────────────
def research():
    today  = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%B %d, %Y")
    state  = load_state()
    title_history = state.get("title_history", [])

    # Gather live trend signals from 4 sources
    print("[research] Fetching live trends...")
    signals      = fetch_trends()
    trend_block  = format_signals(signals)
    print(f"[research] Trend block:\n{trend_block}")

    history_block = ""
    if title_history:
        history_block = "PREVIOUSLY USED TITLES (do NOT repeat or closely paraphrase any of these):\n"
        history_block += "\n".join(f"- {t}" for t in title_history[-30:])
        history_block += "\n\n"

    raw = ask_ai(f"""
You are an SEO strategist for CoderFact — a coding blog by Suman, a frontend developer from Kolkata.
Target audience: developers and small business owners who use AI/automation to save time.

Today is {today}. Here are LIVE real-time signals from 4 sources:

{trend_block}

{history_block}Identify the 3 topics with the highest viral + search potential. Then generate 3 UNIQUE, Google-rankable blog titles.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TITLE SEO RULES — ALL MUST APPLY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. INCLUDE SEARCHABLE KEYWORDS — people search for errors, tools, and how-tos:
   ✓ Name the specific language/tool (Python, Node.js, React, Docker, etc.)
   ✓ Name the specific problem or error (Timeout, Rate Limit, CORS, Memory Leak, etc.)
   ✓ Include an action word (Fix, Automate, Build, Stop, Deploy, Debug)

2. NO DIARY-STYLE TITLES — these don't rank:
   ✗ "My Experience With X"
   ✗ "Thoughts on Y"
   ✗ "Automating My Routines" ← too vague, no keyword
   ✓ "How I Fixed Claude API Timeouts With a Custom Node.js Script"
   ✓ "Stop Manual Deployments: Automate Claude API With Node.js in 30 Minutes"

3. FOLLOW THESE HIGH-EARNING FORMULAS:
   • "How I Fixed [Specific Error] in [Tool] With [Language] (Full Code)"
   • "Stop [Painful Manual Task] — This [Language] Script Does It in [Time]"
   • "The [Specific Tool] Setup That Cut My [Task] From [X] to [Y]"
   • "How to Automate [Specific Workflow] With [Tool] — Step by Step"
   • "[Number] Ways to Fix [Common Error] in [Framework/Tool]"

4. Under 80 characters. Specific. Actionable. Tool + language + outcome in every title.

5. NO banned phrases: "game-changer", "revolutionize", "the future of", "unlock", "master"

Reply ONLY in this format — no explanations, no quotes:
1. [Title]
2. [Title]
3. [Title]
""")

    titles = [l.split(". ", 1)[1].strip().strip('"')
              for l in raw.splitlines() if l.strip()[:2] in ("1.", "2.", "3.")][:3]

    # Append new titles to history and save (keep last 30)
    updated_history = (title_history + titles)[-30:]
    save_state({**state, "topics": titles, "date": today, "title_history": updated_history})
    print(f"[research] Generated: {titles}")
    print(f"[research] Total title history: {len(updated_history)}")

    send_tg(
        f"🔥 *CoderFact — Daily Brief* | _{today}_\n\n"
        + "\n".join(f"{i+1}. {t}" for i, t in enumerate(titles))
        + "\n\n"
        "Reply with your choice:\n"
        "• `1` `2` or `3` — draft one article\n"
        "• `1 2` or `1 3` or `2 3` — draft two\n"
        "• `1 2 3` — draft all three\n"
        "• `0` — skip today"
    )

# ── PHASE 2: Drafter ─────────────────────────────────────────────────────────
def draft_single(title: str, idx: int, total: int):
    """Generate and publish one article. idx/total used for progress messages."""
    progress = f"({idx}/{total}) " if total > 1 else ""

    def tg_step(msg):
        send_tg(f"{progress}{msg}")

    def tg_err(step, e):
        import traceback
        tb = traceback.format_exc()[-600:]
        send_tg(f"❌ {progress}*{step} failed*\n`{str(e)[:300]}`\n\nFull trace in GitHub Actions logs.")
        print(f"[draft_single] {step} error:\n{tb}")

    tg_step(f"⏳ Drafting *\"{title}\"*...")

    # ── Step 1: Complexity ────────────────────────────────────────────────────
    try:
        complexity_raw = ask_ai(f"""Classify this blog post title by complexity: "{title}"
Reply with ONLY a JSON object:
{{"complexity": "simple"|"moderate"|"deep", "reason": "one sentence", "target_words": <600-1000>}}""")
        c = json.loads(complexity_raw.strip("```json").strip("```").strip())
        target_words = min(int(c.get("target_words", 800)), 1000)
        complexity   = _s(c.get("complexity"), "moderate")
        reason       = _s(c.get("reason"), "")
    except Exception as e:
        target_words, complexity, reason = 800, "moderate", ""
        print(f"[draft] Complexity fallback: {e}")
    print(f"[draft] Complexity: {complexity} → {target_words} words")

    # Scale section budgets proportionally to target_words
    hook    = round(target_words * 0.10)
    concept = round(target_words * 0.18)
    build   = round(target_words * 0.50)
    result  = round(target_words * 0.14)
    cta     = round(target_words * 0.08)

    # ── Coercion helpers — available to ALL passes ────────────────────────────
    def _s(val, fallback=""):
        if val is None:           return fallback
        if isinstance(val, dict): return str(next((v for v in val.values() if v), fallback))
        if isinstance(val, list): return " ".join(str(v) for v in val if v)
        return str(val).strip() or fallback

    def _list(val, fallback=None):
        if fallback is None: fallback = []
        if val is None:           return fallback
        if isinstance(val, str):  return [v.strip() for v in val.replace(",","\n").splitlines() if v.strip()]
        if isinstance(val, dict): return [_s(v) for v in val.values() if v]
        if isinstance(val, list): return [_s(v) for v in val if v]
        return fallback

    def _dict(val, keys, fallback=""):
        if not isinstance(val, dict): val = {}
        return {k: _s(val.get(k), fallback) for k in keys}

    # ── Pass 0: Keyword research ──────────────────────────────────────────────
    tg_step("🔍 Pass 0/3: Researching keywords...")
    try:
        kw_research_raw = ask_ai(f"""You are an SEO keyword researcher for coding/developer content on Medium.
Article title: "{title}"
Audience: developers aged 25-34 who search Google when stuck on a problem.

Return ONLY a JSON object — no markdown, no explanation:
{{
  "primary_keyword": "most important specific keyword e.g. 'fix CORS error React vite' not just 'CORS'",
  "secondary_keywords": ["3 closely related terms"],
  "long_tail_keywords": ["4 question-style searches like 'how to fix cors error in react vite 2025'"],
  "lsi_keywords": ["5 semantically related terms Google expects in this article"],
  "keyword_placement": {{
    "title": "rewrite title leading with primary keyword",
    "meta_description": "150-char SEO description with primary + secondary keyword"
  }},
  "medium_tags": ["4 existing Medium/Dev.to tags, lowercase, no hyphens"],
  "competitor_angle": "one sentence: what makes this different from existing articles on this topic"
}}""")
        kw_data = json.loads(kw_research_raw.strip().strip("```json").strip("```").strip())
        if not isinstance(kw_data, dict): raise ValueError("not a dict")
        print(f"[draft] KW research OK")
    except Exception as e:
        tg_err("Pass 0 keyword research", e)
        kw_data = {}

    def _ks(val, fallback=""):
        if not val: return fallback
        if isinstance(val, list): return ", ".join(str(v) for v in val if v)
        return str(val)

    primary_kw       = _s(kw_data.get("primary_keyword"), title)
    secondary_kws    = _list(kw_data.get("secondary_keywords"), [])
    longtail_kws     = _list(kw_data.get("long_tail_keywords"), [])
    lsi_kws          = _list(kw_data.get("lsi_keywords"), [])
    competitor_angle = _s(kw_data.get("competitor_angle"), "Practical tutorial with real working code.")
    kw_placement     = kw_data.get("keyword_placement", {})
    if not isinstance(kw_placement, dict): kw_placement = {}
    seo_title = _s(kw_placement.get("title"), title)
    seo_meta  = _s(kw_placement.get("meta_description"), "")
    kw_tags   = _list(kw_data.get("medium_tags"), [])
    print(f"[draft] primary='{primary_kw}' seo_title='{seo_title}'")

    # ── Pass 1: Outline ───────────────────────────────────────────────────────
    tg_step("📋 Pass 1/3: Building outline...")

    def extract_json(raw: str):
        """Robustly extract JSON from messy AI output."""
        import re as _re
        raw = raw.strip()
        # Strip markdown fences
        raw = _re.sub(r'^```(?:json)?\s*', '', raw, flags=_re.MULTILINE)
        raw = _re.sub(r'```\s*$', '', raw, flags=_re.MULTILINE)
        raw = raw.strip()
        # Try direct parse first
        try:
            return json.loads(raw)
        except Exception:
            pass
        # Find first { ... } block
        start = raw.find('{')
        end   = raw.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(raw[start:end+1])
            except Exception:
                pass
        # Last resort: fix common issues
        # Replace unescaped newlines inside strings
        fixed = _re.sub(r'(?<!\\)\n(?=[^"]*"(?:[^"]*"[^"]*")*[^"]*$)', r'\\n', raw)
        try:
            return json.loads(fixed)
        except Exception as e:
            raise ValueError(f"JSON extraction failed: {e}\nRaw (first 200): {raw[:200]}")

    try:
        outline_raw = ask_ai(f"""You are helping Suman — frontend dev from Kolkata, CoderFact.com — plan a blog post.

Title: "{seo_title}"
Primary keyword: "{primary_kw}"
Secondary: {_ks(secondary_kws, 'none')}
Long-tail: {_ks(longtail_kws, 'none')}
LSI: {_ks(lsi_kws, 'none')}
Competitor angle: {competitor_angle}
Target: ~{target_words} words, complexity: {complexity}

CRITICAL: Return ONLY a JSON object. No markdown. No code fences. No explanation.
Every string value must be valid JSON — no unescaped quotes, no literal newlines inside strings.

{{
  "hook_scene": "2-3 sentences. Specific moment the problem hit Suman.",
  "pain_point": "Exact frustration with tool name and error.",
  "failed_attempts": "1-2 things tried that failed.",
  "solution_name": "Exact tool or library used.",
  "real_metric": "Before/after number e.g. 47 min to 3 min.",
  "surprise_finding": "Unexpected discovery only a builder would know.",
  "reader_benefit": "What reader can do after reading.",
  "h2_headings": ["heading 1","heading 2","heading 3","heading 4"],
  "aeo_h2_headings": ["Question with long-tail keyword 1","Q2","Q3","Q4"],
  "tldr": {{"problem":"one sentence","solution":"one sentence","result":"one sentence"}},
  "engagement_cta": "Specific question for readers.",
  "snippet_plan": [
    {{"section":"H2 heading text","language":"python","style":"before","purpose":"what this shows"}},
    {{"section":"H2 heading text","language":"python","style":"solution","purpose":"what this shows"}},
    {{"section":"H2 heading text","language":"python","style":"bonus","purpose":"what this shows"}}
  ],
  "diagram_plan": [
    {{"section":"H2 heading text","type":"mermaid","purpose":"what flow this shows"}},
    {{"section":"H2 heading text","type":"ascii","purpose":"what structure this shows"}}
  ]
}}

NOTE: snippet_plan and diagram_plan contain DESCRIPTIONS only — no actual code content.
The article writer will generate actual code in Pass 2.
Return ONLY the JSON object.""")

        outline = extract_json(outline_raw)
        if not isinstance(outline, dict): raise ValueError("outline is not a dict")
        print(f"[draft] Outline OK — snippets:{len(outline.get('snippet_plan',[]))}, diagrams:{len(outline.get('diagram_plan',[]))}")

    except Exception as e:
        tg_err("Pass 1 outline", e)
        outline = {}

    # Build backward-compatible snippet/diagram lists from new plan format
    def _plan_to_snippets(outline):
        raw = outline.get("snippet_plan") or outline.get("code_snippets", [])
        if not isinstance(raw, list): return []
        result = []
        for s in raw:
            if not isinstance(s, dict): continue
            result.append({
                "section":  _s(s.get("section"), ""),
                "language": _s(s.get("language"), "python"),
                "purpose":  _s(s.get("purpose"),  ""),
                "style":    _s(s.get("style"),     "solution"),
                "content":  _s(s.get("content"),   ""),  # empty — Pass 2 writes actual code
            })
        return result

    def _plan_to_diagrams(outline):
        raw = outline.get("diagram_plan") or outline.get("diagrams", [])
        if not isinstance(raw, list): return []
        result = []
        for d in raw:
            if not isinstance(d, dict): continue
            result.append({
                "section": _s(d.get("section"), ""),
                "type":    _s(d.get("type"),    "ascii"),
                "purpose": _s(d.get("purpose"), ""),
                "content": _s(d.get("content"), ""),  # empty — Pass 2 writes actual diagram
            })
        return result

    snippets = _plan_to_snippets(outline)
    diagrams = _plan_to_diagrams(outline)

    try:
        outline_raw = outline_raw.strip().strip("```json").strip("```").strip()
        outline = json.loads(outline_raw)
        if not isinstance(outline, dict):
            raise ValueError("outline is not a dict")
    except Exception as e:
        print(f"[draft] Outline parse failed: {e} — using defaults")
        outline = {}

    # ── Extract and harden outline fields ─────────────────────────────────────
    hook_scene      = _s(outline.get("hook_scene"),      "It was 11pm when the error hit again.")
    pain_point      = _s(outline.get("pain_point"),      "The manual process was killing my time.")
    failed_attempts = _s(outline.get("failed_attempts"), "The obvious fixes didn't work.")
    solution_name   = _s(outline.get("solution_name"),   "a custom script")
    real_metric     = _s(outline.get("real_metric"),     "cut time from 45 mins to under 3")
    surprise_finding= _s(outline.get("surprise_finding"),"The hardest part wasn't the code.")
    reader_benefit  = _s(outline.get("reader_benefit"),  "build this in under an hour")
    meta_desc       = _s(outline.get("meta_description"),f"How to fix {title.lower()} with working code.")
    engagement_cta  = _s(outline.get("engagement_cta"),  "What would you do differently? Drop it in the comments.")
    seo_keywords    = _list(outline.get("seo_keywords"),  ["python","automation","tutorial","coding","developer"])

    h2_default = [
        "Why This Problem Is More Painful Than It Looks",
        "What I Tried First (And Why It Failed)",
        "The Actual Fix — With the Full Code",
        "Results, Surprises, and What I'd Do Differently",
    ]
    aeo_default = [
        "Why Does This Problem Keep Happening?",
        "How Do You Fix It Without Breaking Everything Else?",
        "What Does the Full Working Code Look Like?",
        "How Much Time Does This Actually Save?",
    ]
    h2_headings  = _list(outline.get("h2_headings"),     h2_default) or h2_default
    aeo_headings = _list(outline.get("aeo_h2_headings"), aeo_default) or aeo_default

    tldr_raw = outline.get("tldr", {})
    tldr = _dict(tldr_raw, ["problem","solution","result"], "")
    if not any(tldr.values()):
        tldr = {"problem": pain_point, "solution": solution_name, "result": real_metric}

    devto_tags_raw = outline.get("devto_tags", [])
    raw_tag_list   = _list(devto_tags_raw, ["python","tutorial","webdev","programming"])
    def clean_tag(t):
        return str(t).lower().strip().strip('"').strip("'").replace("-","").replace(" ","")
    devto_tags = [clean_tag(t) for t in raw_tag_list if t][:4] or ["python","tutorial","webdev","programming"]

    # snippets and diagrams already built by _plan_to_snippets/_plan_to_diagrams above

    snippets_block = ""
    if snippets:
        snippets_block = "\nCODE SNIPPET PLAN — write actual code for each in the section indicated:\n"
        for i, s in enumerate(snippets, 1):
            snippets_block += (
                f"\nSnippet {i} [{s['style'].upper()}] → Section: \"{s['section']}\"\n"
                f"Language: {s['language']} | Purpose: {s['purpose']}\n"
                f"Write at least 8 lines of real, working, well-commented code.\n"
            )

    diagrams_block = ""
    if diagrams:
        diagrams_block = "\nDIAGRAM PLAN — create actual diagram content for each in the section indicated:\n"
        for i, d in enumerate(diagrams, 1):
            dtype = d["type"]
            diagrams_block += (
                f"\nDiagram {i} [{dtype.upper()}] → Section: \"{d['section']}\"\n"
                f"Purpose: {d['purpose']}\n"
            )
            if dtype == "mermaid":
                diagrams_block += "Use proper Mermaid syntax (graph TD, sequenceDiagram, etc.)\n"
            else:
                diagrams_block += "Use ASCII box-drawing characters for architecture/flow.\n"

    # ── Pass 2: Write article ─────────────────────────────────────────────────
    tg_step("✍️ Pass 2/3: Writing article...")
    try:
        article = ask_ai(f"""
You are ghostwriting a blog post for Suman — a frontend developer from Kolkata who runs CoderFact (coderfact.com).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUMAN'S VOICE — READ THIS TWICE BEFORE WRITING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Suman is a real developer. Not a blogger. Not a content marketer.
He figures stuff out at 11pm, writes about it the next morning, still mildly annoyed it took so long.

PATTERNS HE ACTUALLY USES:
• Opens mid-frustration: "I spent three hours on this. THREE hours. For a config change."
• Uses "I" obsessively — this is his personal experience, not a generic tutorial
• Casually admits mistakes: "I should've checked the docs first. I didn't. You can guess what happened."
• Drops in bracket asides: "(which, by the way, is not documented anywhere)", "(no seriously, try it)"
• Uses contrast for punch: "The wrong way takes 40 mins. The right way? 90 seconds."
• Short questions to the reader: "Sound familiar?" / "Ever been there?" / "Yeah. Me too."
• References real Indian dev context naturally: "My client was calling at 9am. It was 1am. Kolkata time."
• Ends sections abruptly, like finishing a thought: "Anyway. That's the problem. Let's fix it."

VOICE CHECKLIST — every paragraph must pass:
☑ Would a real tired developer say this out loud?
☑ Does it sound like ONE specific person, not generic content?
☑ No padding — if a sentence doesn't add info or personality, delete it
☑ No throat-clearing ("In this article, we will explore...")
☑ No summary at the end ("In conclusion...")

BANNED WORDS (automatic rejection if found):
delve, navigate, leverage, landscape, robust, seamless, unleash, utilize, empower,
groundbreaking, revolutionize, game-changer, synergy, cutting-edge, supercharge,
spearhead, foster, facilitate, paradigm, holistic, it is worth noting, it should be noted,
furthermore, moreover, additionally, in addition, in conclusion, in summary, to summarize

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SEO REQUIREMENTS — DYNAMIC, NOT GENERIC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Primary keyword (MUST appear in: first paragraph, at least 2 H2s, last paragraph):
  → "{primary_kw}"

Secondary keywords (use 2-3 times each, naturally):
  → {_ks(secondary_kws, 'use related terms naturally')}

Long-tail keywords (work these into H2 headings and paragraph text):
  → {_ks(longtail_kws, 'use specific question phrases')}

LSI keywords (Google expects these in an article on this topic — use naturally):
  → {_ks(lsi_kws, 'use semantically related terms')}

SEO meta description to use (append at end as META: line):
  → {seo_meta if seo_meta else f'How to fix {primary_kw} with working code and real examples.'}

Competitor angle — what makes this article DIFFERENT:
  → {competitor_angle}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARTICLE BRIEF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: "{seo_title}"
Target: ~{target_words} words MAX — cut ruthlessly, no padding
Hook scene (open with this, no heading): {hook_scene}
Pain point: {pain_point}
What failed first: {failed_attempts}
The solution: {solution_name}
Real metric to use: {real_metric}
Surprising finding: {surprise_finding}
What reader can do after: {reader_benefit}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURE — exact AEO H2 headings (do NOT rewrite these)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(f'## {h}' for h in aeo_headings)}

These are phrased as questions so Google's Answer Engine indexes them as direct answers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MANDATORY STRUCTURE RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. OPEN with hook scene — no title, no "Introduction". Jump in mid-story.
   Primary keyword "{primary_kw}" must appear in the first 50 words naturally.

2. IMMEDIATELY after hook, before first H2, insert TL;DR:
   **TL;DR**
   - **Problem:** {tldr.get('problem', pain_point)}
   - **Solution:** {tldr.get('solution', solution_name)}
   - **Result:** {tldr.get('result', real_metric)}

3. EVERY H2 section MUST contain at least one of: code block, diagram, or table.
   No section can be text-only.

4. USE ALL pre-planned code snippets (place in section indicated):
{snippets_block}

5. USE ALL pre-planned diagrams (place in section indicated):
{diagrams_block}

6. RESULTS section must include a before/after table:
   | Metric | Before | After |
   |--------|--------|-------|
   (fill with real numbers from: {real_metric})

7. END with:
   — 2 sentences of genuine close (no "In conclusion")
   — This blockquote: > {engagement_cta}
   — Final line: "Found this useful? The clap button is right there 👇 It literally takes one tap and it tells me what to write next."

8. After article body, on separate lines:
   TAGS: {json.dumps(kw_tags if kw_tags else devto_tags)}
   META: {seo_meta if seo_meta else meta_desc}

Output ONLY in Markdown. Start with the hook. Zero preamble.
""")
        if not article or len(article) < 200:
            raise ValueError(f"Article too short ({len(article)} chars) — AI may have returned empty response")
        print(f"[draft] Article generated: {len(article)} chars")
    except Exception as e:
        tg_err("Pass 2 article writing", e)
        raise  # re-raise so draft() catches it and moves to next article

    meta  = ""
    tags_line = ""
    clean = []
    for line in article.splitlines():
        if line.strip().startswith("META:"):
            meta = line.replace("META:", "").strip()
        elif line.strip().startswith("TAGS:"):
            tags_line = line.replace("TAGS:", "").strip()
        else:
            clean.append(line)
    body = "\n".join(clean).strip()
    print(f"[draft] Body: {len(body)} chars, meta: {bool(meta)}")

    # Parse tags — Dev.to rules: max 4, lowercase, no spaces/hyphens/special chars
    def sanitize_tag(t):
        return t.strip().strip('"').strip("'").lower().replace("-", "").replace(" ", "")

    try:
        raw_tags = [sanitize_tag(t) for t in tags_line.strip("[]").split(",")]
        tags = [t for t in raw_tags if t][:4]
        if len(tags) < 2:
            raise ValueError
    except Exception:
        try:
            raw = ask_ai(
                f'Return ONLY a JSON array of 4 Dev.to tags for: "{title}". '
                'Rules: lowercase, no spaces, no hyphens, max 4 items. '
                'Choose from: python, programming, webdev, javascript, ai, tutorial, automation, productivity, devops, beginners. '
                'No explanation.'
            ).strip("```json").strip("```")
            tags = [sanitize_tag(t) for t in json.loads(raw)][:4]
        except Exception:
            tags = ["python", "programming", "automation", "tutorial"]

    # ── Dynamic Image System ──────────────────────────────────────────────────
    import re as _re

    def slugify(text, words=16):
        text = _re.sub(r'[^\w\s]', '', str(text).lower())
        return "-".join(text.split()[:words])

    def pollinations(prompt, w=1280, h=720, seed=None):
        """Generate high-quality specific image via Pollinations flux model."""
        seed_part = f"&seed={seed}" if seed else ""
        return (
            f"https://image.pollinations.ai/prompt/{slugify(prompt)}?"
            f"width={w}&height={h}&model=flux&nologo=true&enhance=true{seed_part}"
        )

    # ── Pass 3: Deep visual analysis — images, diagrams, flowcharts, charts ──
    tg_step("🎨 Pass 3/3: Planning visuals & publishing...")

    article_tech  = _s(solution_name, title)
    article_kw    = primary_kw
    body_headings = [l[3:].strip() for l in body.splitlines() if l.startswith("## ")]
    has_mermaid   = "```mermaid" in body
    has_table     = "| ---" in body or "|---" in body

    try:
        visual_plan_raw = ask_ai(f"""You are a senior technical content designer for CoderFact.
Your job: make this article VISUALLY STUNNING and maximally useful by deciding WHERE to inject each type of visual.

ARTICLE TITLE: "{seo_title}"
MAIN TECHNOLOGY: "{article_tech}"
PRIMARY KEYWORD: "{article_kw}"
ARTICLE ALREADY HAS MERMAID: {has_mermaid}
ARTICLE ALREADY HAS TABLES: {has_table}

ACTUAL H2 HEADINGS IN ARTICLE:
{chr(10).join(f'  - "{h}"' for h in body_headings)}

ARTICLE BODY:
{body[:4000]}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VISUAL TYPES YOU CAN ADD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TYPE 1 — image
  Pollinations AI image. Use for: hero banner, tool screenshots, architecture
  visualization, result dashboards, concept illustrations.
  Prompt MUST be specific to "{article_tech}" — never generic.

TYPE 2 — mermaid_flowchart
  Add ONLY if article has a process/flow/decision tree not already shown.
  Use: graph TD with proper node labels.
  Example content:
    graph TD
      A[User Request] --> B{{CORS Header Present?}}
      B -->|Yes| C[Allow Request]
      B -->|No| D[Block + Error]

TYPE 3 — mermaid_sequence
  Add ONLY if article has API calls / client-server interactions.
  Use: sequenceDiagram with realistic actor names from the article.

TYPE 4 — ascii_diagram
  For architecture, file structures, data flow between components.
  Use box-drawing chars. Example:
    ┌─────────────┐    ┌──────────────┐
    │   Browser   │───▶│  Vite Proxy  │───▶ API Server
    └─────────────┘    └──────────────┘

TYPE 5 — comparison_table
  Add ONLY if article compares options, tools, approaches, or benchmarks.
  Must have real data from the article.

TYPE 6 — callout
  A highlighted tip/warning/note block using markdown blockquote.
  Use for: gotchas, important notes, time-saving tips.
  Example: > 💡 **Pro tip:** ...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Hero image (after="") is MANDATORY — always add it first
2. Read EVERY section. Add a visual wherever it helps understanding
3. Add mermaid_flowchart if ANY section describes a process/pipeline
4. Add mermaid_sequence if ANY section shows request/response flow
5. Add ascii_diagram if ANY section describes components/architecture
6. Add comparison_table if ANY section has performance data or tool comparison
7. Add callouts for any gotcha, tip, or warning you spot in the content
8. For images: max 4 total, prompts must mention "{article_tech}" specifically
9. For diagrams/tables: add as many as genuinely fit — these are always valuable
10. Use EXACT heading text from the list above for all "after" fields

Return ONLY a valid JSON array — no markdown fences, no explanation:
[
  {{
    "type": "image",
    "after": "",
    "prompt": "{article_tech} {article_kw} dark terminal professional cinematic 4k",
    "style": "dark-terminal-code",
    "size": "hero",
    "alt": "specific alt text"
  }},
  {{
    "type": "mermaid_flowchart",
    "after": "exact heading from list",
    "content": "graph TD\\n  A[Step] --> B{{Decision}}\\n  B -->|Yes| C[Result]",
    "caption": "short caption"
  }},
  {{
    "type": "ascii_diagram",
    "after": "exact heading from list",
    "content": "┌───────┐\\n│ Box   │\\n└───────┘",
    "caption": "short caption"
  }},
  {{
    "type": "comparison_table",
    "after": "exact heading from list",
    "content": "| Approach | Time | Complexity |\\n|----------|------|------------|\\n| Before | 45 min | High |\\n| After | 2 min | Low |",
    "caption": "short caption"
  }},
  {{
    "type": "callout",
    "after": "exact heading from list",
    "content": "> 💡 **Pro tip:** specific actionable tip from article content",
    "caption": ""
  }}
]""", max_tokens=3000)

        import re as _re2
        vplan_raw  = visual_plan_raw.strip().strip("```json").strip("```").strip()
        arr_match  = _re2.search(r'\[.*\]', vplan_raw, _re2.DOTALL)
        visual_plan = json.loads(arr_match.group() if arr_match else vplan_raw)
        if not isinstance(visual_plan, list): raise ValueError("not a list")

        # Filter out generic/short image prompts
        visual_plan = [
            v for v in visual_plan if isinstance(v, dict) and (
                v.get("type") != "image" or len(str(v.get("prompt", ""))) > 40
            )
        ]
        print(f"[images] AI planned {len(visual_plan)} visuals: "
              f"{sum(1 for v in visual_plan if v.get('type')=='image')} imgs, "
              f"{sum(1 for v in visual_plan if 'mermaid' in str(v.get('type','')))} mermaid, "
              f"{sum(1 for v in visual_plan if v.get('type') in ('ascii_diagram','comparison_table','callout'))} other")
    except Exception as e:
        print(f"[images] Visual plan failed: {e} — minimal fallback")
        visual_plan = [{
            "type": "image", "after": "",
            "prompt": f"{article_tech} {article_kw} dark terminal professional developer cinematic 4k",
            "style": "dark-terminal-code", "size": "hero", "alt": seo_title,
        }]

    # Style → detailed visual descriptor appended to every image prompt
    STYLE_PROMPTS = {
        "dark-terminal-code":       "VS Code dark theme terminal code editor professional screenshot realistic",
        "architecture-diagram":     "clean technical architecture diagram white background boxes arrows labels minimal professional",
        "diagram-flowchart":        "clean flowchart diagram dark background neon lines decision boxes professional technical",
        "before-after-comparison":  "split panel before after comparison dark terminal output green text professional",
        "benchmark-graph-results":  "performance benchmark bar chart dark background green improvement metrics professional data viz",
        "concept-illustration":     "clean technical concept illustration flat design dark background labeled components",
        "frustrated-dev-at-screen": "cinematic developer frustrated at laptop multiple error screens dark office 4k realistic",
        "tool-screenshot-ui":       "clean modern dark UI dashboard screenshot professional tool interface realistic",
    }
    SIZE_MAP = {
        "hero":   (1280, 720),
        "wide":   (900,  500),
        "inline": (700,  380),
    }

    def build_enriched_body(body: str, visual_plan: list) -> str:
        lines  = body.splitlines()
        output = []
        used_seeds = set()

        def next_seed(base):
            s = int(base)
            while s in used_seeds: s += 1
            used_seeds.add(s)
            return s

        def _ts(val, fallback=""):
            if val is None: return fallback
            if isinstance(val, dict): return str(val.get("section") or val.get("heading") or val.get("text") or fallback)
            if isinstance(val, list): return " ".join(str(v) for v in val)
            return str(val).strip()

        def sanitize_item(item):
            t = _ts(item.get("type"), "image")
            return {
                "type":     t,
                "after":    _ts(item.get("after"),    ""),
                "prompt":   _ts(item.get("prompt"),   title),
                "style":    _ts(item.get("style"),    "dark-terminal-code"),
                "size":     _ts(item.get("size"),     "wide"),
                "alt":      _ts(item.get("alt"),      title),
                "language": _ts(item.get("language"), "python"),
                "content":  _ts(item.get("content"),  ""),
                "caption":  _ts(item.get("caption"),  ""),
            }

        def render_item(item: dict) -> str:
            """Convert a visual plan item into Markdown."""
            t       = item["type"]
            caption = f"\n*{item['caption']}*\n" if item["caption"] else "\n"

            if t == "image":
                style_kw = STYLE_PROMPTS.get(item["style"], "dark neon professional developer")
                w, h     = SIZE_MAP.get(item["size"], (900, 500))
                seed     = next_seed(abs(hash(item["after"])) % 1000 + 10)
                url      = pollinations(f"{item['prompt']} {style_kw}", w, h, seed)
                return f"\n![{item['alt']}]({url})\n"

            elif t == "mermaid_flowchart" or t == "mermaid_sequence":
                fence = "mermaid"
                return f"{caption}```{fence}\n{item['content']}\n```\n"

            elif t == "ascii_diagram":
                return f"{caption}```\n{item['content']}\n```\n"

            elif t == "comparison_table":
                return f"{caption}{item['content']}\n"

            elif t == "callout":
                return f"\n{item['content']}\n"

            elif t == "code":
                lang = item["language"] or "python"
                return f"{caption}```{lang}\n{item['content']}\n```\n"

            return ""

        safe_plan  = [sanitize_item(item) for item in visual_plan if isinstance(item, dict)]
        insertions = {}
        for i, item in enumerate(safe_plan):
            insertions.setdefault(item["after"], []).append((i, item))

        # Hero and other top items (after="")
        top_items = insertions.pop("", [])
        for _, item in top_items:
            if item["type"] == "image":
                style_kw = STYLE_PROMPTS.get(item["style"], "dark background neon developer")
                url = pollinations(f"{item['prompt']} {style_kw}", 1280, 720, next_seed(42))
                output.append(f"![{item['alt']}]({url})\n")
            else:
                output.append(render_item(item))

        for line in lines:
            output.append(line)
            ls = line.strip()
            for trigger, items in list(insertions.items()):
                if not trigger: continue
                if (ls.startswith("## ") and trigger in ls) or ls.startswith(trigger[:40]):
                    for _, item in items:
                        output.append(render_item(item))
                    del insertions[trigger]

        return "\n".join(output)

    # ── Run Pass 3 ────────────────────────────────────────────────────────────
    try:
        enriched_body = build_enriched_body(body, visual_plan)
        print(f"[draft] Enriched body: {len(enriched_body)} chars")
    except Exception as e:
        tg_err("Pass 3 visual injection", e)
        enriched_body = body   # fallback — still publish without images

    # ── Assemble final content ────────────────────────────────────────────────
    content = (
        f"{enriched_body}\n\n"
        f"---\n"
        f"*More free tools and tutorials at [CoderFact](https://coderfact.com). "
        f"AI-assisted draft, reviewed and edited by me.*"
    )

    # ── Publish to Dev.to ─────────────────────────────────────────────────────
    print(f"[draft] Publishing — title='{seo_title}' tags={tags} DEVTO_KEY={bool(DEVTO_KEY)}")
    try:
        res = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
            json={"article": {
                "title": seo_title,
                "body_markdown": content,
                "published": False,
                "tags": tags,
                "canonical_url": "https://coderfact.com",
            }},
            timeout=20,
        )
        print(f"[draft] Dev.to → {res.status_code}: {res.text[:200]}")

        if res.status_code == 201:
            draft_url = res.json().get("url", "https://dev.to/dashboard")
            send_tg(
                f"✅ {progress}*Draft ready on Dev.to!*\n\n"
                f"📝 _{seo_title}_\n"
                f"📏 ~{target_words} words _{complexity}_\n"
                f"🎯 _{hook_scene[:80]}..._\n"
                f"📊 _{real_metric}_\n"
                f"🏷 {', '.join(tags)}\n"
                f"📌 {meta or meta_desc}\n\n"
                f"👉 [Open draft]({draft_url})"
            )
        else:
            send_tg(f"❌ Dev.to error {res.status_code}:\n`{res.text[:300]}`\nCheck GitHub Actions logs.")
    except Exception as e:
        tg_err("Dev.to publish", e)
        raise


def draft():
    """Orchestrator: reads reply, loops over chosen topics."""
    choices = get_reply()
    if choices is None:
        return print("No reply yet.")
    if choices == ["0"]:
        return send_tg("👌 Skipping today. See you tomorrow!")

    topics = load_state().get("topics", [])
    state_date = load_state().get("date", "")
    today_str  = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%B %d, %Y")
    print(f"[draft] choices={choices} state_date='{state_date}' today='{today_str}' topics={topics}")

    if not topics:
        return send_tg("⚠️ No topics found. Morning researcher hasn't run yet today.")
    if state_date and state_date != today_str:
        return send_tg(f"⚠️ Topics in state are from {state_date}, not today ({today_str}). Wait for today's morning brief or run researcher manually.")

    # Validate choices against available topics
    valid = [c for c in choices if int(c) <= len(topics)]
    if not valid:
        return send_tg("⚠️ Invalid choice. Topics 1–3 only.")

    total = len(valid)
    if total > 1:
        titles_list = "\n".join(f"{c}. {topics[int(c)-1]}" for c in valid)
        send_tg(f"📋 Drafting *{total} articles*:\n{titles_list}\n\nThis will take ~{total * 60} seconds.")

    for idx, choice in enumerate(valid, 1):
        title = topics[int(choice) - 1]
        try:
            draft_single(title, idx, total)
        except Exception as e:
            send_tg(f"❌ Article {idx}/{total} failed: {str(e)[:200]}\nMoving to next...")
            print(f"[draft] draft_single failed for '{title}': {e}")

    if total > 1:
        send_tg(f"🎉 All {total} drafts done! Check your Dev.to dashboard.")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    {"research": research, "draft": draft}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print("Usage: python agent.py research | draft"))()