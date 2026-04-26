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

# ── Persona & Branding ────────────────────────────────────────────────────────
AUTHOR_NAME    = os.getenv("AUTHOR_NAME", "Suman Giri")
AUTHOR_CONTEXT = os.getenv("AUTHOR_CONTEXT", "a tech automation enthusiast, senior frontend developer and content creator, Kolkata who builds tools for CoderFact")
AUTHOR_VIBE    = os.getenv("AUTHOR_VIBE", "figures stuff out late at night, writes about it the next morning")

# Helper to prevent UI Markdown parser breakage
TICK3 = chr(96) * 3

# ── AI Routing Engine ─────────────────────────────────────────────────────────
def ask_ai(prompt: str, max_tokens: int = 4000) -> str:
    """Robust 6-provider chain with 429 retry + exponential backoff."""
    import time
    
    def _openai_compat(url, headers, model, prompt, max_tokens, name, retries=2):
        for attempt in range(retries + 1):
            try:
                r = requests.post(
                    url, headers=headers, 
                    json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": max_tokens}, 
                    timeout=60
                )
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except requests.HTTPError as e:
                if attempt < retries and "429" in str(e):
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError(f"{name}: exhausted retries")

    OR_HEADERS = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://coderfact.com", "X-Title": "CoderFact"} if OPENROUTER_KEY else {}
    OR_URL = "https://openrouter.ai/api/v1/chat/completions"
    
    errors = []

    # 1. Primary: Llama 3.3 70B (Fast, extremely capable, free on OR)
    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "meta-llama/llama-3.3-70b-instruct:free", prompt, max_tokens, "OR Llama 3.3 70B")
        except Exception as e: errors.append(f"OR Llama failed: {e}")
    
    # 2. Secondary: Gemini 2.0 Flash (Native Google API)
    if GEMINI_KEY:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}", json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}}, timeout=45)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e: errors.append(f"Gemini failed: {e}")

    # 3. Tertiary: DeepSeek R1
    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "deepseek/deepseek-r1-0528:free", prompt, max_tokens, "OR DeepSeek R1")
        except Exception as e: errors.append(f"OR DeepSeek failed: {e}")

    # 4. Quaternary: Groq Native Llama
    if GROQ_KEY:
        try: return _openai_compat("https://api.groq.com/openai/v1/chat/completions", {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}, "llama-3.3-70b-versatile", prompt, max_tokens, "Groq Llama")
        except Exception as e: errors.append(f"Groq failed: {e}")

    # 5. Quinary: Gemma 3 27B
    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "google/gemma-3-27b-it:free", prompt, max_tokens, "OR Gemma 3")
        except Exception as e: errors.append(f"OR Gemma failed: {e}")

    # 6. Last Resort: OpenRouter Auto
    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "openrouter/auto", prompt, max_tokens, "OR Auto Router")
        except Exception as e: errors.append(f"OR Auto failed: {e}")

    raise RuntimeError(f"All AI providers failed. Error logs:\n" + "\n".join(errors))

# ── State & GitHub ────────────────────────────────────────────────────────────
def load_state(): return json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}

def save_state(data):
    json.dump(data, open(STATE_FILE, "w"), indent=2)
    if not (GITHUB_TOKEN and GITHUB_REPO): return
    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    hdrs = {"Authorization": f"token {GITHUB_TOKEN}"}
    sha = requests.get(api, headers=hdrs).json().get("sha")
    body = {"message": "chore: update state", "content": base64.b64encode(json.dumps(data, indent=2).encode()).decode()}
    if sha: body["sha"] = sha
    requests.put(api, headers=hdrs, json=body)

# ── Telegram ──────────────────────────────────────────────────────────────────
def send_tg(msg):
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage", json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True})

def get_reply():
    state, last_id = load_state(), load_state().get("last_update_id", 0)
    res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT}/getUpdates", params={"offset": last_id + 1, "limit": 20}, timeout=10).json()
    for u in reversed(res.get("result", [])):
        msg, text, chat_id = u.get("message", {}), u.get("message", {}).get("text", "").strip(), str(u.get("message", {}).get("chat", {}).get("id", ""))
        if chat_id != str(TELEGRAM_CHAT) or not text: continue
        save_state({**state, "last_update_id": u["update_id"]})
        if text.strip() == "0": return {"type": "skip"}
        if all(c in "0123456789 " for c in text) and len(text.replace(" ", "")) <= 3: return {"type": "choice", "choices": list(dict.fromkeys(c for c in text.replace(" ", "") if c in "123"))}
        if len(text) >= 10: return {"type": "custom", "topic": text}
    return None

