import os
import sys
import json
import base64
import requests
import feedparser
import re
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# ── Environment Variables & API Keys ──────────────────────────────────────────
DEVTO_KEY      = os.getenv("DEVTO_API_KEY")
TELEGRAM_BOT   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY")
GROQ_KEY       = os.getenv("GROQ_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
GITHUB_REPO    = os.getenv("GITHUB_REPOSITORY")
STATE_FILE     = "state.json"

# ── Persona & Branding (Dynamically injected) ─────────────────────────────────
AUTHOR_NAME    = os.getenv("AUTHOR_NAME", "Suman Giri")
AUTHOR_CONTEXT = os.getenv("AUTHOR_CONTEXT", "a tech automation enthusiast, senior frontend developer and content creator, Kolkata who builds tools for CoderFact")
AUTHOR_VIBE    = os.getenv("AUTHOR_VIBE", "figures stuff out late at night, writes about it the next morning")

# Helper to prevent UI Markdown parser breakage
TICK3 = chr(96) * 3

# ── AI: OpenRouter → Gemini → Groq with retry/backoff ────────────────────────
def ask_ai(prompt: str, max_tokens: int = 4000) -> str:
    """Robust 6-provider chain with 429 retry + exponential backoff."""
    import time

    def _openai_compat(url, headers, model, prompt, max_tokens, name, retries=2):
        for attempt in range(retries + 1):
            try:
                r = requests.post(
                    url, headers=headers,
                    json={"model": model,
                          "messages": [{"role": "user", "content": prompt}],
                          "temperature": 0.7, "max_tokens": max_tokens},
                    timeout=60,
                )
                if r.status_code == 429:
                    wait = 2 ** attempt
                    print(f"[AI] {name} rate-limited — waiting {wait}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                data = r.json()
                if "choices" not in data:
                    raise ValueError(f"No choices key: {str(data)[:200]}")
                text = data["choices"][0]["message"]["content"].strip()
                if len(text) < 50:
                    raise ValueError(f"Too short ({len(text)} chars)")
                print(f"[AI] {name} ✅")
                return text
            except requests.HTTPError as e:
                if attempt < retries and "429" in str(e):
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError(f"{name}: exhausted retries")

    OR_HEADERS = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://coderfact.com",
        "X-Title":       "CoderFact Content Engine",
    } if OPENROUTER_KEY else {}

    OR_URL = "https://openrouter.ai/api/v1/chat/completions"
    errors = []

    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "meta-llama/llama-3.3-70b-instruct:free", prompt, max_tokens, "OR Llama 3.3 70B")
        except Exception as e: errors.append(str(e)); print(f"[AI] OR Llama failed → {e}")

    if GEMINI_KEY:
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}",
                json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}},
                timeout=45,
            )
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            if len(text) < 50: raise ValueError(f"Too short ({len(text)} chars)")
            print("[AI] Gemini 2.0 Flash ✅")
            return text
        except Exception as e:
            errors.append(str(e)); print(f"[AI] Gemini failed → {e}")

    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "deepseek/deepseek-r1-0528:free", prompt, max_tokens, "OR DeepSeek R1 0528")
        except Exception as e: errors.append(str(e)); print(f"[AI] OR DeepSeek failed → {e}")

    if GROQ_KEY:
        try: return _openai_compat("https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}, "llama-3.3-70b-versatile", prompt, max_tokens, "Groq Llama 3.3 70B")
        except Exception as e: errors.append(str(e)); print(f"[AI] Groq failed → {e}")

    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "google/gemma-3-27b-it:free", prompt, max_tokens, "OR Gemma 3 27B")
        except Exception as e: errors.append(str(e)); print(f"[AI] OR Gemma failed → {e}")

    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "openrouter/auto", prompt, max_tokens, "OR Auto Free Router")
        except Exception as e: errors.append(str(e)); print(f"[AI] OR Auto failed → {e}")

    raise RuntimeError("All AI providers failed:\n" + "\n".join(errors[-6:]))

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
                  json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True})

