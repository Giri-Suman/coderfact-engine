import os, sys, json, base64, requests, feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

DEVTO_KEY     = os.getenv("DEVTO_API_KEY")
TELEGRAM_BOT  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY    = os.getenv("GEMINI_API_KEY")
GROQ_KEY      = os.getenv("GROQ_API_KEY")
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN")
GITHUB_REPO   = os.getenv("GITHUB_REPOSITORY")
STATE_FILE    = "state.json"

# ── AI: Gemini 2.0 Flash → Groq fallback ────────────────────────────────────
def ask_ai(prompt):
    # Try Gemini 2.0 Flash (free tier, current stable model)
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}"
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        print(f"Gemini failed → trying Groq: {e}")

    # Fallback: Groq (llama-3.3-70b is current free model)
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if "choices" not in data:
            raise ValueError(f"Groq bad response: {data}")
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Both Gemini and Groq failed. Last error: {e}")

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

# ── Multi-Source Trend Aggregator ────────────────────────────────────────────
def fetch_trends():
    """
    Scrapes/fetches from 4 real-time sources:
    1. GitHub Trending  — what devs are actually building right now
    2. HackerNews API   — top upvoted tech discussions
    3. Reddit           — r/programming + r/MachineLearning hot posts
    4. Dev.to           — trending articles on the platform we publish on
    Returns a structured dict of signals per source.
    """
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoderFact-Bot/1.0)"}
    signals = {}

    # 1. GitHub Trending (scrape — no API exists)
    try:
        r = requests.get("https://github.com/trending", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        repos = []
        for article in soup.find_all("article", class_="Box-row")[:10]:
            name_tag = article.find("h2")
            desc_tag = article.find("p")
            lang_tag = article.find("span", itemprop="programmingLanguage")
            stars_tag = article.find("a", href=lambda h: h and "stargazers" in h)
            if name_tag:
                repos.append({
                    "repo": name_tag.get_text(strip=True).replace("\n", "").replace(" ", ""),
                    "desc": desc_tag.get_text(strip=True) if desc_tag else "",
                    "lang": lang_tag.get_text(strip=True) if lang_tag else "",
                    "stars": stars_tag.get_text(strip=True) if stars_tag else "",
                })
        signals["github_trending"] = repos
        print(f"[trends] GitHub: {len(repos)} repos")
    except Exception as e:
        print(f"[trends] GitHub failed: {e}")
        signals["github_trending"] = []

    # 2. HackerNews — top stories via official API
    try:
        top_ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=8).json()[:12]
        hn_stories = []
        for sid in top_ids:
            item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5).json()
            if item and item.get("type") == "story":
                hn_stories.append({
                    "title": item.get("title", ""),
                    "score": item.get("score", 0),
                    "comments": item.get("descendants", 0),
                    "url": item.get("url", ""),
                })
        signals["hackernews"] = sorted(hn_stories, key=lambda x: x["score"], reverse=True)[:8]
        print(f"[trends] HN: {len(signals['hackernews'])} stories")
    except Exception as e:
        print(f"[trends] HN failed: {e}")
        signals["hackernews"] = []

    # 3. Reddit — r/programming + r/MachineLearning (no auth needed for JSON)
    reddit_posts = []
    for sub in ["programming", "MachineLearning", "webdev"]:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json?limit=8",
                headers={**HEADERS, "Accept": "application/json"},
                timeout=8,
            )
            posts = r.json()["data"]["children"]
            for p in posts:
                d = p["data"]
                if not d.get("stickied"):
                    reddit_posts.append({
                        "title": d.get("title", ""),
                        "upvotes": d.get("ups", 0),
                        "comments": d.get("num_comments", 0),
                        "sub": sub,
                    })
        except Exception as e:
            print(f"[trends] Reddit r/{sub} failed: {e}")
    signals["reddit"] = sorted(reddit_posts, key=lambda x: x["upvotes"], reverse=True)[:10]
    print(f"[trends] Reddit: {len(signals['reddit'])} posts")

    # 4. Dev.to trending articles (free API, no key needed)
    try:
        r = requests.get(
            "https://dev.to/api/articles?top=7&per_page=10",
            headers=HEADERS, timeout=8
        )
        articles = r.json()
        signals["devto"] = [
            {
                "title": a.get("title", ""),
                "tags": a.get("tag_list", []),
                "reactions": a.get("positive_reactions_count", 0),
                "comments": a.get("comments_count", 0),
            }
            for a in articles[:8]
        ]
        print(f"[trends] Dev.to: {len(signals['devto'])} articles")
    except Exception as e:
        print(f"[trends] Dev.to failed: {e}")
        signals["devto"] = []

    return signals