# ── Trends Aggregator ─────────────────────────────────────────────────────────
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
            if name_tag:
                repos.append({
                    "repo":  name_tag.get_text(strip=True).replace("\n","").replace(" ",""),
                    "desc":  desc_tag.get_text(strip=True) if desc_tag else "",
                })
        signals["github"] = repos
    except: signals["github"] = []

    reddit_posts = []
    for sub in ["programming", "MachineLearning", "webdev"]:
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=8", headers={**HEADERS,"Accept":"application/json"}, timeout=8)
            for p in r.json()["data"]["children"]:
                d = p["data"]
                if not d.get("stickied"): reddit_posts.append({"title": d.get("title",""), "upvotes": d.get("ups",0), "sub": sub})
        except: pass
    signals["reddit"] = sorted(reddit_posts, key=lambda x: x["upvotes"], reverse=True)[:12]

    google_rising = []
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=330, timeout=(10, 25), retries=2, backoff_factor=0.5)
        for seed in ["python automation", "AI coding", "frontend developer"]:
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
    if signals.get("reddit"): lines.append("💬 REDDIT HOT: " + " | ".join(f"r/{p['sub']} - {p['title'][:40]}" for p in signals["reddit"][:5]))
    return "\n".join(lines)

# ── Helpers ───────────────────────────────────────────────────────────────────
def convert_mermaid_for_medium(markdown_body: str) -> str:
    def replacer(match):
        encoded = base64.b64encode(match.group(1).strip().encode('utf-8')).decode('ascii')
        return f"\n![Architecture Diagram](https://mermaid.ink/img/{encoded})\n"
    return re.sub(re.compile(rf'{TICK3}mermaid\n(.*?)\n{TICK3}', re.DOTALL), replacer, markdown_body)

def _s(val, fallback=""):
    if val is None: return fallback
    if isinstance(val, dict): return str(next((v for v in val.values() if v), fallback))
    if isinstance(val, list): return " ".join(str(v) for v in val if v)
    return str(val).strip() or fallback

def _list(val, fallback=None):
    if not val: return fallback or []
    if isinstance(val, str): return [v.strip() for v in val.replace(",","\n").splitlines() if v.strip()]
    if isinstance(val, list): return [_s(v) for v in val if v]
    return fallback or []