def get_reply():
    state   = load_state()
    last_id = state.get("last_update_id", 0)
    res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT}/getUpdates",
                       params={"offset": last_id + 1, "limit": 20}, timeout=10).json()

    updates = res.get("result", [])
    today      = datetime.now(timezone.utc).date()
    ist_offset = timedelta(hours=5, minutes=30)
    today_ist  = (datetime.now(timezone.utc) + ist_offset).date()

    for u in reversed(updates):
        msg     = u.get("message", {})
        text    = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        date    = datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc).date()

        if chat_id != str(TELEGRAM_CHAT) or date not in (today, today_ist): continue
        if not text: continue

        save_state({**state, "last_update_id": u["update_id"]})

        if text.strip() == "0": return {"type": "skip"}

        clean = text.replace(" ", "")
        if all(c in "0123456789" for c in clean) and len(clean) <= 3:
            digits = list(dict.fromkeys(c for c in clean if c in "1234567890"))
            valid  = [c for c in digits if c in ("1","2","3")]
            if valid: return {"type": "choice", "choices": valid}

        if len(text) >= 10: return {"type": "custom", "topic": text}

    return None

# ── Multi-Source Trend Aggregator (8 sources) ────────────────────────────────
def fetch_trends():
    HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoderFact-Bot/1.0)"}
    signals = {}
    
    try:
        r = requests.get("https://github.com/trending", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        repos = []
        for article in soup.find_all("article", class_="Box-row")[:10]:
            name_tag  = article.find("h2")
            desc_tag  = article.find("p")
            lang_tag  = article.find("span", itemprop="programmingLanguage")
            if name_tag:
                repos.append({
                    "repo":  name_tag.get_text(strip=True).replace("\n","").replace(" ",""),
                    "desc":  desc_tag.get_text(strip=True) if desc_tag else "",
                    "lang":  lang_tag.get_text(strip=True) if lang_tag else "",
                })
        signals["github"] = repos
    except: signals["github"] = []

    try:
        top_ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=8).json()[:15]
        hn = []
        for sid in top_ids:
            item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5).json()
            if item and item.get("type") == "story":
                hn.append({"title": item.get("title",""), "score": item.get("score",0)})
        signals["hackernews"] = sorted(hn, key=lambda x: x["score"], reverse=True)[:8]
    except: signals["hackernews"] = []

    reddit_posts = []
    for sub in ["programming", "MachineLearning", "webdev", "artificial"]:
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=8", headers={**HEADERS,"Accept":"application/json"}, timeout=8)
            for p in r.json()["data"]["children"]:
                d = p["data"]
                if not d.get("stickied"):
                    reddit_posts.append({"title": d.get("title",""), "upvotes": d.get("ups",0), "sub": sub})
        except: pass
    signals["reddit"] = sorted(reddit_posts, key=lambda x: x["upvotes"], reverse=True)[:12]

    try:
        articles = requests.get("https://dev.to/api/articles?top=7&per_page=10", headers=HEADERS, timeout=8).json()
        signals["devto"] = [{"title": a.get("title",""), "tags": a.get("tag_list",[])} for a in articles[:8]]
    except: signals["devto"] = []

    rss_items = []
    rss_feeds = [
        ("https://towardsdatascience.com/feed", "Towards Data Science"),
        ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch AI"),
        ("https://hnrss.org/frontpage", "HN RSS"),
    ]
    for url, source in rss_feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                if getattr(entry, 'title', ''): rss_items.append({"title": entry.title, "source": source})
        except: pass
    signals["rss_news"] = rss_items[:15]

    google_rising = []
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=330, timeout=(10, 25), retries=2, backoff_factor=0.5)
        for seed in ["python automation", "AI coding", "machine learning"]:
            try:
                pt.build_payload([seed], timeframe="now 7-d", geo="")
                related = pt.related_queries()
                rising = related.get(seed, {}).get("rising")
                if rising is not None and not rising.empty:
                    google_rising += rising["query"].tolist()[:4]
            except: pass
        signals["google_trends"] = list(dict.fromkeys(google_rising))[:12]
    except: signals["google_trends"] = []

    return signals

def format_signals(signals: dict) -> str:
    lines = []
    if signals.get("google_trends"): lines.append("🔍 GOOGLE TRENDS RISING: " + ", ".join(signals["google_trends"][:8]))
    if signals.get("github"): lines.append("🔥 GITHUB VIRAL REPOS: " + " | ".join(f"{r['repo']} ({r['desc'][:30]})" for r in signals["github"][:5]))
    if signals.get("rss_news"): lines.append("📰 AI/CODING NEWS: " + " | ".join(f"{i['source']}: {i['title'][:40]}" for i in signals["rss_news"][:5]))
    if signals.get("reddit"): lines.append("💬 REDDIT HOT: " + " | ".join(f"r/{p['sub']} - {p['title'][:40]}" for p in signals["reddit"][:5]))
    return "\n".join(lines)