def format_signals(signals: dict) -> str:
    """Convert raw trend signals into a clean text block for the AI prompt."""
    lines = []

    if signals.get("github_trending"):
        lines.append("🔥 GITHUB TRENDING (what devs are building RIGHT NOW):")
        for r in signals["github_trending"][:6]:
            lang = f" [{r['lang']}]" if r["lang"] else ""
            lines.append(f"  • {r['repo']}{lang} — {r['desc'][:80]}")

    if signals.get("hackernews"):
        lines.append("\n📈 HACKER NEWS TOP STORIES (score = community interest):")
        for s in signals["hackernews"][:6]:
            lines.append(f"  • [{s['score']} pts, {s['comments']} comments] {s['title']}")

    if signals.get("reddit"):
        lines.append("\n💬 REDDIT HOT (real developer conversations):")
        for p in signals["reddit"][:6]:
            lines.append(f"  • [r/{p['sub']}, {p['upvotes']} upvotes] {p['title']}")

    if signals.get("devto"):
        lines.append("\n📝 DEV.TO TRENDING (what's getting read on our platform):")
        for a in signals["devto"][:5]:
            tags = ", ".join(a["tags"][:3])
            lines.append(f"  • [{a['reactions']}❤️] {a['title']} ({tags})")

    return "\n".join(lines)


