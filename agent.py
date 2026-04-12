import os, sys, json, base64, requests, feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone

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
    """Returns today's first unprocessed reply (0-3), or None."""
    state = load_state()
    last_id = state.get("last_update_id", 0)
    print(f"[get_reply] last_update_id={last_id}")

    res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT}/getUpdates",
                       params={"offset": last_id + 1, "limit": 20}, timeout=10).json()

    updates = res.get("result", [])
    print(f"[get_reply] {len(updates)} new updates found")

    today = datetime.now(timezone.utc).date()
    for u in reversed(updates):
        msg     = u.get("message", {})
        text    = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        date    = datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc).date()
        print(f"[get_reply] update_id={u.get('update_id')} chat={chat_id} text='{text}' date={date} today={today}")

        if chat_id == str(TELEGRAM_CHAT) and date == today and text in ("0", "1", "2", "3"):
            print(f"[get_reply] ✅ Valid reply: '{text}'")
            save_state({**state, "last_update_id": u["update_id"]})
            return text

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
Target audience: developers and small business owners who want to use AI/automation to save time.

Today is {today}. Here are LIVE real-time signals from 4 sources showing what the dev community is excited about RIGHT NOW:

{trend_block}

{history_block}Your job: Analyze these signals and identify the 3 topics with the HIGHEST viral potential for a Dev.to/Medium article today. Pick topics where:
- Multiple sources agree (e.g. same tool trending on GitHub AND discussed on Reddit = strong signal)
- The topic is practical and buildable (something Suman can write a "I built this" tutorial about)
- There's a clear "developer pain point" angle

Then generate 3 UNIQUE blog post titles, one per winning topic.

TITLE RULES:
- Each title must cover a DIFFERENT topic — no overlapping themes
- Follow proven earning title formulas:
  * "I Built X in Y Minutes Using Z — Here's the Exact Code"
  * "The [Tool/Script] That Saved Me [X Hours] Every Week"  
  * "Stop Doing X Manually — This Free Python Script Does It in Seconds"
  * "How I Automated [Relatable Task] With [Specific Tool] (Full Tutorial)"
- Be specific: name the language, tool, or result
- Under 75 characters
- NO banned phrases: "game-changer", "revolutionize", "the future of"

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
        + "\n\nReply *1*, *2*, *3* to draft • *0* to skip"
    )

# ── PHASE 2: Drafter ─────────────────────────────────────────────────────────
def draft():
    choice = get_reply()
    if choice is None: return print("No reply yet.")
    if choice == "0":  return send_tg("👌 Skipping today. See you tomorrow!")

    topics = load_state().get("topics", [])
    print(f"[draft] choice={choice} topics={topics}")
    if not topics: return send_tg("⚠️ No topics found. Run the morning researcher first.")

    title = topics[int(choice) - 1]
    send_tg(f"⏳ Drafting *\"{title}\"*... ~60 seconds")

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
You are helping Suman — a frontend developer from Kolkata who runs CoderFact (coderfact.com) — plan a blog post.

Title: "{title}"
Target length: ~{target_words} words
Complexity: {complexity}

Create a DETAILED writing outline. Be hyper-specific — invent realistic details that feel lived-in.
This outline will be used to write the full article, so every detail matters.

Return ONLY a JSON object like this:
{{
  "hook_scene": "A specific 2-3 sentence opening scene. Time of day, what Suman was doing, the exact moment the problem appeared. E.g.: It was 11pm on a Tuesday and I had just pushed a client project when I noticed my deploy script had been running for 40 minutes. Again.",
  "pain_point": "The exact frustration in 1-2 sentences. Be specific — name the tool, the error, the wasted time.",
  "failed_attempts": "1-2 things Suman tried first that didn't work. Makes the story credible.",
  "solution_name": "The exact tool/library/technique used to solve it",
  "real_metric": "A specific before/after number. E.g.: went from 47 minutes to 3 minutes, or reduced 200 lines to 18 lines",
  "surprise_finding": "One unexpected thing discovered while building this. Makes the article feel like genuine experience.",
  "code_concept": "In 1 sentence, what the core code snippet does. Be specific about the language and approach.",
  "reader_benefit": "What the reader walks away able to DO after reading this",
  "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "h2_headings": ["heading1", "heading2", "heading3", "heading4"],
  "devto_tags": ["tag1", "tag2", "tag3", "tag4"],
  "meta_description": "One punchy SEO sentence under 160 chars"
}}