# ── PHASE 1: Morning Researcher ───────────────────────────────────────────────
def research():
    today         = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%B %d, %Y")
    state         = load_state()
    title_history = state.get("title_history", [])

    signals     = fetch_trends()
    trend_block = format_signals(signals)
    history_block = "ALREADY PUBLISHED:\n" + "\n".join(f"- {t}" for t in title_history[-30:]) + "\n\n" if title_history else ""

    print("[research] Pass A: Scoring virality...")
    virality_raw = ask_ai(f"""You are a senior content strategist for tech articles. Today is {today}.
CRITICAL DIVERSITY RULES — the 3 topics MUST cover different categories.

LIVE SIGNALS:
{trend_block}
{history_block}

TASK: Analyze the provided signals deeply. Specifically review the trending AI/coding news, viral GitHub repos, and Google Trends.
Score topics 0-100 for Medium virality. Pick TOP 3.

Return ONLY a valid JSON array. DO NOT wrap it in backticks or markdown fences.
[
  {{
    "topic": "raw topic",
    "virality_score": 88,
    "virality_reasoning": "WHY this will go viral based on GitHub or News trends",
    "developer_pain": "high",
    "freshness": "breaking",
    "author_angle": "Specific first-person angle",
    "target_keywords": ["keyword1", "keyword2"]
  }}
]""")

    try:
        cleaned_json = virality_raw.replace(f'{TICK3}json', '').replace(TICK3, '').strip()
        vdata = json.loads(cleaned_json)[:3]
    except Exception as e:
        vdata = [{"topic": "Python asyncio common bugs", "virality_score": 74, "author_angle": "The async mistakes that burned 3 hours of my life"}]

    print("[research] Pass B: Crafting titles...")
    title_raw = ask_ai(f"""Convert these topics into PERFECT Medium article titles.
Titles must be under 80 chars, specific, first-person where natural. No banned clickbait words.
{json.dumps(vdata)}

Reply ONLY in this exact format:
1. [Title]
2. [Title]
3. [Title]""")

    titles = [line.split(". ", 1)[1].strip().strip('"') for line in title_raw.strip().splitlines() if line.strip()[:2] in ("1.", "2.", "3.")][:3]
    if len(titles) < 3: titles = [v.get("author_angle", "Topic") for v in vdata]

    save_state({**state, "topics": titles, "date": today, "title_history": (title_history + titles)[-30:], "virality_data": vdata})

    tg_lines = [f"🔥 *CoderFact — Daily Brief* | _{today}_\n"]
    for i, (title, v) in enumerate(zip(titles, vdata), 1):
        tg_lines.append(f"{i}. *{title}*\n   📊 {v.get('virality_score', '?')}/100 | {v.get('developer_pain', 'medium')} pain")
    
    tg_lines.append("\n*Reply options:*\n• `1`, `2`, `3` to draft\n• `0` to skip\n• *Type any custom topic* to draft it directly.")
    send_tg("\n".join(tg_lines))

# ── Helpers ───────────────────────────────────────────────────────────────────
def convert_mermaid_for_medium(markdown_body: str) -> str:
    """Finds all Mermaid blocks and converts them to mermaid.ink image links for Medium compatibility."""
    def replacer(match):
        mermaid_code = match.group(1).strip()
        encoded = base64.b64encode(mermaid_code.encode('utf-8')).decode('ascii')
        image_url = f"https://mermaid.ink/img/{encoded}"
        return f"\n![Architecture Diagram]({image_url})\n"
        
    pattern = re.compile(rf'{TICK3}mermaid\n(.*?)\n{TICK3}', re.DOTALL)
    return re.sub(pattern, replacer, markdown_body)

def _s(val, fallback=""):
    if val is None:           return fallback
    if isinstance(val, dict): return str(next((v for v in val.values() if v), fallback))
    if isinstance(val, list): return " ".join(str(v) for v in val if v)
    return str(val).strip() or fallback