# ── PHASE 1: Researcher ───────────────────────────────────────────────────────
def research():
    today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%B %d, %Y")
    state = load_state()
    title_history = state.get("title_history", [])

    signals = fetch_trends()
    trend_block = format_signals(signals)
    history_block = "ALREADY PUBLISHED:\n" + "\n".join(f"- {t}" for t in title_history[-30:]) + "\n\n" if title_history else ""

    print("[research] Pass A: Scoring virality...")
    virality_raw = ask_ai(f"""You are a senior content strategist for tech articles. Today is {today}.
    CRITICAL DIVERSITY RULES — the 3 topics MUST cover different categories.

    LIVE SIGNALS:
    {trend_block}
    {history_block}

    TASK: Analyze the provided signals deeply. Score topics 0-100 for Medium virality. Pick TOP 3.

    Return ONLY a valid JSON array. DO NOT wrap it in backticks or markdown fences.
    [
      {{
        "topic": "raw topic",
        "virality_score": 92,
        "developer_pain": "high",
        "author_angle": "Specific first-person angle"
      }}
    ]""")

    try:
        cleaned_json = virality_raw.replace(f'{TICK3}json', '').replace(TICK3, '').strip()
        vdata = json.loads(cleaned_json)[:3]
    except Exception:
        # Fallback to 3 realistic items if JSON parsing fails
        vdata = [
            {"topic": "Python Pandas Optimization", "virality_score": 92, "developer_pain": "high", "author_angle": "How I cut Pandas processing from 47 mins to 3 mins"},
            {"topic": "GitHub Actions Setup", "virality_score": 88, "developer_pain": "medium", "author_angle": "My GitHub Actions setup for instant deployments"},
            {"topic": "Frontend AI Tools", "virality_score": 85, "developer_pain": "low", "author_angle": "I tried the newest AI coding tools so you don't have to"}
        ]

    print("[research] Pass B: Crafting titles...")
    title_raw = ask_ai(f"""Convert these 3 topics into PERFECT Medium article titles.
    CRITICAL RULE: Titles MUST create a 'curiosity gap' using specific metrics or outcomes. DO NOT use generic titles like 'Tips and Tricks' or 'A Guide To'.
    {json.dumps(vdata)}
    Reply ONLY in format:
    1. [Title]
    2. [Title]
    3. [Title]""")

    titles = [line.split(". ", 1)[1].strip().strip('"') for line in title_raw.strip().splitlines() if line.strip()[:2] in ("1.", "2.", "3.")][:3]
    if len(titles) < 3: titles = [v.get("author_angle", "Topic") for v in vdata]

    save_state({**state, "topics": titles, "date": today, "title_history": (title_history + titles)[-30:], "virality_data": vdata})

    # Crafting the exact Telegram Message format requested
    tg_lines = [f"🔥 *CoderFact Brief* | _{today}_\n"]
    for i, (title, v) in enumerate(zip(titles, vdata), 1):
        score = v.get('virality_score', '90')
        pain = v.get('developer_pain', 'medium')
        tg_lines.append(f"{i}. *{title}*\n   📊 {score}/100 | {pain} pain")
    
    tg_lines.append("\n*Reply options:*\n• `1`, `2`, `3` to draft\n• `0` to skip\n• *Type any custom topic* to draft it directly.")
    
    send_tg("\n".join(tg_lines))