Make every field feel like it came from a real person's actual experience. No vague placeholders.
Return ONLY valid JSON. No markdown, no explanation.
""")

    try:
        outline_raw = outline_raw.strip().strip("```json").strip("```").strip()
        outline = json.loads(outline_raw)
    except Exception as e:
        print(f"[draft] Outline parse failed: {e} — using defaults")
        outline = {
            "hook_scene": "It was midnight and I was staring at the same error for the third time that week.",
            "pain_point": "The manual process was eating hours I didn't have.",
            "failed_attempts": "I tried the obvious Stack Overflow solutions. None worked cleanly.",
            "solution_name": "a simple Python script",
            "real_metric": "cut the process from 45 minutes to under 2",
            "surprise_finding": "The hardest part wasn't the code — it was figuring out the right data structure.",
            "code_concept": "A Python script that automates the core workflow end-to-end",
            "reader_benefit": "automate this exact workflow in under an hour",
            "seo_keywords": ["python", "automation", "developer tools", "coding", "tutorial"],
            "h2_headings": [
                "Why This Problem Is More Painful Than It Looks",
                "What I Tried First (And Why It Failed)",
                "The Actual Fix — With the Full Code",
                "Results, Surprises, and What I'd Do Differently"
            ],
            "devto_tags": ["python", "tutorial", "automation", "programming"],
            "meta_description": f"A practical guide to {title.lower()} with real code and real results."
        }

    # ── Pass 2: Write the full article using the outline ──
    article = ask_ai(f"""
You are ghostwriting a blog post for Suman — a frontend developer from Kolkata who runs CoderFact (coderfact.com).

SUMAN'S VOICE — study this carefully before writing a single word:
- Talks like a real person, not a tech writer. Uses "I" constantly. Says things like "honestly", "look", "here's the thing", "I'm not gonna lie"
- Drops into casual mid-thought asides — "(yeah, I know, not ideal)" or "(this took me embarrassingly long to figure out)"
- Uses SHORT punchy paragraphs. Never more than 3 sentences. Lots of white space.
- Occasionally uses em-dashes for rhythm — like this — to add personality
- References being from Kolkata naturally when relevant (power cuts, slow internet, client expectations)
- Never writes "In conclusion" or "In summary" — just ends with a direct human thought
- Does NOT use: "delve", "navigate", "leverage", "landscape", "robust", "seamless", "unleash", "utilize", "empower", "groundbreaking", "revolutionize", "game-changer", "synergy", "cutting-edge", "supercharge", "it's worth noting"
- NEVER starts a paragraph with "Furthermore", "Moreover", "Additionally", "In addition"
- The writing should pass any AI detector — it sounds like a tired, smart developer venting and teaching at the same time

ARTICLE BRIEF:
- Title: "{title}"
- Target: ~{target_words} words
- Hook scene: {outline.get('hook_scene')}
- Pain point: {outline.get('pain_point')}
- What failed first: {outline.get('failed_attempts')}
- The solution: {outline.get('solution_name')}
- Real metric to mention: {outline.get('real_metric')}
- Surprising finding: {outline.get('surprise_finding')}
- Core code concept: {outline.get('code_concept')}
- What reader can do after: {outline.get('reader_benefit')}
- SEO keywords to weave in naturally (don't stuff): {', '.join(outline.get('seo_keywords', []))}

STRUCTURE — use these exact H2 headings:
{chr(10).join(f'## {h}' for h in outline.get('h2_headings', ['The Problem', 'What I Tried', 'The Fix', 'Results']))}

WRITING RULES:
1. Open with the hook scene — no title, no "Introduction" heading. Just jump in mid-story.
2. Every H2 section must have at least one of: a personal anecdote, a specific number, or a code snippet
3. Include ONE clean, working, well-commented code block with the language tag. Make it genuinely useful — not hello-world level.
4. After the code block, explain it like you're talking to a friend: "What this does is..." — not "The above code demonstrates..."
5. The "results" section MUST mention the specific metric: {outline.get('real_metric')}
6. Mention the surprising finding naturally: {outline.get('surprise_finding')}
7. End with a 2-3 sentence human close. Something like: "If you build this, drop a comment — I'm genuinely curious what you use it for. And if it saves you time, the clap button is right there. It costs you nothing and it tells me to keep building stuff like this."
8. Weave in a natural link to coderfact.com at least once (e.g. "I wrote about the full setup over at CoderFact if you want the extended version")
9. HARD LIMIT: {target_words} words. Cut ruthlessly. No fluff.

Append these two lines at the very end (outside the article body):
TAGS: {json.dumps(outline.get('devto_tags', ['python','tutorial','automation','programming']))}
META: {outline.get('meta_description', '')}

Output in Markdown. Start directly with the hook — no preamble, no "Here is your article".
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

    thumb = "-".join(title.lower().split()[:6]) + "-dark-neon-code"
    img   = f"https://image.pollinations.ai/prompt/{thumb}?width=1280&height=720&nologo=true"

    content = f"![{title}]({img})\n\n{body}\n\n---\n*More free tools at [CoderFact](https://coderfact.com). AI-assisted draft, reviewed and edited by me.*"

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
        send_tg(
            f"✅ *Draft ready on Dev.to!*\n\n"
            f"📝 _{title}_\n"
            f"📏 ~{target_words} words _{complexity}_\n"
            f"🎯 Angle: _{outline.get('hook_scene', '')[:80]}..._\n"
            f"📊 Metric: _{outline.get('real_metric', '')}_\n"
            f"🏷 {', '.join(tags)}\n"
            f"📌 {meta}\n\n"
            f"👉 [Open draft]({draft_url}) → review → publish!"
        )
    else:
        send_tg(f"❌ Dev.to error {res.status_code}: {res.text[:300]}\n\nCheck GitHub Actions logs for full details.")

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    {"research": research, "draft": draft}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: print("Usage: python agent.py research | draft"))()