def _list(val, fallback=None):
    if fallback is None: fallback = []
    if not val: return fallback
    if isinstance(val, str):  return [v.strip() for v in val.replace(",","\n").splitlines() if v.strip()]
    if isinstance(val, dict): return [_s(v) for v in val.values() if v]
    if isinstance(val, list): return [_s(v) for v in val if v]
    return fallback

# ── PHASE 2: Drafter ─────────────────────────────────────────────────────────
def draft_single(title: str, idx: int, total: int):
    progress = f"({idx}/{total}) " if total > 1 else ""
    def tg_step(msg): send_tg(f"{progress}{msg}")
    def tg_err(step, e): send_tg(f"❌ {progress}*{step} failed*\n{str(e)[:300]}")

    tg_step(f"⏳ Drafting *\"{title}\"*...")

    # Pass 0: PAA Keyword Research
    tg_step("🔍 Pass 0: Scraping PAA & Keywords...")
    try:
        kw_research_raw = ask_ai(f"""You are an SEO keyword researcher for coding/developer content on Medium.
Article title: "{title}"
Audience: developers who search Google when stuck on a problem.

Return ONLY a JSON object. Do NOT wrap it in markdown backticks:
{{
  "primary_keyword": "most important specific keyword",
  "people_also_ask": ["4 real Google 'People Also Ask' questions related to the keyword to use as H2s"],
  "lsi_keywords": ["5 semantically related terms"],
  "keyword_placement": {{
    "title": "rewrite title leading with primary keyword",
    "meta_description": "150-char SEO description"
  }},
  "medium_tags": ["4 existing Medium tags"]
}}""")
        cleaned_json = kw_research_raw.replace(f'{TICK3}json', '').replace(TICK3, '').strip()
        kw_data = json.loads(cleaned_json)
    except Exception as e:
        tg_err("Keyword research", e); kw_data = {}

    primary_kw   = _s(kw_data.get("primary_keyword"), title)
    lsi_keywords = _list(kw_data.get("lsi_keywords"), [primary_kw])
    aeo_headings = _list(kw_data.get("people_also_ask"), ["Why Does This Happen?", "How To Fix It?", "What Is The Code?"])
    seo_title    = _s(kw_data.get("keyword_placement", {}).get("title"), title)
    seo_meta     = _s(kw_data.get("keyword_placement", {}).get("meta_description"), f"Learn how to optimize {primary_kw} with this technical guide.")
    tags         = _list(kw_data.get("medium_tags"), ["python", "tutorial", "programming"])[:4]

    # Pass 1: Outline
    tg_step("📋 Pass 1: Building outline...")
    try:
        outline_raw = ask_ai(f"""You are helping {AUTHOR_NAME} plan a comprehensive, interactive blog post.
Title: "{seo_title}"
Target: ~900 words

CRITICAL: Return ONLY a JSON object. Do NOT wrap it in markdown backticks.
{{
  "hook_scene": "2-3 sentences. Specific moment the problem hit {AUTHOR_NAME}.",
  "pain_point": "Exact frustration with tool name and error.",
  "solution_name": "Exact tool or library used.",
  "best_practice_rule": "The absolute golden rule for this topic (e.g. Vectorization vs Iteration).",
  "real_metric": "Before/after number e.g. 47 min to 3 min.",
  "thumbnail_prompt": "Cinematic visual prompt for Midjourney/Flux representing this coding challenge.",
  "snippet_plan": [ {{"section":"H2 heading","language":"python","style":"solution","purpose":"what this shows"}} ],
  "diagram_plan": [ {{"section":"H2 heading","type":"mermaid","purpose":"what architecture flow this shows"}} ],
  "interactive_widget_prompt": "A precise 3-sentence prompt for a UI Interactive Simulator comparing the slow way vs the fast way. Include inputs and behaviors."
}}""")
        cleaned_json = outline_raw.replace(f'{TICK3}json', '').replace(TICK3, '').strip()
        outline = json.loads(cleaned_json)
    except Exception as e:
        tg_err("Outline", e); outline = {}

    snippets_block = "\n".join([f"Snippet: {s.get('purpose')} in section {s.get('section')} ({s.get('language')})" for s in outline.get("snippet_plan", [])])
    diagrams_block = "\n".join([f"Diagram ({d.get('type')}): {d.get('purpose')} in section {d.get('section')}" for d in outline.get("diagram_plan", [])])
    widget_prompt = _s(outline.get("interactive_widget_prompt"), f"Create an interactive data processing simulator for {primary_kw}")
    best_practice = _s(outline.get("best_practice_rule"), "Always follow core optimization rules.")
    thumbnail_prompt = _s(outline.get("thumbnail_prompt"), "Developer working late in a dark neon room")

    # Pass 2: Write Article
    tg_step("✍️ Pass 2: Writing article & injecting UI Widget...")
    try:
        article = ask_ai(f"""
You are ghostwriting a highly visual, structured blog post for {AUTHOR_NAME} — {AUTHOR_CONTEXT}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{AUTHOR_NAME.upper()}'S VOICE — READ THIS TWICE BEFORE WRITING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{AUTHOR_NAME} is a real developer. Not a generic content marketer.
{AUTHOR_NAME} {AUTHOR_VIBE}.

PATTERNS TO USE:
• Opens mid-frustration: "I spent three hours on this. THREE hours. For a config change."
• Uses "I" obsessively — this is personal experience.
• References real dev context naturally: "My client was calling at 9am. It was 1am. Kolkata time."
• Short questions to the reader: "Sound familiar?" / "Yeah. Me too."
• NO throat-clearing, NO clickbait words (delve, leverage, game-changer).

ARTICLE BRIEF
Title: "{seo_title}"
Primary Keyword: "{primary_kw}"
Hook scene: {outline.get('hook_scene', 'It was late when the error hit.')}
Metric to flaunt: {outline.get('real_metric', 'Saved 2 hours')}
Best Practice to Feature: {best_practice}

AEO H2 HEADINGS TO USE EXACTLY:
{chr(10).join(f'## {h}' for h in aeo_headings)}

MANDATORY STRUCTURAL REQUIREMENTS:
1. OPEN with hook scene. No intro text.
2. COMPARISON TABLE: You MUST include a Markdown Before/After table showing the metrics.
3. ARCHITECTURE DIAGRAM: You MUST include a `{TICK3}mermaid` block (graph TD or sequenceDiagram) illustrating the flow or architecture.
4. CODE BLOCKS: All code must be properly fenced e.g. `{TICK3}python`. Cover all planned snippets: {snippets_block}
5. BEST PRACTICES: You must include a section explaining the 'Golden Rule' ({best_practice}).
6. INTERACTIVE WIDGET: At the very end of the article, you MUST append a Chameleon JSON block for interactivity. Use exactly this format:
{TICK3}json?chameleon
{{
  "component": "LlmGeneratedComponent",
  "props": {{
    "height": "600px",
    "prompt": "{widget_prompt}"
  }}
}}
{TICK3}

Output ONLY in Markdown. Start immediately with the text.
""")
    except Exception as e:
        tg_err("Article writing", e); raise

    # Pass 3: Visual & Formatting Injection
    tg_step("🎨 Pass 3: Formatting & Enhancing...")
    
    # 1. Convert any generated Mermaid blocks to image links for Medium compatibility
    medium_ready_body = convert_mermaid_for_medium(article)
    
    # 2. Append standard automated footer
    article_body_with_footer = (
        f"{medium_ready_body}\n\n"
        f"---\n"
        f"*Tutorial by {AUTHOR_NAME}. Find more tech automation and education resources at [CoderFact](https://coderfact.com).*\n"
    )

    # 3. Create the distinct SEO CUT Block for GitHub/Medium (Fixing the YAML bug)
    seo_block = (
        "---\n"
        f"VIRAL TITLE: {seo_title}\n"
        f"META DESCRIPTION: {seo_meta}\n"
        f"TAGS: {', '.join(tags)}\n"
        f"SEO KEYWORDS: {', '.join(lsi_keywords)}\n"
        f"THUMBNAIL PROMPT (For Midjourney/Flux): {thumbnail_prompt}\n"
        "---\n\n"
        "✂️ CUT THE ABOVE BLOCK BEFORE PUBLISHING TO MEDIUM ✂️\n\n"
    )

    # The version we send to GitHub gets the SEO block so you can copy/paste it easily
    github_file_content = seo_block + article_body_with_footer
    
    # The version we send to Dev.to skips the SEO block so it looks clean immediately
    devto_payload_content = article_body_with_footer

    # ── Export to File System & GitHub ────────────────────────────────────────
    tg_step("💾 Saving Medium Draft and Remotion Props...")
    try:
        slug = re.sub(r'[^\w\s]', '', seo_title.lower()).replace(' ', '-')
        
        os.makedirs("medium_drafts", exist_ok=True)
        md_filename = f"medium_drafts/{slug}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(github_file_content)
            
        # Extract code blocks for Remotion Video Automation, excluding the JSON UI Widget
        pattern = re.compile(rf'{TICK3}(?:python|bash|json|javascript|ts)\n(.*?)\n{TICK3}', re.DOTALL)
        code_blocks = re.findall(pattern, devto_payload_content)
        code_blocks = [c for c in code_blocks if "LlmGeneratedComponent" not in c]
        
        remotion_data = {
            "title": seo_title,
            "author": AUTHOR_NAME,
            "snippets": code_blocks[:3]
        }
        json_filename = f"medium_drafts/{slug}_remotion.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(remotion_data, f, indent=2)

        if GITHUB_TOKEN and GITHUB_REPO:
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{md_filename}"
            hdrs = {"Authorization": f"token {GITHUB_TOKEN}"}
            
            sha = requests.get(api_url, headers=hdrs).json().get("sha")
            body = {
                "message": f"docs: generated highly visual medium draft for {slug}",
                "content": base64.b64encode(github_file_content.encode()).decode()
            }
            if sha: body["sha"] = sha
            requests.put(api_url, headers=hdrs, json=body)
            
            api_url_json = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{json_filename}"
            sha_json = requests.get(api_url_json, headers=hdrs).json().get("sha")
            body_json = {
                "message": f"docs: generated remotion props for {slug}",
                "content": base64.b64encode(json.dumps(remotion_data, indent=2).encode()).decode()
            }
            if sha_json: body_json["sha"] = sha_json
            requests.put(api_url_json, headers=hdrs, json=body_json)

    except Exception as e:
        tg_err("File Export & GitHub Push", e)
        raise

    # ── Publish to Dev.to ─────────────────────────────────────────────────────
    print(f"[draft] Publishing — title='{seo_title}' tags={tags} DEVTO_KEY={bool(DEVTO_KEY)}")
    devto_url = ""
    try:
        res = requests.post(
            "https://dev.to/api/articles",
            headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"} if DEVTO_KEY else {},
            json={"article": {
                "title": seo_title,
                "body_markdown": devto_payload_content,
                "published": False,
                "tags": tags,
                "canonical_url": "https://coderfact.com",
            }},
            timeout=20,
        )
        if res.status_code == 201:
            devto_url = res.json().get("url", "https://dev.to/dashboard")
            print(f"[draft] Dev.to success! URL: {devto_url}")
        else:
            print(f"❌ Dev.to error {res.status_code}: {res.text[:300]}")
    except Exception as e:
        print(f"❌ Dev.to publish failed: {e}")

    # ── Final Success Notification ────────────────────────────────────────
    msg = f"✅ {progress}*Interactive Draft completely generated!*\n\n📝 _{seo_title}_\n🏷 {', '.join(tags)}\n"
    if devto_url:
        msg += f"\n🌐 **Uploaded to Dev.to:** [Open Draft]({devto_url})"
    msg += f"\n💾 **Exported to GitHub:** `.md` and `_remotion.json` saved in `medium_drafts/` directory."
    
    send_tg(msg)

# ── Entry point ───────────────────────────────────────────────────────────────
def draft():
    reply = get_reply()
    if not reply: return print("No reply yet.")

    rtype = reply.get("type")
    if rtype == "skip": return send_tg("👌 Skipping today.")
    if rtype == "custom":
        send_tg(f"✍️ Got custom topic: *\"{reply['topic']}\"*. Drafting now...")
        return draft_single(reply['topic'], 1, 1)

    state = load_state()
    topics = state.get("topics", [])
    valid = [c for c in reply.get("choices", []) if c.isdigit() and int(c) <= len(topics)]
    
    if not valid: return send_tg("⚠️ Invalid choice. Send 1, 2, 3 or custom topic.")

    send_tg(f"📋 Drafting {len(valid)} articles...")
    for idx, choice in enumerate(valid, 1):
        try: draft_single(topics[int(choice) - 1], idx, len(valid))
        except Exception as e: print(f"Failed: {e}")
    send_tg("🎉 All operations completed!")

if __name__ == "__main__":
    {"research": research, "draft": draft}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print("Usage: python agent.py research | draft"))()