# ── PHASE 2: Drafter ──────────────────────────────────────────────────────────
def draft_single(title: str, idx: int, total: int):
    progress = f"({idx}/{total}) " if total > 1 else ""
    def tg_step(msg): send_tg(f"{progress}{msg}")
    def tg_err(step, e): send_tg(f"❌ {progress}*{step} failed*\n{str(e)[:300]}")

    tg_step(f"⏳ Drafting *\"{title}\"*...")

    tg_step("🔍 Pass 0 & 1: Outline & SEO...")
    try:
        raw_json = ask_ai(f"""Article title: "{title}". Return ONLY JSON without markdown backticks:
        {{
          "primary_keyword": "specific keyword",
          "people_also_ask": ["3 real Google questions for H2s"],
          "lsi_keywords": ["5 related terms"],
          "keyword_placement": {{"title": "rewrite title", "meta_description": "150-char SEO description"}},
          "medium_tags": ["4 existing tags"],
          "hook_scene": "2-3 sentences. Specific problem moment.",
          "best_practice_rule": "The golden rule.",
          "real_metric": "Before/after number.",
          "thumbnail_prompt": "Cinematic visual prompt for Midjourney.",
          "interactive_widget_prompt": "Prompt for an interactive UI simulator."
        }}""").replace(f'{TICK3}json', '').replace(TICK3, '').strip()
        outline = json.loads(raw_json)
    except: outline = {}

    primary_kw   = _s(outline.get("primary_keyword"), title)
    lsi_keywords = _list(outline.get("lsi_keywords"), [primary_kw])
    aeo_headings = _list(outline.get("people_also_ask"), ["Why Does This Happen?", "How To Fix It?", "What Is The Code?"])
    seo_title    = _s(outline.get("keyword_placement", {}).get("title"), title)
    seo_meta     = _s(outline.get("keyword_placement", {}).get("meta_description"), f"Learn how to optimize {primary_kw} with this technical guide.")
    tags         = _list(outline.get("medium_tags"), ["python", "tutorial", "programming"])[:4]
    best_practice= _s(outline.get("best_practice_rule"), "Always follow core optimization rules.")
    thumbnail_prompt = _s(outline.get("thumbnail_prompt"), "Developer working late in a dark neon room")

    tg_step("✍️ Pass 2: Writing article in Persona...")
    try:
        article = ask_ai(f"""
        Ghostwrite a highly visual, structured blog post for {AUTHOR_NAME} — {AUTHOR_CONTEXT}.
        Voice: {AUTHOR_VIBE}. Use "I", mention "1am Kolkata time". 
        
        CRITICAL RULES:
        1. CODE AUTHENTICITY: When writing code blocks, YOU MUST generate realistic, large-scale mock datasets (e.g., using `np.random.randint(1, 100, 10000000)` for 10 million rows). DO NOT use tiny lists like [1,2,3].
        2. ARCHITECTURE DIAGRAM: Include a `{TICK3}mermaid` block. It MUST be highly technical (e.g., showing CPU core splits for Dask or C-engine SIMD for Vectorization), not just a basic flow.
        3. TABLES: Include a Before/After comparison Markdown table.
        4. WIDGET: End with this exact block:
        {TICK3}json?chameleon
        {{ "component": "LlmGeneratedComponent", "props": {{ "height": "600px", "prompt": "{outline.get('interactive_widget_prompt', 'simulator')}" }} }}
        {TICK3}
        
        Title: {seo_title}
        H2s to use exactly: {', '.join(aeo_headings)}
        Feature this best practice: {best_practice}
        
        Output ONLY Markdown. Start immediately with the text.
        """)
    except Exception as e:
        tg_err("Article writing", e); raise

    tg_step("🎨 Pass 3: Formatting & Enhancing...")
    medium_ready_body = convert_mermaid_for_medium(article)
    article_body_with_footer = f"{medium_ready_body}\n\n---\n*Tutorial by {AUTHOR_NAME}. Find more at [CoderFact](https://coderfact.com).*\n"

    seo_block = (
        "---\n"
        f"VIRAL TITLE: {seo_title}\n"
        f"META DESCRIPTION: {seo_meta}\n"
        f"TAGS: {', '.join(tags)}\n"
        f"SEO KEYWORDS: {', '.join(lsi_keywords)}\n"
        f"THUMBNAIL PROMPT (For Midjourney/Flux): {thumbnail_prompt}\n"
        "---\n\n✂️ CUT THE ABOVE BLOCK BEFORE PUBLISHING TO MEDIUM ✂️\n\n"
    )

    github_file_content = seo_block + article_body_with_footer
    devto_payload_content = article_body_with_footer

    tg_step("💾 Exporting to GitHub & Dev.to...")
    slug = re.sub(r'[^\w\s]', '', seo_title.lower()).replace(' ', '-')
    
    try:
        # Save to local/GitHub
        os.makedirs("medium_drafts", exist_ok=True)
        md_filename = f"medium_drafts/{slug}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(github_file_content)

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
            hdrs = {"Authorization": f"token {GITHUB_TOKEN}"}
            
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{md_filename}"
            sha = requests.get(api_url, headers=hdrs).json().get("sha")
            body = {"message": f"docs: generated highly visual medium draft for {slug}", "content": base64.b64encode(github_file_content.encode()).decode()}
            if sha: body["sha"] = sha
            requests.put(api_url, headers=hdrs, json=body)
            
            api_url_json = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{json_filename}"
            sha_json = requests.get(api_url_json, headers=hdrs).json().get("sha")
            body_json = {"message": f"docs: generated remotion props for {slug}", "content": base64.b64encode(json.dumps(remotion_data, indent=2).encode()).decode()}
            if sha_json: body_json["sha"] = sha_json
            requests.put(api_url_json, headers=hdrs, json=body_json)

    except Exception as e:
        tg_err("File Export & GitHub Push", e)
        raise

    # Dev.to
    devto_url = ""
    if DEVTO_KEY:
        try:
            res = requests.post("https://dev.to/api/articles", headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"}, json={"article": {"title": seo_title, "body_markdown": devto_payload_content, "published": False, "tags": tags, "canonical_url": "https://coderfact.com"}}, timeout=20)
            if res.status_code == 201: devto_url = res.json().get("url", "")
        except Exception as e:
            print(f"❌ Dev.to publish failed: {e}")

    msg = f"✅ {progress}*Interactive Draft Generated!*\n📝 _{seo_title}_\n"
    if devto_url: msg += f"🌐 [Open Dev.to Draft]({devto_url})\n"
    msg += f"💾 Saved to `medium_drafts/` on GitHub."
    send_tg(msg)

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