# ── PHASE 1: Morning Researcher ───────────────────────────────────────────────
def research():
    today  = datetime.now(timezone.utc).strftime("%B %d, %Y")
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
    send_tg(f"⏳ {progress}Drafting *\"{title}\"*... ~60 seconds")

    # Dynamically decide article length based on topic complexity
    complexity_raw = ask_ai(f"""
Classify this blog post title by complexity: "{title}"

Reply with ONLY a JSON object, nothing else:
{{"complexity": "simple"|"moderate"|"deep", "reason": "one sentence", "target_words": <number between 600 and 1000>}}

Rules for target_words:
- simple (concept/tip/list): 600–700
- moderate (tool/tutorial): 700–850  
- deep (build/architecture/code-heavy): 850–1000
""")
    try:
        c = json.loads(complexity_raw.strip("```json").strip("```").strip())
        target_words = min(int(c.get("target_words", 800)), 1000)
        complexity   = c.get("complexity", "moderate")
        reason       = c.get("reason", "")
    except Exception:
        target_words, complexity, reason = 800, "moderate", ""

    print(f"Complexity: {complexity} → {target_words} words ({reason})")

    # Scale section budgets proportionally to target_words
    hook    = round(target_words * 0.10)
    concept = round(target_words * 0.18)
    build   = round(target_words * 0.50)
    result  = round(target_words * 0.14)
    cta     = round(target_words * 0.08)

    # ── Pass 1: Generate a rich, specific outline before writing ──
    outline_raw = ask_ai(f"""
You are helping Suman — a frontend developer from Kolkata who runs CoderFact (coderfact.com) — plan a deeply visual, human-written blog post.

Title: "{title}"
Target length: ~{target_words} words
Complexity: {complexity}

Create a DETAILED outline. Every field must be hyper-specific and feel lived-in.
This outline drives Pass 2 which writes the full article — be precise.

Analyze the topic carefully and decide which VISUAL ELEMENTS fit naturally:
- flowcharts (when showing a process/decision/pipeline)
- ASCII diagrams (when showing architecture, data flow, file structure, before/after)
- Mermaid diagrams (when showing sequences, state machines, entity relationships)
- code animations described as step-by-step commented code (when showing how something builds up)
- tables (when comparing options, benchmarking, listing params)
- numbered step lists with inline code (when showing a CLI workflow)

Return ONLY a JSON object:
{{
  "hook_scene": "2-3 sentences. Specific time, what Suman was doing, exact moment problem hit.",
  "pain_point": "The exact frustration. Name the tool, error, wasted time.",
  "failed_attempts": "1-2 things tried first that failed. Makes story credible.",
  "solution_name": "Exact tool/library/technique that solved it.",
  "real_metric": "Specific before/after number. E.g. 47 min → 3 min, 200 lines → 18 lines.",
  "surprise_finding": "One unexpected discovery. Only someone who built this would know.",
  "reader_benefit": "What reader can DO after reading.",
  "seo_keywords": ["kw1","kw2","kw3","kw4","kw5"],
  "h2_headings": ["heading1","heading2","heading3","heading4"],
  "aeo_h2_headings": ["Question-style H2 for AEO 1","Question-style H2 for AEO 2","Question-style H2 for AEO 3","Question-style H2 for AEO 4"],
  "tldr": {{
    "problem": "One sentence — name the specific error or pain (e.g. ETIMEDOUT errors on Claude API batch calls)",
    "solution": "One sentence — name the exact tool/script/fix used",
    "result": "One sentence — the specific metric (e.g. deployment time cut from 45 min to 2 min)"
  }},
  "devto_tags": ["tag1","tag2","tag3","tag4"],
  "meta_description": "One punchy SEO sentence under 160 chars.",
  "engagement_cta": "A specific question to ask readers at the end that encourages comments. Should relate to the article topic. E.g.: 'What deployment step wastes the most time for you? Drop it in the comments — I'm building a follow-up on that next.'"

  "code_snippets": [
    {{
      "section": "which H2 heading this belongs to",
      "language": "python|bash|javascript|yaml|json|etc",
      "purpose": "what this snippet proves or demonstrates",
      "style": "before|solution|bonus",
      "content": "actual working code here — not a placeholder. minimum 8 lines. well commented."
    }}
  ],

  "diagrams": [
    {{
      "section": "which H2 heading this belongs to",
      "type": "mermaid|ascii|table",
      "purpose": "what concept this diagram explains",
      "content": "the full diagram content here — not a placeholder. for mermaid use proper syntax. for ascii use box-drawing chars."
    }}
  ],

  "visual_summary": "One sentence describing the overall visual richness planned for this article."
}}

Rules:
- code_snippets: minimum 3 snippets. At least one before (broken/naive), one solution (full working), one bonus (tweak or variant).
- diagrams: minimum 2 diagrams. At least one must be mermaid or ASCII showing the architecture or flow.
- Every snippet and diagram must be ACTUAL CONTENT — no placeholders like "# your code here".
- The code must relate directly to the specific topic: "{title}".
- Return ONLY valid JSON. No markdown fences. No explanation.
""")

    try:
        outline_raw = outline_raw.strip().strip("```json").strip("```").strip()
        outline = json.loads(outline_raw)
    except Exception as e:
        print(f"[draft] Outline parse failed: {e} — using defaults")
        outline = {{
            "hook_scene": "It was midnight and I was staring at the same error for the third time that week.",
            "pain_point": "The manual process was eating hours I didn't have.",
            "failed_attempts": "I tried the obvious Stack Overflow solutions. None worked cleanly.",
            "solution_name": "a simple Python script",
            "real_metric": "cut the process from 45 minutes to under 2",
            "surprise_finding": "The hardest part wasn't the code — it was figuring out the right data structure.",
            "reader_benefit": "automate this exact workflow in under an hour",
            "seo_keywords": ["python", "automation", "developer tools", "coding", "tutorial"],
            "h2_headings": [
                "Why This Problem Is More Painful Than It Looks",
                "What I Tried First (And Why It Failed)",
                "The Actual Fix — With the Full Code",
                "Results, Surprises, and What I'd Do Differently"
            ],
            "aeo_h2_headings": [
                "Why Does This Problem Keep Happening?",
                "How Do You Fix It Without Breaking Everything Else?",
                "What Does the Full Working Code Look Like?",
                "How Much Time Does This Actually Save?"
            ],
            "tldr": {
                "problem": "Manual process was slow and error-prone.",
                "solution": "A Python automation script using the core library.",
                "result": "Cut the process from 45 minutes to under 2."
            },
            "engagement_cta": "What part of this workflow would you automate first? Drop it in the comments — I read every one.",
            "devto_tags": ["python", "tutorial", "automation", "programming"],
            "meta_description": f"A practical tutorial on {title.lower()} with real code and real results.",
            "code_snippets": [],
            "diagrams": [],
            "visual_summary": "Code-heavy tutorial with before/after snippets."
        }}

    # ── Build visual assets string from outline ──────────────────────────────
    snippets  = outline.get("code_snippets", [])
    diagrams  = outline.get("diagrams", [])

    snippets_block = ""
    if snippets:
        snippets_block = "\nPRE-PLANNED CODE SNIPPETS (use these — place each in the section indicated):\n"
        for i, s in enumerate(snippets, 1):
            snippets_block += (
                f"\nSnippet {i} [{s.get('style','').upper()}] → Section: \"{s.get('section','')}\"\n"
                f"Purpose: {s.get('purpose','')}\n"
                f"```{s.get('language','python')}\n{s.get('content','# code here')}\n```\n"
            )

    diagrams_block = ""
    if diagrams:
        diagrams_block = "\nPRE-PLANNED DIAGRAMS (use these — place each in the section indicated):\n"
        for i, d in enumerate(diagrams, 1):
            dtype = d.get("type", "ascii")
            diagrams_block += (
                f"\nDiagram {i} [{dtype.upper()}] → Section: \"{d.get('section','')}\"\n"
                f"Purpose: {d.get('purpose','')}\n"
            )
            if dtype == "mermaid":
                diagrams_block += f"```mermaid\n{d.get('content','')}\n```\n"
            else:
                diagrams_block += f"```\n{d.get('content','')}\n```\n"

    # ── Pass 2: Write the full article using the outline ──
    article = ask_ai(f"""
You are ghostwriting a blog post for Suman — a frontend developer from Kolkata who runs CoderFact (coderfact.com).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUMAN'S VOICE — internalize this before writing a single word
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Talks like a real person, not a tech writer
• Says "honestly", "look", "here's the thing", "I'm not gonna lie", "real talk"
• Mid-thought asides: "(yeah, I know, not ideal)" "(took me embarrassingly long)"
• SHORT paragraphs — max 3 sentences, lots of white space
• Em-dashes for rhythm — like this — mid sentence
• References Kolkata naturally: power cuts, slow internet, client timelines, 11pm sessions
• Ends sections with a punchy one-liner, not a summary
• NEVER writes: "In conclusion", "In summary", "To summarize", "It is worth noting"
• NEVER starts paragraphs with: "Furthermore", "Moreover", "Additionally", "In addition"
• BANNED WORDS — firing offence: delve, navigate, leverage, landscape, robust, seamless,
  unleash, utilize, empower, groundbreaking, revolutionize, game-changer, synergy,
  cutting-edge, supercharge, spearhead, foster, facilitate, paradigm, holistic
• MUST pass AI detectors — write like a tired smart dev who's venting and teaching

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARTICLE BRIEF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Title: "{title}"
Target: ~{target_words} words (HARD LIMIT — cut ruthlessly)
Hook scene: {outline.get('hook_scene')}
Pain point: {outline.get('pain_point')}
What failed first: {outline.get('failed_attempts')}
The solution: {outline.get('solution_name')}
Real metric: {outline.get('real_metric')}
Surprising finding: {outline.get('surprise_finding')}
What reader can do after: {outline.get('reader_benefit')}
SEO keywords (weave in naturally, never stuff): {', '.join(outline.get('seo_keywords', []))}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUCTURE — use these AEO-optimised H2 headings
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{chr(10).join(f'## {h}' for h in outline.get('aeo_h2_headings', outline.get('h2_headings', ['The Problem', 'What I Tried', 'The Fix', 'Results'])))}

These headings are phrased as questions/answers that Google's Answer Engine can index directly.
Use them EXACTLY — do not rewrite them.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VISUAL CONTENT RULES — THIS IS MANDATORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The article MUST be visually rich. Readers scan before they read.
Every H2 section MUST contain at least ONE of: code block, diagram, table, or ASCII art.

CODE RULES:
- Every code block must have a language tag (```python, ```bash, ```yaml, ```js etc)
- Every code block must have inline comments explaining non-obvious lines
- After every code block, write 2-3 sentences explaining it in plain English
  (start with "What this does is..." or "So basically..." — NOT "The above code demonstrates")
- Minimum 3 code blocks total in the article

DIAGRAM RULES — use whichever fits the section:
- Mermaid flowchart: use for decision flows, pipelines, processes
  Format: ```mermaid\\ngraph TD\\n  A[Start] --> B{{Decision}}\\n```
- Mermaid sequence: use for API calls, service interactions
  Format: ```mermaid\\nsequenceDiagram\\n  Alice->>Bob: Hello\\n```
- ASCII diagram: use for architecture, file structure, data flow
  Format: ```\\n[Box] --> [Box]\\n  |\\n  v\\n[Box]\\n```
- Markdown table: use for comparisons, benchmark results, option lists
  Format: | Col1 | Col2 | Col3 |

SPECIFIC REQUIREMENT — pick the ones that fit this article:
✓ If the article shows a workflow/pipeline → add a Mermaid flowchart
✓ If the article compares options/tools → add a Markdown table
✓ If the article shows architecture/structure → add an ASCII diagram
✓ If the article has a sequence of API/service calls → add a Mermaid sequence diagram
✓ If results can be shown numerically → add a before/after table

{snippets_block}
{diagrams_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WRITING RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Open with the hook scene — no title, no "Introduction" heading. Jump in mid-story.

2. IMMEDIATELY after the opening hook (before the first H2), insert a TL;DR block:
   Format it EXACTLY like this — this is critical for Medium's read ratio algorithm:

   **TL;DR**
   - **Problem:** {outline.get('tldr', {}).get('problem', 'The specific pain point')}
   - **Solution:** {outline.get('tldr', {}).get('solution', 'The exact fix used')}
   - **Result:** {outline.get('tldr', {}).get('result', 'The measurable outcome')}

   This lets scanners immediately understand the value before committing to read.

3. Use ALL pre-planned code snippets — place each in the section indicated
4. Use ALL pre-planned diagrams — place each in the section indicated
5. Add MORE diagrams/tables wherever they naturally explain something
6. Results section MUST show: {outline.get('real_metric')} — use a before/after table
7. Mention the surprise naturally: {outline.get('surprise_finding')}
8. Link to coderfact.com once naturally

9. END THE ARTICLE with this exact engagement close — this drives the comments that
   boost Medium/Dev.to ranking within the first 2 hours of publishing:

   Write 2 sentences of genuine human close (no "In conclusion"), then on a new line:
   > {outline.get('engagement_cta', 'What would you do differently? Drop it in the comments.')}
   
   Then: "If this saved you time, the clap button costs nothing — and it tells me what to build next. 👇"

Append at the very end (outside article body):
TAGS: {json.dumps(outline.get('devto_tags', ['python','tutorial','automation','programming']))}
META: {outline.get('meta_description', '')}

Output in Markdown. Start directly with the hook. No preamble.
""")

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

    # ── Dynamic Image + Code System ──────────────────────────────────────────
    import re as _re

    def slugify(text, words=12):
        text = _re.sub(r'[^\w\s]', '', str(text).lower())
        return "-".join(text.split()[:words])

    def pollinations(prompt, w=1280, h=720, seed=None):
        seed_part = f"&seed={seed}" if seed else ""
        return (
            f"https://image.pollinations.ai/prompt/{slugify(prompt)}?"
            f"width={w}&height={h}&nologo=true&enhance=true{seed_part}"
        )

    # ── Pass 3: AI analyzes the article and plans ALL visual insertions ──────
    visual_plan_raw = ask_ai(f"""
You are a technical blog editor reviewing this article draft.
Your job: decide exactly WHERE to place images and WHAT each image should show,
AND identify any sections that need an extra code snippet added.

ARTICLE TITLE: "{title}"
ARTICLE BODY:
{body}

Analyze the article carefully. Then return a JSON array of insertion objects.
Each object describes ONE thing to insert at a specific location.

Types of insertions:
- "image": a Pollinations image to generate
- "code": an additional code snippet to insert

For IMAGES decide:
- After which line? (Give the exact heading text or first 6 words of the paragraph before it)
- What should it visually show? (Be specific — mention the tool, concept, outcome)
- What visual style fits? Choose one: "dark-terminal-code", "diagram-flowchart", "frustrated-dev-at-screen", "benchmark-graph-results", "architecture-diagram", "concept-illustration", "before-after-comparison", "tool-screenshot-ui"
- Dimensions: "hero" (1280x720), "wide" (900x500), "inline" (700x380)

For extra CODE SNIPPETS decide:
- After which line? (Give the exact heading text or first 6 words of paragraph)  
- What should the snippet show? (language + exact purpose — e.g. "python: the naive for-loop that caused the slowdown")
- Label: short human-readable caption

Rules:
- Hero image MUST be first (after nothing — top of article)
- Minimum 3 images total, maximum 6
- Add an extra code snippet only if a section explains a concept but has no code yet
- Every image prompt must mention the specific tool/technology from the article — not generic
- Space images evenly — don't cluster 3 together

Return ONLY a valid JSON array. No explanation. No markdown fences. Example format:
[
  {{"type":"image","after":"","prompt":"python automation script dark terminal neon glow professional","style":"dark-terminal-code","size":"hero","alt":"Setting up the automation"}},
  {{"type":"image","after":"## Why This Problem","prompt":"developer frustrated manual csv export excel python","style":"frustrated-dev-at-screen","size":"wide","alt":"The painful manual process"}},
  {{"type":"code","after":"## What I Tried First","language":"python","content":"# The slow way - what I was doing before\\nfor row in rows:\\n    process(row)  # This blocks everything","caption":"The original bottleneck"}}
]
""")

    # Parse the visual plan
    try:
        vplan_clean = visual_plan_raw.strip().strip("```json").strip("```").strip()
        visual_plan = json.loads(vplan_clean)
        print(f"[images] AI planned {len(visual_plan)} insertions")
    except Exception as e:
        print(f"[images] Visual plan parse failed: {e} — using minimal fallback")
        hero_prompt_fb = f"{title} dark terminal developer workspace cinematic neon glow"
        visual_plan = [
            {"type": "image", "after": "", "prompt": hero_prompt_fb, "style": "dark-terminal-code", "size": "hero", "alt": title},
            {"type": "image", "after": headings[1] if len(headings) > 1 else "## ", "prompt": f"{outline.get('solution_name','python')} code result terminal output", "style": "benchmark-graph-results", "size": "wide", "alt": "Results"},
        ]

    # Map style → visual keywords
    STYLE_PROMPTS = {
        "dark-terminal-code":       "dark background terminal green text syntax highlighting professional developer",
        "diagram-flowchart":        "clean whiteboard diagram flowchart arrows nodes minimal vector art",
        "frustrated-dev-at-screen": "frustrated developer staring at screen messy desk dark moody cinematic",
        "benchmark-graph-results":  "dashboard benchmark graph before after comparison results metrics success",
        "architecture-diagram":     "software architecture diagram system design boxes arrows clean minimal",
        "concept-illustration":     "concept illustration flat design colorful developer workflow",
        "before-after-comparison":  "split screen before after comparison terminal output dark professional",
        "tool-screenshot-ui":       "modern dark UI tool screenshot dashboard clean professional",
    }

    SIZE_MAP = {
        "hero":   (1280, 720),
        "wide":   (900,  500),
        "inline": (700,  380),
    }

    # ── Inject visuals into body ──────────────────────────────────────────────
    def build_enriched_body(body: str, visual_plan: list) -> str:
        lines  = body.splitlines()
        output = []
        used_seeds = set()

        def next_seed(base):
            s = base
            while s in used_seeds:
                s += 1
            used_seeds.add(s)
            return s

        # Build lookup: "after" text → list of insertions
        insertions = {}
        for i, item in enumerate(visual_plan):
            key = item.get("after", "").strip()
            insertions.setdefault(key, []).append((i, item))

        # Hero image goes at the very top (after="" key)
        top_items = insertions.pop("", [])
        for _, item in top_items:
            if item["type"] == "image":
                style_kw = STYLE_PROMPTS.get(item.get("style", "dark-terminal-code"), "")
                full_prompt = f"{item['prompt']} {style_kw}"
                w, h = SIZE_MAP.get(item.get("size", "wide"), (900, 500))
                seed = next_seed(42)
                url  = pollinations(full_prompt, w, h, seed)
                output.append(f"![{item.get('alt', title)}]({url})\n")

        for line in lines:
            output.append(line)

            # Check if this line matches any insertion trigger
            line_stripped = line.strip()
            for trigger, items in list(insertions.items()):
                if not trigger:
                    continue
                # Match on heading or first ~6 words of paragraph
                if (line_stripped.startswith("## ") and trigger in line_stripped) or \
                   (trigger and line_stripped.startswith(trigger[:40])):
                    for _, item in items:
                        if item["type"] == "image":
                            style_kw    = STYLE_PROMPTS.get(item.get("style", "dark-terminal-code"), "")
                            full_prompt = f"{item['prompt']} {style_kw}"
                            w, h = SIZE_MAP.get(item.get("size", "wide"), (900, 500))
                            seed = next_seed(len(trigger) + 10)
                            url  = pollinations(full_prompt, w, h, seed)
                            output.append(f"\n![{item.get('alt', '')}]({url})\n")
                        elif item["type"] == "code":
                            lang    = item.get("language", "python")
                            caption = item.get("caption", "")
                            code    = item.get("content", "# example")
                            output.append(f"\n*{caption}*\n```{lang}\n{code}\n```\n")
                    del insertions[trigger]

        return "\n".join(output)

    enriched_body = build_enriched_body(body, visual_plan)

    # ── Assemble final content ────────────────────────────────────────────────
    # Hero image is already prepended inside build_enriched_body (it handles after="" items)
    # so just wrap with footer
    content = (
        f"{enriched_body}\n\n"
        f"---\n"
        f"*More free tools and tutorials at [CoderFact](https://coderfact.com). "
        f"AI-assisted draft, reviewed and edited by me.*"
    )

    print(f"[draft] title='{title}' tags={tags} words={target_words}")
    print(f"[draft] DEVTO_KEY set: {bool(DEVTO_KEY)}")

    res = requests.post(
        "https://dev.to/api/articles",
        headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
        json={"article": {
            "title": title,
            "body_markdown": content,
            "published": False,
            "tags": tags,
            "canonical_url": "https://coderfact.com",
        }},
        timeout=15,
    )

    print(f"[draft] Dev.to response: {res.status_code} — {res.text[:300]}")

    if res.status_code == 201:
        draft_url = res.json().get("url", "https://dev.to/dashboard")
        progress  = f"({idx}/{total}) " if total > 1 else ""
        send_tg(
            f"✅ {progress}*Draft ready!*\n\n"
            f"📝 _{title}_\n"
            f"📏 ~{target_words} words _{complexity}_\n"
            f"🎯 _{outline.get('hook_scene', '')[:80]}..._\n"
            f"📊 _{outline.get('real_metric', '')}_\n"
            f"🏷 {', '.join(tags)}\n"
            f"📌 {meta}\n\n"
            f"👉 [Open draft]({draft_url})"
        )
    else:
        send_tg(f"❌ Dev.to error {res.status_code}: {res.text[:300]}\n\nCheck GitHub Actions logs.")


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