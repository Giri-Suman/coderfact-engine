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
    import time
    def _openai_compat(url, headers, model, prompt, max_tokens, name, retries=2):
        for attempt in range(retries + 1):
            try:
                r = requests.post(url, headers=headers, json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": max_tokens}, timeout=60)
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
    
    if OPENROUTER_KEY:
        try: return _openai_compat(OR_URL, OR_HEADERS, "meta-llama/llama-3.3-70b-instruct:free", prompt, max_tokens, "OR Llama 3.3 70B")
        except Exception: pass
    
    if GEMINI_KEY:
        try:
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}", json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}}, timeout=45)
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception: pass

    raise RuntimeError("All AI providers failed.")

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
def fetch_trends(): return {"github": [], "google_trends": []} # Simplified for brevity, use your full fetch_trends here.

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
    
    vdata = [{"topic": "Python Pandas Optimization", "virality_score": 92, "developer_pain": "high", "author_angle": "How I cut Pandas processing from 47 mins to 3 mins"}]
    
    title_raw = ask_ai(f"""Convert these topics into PERFECT Medium article titles.
    CRITICAL RULE: Titles MUST create a 'curiosity gap' using specific metrics (e.g., 'How I Cut My Pandas Processing Time from 47 Minutes to 3 Minutes'). DO NOT use generic titles like 'Tips and Tricks' or 'A Guide To'.
    {json.dumps(vdata)}
    Reply ONLY in format:
    1. [Title]""")
    
    titles = [line.split(". ", 1)[1].strip().strip('"') for line in title_raw.strip().splitlines() if line.strip()[:2] in ("1.", "2.", "3.")][:3]
    if not titles: titles = [v.get("author_angle", "Topic") for v in vdata]

    save_state({**state, "topics": titles, "date": today, "virality_data": vdata})
    send_tg(f"🔥 *CoderFact Brief* | _{today}_\n1. *{titles[0]}*\n\nReply `1` to draft.")

# ── PHASE 2: Drafter ──────────────────────────────────────────────────────────
def draft_single(title: str, idx: int, total: int):
    progress = f"({idx}/{total}) " if total > 1 else ""
    def tg_step(msg): send_tg(f"{progress}{msg}")

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

    tg_step("✍️ Pass 2: Writing article in Persona...")
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
    
    Title: {title}
    H2s to use: {', '.join(_list(outline.get('people_also_ask')))}
    Output ONLY Markdown.
    """)

    tg_step("🎨 Pass 3: Formatting & Enhancing...")
    medium_ready_body = convert_mermaid_for_medium(article)
    article_body_with_footer = f"{medium_ready_body}\n\n---\n*Tutorial by {AUTHOR_NAME}. Find more at [CoderFact](https://coderfact.com).*\n"

    seo_block = (
        "---\n"
        f"VIRAL TITLE: {title}\n"
        f"META DESCRIPTION: {outline.get('keyword_placement', {}).get('meta_description', '')}\n"
        f"TAGS: {', '.join(_list(outline.get('medium_tags')))}\n"
        f"THUMBNAIL PROMPT: {outline.get('thumbnail_prompt', '')}\n"
        "---\n\n✂️ CUT THE ABOVE BLOCK BEFORE PUBLISHING TO MEDIUM ✂️\n\n"
    )

    github_file_content = seo_block + article_body_with_footer
    devto_payload_content = article_body_with_footer

    tg_step("💾 Exporting to GitHub & Dev.to...")
    slug = re.sub(r'[^\w\s]', '', title.lower()).replace(' ', '-')
    
    # Save to local/GitHub (Mocked for brevity in this display, keep your existing requests.put logic here)
    if GITHUB_TOKEN:
        hdrs = {"Authorization": f"token {GITHUB_TOKEN}"}
        requests.put(f"https://api.github.com/repos/{GITHUB_REPO}/contents/medium_drafts/{slug}.md", headers=hdrs, json={"message": f"docs: new draft {slug}", "content": base64.b64encode(github_file_content.encode()).decode()})

    # Dev.to
    if DEVTO_KEY:
        requests.post("https://dev.to/api/articles", headers={"api-key": DEVTO_KEY}, json={"article": {"title": title, "body_markdown": devto_payload_content, "published": False}})

    send_tg(f"✅ *Interactive Draft Generated!*\n📝 _{title}_\n💾 Exported to `medium_drafts/` on GitHub and uploaded to Dev.to.")

def draft():
    reply = get_reply()
    if reply and reply.get("type") == "choice":
        topics = load_state().get("topics", [])
        for c in reply["choices"]: draft_single(topics[int(c)-1], 1, 1)

if __name__ == "__main__":
    {"research": research, "draft": draft}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print("Usage: python agent.py research | draft"))()