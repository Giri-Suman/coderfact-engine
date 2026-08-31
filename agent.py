import os, sys, json, base64, re, hashlib, requests, feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

import humanizer
import research_engine as rx
import judge
import promo
import brain
import claims


def _load_dotenv(path=".env"):
    """Read a local .env into os.environ for CLI runs.

    .env has always been gitignored here, which implies it was meant to work —
    but nothing ever read it, so a local key file was silently ignored and every
    CLI run behaved as though no keys were set. Deliberately dependency-free and
    deliberately non-overriding: a real environment variable (which is how
    GitHub Actions injects secrets) always wins over the file.
    """
    if not os.path.exists(path):
        return 0
    n = 0
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
                    n += 1
    except Exception as e:
        print(f"[env] could not read {path}: {e}")
    return n


_load_dotenv()

DEVTO_KEY      = os.getenv("DEVTO_API_KEY")
TELEGRAM_BOT   = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY")
GROQ_KEY       = os.getenv("GROQ_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")
GITHUB_REPO    = os.getenv("GITHUB_REPOSITORY")
STATE_FILE     = "state.json"

# Gemini models, tried in order. All Flash tiers are free-of-charge on the free
# tier, and each model ID carries its OWN quota, so listing two is real fallback
# capacity rather than a preference — one article costs 12-15 model calls and the
# free tier allows 10 requests/minute.
#
# Override without touching code when Google retires one:
#   GEMINI_MODELS="gemini-3.7-flash,gemini-3.6-flash"
# This list was previously a single hardcoded "gemini-2.0-flash", which Google
# has since shut down — the whole Gemini leg was dead and every run silently
# fell through to the next provider.
GEMINI_MODELS  = [m.strip() for m in os.getenv(
    "GEMINI_MODELS", "gemini-3.7-flash,gemini-3.5-flash").split(",") if m.strip()]

# OpenRouter ':free' slugs, tried in order. These rot faster than anything else
# in this file — the three previously hardcoded here (llama-3.3-70b-instruct,
# deepseek-r1-0528, gemma-3-27b-it) had ALL been removed from the catalogue, so
# the entire OpenRouter leg was returning 404 on every call.
#
# Chosen for long-form drafting: big context (the article prompt is large) and a
# high completion cap. Verify the list any time with `python agent.py models`.
OPENROUTER_MODELS = [m.strip() for m in os.getenv(
    "OPENROUTER_MODELS",
    "z-ai/glm-5.2:free,"
    "minimax/minimax-m3:free,"
    "nvidia/nemotron-3-super-120b-a12b:free,"
    "google/gemma-4-31b-it:free").split(",") if m.strip()]

# Gemini 3.x thinks by default and thinking shares the output-token budget with
# the answer, so the budget has to cover BOTH. "low" keeps reasoning cheap for a
# drafting workload; set GEMINI_THINKING="" to send no thinking field at all.
GEMINI_THINKING = os.getenv("GEMINI_THINKING", "low").strip()
GEMINI_TOKEN_HEADROOM = float(os.getenv("GEMINI_TOKEN_HEADROOM", "3.0"))

# Minimum share of the target word count an article must reach before it is
# allowed to continue down the pipeline.
# A heading is only interrogative when a wh-word is followed by an auxiliary
# ("How DO I build...", "What DOES it cost"). "Why the linear scan falls over"
# and "What actually worked" are noun phrases and are exactly the narrative
# style we want, so matching on the wh-word alone would reject good headings.
_QUESTION_HEAD_RE = re.compile(
    r"^\s*(?:how|what|why|when|where|which|who)\s+(?:do|does|did|is|are|was|were|can|could|should|will|would|have|has|had)\b"
    r"|^\s*(?:can|does|do|is|are|should|will|would|have|has)\s+(?:i|you|we|it|they|the)\b",
    re.IGNORECASE)

ARTICLE_MIN_RATIO = float(os.getenv("ARTICLE_MIN_RATIO", "0.45"))

# openrouter/auto has variable pricing and can bill real money. Off unless asked.
OPENROUTER_ALLOW_PAID = os.getenv("OPENROUTER_ALLOW_PAID", "").strip().lower() in ("1", "true", "yes")

GROQ_MODEL     = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

AUTHOR_NAME    = os.getenv("AUTHOR_NAME",    "Suman Giri")
AUTHOR_CONTEXT = os.getenv("AUTHOR_CONTEXT", "a tech automation enthusiast, senior frontend developer from Kolkata who builds tools for CoderFact")
AUTHOR_VIBE    = os.getenv("AUTHOR_VIBE",    "figures stuff out at 1am, writes about it next morning, still mildly annoyed it took so long")
TICK3          = chr(96) * 3

# ═══════════════════════════════════════════════════════════════════════════════
# FIX 1: Added missing convert_mermaid_for_medium() function
# This was called in draft_single() but NEVER DEFINED -> NameError crash
# ═══════════════════════════════════════════════════════════════════════════════
def convert_mermaid_for_medium(body: str) -> str:
    """Convert Mermaid code blocks to mermaid.ink image URLs for Medium compatibility.

    Must be URL-SAFE base64. Standard base64 emits '+' and '/', and a '/' inside
    the path segment splits the URL — mermaid.ink then 404s and the article ships
    with a broken image. Real example: 'graph TD\\n A-->B' encodes to a string
    containing '...LS0+fHllc3wg...'.
    """
    pattern = re.compile(r'```mermaid\s*\n(.*?)```', re.DOTALL)

    def replace_mermaid(match):
        diagram = match.group(1).strip()
        encoded = base64.urlsafe_b64encode(diagram.encode('utf-8')).decode('ascii')
        img_url = f"https://mermaid.ink/img/{encoded}?theme=dark&bgColor=!1a1a2e"
        # Alt text matters more than usual: Medium has no native Mermaid
        # support, so when the image fails the reader sees this string. It said
        # "Mermaid diagram", which is why the critique reported exactly that.
        labels = re.findall(r"\[([^\]]{3,40})\]|\{([^}]{3,40})\}", diagram)
        names = [a or b for a, b in labels][:3]
        head = (diagram.splitlines() or ["diagram"])[0].strip()
        alt = " to ".join(names) if len(names) >= 2 else (names[0] if names else head)
        return f"![Diagram: {alt}]({img_url})\n"

    return pattern.sub(replace_mermaid, body)


# ═══════════════════════════════════════════════════════════════════════════════
# JSON extraction — one implementation for the whole file.
#
# The old code used `raw.strip("```json").strip("```")` in five places. str.strip
# takes a SET OF CHARACTERS, not a suffix, so that call strips any leading or
# trailing ` j s o n from the payload. A response starting with `[{"name": ...`
# survives by luck; one starting with `no results` loses its 'n' and 'o'.
# ═══════════════════════════════════════════════════════════════════════════════
def extract_json(raw: str, want=None):
    """Parse JSON out of an LLM response. Handles code fences, preamble prose and
    trailing commas. `want` may be dict or list to assert the top-level type."""
    if not raw:
        raise ValueError("empty response")
    text = re.sub(r'^\s*```(?:json)?\s*', '', raw.strip(), flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE).strip()

    candidates = [text]
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])

    last_err = None
    for blob in candidates:
        for attempt in (blob, re.sub(r',(\s*[}\]])', r'\1', blob)):
            try:
                data = json.loads(attempt, strict=False)
            except Exception as e:
                last_err = e
                continue
            if want and not isinstance(data, want):
                last_err = ValueError(f"expected {want}, got {type(data).__name__}")
                continue
            return data
    raise ValueError(f"JSON extraction failed: {last_err} | raw[:200]={raw[:200]!r}")


# ═══════════════════════════════════════════════════════════════════════════════
# QuickChart.io — render real data charts as PNG URLs (no API key required)
# Pass a Chart.js config dict; get back a Markdown image string.
# ═══════════════════════════════════════════════════════════════════════════════
def _medium_checklist(body: str) -> str:
    """Medium-specific steps the Markdown cannot express.

    Medium renders neither Mermaid nor syntax-highlighted code. The pipeline
    converts diagrams to mermaid.ink images, but the import still needs a human
    pass, and a checklist naming the actual counts beats a generic reminder.
    """
    n_diagrams = body.count("![Diagram:")
    fences = re.findall(r"```(\w*)", body)
    real = [f for f in fences if f and f.lower() not in ("mermaid", "json?chameleon")]
    langs = sorted(set(real))

    L = ["MEDIUM PUBLISHING CHECKLIST\n"]
    if n_diagrams:
        L.append(
            "  [ ] %d diagram(s) are mermaid.ink images. Open each in the preview.\n"
            "      If one shows alt text instead of a picture, rebuild it at\n"
            "      mermaid.live and upload the PNG - Medium has no Mermaid support.\n"
            % n_diagrams)
    if real:
        L.append(
            "  [ ] %d code block(s) (%s). Medium's native blocks barely highlight.\n"
            "      Paste each into a GitHub Gist and embed the Gist URL, or use\n"
            "      carbon.now.sh images. Gists stay copyable; carbon images do not.\n"
            % (len(real), ", ".join(langs) or "no language tags"))
    L.append(
        "  [ ] Any throughput/latency/memory number: confirm the machine and the\n"
        "      method are in the same paragraph. The .claims.md file lists ones\n"
        "      flagged NEEDS_METHOD - those get fact-checked in the comments.\n")
    L.append("  [ ] Headings read as narrative, not as search queries.\n")
    return "".join(L)


def quickchart_url(config: dict, w: int = 700, h: int = 400, bg: str = "#1a1a2e") -> str:
    try:
        import urllib.parse as _u
        cfg_json = json.dumps(config, separators=(",", ":"))
        return (
            "https://quickchart.io/chart"
            f"?w={w}&h={h}&bkg={_u.quote(bg)}&c={_u.quote(cfg_json)}"
        )
    except Exception as e:
        print(f"[chart] QuickChart URL build failed: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Pull-quote card — large blockquote with attribution, renders well on Medium.
# ═══════════════════════════════════════════════════════════════════════════════
def render_quote_card(quote: str, attribution: str = "") -> str:
    quote = quote.strip().strip('"').strip("'")
    if not quote:
        return ""
    if attribution:
        return f"\n> ## {quote}\n>\n> — *{attribution.strip()}*\n"
    return f"\n> ## {quote}\n"


# ═══════════════════════════════════════════════════════════════════════════════
# HUMANIZATION — anti-AI-detection rewrite pass.
# Runs after the article is written. Different model, different prompt.
# Goal: kill "AI tells" without losing technical accuracy.
# ═══════════════════════════════════════════════════════════════════════════════
HUMAN_BANNED = humanizer.AI_VOCAB   # kept as an alias; the list lives in humanizer.py

def humanize_pass(article_md: str, voice_context: str, target_words: int):
    """Rewrite + repair loop. Returns (article, humanizer.Report | None).

    The old implementation did one blind rewrite, then ai_lint() PRINTED its
    findings and returned the article unchanged — every tell it detected still
    shipped. humanizer.humanize() feeds those findings back to the model and
    re-scans, and only keeps a repair that measurably improves the score.
    """
    if not article_md or len(article_md) < 200:
        return article_md, None
    try:
        return humanizer.humanize(
            article_md, ask_ai,
            voice_context=voice_context,
            target_words=target_words,
            max_rounds=int(os.getenv("HUMANIZE_ROUNDS", "2")),
            target_score=int(os.getenv("HUMANIZE_TARGET", "85")),
        )
    except Exception as e:
        print(f"[humanize] failed: {e} — keeping AI draft")
        return article_md, None


def ai_lint(article_md: str):
    """Back-compat shim: (article, warnings). Detection lives in humanizer.py."""
    fixed, _ = humanizer.autofix(article_md)
    findings = humanizer.scan(fixed)
    return fixed, [f"{f.name}: {f.excerpt}" for f in findings]


# ═══════════════════════════════════════════════════════════════════════════════
# FIX 2: Added robust GitHub file saver with proper error handling
# GitHub API creates folders implicitly when you PUT a file with path like folder/file.md
# ═══════════════════════════════════════════════════════════════════════════════
def draft_slug(title: str, maxlen: int = 60, fallback: str = "draft") -> str:
    """Filename slug that will not silently overwrite a different draft.

    The old inline expression truncated at 60 characters, so two titles sharing
    a long prefix mapped to the same medium_drafts/<slug>.md and the second run
    clobbered the first. When truncation actually happens, disambiguate with a
    short hash of the full title.
    """
    base = re.sub(r"[^\w\s-]", "", str(title).lower()).strip()
    base = re.sub(r"[\s_]+", "-", base).strip("-")
    if not base:
        return fallback
    if len(base) <= maxlen:
        return base
    digest = hashlib.sha1(str(title).encode("utf-8")).hexdigest()[:6]
    return f"{base[:maxlen].rstrip('-')}-{digest}"


def _save_local(path: str, content: str) -> str:
    """Write beside the repo so a run without a GitHub token still leaves its
    output on disk. Returns the path, or '' on failure."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"[local] wrote {path} ({len(content)} chars)")
        return path
    except Exception as e:
        print(f"[local] could not write {path}: {e}")
        return ""


def save_file_to_github(path: str, content: str, message: str) -> str:
    """Save a file to the GitHub repo. Returns the file URL, or on failure the
    local path it fell back to.

    Without a token this used to return '' and drop the content on the floor —
    so a local run generated a full article, a claims map and a promo pack and
    then discarded all three. Local runs now keep their output.
    """
    if not (GITHUB_TOKEN and GITHUB_REPO):
        print("[GitHub] SKIP: no token/repo — saving locally instead")
        return _save_local(path, content)

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    hdrs = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    sha = None
    try:
        r = requests.get(api_url, headers=hdrs, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
            print(f"[GitHub] File exists, sha={sha[:8] if sha else 'none'}")
        elif r.status_code == 404:
            print(f"[GitHub] New file: {path}")
        else:
            print(f"[GitHub] GET {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[GitHub] GET error: {e}")

    payload = {
        "message": message,
        "content": base64.b64encode(content.encode('utf-8')).decode('ascii'),
        "committer": {"name": AUTHOR_NAME, "email": "bot@coderfact.com"}
    }
    if sha:
        payload["sha"] = sha

    try:
        r = requests.put(api_url, headers=hdrs, json=payload, timeout=15)
        if r.status_code in (200, 201):
            url = r.json().get("content", {}).get("html_url", "")
            print(f"[GitHub] SAVED: {url}")
            return url
        else:
            print(f"[GitHub] PUT FAILED {r.status_code}: {r.text[:300]}")
            return _save_local(path, content)
    except Exception as e:
        print(f"[GitHub] PUT error: {e}")
        return _save_local(path, content)


def ask_ai(prompt: str, max_tokens: int = 4000) -> str:
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
                print(f"[AI] {name} OK")
                return text
            except requests.HTTPError as e:
                if attempt < retries and "429" in str(e):
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError(f"{name}: exhausted retries")

    def _gemini(model, prompt, max_tokens, retries=2):
        """Google's own endpoint. Kept separate from _openai_compat because the
        request and response shapes differ.

        Gemini 3.x Flash has thinking ON by default (medium), and thinking
        shares the maxOutputTokens budget with the visible answer. A 900-word
        article asked for with maxOutputTokens=2760 came back as 70 words with
        finishReason=MAX_TOKENS, because reasoning had eaten the budget. Two
        defences: ask for a low thinking level, and give the budget real
        headroom.
        """
        budget = max(int(max_tokens * GEMINI_TOKEN_HEADROOM), 4096)
        cfg = {"maxOutputTokens": budget, "temperature": 0.7}
        if GEMINI_THINKING:
            # Field name is not in the public REST reference; if the API
            # rejects it we drop it and retry rather than failing the call.
            cfg["thinkingConfig"] = {"thinkingLevel": GEMINI_THINKING}

        for attempt in range(retries + 1):
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": cfg},
                timeout=90,
            )
            if r.status_code == 400 and "thinkingConfig" in cfg:
                print(f"[AI] Gemini {model}: thinkingConfig rejected — retrying without")
                cfg.pop("thinkingConfig")
                continue
            if r.status_code == 429 and attempt < retries:
                wait = 2 ** attempt
                print(f"[AI] Gemini {model} rate-limited — waiting {wait}s")
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()

            # A safety block or a MAX_TOKENS stop returns 200 with no parts.
            # Indexing straight into candidates[0].content.parts[0] turned those
            # into a bare KeyError that said nothing about what happened.
            cands = data.get("candidates") or []
            if not cands:
                fb = data.get("promptFeedback") or {}
                raise ValueError(f"no candidates (blockReason="
                                 f"{fb.get('blockReason', 'unknown')})")
            parts = (cands[0].get("content") or {}).get("parts") or []
            if not parts:
                raise ValueError(f"empty response (finishReason="
                                 f"{cands[0].get('finishReason', 'unknown')})")
            text = "".join(p.get("text", "") for p in parts).strip()
            if len(text) < 50:
                raise ValueError(f"Too short ({len(text)} chars)")

            # A MAX_TOKENS stop that still produced some text is the dangerous
            # case: it looks like success and returns a sentence fragment. That
            # fragment previously flowed into the humanizer, which responded
            # with commentary about the truncation, and the commentary was
            # saved as the article. Treat it as a failure and fall through.
            finish = (cands[0].get("finishReason") or "").upper()
            if finish in ("MAX_TOKENS", "RECITATION", "SAFETY", "PROHIBITED_CONTENT"):
                usage = data.get("usageMetadata") or {}
                raise ValueError(
                    f"truncated: finishReason={finish}, budget={budget}, "
                    f"thoughts={usage.get('thoughtsTokenCount', '?')}, "
                    f"output={usage.get('candidatesTokenCount', '?')} "
                    f"({len(text)} chars kept)")
            print(f"[AI] Gemini {model} OK ({len(text)} chars)")
            return text
        raise RuntimeError(f"Gemini {model}: exhausted retries")

    OR_HEADERS = {
        "Authorization": f"Bearer {OPENROUTER_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "https://coderfact.com",
        "X-Title":       "CoderFact Content Engine",
    } if OPENROUTER_KEY else {}

    OR_URL = "https://openrouter.ai/api/v1/chat/completions"
    errors = []

    # Gemini first: the direct API is the only genuinely free path to a Flash
    # model. OpenRouter carries every Gemini tier but NONE of them free —
    # google/gemini-3.5-flash bills $1.50/$9.00 per million there.
    for _model in GEMINI_MODELS:
        if not GEMINI_KEY:
            break
        try:
            return _gemini(_model, prompt, max_tokens)
        except Exception as e:
            errors.append(str(e)); print(f"[AI] Gemini {_model} failed -> {e}")

    if GROQ_KEY:
        try:
            return _openai_compat(
                "https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                GROQ_MODEL, prompt, max_tokens, f"Groq {GROQ_MODEL}")
        except Exception as e:
            errors.append(str(e)); print(f"[AI] Groq failed -> {e}")

    for _model in OPENROUTER_MODELS:
        if not OPENROUTER_KEY:
            break
        try:
            return _openai_compat(OR_URL, OR_HEADERS, _model,
                                  prompt, max_tokens, f"OR {_model}")
        except Exception as e:
            errors.append(str(e)); print(f"[AI] OR {_model} failed -> {e}")

    # openrouter/auto is deliberately last and off by default: its pricing is
    # variable (-1), so it can route a request to a PAID model and bill for it.
    # Opt in with OPENROUTER_ALLOW_PAID=1 if a run completing matters more than
    # the run being free.
    if OPENROUTER_KEY and OPENROUTER_ALLOW_PAID:
        try:
            return _openai_compat(OR_URL, OR_HEADERS, "openrouter/auto",
                                  prompt, max_tokens, "OR Auto (PAID — variable pricing)")
        except Exception as e:
            errors.append(str(e)); print(f"[AI] OR Auto failed -> {e}")

    raise RuntimeError("All AI providers failed:\n" + "\n".join(errors[-6:]))


def load_state():
    return json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}

def save_state(data):
    """Write state locally, then mirror to GitHub.

    Every network call here is bounded and non-fatal. The old version called
    requests.get(...).json() with no timeout and no try/except: the Telegram
    listener runs this every 15 minutes, so one hung GitHub API call stalled the
    job until the 20-minute workflow timeout killed it.
    """
    payload = json.dumps(data, indent=2)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        fh.write(payload)
    if not (GITHUB_TOKEN and GITHUB_REPO):
        return

    api = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{STATE_FILE}"
    hdrs = {"Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"}
    sha = None
    try:
        r = requests.get(api, headers=hdrs, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception as e:
        print(f"[state] GET failed ({e}) — attempting blind PUT")

    body = {"message": "chore: update state",
            "content": base64.b64encode(payload.encode()).decode()}
    if sha:
        body["sha"] = sha
    try:
        r = requests.put(api, headers=hdrs, json=body, timeout=15)
        if r.status_code not in (200, 201):
            print(f"[state] PUT {r.status_code}: {r.text[:160]}")
    except Exception as e:
        print(f"[state] PUT failed (non-fatal): {e}")


def send_tg(msg):
    if not (TELEGRAM_BOT and TELEGRAM_CHAT):
        print(f"[TG SKIP] No bot config")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=10
        )
        print(f"[TG] {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"[TG ERROR] {e}")


def get_reply():
    state   = load_state()
    last_id = state.get("last_update_id", 0)
    print(f"[get_reply] last_update_id={last_id}")

    res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT}/getUpdates",
                       params={"offset": last_id + 1, "limit": 20}, timeout=10).json()

    updates = res.get("result", [])
    print(f"[get_reply] {len(updates)} new updates found")

    today     = datetime.now(timezone.utc).date()
    ist_offset = timedelta(hours=5, minutes=30)
    today_ist  = (datetime.now(timezone.utc) + ist_offset).date()

    for u in reversed(updates):
        msg     = u.get("message", {})
        text    = msg.get("text", "").strip()
        chat_id = str(msg.get("chat", {}).get("id", ""))
        date    = datetime.fromtimestamp(msg.get("date", 0), tz=timezone.utc).date()
        print(f"[get_reply] update_id={u.get('update_id')} chat={chat_id} text='{text[:60]}' date={date}")

        if chat_id != str(TELEGRAM_CHAT) or date not in (today, today_ist):
            continue
        if not text:
            continue

        save_state({**state, "last_update_id": u["update_id"]})

        if text.strip() == "0":
            return {"type": "skip"}

        clean = text.replace(" ", "")
        if all(c in "0123456789" for c in clean) and len(clean) <= 3:
            digits = list(dict.fromkeys(c for c in clean if c in "1234567890"))
            valid  = [c for c in digits if c in ("1","2","3")]
            if valid:
                print(f"[get_reply] Numbered choices: {valid}")
                return {"type": "choice", "choices": valid}

        if len(text) >= 10:
            print(f"[get_reply] Custom topic: '{text[:60]}'")
            return {"type": "custom", "topic": text}

    print("[get_reply] No valid reply found.")
    return None


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

    try:
        articles = requests.get("https://dev.to/api/articles?top=7&per_page=10", headers=HEADERS, timeout=8).json()
        signals["devto"] = [{"title": a.get("title",""), "tags": a.get("tag_list",[]),
                              "reactions": a.get("positive_reactions_count",0)} for a in articles[:8]]
        print(f"[trends] Dev.to: {len(signals['devto'])} articles")
    except Exception as e:
        print(f"[trends] Dev.to failed: {e}")
        signals["devto"] = []

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

    rss_items = []
    rss_feeds = [
        ("https://towardsdatascience.com/feed",                    "Towards Data Science"),
        ("https://medium.com/feed/better-programming",             "Better Programming"),
        ("https://medium.com/feed/towards-artificial-intelligence","Towards AI"),
        ("https://medium.com/feed/hackernoon",                     "HackerNoon"),
        ("https://medium.com/feed/level-up-coding",                "Level Up Coding"),
        ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch AI"),
        ("https://www.technologyreview.com/feed/",                 "MIT Tech Review"),
        ("https://freecodecamp.org/news/rss/",                     "freeCodeCamp"),
        ("https://hnrss.org/frontpage",                            "HN RSS"),
        ("https://rss.arxiv.org/rss/cs.AI",                        "arXiv CS.AI"),
    ]
    for url, source in rss_feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                title = getattr(entry, 'title', '')
                if title:
                    rss_items.append({"title": title, "source": source})
        except Exception:
            pass
    signals["rss_news"] = rss_items[:25]
    print(f"[trends] RSS (Medium pubs + tech blogs): {len(rss_items)} items")

    try:
        feed = feedparser.parse("https://stackoverflow.blog/feed/")
        signals["stackoverflow"] = [e.title for e in feed.entries[:6]]
        print(f"[trends] StackOverflow blog: {len(signals['stackoverflow'])} items")
    except Exception as e:
        print(f"[trends] StackOverflow failed: {e}")
        signals["stackoverflow"] = []

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


# ═══════════════════════════════════════════════════════════════════════════════
# REAL SUCCESS STORIES — scrape actual indie-dev income/launch posts
# Sources: Hacker News (Show HN via Algolia), income-focused subreddits, Dev.to
# Returns a list of {source, title, snippet, url, signal} dicts with REAL URLs
# so the article writer can cite them instead of fabricating numbers.
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_success_stories() -> list:
    HEADERS  = {"User-Agent": "Mozilla/5.0 (compatible; CoderFact-Bot/1.0)"}
    income_kw = ("$", " mrr", " arr", "revenue", "made $", "earned", "passive income",
                 "side project", "side hustle", "launched", "shipped", "first sale",
                 "first user", "first customer", "indie hacker", "solo founder",
                 "ai automation", "ai agent", "vibe coding", "built with cursor")
    stories = []

    # 1) Hacker News — Show HN posts via Algolia, sorted by points
    try:
        r = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"tags": "show_hn", "hitsPerPage": 30,
                    "numericFilters": "points>20"},
            timeout=10
        )
        for hit in r.json().get("hits", []):
            title = (hit.get("title") or "").strip()
            if not title: continue
            tl = title.lower()
            if not any(k in tl for k in income_kw + ("ai ", "agent", "automation", "saas")):
                continue
            stories.append({
                "source": "Hacker News (Show HN)",
                "title":   title,
                "snippet": (hit.get("story_text") or "")[:200],
                "url":     hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}",
                "signal":  f"{hit.get('points',0)} points · {hit.get('num_comments',0)} comments",
            })
        print(f"[stories] HN Show HN: {len([s for s in stories if 'Hacker News' in s['source']])} hits")
    except Exception as e:
        print(f"[stories] HN failed: {e}")

    # 2) Reddit — income/builder subs, look for income or launch signal in title/body
    income_subs = ["indiehackers", "SideProject", "EntrepreneurRideAlong",
                   "passive_income", "Entrepreneur", "SaaS"]
    for sub in income_subs:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/top.json?t=month&limit=15",
                headers={**HEADERS, "Accept": "application/json"}, timeout=8
            )
            for p in r.json().get("data", {}).get("children", []):
                d = p.get("data", {})
                if d.get("stickied"): continue
                title    = (d.get("title") or "").strip()
                selftext = (d.get("selftext") or "")
                combined = (title + " " + selftext[:400]).lower()
                if not any(k in combined for k in income_kw):
                    continue
                ups = d.get("ups", 0)
                if ups < 30: continue   # noise filter
                stories.append({
                    "source":  f"Reddit r/{sub}",
                    "title":   title,
                    "snippet": selftext[:240].replace("\n", " ").strip(),
                    "url":     "https://www.reddit.com" + (d.get("permalink") or ""),
                    "signal":  f"{ups} upvotes · {d.get('num_comments',0)} comments",
                })
        except Exception as e:
            print(f"[stories] Reddit r/{sub} failed: {e}")
    print(f"[stories] Reddit income subs: {len([s for s in stories if 'Reddit' in s['source']])} hits")

    # 3) Dev.to — articles tagged for indie / side-project / passive-income content
    for tag in ("indiehackers", "sideproject", "passiveincome", "saas"):
        try:
            r = requests.get(f"https://dev.to/api/articles?tag={tag}&top=30&per_page=10",
                             headers=HEADERS, timeout=8)
            for a in r.json():
                title = (a.get("title") or "").strip()
                if not title: continue
                tl = title.lower()
                if not any(k in tl for k in income_kw):
                    continue
                stories.append({
                    "source":  f"Dev.to (#{tag})",
                    "title":   title,
                    "snippet": (a.get("description") or "")[:240],
                    "url":     a.get("url") or "",
                    "signal":  f"{a.get('positive_reactions_count',0)} reactions · {a.get('comments_count',0)} comments",
                })
        except Exception as e:
            print(f"[stories] Dev.to #{tag} failed: {e}")
    print(f"[stories] Dev.to tags: {len([s for s in stories if 'Dev.to' in s['source']])} hits")

    # Dedup by title (lowercased), keep highest-signal version
    def _signal_num(s):
        digits = re.findall(r'\d+', s.get("signal", ""))
        return int(digits[0]) if digits else 0
    seen = {}
    for s in sorted(stories, key=_signal_num, reverse=True):
        key = s["title"].lower()[:80]
        if key not in seen:
            seen[key] = s
    final = list(seen.values())[:20]
    print(f"[stories] FINAL (deduped, top 20): {len(final)}")
    return final


def format_success_stories(stories: list) -> str:
    if not stories:
        return ""
    lines = ["\n💎 REAL DEVELOPER SUCCESS STORIES (use these as REAL evidence — cite the URL):"]
    for s in stories[:15]:
        lines.append(f"  • [{s['source']}] {s['title'][:110]}")
        if s.get("snippet"):
            lines.append(f"      _{s['snippet'][:140]}_")
        lines.append(f"      Signal: {s['signal']}  |  URL: {s['url']}")
    return "\n".join(lines)


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
        lines.append("\n📰 MEDIUM PUBLICATIONS + TECH BLOGS (what's already working):")
        for item in signals["rss_news"][:15]:
            if isinstance(item, dict):
                lines.append(f"  • [{item.get('source','')}] {item.get('title','')}")
            else:
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


def research():
    today         = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%B %d, %Y")
    state         = load_state()
    title_history = state.get("title_history", [])

    print("[research] Parallel sweep across all sources...")
    clusters, health = [], []
    try:
        clusters, health, _items = rx.research_sweep()
        trend_block   = rx.format_clusters(clusters, limit=18)
        stories_block = rx.format_stories(clusters)
        health_block  = rx.format_health(health)
        # Legacy shape — draft_single reads these back out of state.json.
        success_stories = [
            {"source": it.source, "title": it.title, "url": it.url,
             "signal": it.detail, "snippet": it.meta.get("snippet", "")}
            for c in clusters for it in c.items if it.meta.get("story") and it.url
        ][:20]
    except Exception as e:
        print(f"[research] sweep failed ({e}) — falling back to the legacy fetchers")
        signals         = fetch_trends()
        trend_block     = format_signals(signals)
        success_stories = fetch_success_stories()
        stories_block   = format_success_stories(success_stories)
        health_block    = "SOURCE HEALTH: unavailable (ranked sweep failed)."
        clusters        = []
    print(f"[research] trends {len(trend_block)} chars, stories {len(stories_block)} chars")

    history_block = ""
    if title_history:
        history_block = (
            "ALREADY PUBLISHED (do NOT repeat or closely paraphrase these):\n"
            + "\n".join(f"- {t}" for t in title_history[-30:])
            + "\n\n"
        )

    print("[research] Pass A: Scoring virality...")
    virality_raw = ask_ai(f"""You are a senior content strategist who knows exactly what makes tech articles go viral on Medium in 2026.

Today is {today}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTENT CATEGORIES — the 3 topics MUST come from 3 DIFFERENT categories below.
Rotate aggressively across these — readers are bored of "another debugging fix" every day.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CATEGORY A — Developer Success Story
   "How I shipped X in Y days as a solo dev" / "From zero users to N in N months"
   Hook: real journey, specific numbers, what worked, what failed.
   Why viral: Medium readers love builder narratives. High read-ratio.

CATEGORY B — Vibe Coding / AI-Assisted Workflow
   "I built a full app in one afternoon using Cursor + Claude" / "Vibe coding a SaaS in a weekend"
   Hook: shows the modern AI-augmented dev loop. Real prompts, real diffs.
   Why viral: this is the dominant 2026 dev trend — high search volume + curiosity.

CATEGORY C — AI Agents & Multi-Agent Workflows
   "Building a research agent with LangGraph in 80 lines" / "My 4-agent system that writes my newsletter"
   Hook: actual architecture diagram, message-passing, working orchestration code.
   Why viral: every dev wants to build agents but most posts are theoretical. Be concrete.

CATEGORY D — AI Automation Across Domains
   Pick a non-coding domain (sales / finance / content / customer support / hiring / ops)
   and show a working automation. e.g. "Auto-categorizing 1000 invoices a day with Gemini".
   Why viral: bridges devs into business value — much wider audience than coding-only posts.

CATEGORY E — Money / Income Story
   "How I made $X/month from a 200-line script" / "Why my $9 SaaS beats my $90k job"
   Real numbers, real Stripe/Gumroad screenshots referenced, honest about failures.
   Why viral: highest engagement category on Medium. Be specific, not aspirational.

CATEGORY F — Debugging / Fix With Code (the only "old" category — keep, but cap at 1 of 3)
   Named error, named tool version, exact root cause, working fix.

CATEGORY G — Software Architecture Insight
   "Why I rewrote our queue from Celery to Redis Streams" / "The 3 trade-offs nobody warns you about with microservices"
   Real production decision, alternatives considered, honest trade-offs.

CATEGORY H — Tips & Tricks / Real Workflow
   "7 git aliases I use every day" / "My terminal setup as a senior dev (with config files)"
   Practical, copyable, specific. Each tip has a tiny proof — command, screenshot, or config snippet.

DIVERSITY CONSTRAINT (HARD):
- 3 topics from 3 DIFFERENT categories
- At most 1 of the 3 may be Category F (debugging fix)
- At least 1 must be from {{B, C, D, E}} (the AI/automation/income cluster)
- No category should appear in 2 consecutive days — check title_history below

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT MAKES A CODING/AI ARTICLE GO VIRAL ON MEDIUM (research-backed):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. CROSS-SOURCE SIGNAL: Topic surfacing on GitHub + Reddit + Google Trends = 3x multiplier
2. DEVELOPER PAIN POINT: "I wasted X hours on this" = highest clap rate
3. ACTIONABLE + CODE: Working code readers can copy = high bookmark + share rate
4. FRESH ANGLE: First-mover on a new tool (<30 days) = Google SEO advantage
5. AI + AUTOMATION: Medium tech readers favor these heavily in 2026
6. PERSONAL STORY with NUMBERS: "$3k MRR in 4 months" out-performs "I built an app"
7. SEARCH DEMAND: Low-competition keyword with real search volume = ranks on Google
8. BOOST-WORTHY: Original insight + expert voice + actionable takeaway = editorial boost
9. AUDIENCE: CoderFact readers are devs 25-40, practical builders, India + global
10. SPECIFICITY: Named errors, specific tools, exact time saved = more trust

{health_block}

{trend_block}

{stories_block}

{history_block}TASK: Analyze every signal AND every real success story above.
For Category A / B / E topics, you MUST anchor the topic in 1-2 of the REAL stories from the list above (cite the source URL in `real_story_evidence`).
Pick 3 topics from 3 DIFFERENT categories above.
Score each 0-100 for Medium virality. Be honest — don't inflate scores.

Return ONLY a valid JSON array — no markdown, no explanation:
[
  {{
    "topic": "specific raw topic e.g. 'How I built a research agent that runs my morning brief'",
    "category": "C",
    "category_name": "AI Agents & Multi-Agent Workflows",
    "virality_score": 88,
    "analysis": "3 sentences: WHY this will rank on Medium THIS WEEK, what the cross-source evidence is, and what makes it different from existing posts on the topic.",
    "cross_source_signals": ["GitHub: langgraph repo trending", "Reddit r/MachineLearning: 4 posts this week", "Google Trends: 'ai agent tutorial' rising"],
    "developer_pain": "high",
    "freshness": "breaking",
    "money_angle": "Optional: monetization or income angle if relevant — empty string if not",
    "story_angle": "First-person hook in 1 sentence — what specifically happened to Suman that triggered this",
    "suman_angle": "Specific first-person rewrite: 'How I built a 3-agent newsletter pipeline in one weekend (full code)'",
    "target_keywords": ["langgraph tutorial", "build ai agent python", "multi agent workflow"],
    "competing_articles": "Most existing posts are abstract — Suman shows working orchestration code with a real result",
    "real_story_evidence": [
      {{ "source": "Hacker News (Show HN)", "title": "exact title from list", "url": "exact URL from list", "what_to_cite": "1 line on what number/quote/fact to reference in the article" }}
    ]
  }},
  {{...}},
  {{...}}
]

PICK topics Suman can write from personal experience (frontend dev, automation tinkerer, builds in Python + JS).
NO think-pieces, NO opinion articles, NO listicles longer than 7 items, NO news summaries.""", max_tokens=2500)

    try:
        vdata = extract_json(virality_raw, want=list)
        vdata = [v for v in vdata if isinstance(v, dict)][:3]
        if len(vdata) < 1: raise ValueError("empty list")
        print(f"[research] Scored {len(vdata)} topics")
        for v in vdata:
            print(f"  [{v.get('virality_score','?')}] {str(v.get('topic',''))[:60]}")
    except Exception as e:
        print(f"[research] Virality parse failed: {e} — using fallback")
        vdata = [
            {"topic": "Vibe coding a small SaaS in one weekend", "category": "B",
             "category_name": "Vibe Coding / AI-Assisted Workflow",
             "virality_score": 78, "developer_pain": "medium", "freshness": "fresh",
             "suman_angle": "Vibe coding a $19 SaaS in 11 hours — full prompts, full code, full Stripe screenshot",
             "target_keywords": ["vibe coding tutorial", "build saas with cursor", "ai assisted coding"],
             "money_angle": "Real Gumroad/Stripe revenue from a one-weekend build",
             "story_angle": "Closed the laptop Friday at 9pm with an idea, opened it Sunday with a paying customer",
             "analysis": "Vibe coding is the dominant 2026 dev meme. Real numbers + working code beats every theoretical post.",
             "competing_articles": "Most posts show the workflow but skip the money / honest failures — Suman shows both."},
            {"topic": "Building a research AI agent in 80 lines", "category": "C",
             "category_name": "AI Agents & Multi-Agent Workflows",
             "virality_score": 76, "developer_pain": "high", "freshness": "breaking",
             "suman_angle": "I replaced my morning news scroll with a 4-agent pipeline (full code)",
             "target_keywords": ["ai agent tutorial", "langgraph python", "multi agent workflow"],
             "money_angle": "", "story_angle": "Tired of the morning doom-scroll, built a personal news agent over chai",
             "analysis": "Agent-building tutorials have huge search demand and most are abstract. Concrete code wins.",
             "competing_articles": "Existing posts are diagrams without working orchestration."},
            {"topic": "GitHub Actions silent failures", "category": "F",
             "category_name": "Debugging / Fix With Code",
             "virality_score": 70, "developer_pain": "high", "freshness": "established",
             "suman_angle": "Why my GitHub Action failed with zero error message — the 3-hour root cause",
             "target_keywords": ["github actions not working", "github actions debug", "github actions silent fail"],
             "money_angle": "", "story_angle": "Pipeline went green, repo did nothing — chased it for three hours",
             "analysis": "Persistent pain on Stack Overflow weekly. Existing posts are outdated. Fresh root-cause wins.",
             "competing_articles": "Existing articles are 2023/2024 — runner image and syntax both moved on."},
        ]

    print("[research] Pass B: Crafting titles...")
    topics_block = "\n\n".join([
        f"TOPIC {i+1} (virality score: {v.get('virality_score','?')}/100):\n"
        f"  Raw topic: {v.get('topic','')}\n"
        f"  Suman's angle: {v.get('suman_angle','')}\n"
        f"  Primary keywords: {', '.join(v.get('target_keywords',[])[:3]) if isinstance(v.get('target_keywords'), list) else ''}\n"
        f"  Pain level: {v.get('developer_pain','medium')} | Freshness: {v.get('freshness','fresh')}\n"
        f"  Why viral: {v.get('virality_reasoning','')}"
        for i, v in enumerate(vdata)
    ])

    title_raw = ask_ai(f"""You are a headline writer for CoderFact — a coding blog by Suman, a frontend dev from Kolkata.
Convert these 3 scored topics into PERFECT Medium article titles.

{topics_block}

TITLE FORMULA RULES (Medium virality-tested):
  ✓ "How I Fixed [Specific Error] in [Tool] — Here's the Exact Code"
  ✓ "Stop [Painful Task] Manually — This [Language] Script Does It in [Time]"
  ✓ "[N] [Tool] Mistakes That Wasted My [X Hours] (And the Fixes)"
  ✓ "I Built [Thing] Using [Tool] in [Time] — Full Walkthrough With Code"
  ✓ "Why [Common Approach] Breaks [Tool] (And What to Do Instead)"
  ✓ "The [Specific Fix] That Cut My [Metric] From [X] to [Y]"

RULES:
- Primary keyword must appear in FIRST 4 WORDS of title
- Name the specific tool OR language OR error — no vague titles
- Under 80 characters
- First-person ("I", "My") where natural
- Each title must be a DIFFERENT topic/angle
- BANNED: "game-changer", "revolutionize", "unlock", "master", "the future of"
- BANNED FORMATS: "My Journey With X", "Thoughts on Y", "X Changed Everything"

Reply ONLY in this exact format, nothing else:
1. [Title]
2. [Title]
3. [Title]""")

    titles = []
    for line in title_raw.strip().splitlines():
        s = line.strip()
        if s[:2] in ("1.", "2.", "3."):
            titles.append(s.split(". ", 1)[1].strip().strip('"'))
    titles = titles[:3]

    if len(titles) < 3:
        titles = [v.get("suman_angle", v.get("topic", f"Topic {i+1}")) for i, v in enumerate(vdata)]

    # Novelty is checked against the whole archive, not the last 30 titles.
    for t in titles:
        is_new, closest, sim = rx.novelty(t, threshold=0.55)
        if not is_new:
            print(f"[research] NEAR-DUPLICATE ({sim}) of past title: {closest[:70]}")
    try:
        rx.library_append({
            "date": today,
            "titles": titles,
            "clusters": [c.as_dict() for c in clusters[:20]],
            "health": [f"{h.name}:{h.status}" for h in health],
        })
    except Exception as e:
        print(f"[research] library append failed (non-fatal): {e}")

    updated_history = (title_history + titles)[-30:]
    save_state({
        **state,
        "topics":          titles,
        "date":            today,
        "title_history":   updated_history,
        "virality_data":   vdata,
        "success_stories": success_stories,
    })
    print(f"[research] Final titles: {titles}")

    tg_lines = [f"🔥 *CoderFact — Daily Brief* | _{today}_\n"]
    for i, (title, v) in enumerate(zip(titles, vdata), 1):
        score    = v.get("virality_score", "?")
        pain     = v.get("developer_pain", "")
        fresh    = v.get("freshness", "")
        category = v.get("category_name") or v.get("category", "")
        analysis = (v.get("analysis") or v.get("virality_reasoning") or "").strip()
        money    = (v.get("money_angle") or "").strip()
        pe = "🔥" if pain == "high" else "⚡" if pain == "medium" else "💡"
        fe = "🆕" if fresh == "breaking" else "✨" if fresh == "fresh" else "📌"
        block = f"{i}. *{title}*\n   {pe} {pain} pain | {fe} {fresh} | 📊 {score}/100"
        if category:
            block += f"\n   🗂 _{category}_"
        if analysis:
            block += f"\n   💬 _{analysis[:240]}_"
        if money:
            block += f"\n   💰 _{money[:160]}_"
        tg_lines.append(block)

    tg_lines.append(
        "\n*Reply options:*\n"
        "• `1` `2` `3` — draft one  |  `1 2` `2 3` `1 3` — draft two  |  `1 2 3` — all three\n"
        "• `0` — skip today\n"
        "• *Type any topic* — I'll draft your own idea instead\n"
        "  _e.g._ `How to use Ollama with Python locally`\n"
        "• Prefix with `edu:` for short-form (hooks + tips + steps)\n"
        "  _e.g._ `edu: building your first AI agent`"
    )
    send_tg("\n".join(tg_lines))


def draft_single(title: str, idx: int, total: int):
    progress = f"({idx}/{total}) " if total > 1 else ""

    def tg_step(msg):
        send_tg(f"{progress}{msg}")

    def tg_err(step, e):
        import traceback
        tb = traceback.format_exc()[-600:]
        send_tg(f"❌ {progress}*{step} failed*\n`{str(e)[:300]}`\n\nFull trace in GitHub Actions logs.")
        print(f"[draft_single] {step} error:\n{tb}")

    tg_step(f"⏳ Drafting *`{title}`*...")

    # Pull real success stories from state — used by article prompt for evidence-backed citations.
    _state_for_stories  = load_state()
    _all_stories        = _state_for_stories.get("success_stories", []) or []
    _virality_data      = _state_for_stories.get("virality_data", []) or []
    _per_topic_evidence = []
    for v in _virality_data:
        if isinstance(v, dict) and (v.get("suman_angle") == title or v.get("topic") == title):
            ev = v.get("real_story_evidence", [])
            if isinstance(ev, list):
                _per_topic_evidence = [e for e in ev if isinstance(e, dict) and e.get("url")]
            break
    _kw_terms = [w.lower() for w in re.findall(r'[A-Za-z][A-Za-z0-9]+', title) if len(w) > 3][:6]
    def _story_relevance(s):
        t = (s.get("title","") + " " + s.get("snippet","")).lower()
        return sum(1 for k in _kw_terms if k in t)
    _ranked = sorted(_all_stories, key=_story_relevance, reverse=True)
    _relevant_stories = [s for s in _ranked if _story_relevance(s) > 0][:5] or _ranked[:3]

    real_stories_block = ""
    if _per_topic_evidence:
        real_stories_block = "\n\nREAL STORIES TO CITE (the researcher already matched these to this topic — cite ALL of them):\n"
        for e in _per_topic_evidence:
            real_stories_block += f"  • {e.get('source','')} — {e.get('title','')}\n    URL: {e.get('url','')}\n    What to cite: {e.get('what_to_cite','')}\n"
    if _relevant_stories:
        real_stories_block += "\nADDITIONAL REAL STORIES AVAILABLE (use 1-2 if they fit naturally):\n"
        for s in _relevant_stories[:5]:
            real_stories_block += f"  • [{s.get('source','')}] {s.get('title','')[:110]}\n    URL: {s.get('url','')}  |  Signal: {s.get('signal','')}\n"
    print(f"[draft] Real-story citations available: {len(_per_topic_evidence)} matched + {len(_relevant_stories)} relevant")

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

    try:
        complexity_raw = ask_ai(f'''Classify this blog post title by complexity: "{title}"
Reply with ONLY a JSON object:
{{"complexity": "simple"|"moderate"|"deep", "reason": "one sentence", "target_words": <800-1400>}}''')
        c = extract_json(complexity_raw, want=dict)
        target_words = min(max(int(c.get("target_words", 1100)), 800), 1400)
        complexity   = _s(c.get("complexity"), "moderate")
        reason       = _s(c.get("reason"), "")
    except Exception as e:
        target_words, complexity, reason = 1100, "moderate", ""
        print(f"[draft] Complexity fallback: {e}")
    print(f"[draft] Complexity: {complexity} -> {target_words} words")

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
        kw_data = extract_json(kw_research_raw, want=dict)
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

    tg_step("📋 Pass 1/3: Building outline...")

    try:
        outline_raw = ask_ai(f"""You are helping {AUTHOR_NAME} — {AUTHOR_CONTEXT} — plan a blog post.

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
  "article_format": "Classify as exactly one of: Tech News, Repo Review, System Automation, Code Tutorial",
  "hook_scene": "2-3 sentences. Specific moment the problem hit the author.",
  "pain_point": "Exact frustration with tool name and error.",
  "failed_attempts": "1-2 things tried that failed.",
  "solution_name": "Exact tool or library used.",
  "real_metric": "Before/after number e.g. 47 min to 3 min.",
  "surprise_finding": "Unexpected discovery only a builder would know.",
  "reader_benefit": "What reader can do after reading.",
  "h2_headings": ["5-6 NARRATIVE headings that tell the story in order: the incident, why the obvious approach fails, the actual fix, the gotcha nobody warns you about, the refinement, the results. Short noun phrases, NOT questions. e.g. 'Why the linear scan falls over', 'The memory gotcha', 'Caching the warm start'"],
  "tldr": {{"problem":"one sentence","solution":"one sentence","result":"one sentence"}},
  "engagement_cta": "Specific question for readers.",
  "thumbnail_prompt": "Cinematic Midjourney/Flux prompt for a dark-theme tech thumbnail. Be specific about the technology shown.",
  "interactive_widget_prompt": "Design a UI simulator. Objective: [1 sentence goal]. Data State: [realistic technical data]. Inputs: [specific sliders/buttons]. Behavior: [what changes visually when inputs change].",
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

NOTE: snippet_plan and diagram_plan contain DESCRIPTIONS only — no actual code.
Return ONLY the JSON object.""")

        outline = extract_json(outline_raw)
        if not isinstance(outline, dict): raise ValueError("outline is not a dict")
        print(f"[draft] Outline OK — snippets:{len(outline.get('snippet_plan',[]))}, diagrams:{len(outline.get('diagram_plan',[]))}")

    except Exception as e:
        tg_err("Pass 1 outline", e)
        outline = {}

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
                "content":  _s(s.get("content"),   ""),
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
                "content": _s(d.get("content"), ""),
            })
        return result

    snippets = _plan_to_snippets(outline)
    diagrams = _plan_to_diagrams(outline)

    article_format   = _s(outline.get("article_format"),   "Code Tutorial")
    hook_scene       = _s(outline.get("hook_scene"),       "It was 11pm when the error hit again.")
    pain_point       = _s(outline.get("pain_point"),       "The manual process was killing my time.")
    failed_attempts  = _s(outline.get("failed_attempts"),  "The obvious fixes didn't work.")
    solution_name    = _s(outline.get("solution_name"),    "a custom script")
    real_metric      = _s(outline.get("real_metric"),      "")
    if not real_metric or "47" in real_metric or "45 min" in real_metric or "minutes to" in real_metric.lower():
        # Don't lift the placeholder — make the article prompt invent a topic-fitting number
        real_metric = f"a measurable improvement specific to {primary_kw or solution_name}"
    surprise_finding = _s(outline.get("surprise_finding"), "The hardest part wasn't the code.")
    reader_benefit   = _s(outline.get("reader_benefit"),   "build this in under an hour")
    meta_desc        = _s(outline.get("meta_description"), f"How to fix {title.lower()} with working code.")
    engagement_cta   = _s(outline.get("engagement_cta"),   "What would you do differently? Drop it in the comments.")
    thumbnail_prompt = _s(outline.get("thumbnail_prompt"), f"{solution_name} dark terminal cinematic 4k professional")
    widget_prompt    = _s(outline.get("interactive_widget_prompt"), "An interactive code simulator for this topic")
    seo_keywords     = _list(outline.get("seo_keywords"),  ["python","automation","tutorial","coding","developer"])

    # Narrative arc, not People-Also-Ask questions. A stack of question headings
    # ("How do I build X in Python using a trie?") is the tell of SEO-farm
    # content: Medium's curation downranks it and readers bounce. The keyword
    # goes in the prose; the heading moves the story.
    h2_default = [
        "The incident",
        "Why the obvious fix falls over",
        "What actually worked",
        "The gotcha nobody warns you about",
        "Results, and what I would do differently",
    ]
    h2_headings = _list(outline.get("h2_headings"), h2_default) or h2_default

    # Reject question-form headings even if the model ignored the instruction.
    _questiony = [h for h in h2_headings
                  if h.strip().endswith("?")
                  or _QUESTION_HEAD_RE.match(h.strip())]
    if len(_questiony) > 1:
        print(f"[draft] {len(_questiony)} question-form headings from the outline — "
              f"using the narrative default instead")
        h2_headings = h2_default

    tldr_raw = outline.get("tldr", {})
    tldr = _dict(tldr_raw, ["problem","solution","result"], "")
    if not any(tldr.values()):
        tldr = {"problem": pain_point, "solution": solution_name, "result": real_metric}

    devto_tags_raw = outline.get("devto_tags", [])
    raw_tag_list   = _list(devto_tags_raw, ["python","tutorial","webdev","programming"])
    def clean_tag(t):
        return str(t).lower().strip().strip('"').strip("'").replace("-","").replace(" ","")
    devto_tags = [clean_tag(t) for t in raw_tag_list if t][:4] or ["python","tutorial","webdev","programming"]

    snippets_block = ""
    if snippets:
        snippets_block = "\nCODE SNIPPET PLAN — write actual code for each in the section indicated:\n"
        for i, s in enumerate(snippets, 1):
            snippets_block += (
                f"\nSnippet {i} [{s['style'].upper()}] → Section: `{s['section']}`\n"
                f"Language: {s['language']} | Purpose: {s['purpose']}\n"
                f"Write at least 8 lines of real, working, well-commented code.\n"
            )

    diagrams_block = ""
    if diagrams:
        diagrams_block = "\nDIAGRAM PLAN — create actual diagram content for each in the section indicated:\n"
        for i, d in enumerate(diagrams, 1):
            dtype = d["type"]
            diagrams_block += (
                f"\nDiagram {i} [{dtype.upper()}] → Section: `{d['section']}`\n"
                f"Purpose: {d['purpose']}\n"
            )
            if dtype == "mermaid":
                diagrams_block += "Use proper Mermaid syntax (graph TD, sequenceDiagram, etc.)\n"
            else:
                diagrams_block += "Use ASCII box-drawing characters for architecture/flow.\n"


    # The author's own sourced material. A writer with a real number to hand
    # does not need to invent one — this is the cause-side fix that judge.py
    # and claims.py check from the proof side.
    _brain = brain.load()
    brain_block = _brain.for_topic(f"{title} {primary_kw} {solution_name}")
    if _brain:
        print(f"[brain] {_brain.summary()}")

    tg_step("✍️ Pass 2/3: Writing article...")
    try:
        article = ask_ai(f"""You are ghostwriting for {AUTHOR_NAME}: {AUTHOR_CONTEXT}. Vibe: {AUTHOR_VIBE}.

Today is {datetime.now().strftime('%B %Y')}. Write the post in past tense — something that already happened to {AUTHOR_NAME.split()[0]} this week.

▌READ THIS FIRST — HOW THIS PROMPT WORKS
Examples below show *patterns*, not text to copy. If a phrase from this prompt appears in your output, you have failed.
Do not echo my instructions back. Do not write meta-commentary. Start with the story.

▌AUDIENCE
A working developer hits Google with a frustrated query at 11pm. They land on this article. They have 90 seconds before they bounce. Earn the bounce-back by being specific in the first 50 words.

▌NON-NEGOTIABLE FACTS — these come from the brief, do NOT change them
Title:           {seo_title}
Primary keyword: {primary_kw}   ← must appear in first paragraph + 2 H2s + last paragraph
Pain point:      {pain_point}
Solution:        {solution_name}
The metric:      {real_metric}  ← if this looks like a placeholder, invent a *different* believable number that fits the topic. Do NOT use my example numbers literally.
Surprise:        {surprise_finding}
Article format:  {article_format}

▌FORMAT ADAPTATION ({article_format.upper()})
- Tech News:         Lead with the architectural shift. Include an Old vs New comparison table.
- Repo Review:       Teardown the codebase. Include a Pros/Cons matrix.
- System Automation: Show the full pipeline. Include a before/after performance table.
- Code Tutorial:     Step-by-step with working code. Include a benchmark table.
NEVER wrap markdown tables in backticks — render them as raw markdown.

▌VOICE — three rules, applied throughout
1. Every paragraph passes the "would I say this out loud?" test. If it sounds like a LinkedIn post, rewrite it.
2. One specific noun per paragraph: a tool version, a file path, a command flag, a port number, an exact timestamp, a CLI output line. No vague nouns ("the tool", "my setup", "various approaches").
3. Vary opener length. Don't start three paragraphs in a row with "I". Don't start two in a row with the same word.

▌SEO REQUIREMENTS
Primary keyword "{primary_kw}" appears in: first paragraph, ≥2 H2s, last paragraph.
Secondary keywords (use 2-3 times each, naturally):
  → {_ks(secondary_kws, 'use related terms naturally')}
Long-tail keywords (work into H2 headings + paragraph text):
  → {_ks(longtail_kws, 'use specific question phrases')}
LSI keywords (Google expects these — use naturally):
  → {_ks(lsi_kws, 'use semantically related terms')}
Competitor angle (what makes this DIFFERENT):
  → {competitor_angle}

{brain_block if brain_block else ''}

▌STRUCTURE (markdown, no HTML)
1. HOOK — 2 sentences max. A specific moment. No headline, no "Introduction".
   Hint, not template: a real timestamp + a real error string + what was at stake.
   The primary keyword "{primary_kw}" appears in this opening, naturally.

2. TL;DR (immediately after hook, before any H2):
   **TL;DR**
   - **Problem:** {tldr.get('problem', pain_point)}
   - **Fix:** {tldr.get('solution', solution_name)}
   - **Result:** {tldr.get('result', real_metric)}

3. H2 SECTIONS — use these exact headings, in order:
{chr(10).join(f'   ## {h}' for h in h2_headings)}

   These are NARRATIVE headings and they must stay that way. Do NOT rewrite them
   as questions. A stack of "How do I X in Python using Y?" headings is the
   signature of SEO-farm content: Medium's curation system downranks it and human
   readers bounce. The heading's job is to move the story forward, not to match a
   search query. The keyword belongs in the prose underneath it.
   Never write "The Answer is:", "In short:", "TL;DR:" or a bolded restatement
   directly under a heading.

4. Each H2 contains ALL THREE of: prose (2-4 paragraphs), one concrete artifact (code OR diagram OR table OR chart), one specific named detail (version, error message, command).

5. CODE — when you write a code block:
   - Real imports with real package names + version comment: `import requests  # 2.31.0`
   - At least one comment that says *why*, not *what*: `# retry — flaky on cold start`
   - At least one realistic value: a real-looking API key prefix (sk-proj-...), a real port (:8787), an actual error message
   - Show CLI output where relevant, fenced as a separate block

6. DIAGRAMS — only mermaid or pipe-tables. Mermaid blocks must use `graph TD` or `sequenceDiagram` with at least 5 nodes/messages.

7. RESULTS section — required pipe-table comparing 2-3 real metrics before/after. No placeholder round numbers (avoid 100, 1000, 10x). Use {real_metric} as one row, invent two more believable ones that fit the topic — response time, lines of code, error rate, memory, API calls — pick what makes sense.

8. CLOSING — 3 lines, that's it:
   - One honest line about what you'd do differently
   - This blockquote on its own line: > {engagement_cta}
   - One CTA line, written fresh — do NOT say "the clap button is right there"

9. INTERACTIVE WIDGET — add this exact block at the very end:
{TICK3}json?chameleon
{{ "component": "LlmGeneratedComponent", "props": {{ "height": "650px", "prompt": "{widget_prompt}" }} }}
{TICK3}

10. After the body, on separate lines:
    TAGS: {json.dumps(kw_tags if kw_tags else devto_tags)}
    META: {seo_meta if seo_meta else meta_desc}

▌HARD BANS (exact strings — these will be checked by a regex linter)
"I spent three hours on this", "THREE hours", "Sound familiar", "Yeah. Me too",
"It was 1am", "the clap button is right there", "tap that clap",
"In conclusion", "In summary", "To summarize", "It is worth noting",
"Furthermore", "Moreover", "Additionally", "delve", "leverage", "robust",
"seamless", "unleash", "empower", "groundbreaking", "revolutionize",
"game-changer", "synergy", "cutting-edge", "supercharge", "paradigm",
"In this article we will", "Let's dive in", "Buckle up", "Without further ado".

▌HARD BANS (patterns)
- Same sentence structure two paragraphs in a row
- Two short fragments back-to-back (e.g. "Yeah. Me too.")
- Em-dash + parenthetical aside in the same sentence
- Any "rhetorical question to reader?" pattern more than twice in the article
- Any number that ends in two zeros and is not a real benchmark (no "100x faster", no "1000 users")

▌LENGTH
~{target_words} words. If you need to cut, cut adjectives and the second sentence of every paragraph that has three sentences. Never cut code or diagrams.

▌BENCHMARK NUMBERS NEED METHODOLOGY
Any throughput, latency, or memory figure gets a methodology clause in the same
paragraph — machine, dataset size, and how it was measured. Not a footnote, not
"benchmarks show". Write it the way you would defend it in a comment thread,
because that is exactly where it will be challenged:
  BAD:  "It handles 22,400 req/s."
  GOOD: "It held 22,400 req/s on a 4-core M2 with wrk, 100 connections, 30s, all
         keys warm — single process, no network hop, so treat it as a ceiling."
If you cannot state the machine and the method, do not state the number. Say
"roughly an order of magnitude faster" and move on. A hedged number survives
fact-checking; a precise one you cannot defend costs the author the reader.

▌ANTI-FABRICATION
A. NEVER invent specific dollar amounts, MRR, user counts, follower counts, or company revenue without a real source.
B. The ONLY specific numbers you may invent are technical metrics: timing, error counts, API response times, lines of code, memory usage.
C. If a section needs a real example, cite from the REAL STORIES block below — title, source, URL.
D. If no real story fits, write in first-person voice without specific external numbers. Vague is OK ("a founder I follow"). Fabricated names + dollars is not.
E. Never say "according to a study" or "research shows" without a real URL.

▌SOURCES — when you cite, use one of these (no inventions):
{real_stories_block if real_stories_block else '(No external sources available — write entirely from first-person experience. Do not cite anyone.)'}

▌SNIPPET PLAN (write actual code for each):
{snippets_block}

▌DIAGRAM PLAN (write actual diagram for each):
{diagrams_block}

Output: clean Markdown only. Start with the hook scene. No preamble.
""", max_tokens=int(target_words * 2.4) + 600)
        if not article or len(article) < 200:
            raise ValueError(f"Article too short ({len(article)} chars)")

        # A flat 200-char floor let a 70-word stub through on a 900-word target.
        # Measure against what was actually asked for, and treat a draft ending
        # mid-sentence as truncation regardless of length — both are the
        # signature of an output-token budget that ran out.
        _words = humanizer.prose_word_count(article)
        if _words < target_words * ARTICLE_MIN_RATIO:
            raise ValueError(
                f"Article truncated: {_words} words vs {target_words} target "
                f"(floor {ARTICLE_MIN_RATIO:.0%}). Usually the model's output-token "
                f"budget ran out — check the provider log above for finishReason.")
        if not re.search(r'[.!?)\]`"’]\s*$', article.strip()):
            raise ValueError(
                f"Article ends mid-sentence ({_words} words): "
                f"...{article.strip()[-70:]!r}")
        print(f"[draft] Article generated: {len(article)} chars, {_words} prose words")
    except Exception as e:
        tg_err("Pass 2 article writing", e)
        raise

    tg_step("🧬 Pass 2.5/3: Humanizing (rewrite -> lint -> repair loop)...")
    voice_ctx = f"{AUTHOR_NAME} — {AUTHOR_CONTEXT}. Vibe: {AUTHOR_VIBE}"
    article, human_report = humanize_pass(article, voice_ctx, target_words)

    human_score, human_grade = 0, "unknown"
    if human_report:
        human_score, human_grade = human_report.after.score, human_report.after.grade()
        print(f"[humanize] {human_report.summary()}")
        for f in human_report.remaining[:8]:
            print(f"  - [{f.severity}] {f.name}: {f.excerpt[:70]}")
        if human_grade in ("needs-work", "reject"):
            top = ", ".join(sorted({f.name for f in human_report.remaining
                                    if f.severity == "high"})[:5]) or "none"
            send_tg(f"⚠️ AI-tell score *{human_score}/100* ({human_grade}) — "
                    f"review before publishing.\nTop tells: _{top}_")

    # ── Pass 2.75: editorial review ─────────────────────────────────────────
    # The humanizer catches mechanical tells. It cannot tell that the hook is
    # generic or that a revenue figure was invented, so a reviewer scores the
    # draft against a rubric grounded in facts measured here, then the findings
    # go back to the model. A revision is kept only if it scores higher.
    tg_step("⚖️ Pass 2.75/3: Editorial review (judge -> revise loop)...")
    judge_ctx = {
        "title": seo_title,
        "article_format": article_format,
        "primary_keyword": primary_kw,
        "target_words": target_words,
        "allowed_urls": [e.get("url") for e in _per_topic_evidence if e.get("url")]
                        + [s.get("url") for s in _relevant_stories if s.get("url")],
        "evidence_text": [f"{e.get('source', '')} — {e.get('title', '')} ({e.get('url', '')})"
                          for e in _per_topic_evidence]
                         + [f"{s.get('source', '')} — {s.get('title', '')} ({s.get('url', '')})"
                            for s in _relevant_stories[:5]],
    }
    verdicts = []
    try:
        article, verdicts = judge.review_loop(article, judge_ctx, ask_ai)
    except Exception as e:
        print(f"[judge] review loop failed (non-fatal): {e}")

    if verdicts:
        final_v = verdicts[-1]
        print(f"[judge] final — {final_v.summary()}")
        if final_v.blocking or final_v.verdict == "reject":
            issues = "\n".join(f"• {b[:150]}" for b in final_v.blocking[:3]) \
                     or "• see the run log for the reviewer's findings"
            send_tg(f"🛑 *Editorial review: {final_v.verdict}* "
                    f"({final_v.weighted:.0f}/100)\n"
                    f"Publishing anyway as a Dev.to *draft* — do not publish "
                    f"until these are fixed:\n{issues}")
        elif final_v.weighted < judge.TARGET_SCORE:
            weak = ", ".join(f"{k} {s}/10" for k, s in
                             sorted(final_v.scores.items(), key=lambda kv: kv[1])[:3])
            send_tg(f"⚠️ *Editorial score {final_v.weighted:.0f}/100* — weakest: _{weak}_")

    # ── Claims map: every checkable figure gets a receipt, or it is listed ──
    claims_map = None
    try:
        claims_map = claims.build_map(
            article, title=seo_title, slug=draft_slug(seo_title), brain=_brain,
            evidence_urls=judge_ctx["allowed_urls"],
            evidence_text=judge_ctx["evidence_text"])
        print(f"[claims] {claims_map.summary()}")
        for c in claims_map.unsourced[:8]:
            print(f"  UNSOURCED line {c.line}: {c.figure or c.text[:60]}")
    except Exception as e:
        print(f"[claims] map failed (non-fatal): {e}")

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
            )
            tags = [sanitize_tag(t) for t in extract_json(raw, want=list)][:4]
        except Exception:
            tags = ["python", "programming", "automation", "tutorial"]

    import re as _re

    def slugify(text, words=16):
        text = _re.sub(r'[^\w\s]', '', str(text).lower())
        return "-".join(text.split()[:words])

    def pollinations(prompt, w=1280, h=720, seed=None):
        seed_part = f"&seed={seed}" if seed else ""
        return (
            f"https://image.pollinations.ai/prompt/{slugify(prompt)}?"
            f"width={w}&height={h}&model=flux&nologo=true&enhance=true{seed_part}"
        )

    tg_step("🎨 Pass 3/3: Planning visuals & publishing...")

    article_tech  = _s(solution_name, title)
    article_kw    = primary_kw
    body_headings = [l[3:].strip() for l in body.splitlines() if l.startswith("## ")]
    has_mermaid   = "```mermaid" in body
    has_table     = "| ---" in body or "|---" in body

    try:
        visual_plan_raw = ask_ai(f"""You are designing visuals for a Medium-quality technical post. Cap is 6 visuals total. Quality > quantity. A bad meme costs more reader trust than no meme.

ARTICLE TITLE: "{seo_title}"
PRIMARY TECH: "{article_tech}"
PRIMARY KW:   "{article_kw}"

ARTICLE H2 HEADINGS (use these exact strings in 'after'):
{chr(10).join(f'  - "{h}"' for h in body_headings)}

ARTICLE BODY (first 4000 chars):
{body[:4000]}

▌RULES OF SELECTION
You will pick a maximum of 6 visuals. Score each candidate against the body. Skip visuals that don't earn their slot.

▌MANDATORY: 1 hero image (after = "")
The hero image is a banner. Pollinations prompt must contain BOTH "{article_tech}" AND a specific noun from the article (an error name, a tool version, a config file, a CLI command). Generic = wasted slot.

▌STRONGLY RECOMMENDED (pick 2-3):
- mermaid_flowchart — only if article has a >=4-step process. Diagram MUST have 5+ nodes including at least one decision diamond ({{ }}).
- chart — only if article cites >=3 numerical data points. Use real numbers from the body, not placeholders. Format as Chart.js v4 with dark colors (#22c55e for good, #ef4444 for bad, #3b82f6 for neutral).
- comparison_table — only if there's a real before/after or A vs B in the body.

▌OPTIONAL (pick at most 2):
- ascii_diagram — for file structures or component layout. Must use box-drawing characters.
- callout — only for a non-obvious gotcha mentioned in the body. Format: > ⚠️ **Gotcha:** [specific thing]
- quote_card — only for an existing sharp line in the body. Don't invent quotes.

▌FORBIDDEN UNLESS THE BODY DEMANDS IT:
- meme — only if the body has a clear shared-pain moment. Default = no meme. A weak meme tanks the article's credibility.
- infographic — Pollinations renders infographics badly with text. Skip unless absolutely needed.
- mermaid_sequence — only if article has actual client/server message flow with >=4 messages.

▌PROMPT QUALITY BAR (for image / infographic / meme types)
Bad:  "python automation dark professional"
Good: "VS Code terminal showing pytest output green dots, Python 3.11 logo bottom right, dark background, code visible behind, cinematic 4k"

The Pollinations prompt MUST name:
1. The specific tool (with version if reasonable)
2. What's on screen (terminal output? UI? error?)
3. The visual frame (split-panel? single-screen? close-up?)
4. The mood (dark cinematic / clean editorial / glitchy)

▌CHART CONFIG QUALITY BAR
Bad:  "data": [100, 50, 25]   ← round numbers = obvious placeholder
Good: "data": [847, 312, 91]  ← if these are pulled from the body

If you can't find real numbers in the body, do NOT include a chart. Return nothing for that slot.

▌PLACEMENT
"after" must match an H2 string from the list above EXACTLY (case-sensitive). If unsure, leave "after" empty (places at top).

Return ONLY a JSON array with 3-6 objects. No markdown fences. Schema:

[
  {{
    "type": "image",
    "after": "",
    "prompt": "specific multi-noun prompt per quality bar above mentioning {article_tech}",
    "style": "dark-terminal-code",
    "size": "hero",
    "alt": "descriptive alt under 80 chars"
  }},
  {{
    "type": "mermaid_flowchart",
    "after": "exact H2 string",
    "content": "graph TD\\n  A[Specific Step Name] --> B{{Decision: condition}}\\n  B -->|yes| C[Outcome]\\n  B -->|no| D[Other outcome]\\n  C --> E[Final state]",
    "caption": "one-line caption naming what the flow shows"
  }},
  {{
    "type": "chart",
    "after": "exact H2 string",
    "chart_config": {{
      "type": "bar",
      "data": {{
        "labels": ["label from body", "label from body"],
        "datasets": [{{
          "label": "metric name with unit",
          "data": [123, 456],
          "backgroundColor": ["#ef4444", "#22c55e"]
        }}]
      }},
      "options": {{
        "plugins": {{ "legend": {{ "labels": {{ "color": "#fff" }} }} }},
        "scales": {{
          "x": {{ "ticks": {{ "color": "#fff" }} }},
          "y": {{ "ticks": {{ "color": "#fff" }} }}
        }}
      }}
    }},
    "caption": "caption with the actual delta — e.g. '4.2x faster after caching'"
  }},
  {{
    "type": "comparison_table",
    "after": "exact H2 string",
    "content": "| Approach | Time | Complexity |\\n|----------|------|------------|\\n| Before | real number | High |\\n| After | real number | Low |",
    "caption": "short caption"
  }},
  {{
    "type": "callout",
    "after": "exact H2 string",
    "content": "> ⚠️ **Gotcha:** specific non-obvious thing from the article body",
    "caption": ""
  }}
]""", max_tokens=3500)

        visual_plan = extract_json(visual_plan_raw, want=list)

        visual_plan = [
            v for v in visual_plan if isinstance(v, dict) and (
                v.get("type") != "image" or len(str(v.get("prompt", ""))) > 40
            )
        ]
        print(f"[images] AI planned {len(visual_plan)} visuals")
    except Exception as e:
        print(f"[images] Visual plan failed: {e} — minimal fallback")
        visual_plan = [{
            "type": "image", "after": "",
            "prompt": f"{article_tech} {article_kw} dark terminal professional developer cinematic 4k",
            "style": "dark-terminal-code", "size": "hero", "alt": seo_title,
        }]


    STYLE_PROMPTS = {
        "dark-terminal-code":       "VS Code dark theme terminal code editor professional screenshot realistic",
        "architecture-diagram":     "clean technical architecture diagram white background boxes arrows labels minimal professional",
        "diagram-flowchart":        "clean flowchart diagram dark background neon lines decision boxes professional technical",
        "before-after-comparison":  "split panel before after comparison dark terminal output green text professional",
        "benchmark-graph-results":  "performance benchmark bar chart dark background green improvement metrics professional data viz",
        "concept-illustration":     "clean technical concept illustration flat design dark background labeled components",
        "frustrated-dev-at-screen": "cinematic developer frustrated at laptop multiple error screens dark office 4k realistic",
        "tool-screenshot-ui":       "clean modern dark UI dashboard screenshot professional tool interface realistic",
        "infographic-flat":         "flat design infographic dark background numbered steps clear icons modern typography editorial",
        "meme-format":              "single frame programmer meme bold caption dark background expressive face cinematic lighting",
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
                "type":         t,
                "after":        _ts(item.get("after"),    ""),
                "prompt":       _ts(item.get("prompt"),   title),
                "style":        _ts(item.get("style"),    "dark-terminal-code"),
                "size":         _ts(item.get("size"),     "wide"),
                "alt":          _ts(item.get("alt"),      title),
                "language":     _ts(item.get("language"), "python"),
                "content":      _ts(item.get("content"),  ""),
                "caption":      _ts(item.get("caption"),  ""),
                "chart_config": item.get("chart_config")  if isinstance(item.get("chart_config"), dict) else None,
            }

        def render_item(item: dict) -> str:
            t       = item["type"]
            caption = f"\n*{item['caption']}*\n" if item['caption'] else "\n"

            if t == "image":
                style_kw = STYLE_PROMPTS.get(item["style"], "dark neon professional developer")
                w, h     = SIZE_MAP.get(item["size"], (900, 500))
                seed     = next_seed(abs(hash(item["after"])) % 1000 + 10)
                url      = pollinations(f"{item['prompt']} {style_kw}", w, h, seed)
                return f"\n![{item['alt']}]({url})\n"

            elif t == "infographic":
                style_kw = STYLE_PROMPTS["infographic-flat"]
                w, h     = SIZE_MAP.get(item["size"], (900, 600))
                seed     = next_seed(abs(hash(item["after"] + "infographic")) % 1000 + 100)
                url      = pollinations(f"{item['prompt']} {style_kw}", w, h, seed)
                cap      = f"\n*{item['caption']}*\n" if item['caption'] else "\n"
                return f"\n![{item['alt'] or 'Infographic'}]({url}){cap}"

            elif t == "meme":
                style_kw = STYLE_PROMPTS["meme-format"]
                w, h     = SIZE_MAP.get(item["size"], (700, 500))
                seed     = next_seed(abs(hash(item["after"] + "meme")) % 1000 + 200)
                url      = pollinations(f"{item['prompt']} {style_kw}", w, h, seed)
                return f"\n![{item['alt'] or 'Programmer meme'}]({url})\n"

            elif t == "chart":
                cfg = item.get("chart_config")
                if not isinstance(cfg, dict):
                    return ""
                w, h = SIZE_MAP.get(item["size"], (700, 400))
                url  = quickchart_url(cfg, w=w, h=h)
                if not url:
                    return ""
                return f"\n![{item['alt'] or item['caption'] or 'Chart'}]({url}){caption}"

            elif t == "quote_card":
                return render_quote_card(item["content"], item["caption"])

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

    try:
        enriched_body = build_enriched_body(body, visual_plan)
        print(f"[draft] Enriched body: {len(enriched_body)} chars")
    except Exception as e:
        tg_err("Pass 3 visual injection", e)
        enriched_body = body

    footer  = f"\n\n---\n*Written by {AUTHOR_NAME}. More tools at [CoderFact](https://coderfact.com). AI-assisted draft, reviewed and edited by me.*"

    # FIX 1 applied: convert_mermaid_for_medium now exists and works
    medium_body   = convert_mermaid_for_medium(enriched_body)
    devto_content = enriched_body + footer
    medium_content = medium_body + footer

    seo_block = (
        "---\n"
        f"VIRAL TITLE: {seo_title}\n"
        f"FORMAT: {article_format}\n"
        f"META DESCRIPTION: {meta or meta_desc}\n"
        f"TAGS: {', '.join(tags)}\n"
        f"THUMBNAIL PROMPT: {thumbnail_prompt}\n"
        "---\n"
        f"{_medium_checklist(medium_body)}"
        "---\n"
        "✂️ CUT EVERYTHING ABOVE THIS LINE BEFORE PUBLISHING TO MEDIUM ✂️\n\n"
    )
    github_content = seo_block + medium_content

    # ═══════════════════════════════════════════════════════════════════════════════
    # FIX 2 applied: Use new save_file_to_github() with better error handling
    # ═══════════════════════════════════════════════════════════════════════════════
    github_url = ""
    try:
        slug = draft_slug(seo_title)
        md_path = f"medium_drafts/{slug}.md"
        github_url = save_file_to_github(
            md_path,
            github_content,
            f"docs: new draft — {seo_title[:50]}"
        )
    except Exception as e:
        print(f"[draft] GitHub save failed (non-fatal): {e}")

    # The claims map ships beside the draft so the receipts are reviewable
    # alongside the prose, not buried in a run log.
    if claims_map is not None:
        try:
            save_file_to_github(f"medium_drafts/{draft_slug(seo_title)}.claims.md",
                                claims.render(claims_map),
                                f"docs: claims map — {seo_title[:50]}")
            if claims_map.unsourced:
                worst = "\n".join(f"• `{c.figure or c.text[:60]}` (line {c.line})"
                                  for c in claims_map.unsourced[:4])
                send_tg(f"🧾 *Claims map: {claims_map.coverage:.0%} sourced* "
                        f"({len(claims_map.unsourced)} without a receipt)\n{worst}")
        except Exception as e:
            print(f"[claims] save failed (non-fatal): {e}")

    # ═══════════════════════════════════════════════════════════════════════════════
    # FIX 3: Check DEVTO_KEY before attempting publish + better error reporting
    # ═══════════════════════════════════════════════════════════════════════════════
    print(f"[draft] Publishing to Dev.to — title='{seo_title}' DEVTO_KEY={'SET' if DEVTO_KEY else 'MISSING'}")

    if not DEVTO_KEY:
        tg_step("⚠️ DEVTO_API_KEY not set — skipping Dev.to publish. Draft saved to GitHub only.")
        if github_url:
            send_tg(f"✅ {progress}*Draft saved to GitHub only*\n\n📝 _{seo_title}_\n💾 [GitHub .md file]({github_url})")
    else:
        try:
            res = requests.post(
                "https://dev.to/api/articles",
                headers={"api-key": DEVTO_KEY, "Content-Type": "application/json"},
                json={"article": {
                    "title":          seo_title,
                    "body_markdown":  devto_content,
                    "published":      False,
                    "tags":           tags,
                    "canonical_url":  "https://coderfact.com",
                }},
                timeout=20,
            )
            print(f"[draft] Dev.to -> {res.status_code}: {res.text[:200]}")

            if res.status_code == 201:
                draft_url = res.json().get("url", "https://dev.to/dashboard")
                msg = (
                    f"✅ {progress}*Draft ready!*\n\n"
                    f"📝 _{seo_title}_\n"
                    f"📌 Format: {article_format}\n"
                    f"📏 ~{target_words} words _{complexity}_\n"
                    f"📊 _{real_metric}_\n"
                    f"🏷 {', '.join(tags)}\n"
                    f"🖼 Thumbnail: _{thumbnail_prompt[:80]}_\n\n"
                    f"🌐 [Open Dev.to Draft]({draft_url})\n"
                )
                if github_url:
                    msg += f"💾 [GitHub .md file]({github_url})"
                send_tg(msg)
            else:
                error_detail = res.text[:300]
                send_tg(f"❌ Dev.to error {res.status_code}:\n`{error_detail}`")
                # Try to save to GitHub even if Dev.to fails
                if not github_url:
                    try:
                        slug = draft_slug(seo_title)
                        github_url = save_file_to_github(
                            f"medium_drafts/{slug}.md",
                            github_content,
                            f"docs: new draft (devto-failed) — {seo_title[:50]}"
                        )
                        if github_url:
                            send_tg(f"💾 Draft saved to GitHub instead: [View file]({github_url})")
                    except Exception:
                        pass
        except Exception as e:
            tg_err("Dev.to publish", e)
            # Emergency GitHub save
            try:
                slug = draft_slug(seo_title)
                github_url = save_file_to_github(
                    f"medium_drafts/{slug}.md",
                    github_content,
                    f"docs: emergency save — {seo_title[:50]}"
                )
                if github_url:
                    send_tg(f"💾 Emergency save to GitHub: [View file]({github_url})")
            except Exception:
                pass
            raise

    # ── Pass 3.5: flywheel ──────────────────────────────────────────────────
    # What did this piece establish that the next one should start with?
    # Candidates land in brain/inbox.md; nothing is auto-promoted, because an
    # unreviewed "fact" would be laundered into every future article as verified.
    try:
        n = brain.seed_entry(article, seo_title, ask_ai,
                             evidence_text=judge_ctx["evidence_text"])
        if n:
            send_tg(f"🌱 {n} brain candidate(s) in `brain/inbox.md` — "
                    f"review and move the good ones into `brain/stories.md`.")
    except Exception as e:
        print(f"[brain] seeding failed (non-fatal): {e}")

    # ── Pass 4: promotion ───────────────────────────────────────────────────
    # Generated FROM the finished article, so the posts quote details that
    # actually exist in it. Never fatal — the article is already published.
    try:
        promo_pack_for(article=medium_content, title=seo_title,
                       article_url=github_url or "https://coderfact.com",
                       slug=draft_slug(seo_title), notify=True)
    except Exception as e:
        print(f"[promo] pack failed (non-fatal): {e}")
        send_tg(f"⚠️ Promo pack failed: `{str(e)[:150]}`\nArticle is fine.")


def promo_pack_for(article: str, title: str, article_url: str = "",
                   slug: str = "", notify: bool = False):
    """Build + save the LinkedIn/X promo pack for a finished article."""
    voice_ctx = f"{AUTHOR_CONTEXT}. Vibe: {AUTHOR_VIBE}"
    pack = promo.build_promo(article, title, ask_ai, article_url=article_url,
                             author=AUTHOR_NAME, voice_context=voice_ctx)

    md = promo.render_markdown(pack, AUTHOR_NAME)
    path = f"social/{slug or draft_slug(title, fallback='promo')}-promo.md"
    url = save_file_to_github(path, md, f"docs: promo pack — {title[:50]}")

    if not (GITHUB_TOKEN and GITHUB_REPO):
        os.makedirs("social", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md)
        print(f"[promo] wrote {path}")

    if notify:
        hook = pack.linkedin_hook or (pack.linkedin.split("\n", 1)[0] if pack.linkedin else "")
        msg = (f"📣 *Promo pack ready*\n\n"
               f"📝 _{title[:80]}_\n"
               f"💼 LinkedIn: {len(pack.linkedin)} chars\n"
               f"🐦 X thread: {len(pack.x_thread)} posts\n")
        if pack.human_scores:
            msg += "🧬 " + ", ".join(f"{k} {v}/100" for k, v in pack.human_scores.items()) + "\n"
        if url:
            msg += f"💾 [Promo pack file]({url})\n"
        if pack.warnings:
            msg += "\n⚠️ " + "\n⚠️ ".join(w[:120] for w in pack.warnings[:3]) + "\n"
        if hook:
            msg += f"\n_Hook:_\n```\n{hook[:220]}\n```"
        send_tg(msg)
    return pack


def promo_cli():
    """CLI: python agent.py promo <file.md> [url]"""
    args = [a for a in sys.argv[2:] if a]
    if not args:
        print("Usage: python agent.py promo <file.md> [article_url]")
        return 1
    path = args[0]
    url = args[1] if len(args) > 1 else ""
    if not os.path.exists(path):
        print(f"No such file: {path}")
        return 1
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    title = next((l.lstrip("# ").strip() for l in text.splitlines()
                  if l.startswith("# ")), os.path.basename(path))
    pack = promo_pack_for(text, title, article_url=url,
                          slug=os.path.splitext(os.path.basename(path))[0], notify=False)
    print(promo.render_markdown(pack, AUTHOR_NAME))
    return 0


def claims_cli():
    """CLI: python agent.py claims <file.md> [--write]"""
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    if not args:
        print("Usage: python agent.py claims <file.md> [--write]")
        return 1
    path = args[0]
    if not os.path.exists(path):
        print(f"No such file: {path}")
        return 1
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    title = next((l.lstrip("# ").strip() for l in text.splitlines()
                  if l.startswith("# ")), os.path.basename(path))
    slug = os.path.splitext(os.path.basename(path))[0]
    cmap = claims.build_map(text, title=title, slug=slug, brain=brain.load(),
                            evidence_urls=claims._URL_RE.findall(text))
    print(cmap.summary())
    for c in cmap.unsourced:
        print(f"  UNSOURCED line {c.line}: `{c.figure or ''}` {c.text[:90]}")
    if "--write" in sys.argv:
        out = os.path.join(os.path.dirname(path), slug + ".claims.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(claims.render(cmap))
        print(f"wrote {out}")
    return 0


def brain_cli():
    """CLI: python agent.py brain [init|list|check <topic>]"""
    sub = sys.argv[2] if len(sys.argv) > 2 else "list"
    if sub == "init":
        made = brain.scaffold()
        print(f"created: {', '.join(made)}" if made else
              f"{brain.BRAIN_DIR}/ already set up — nothing overwritten")
        return 0
    b = brain.load()
    if not b:
        print(f"No brain at {brain.BRAIN_DIR}/. Run: python agent.py brain init")
        return 1
    if sub == "check":
        print(b.for_topic(" ".join(sys.argv[3:]) or "python automation"))
    else:
        print(b.summary())
        for s in b.stories:
            print(f"  - {s.title}  [{', '.join(s.numbers) or 'no numbers'}]")
    return 0


def judge_cli():
    """CLI: python agent.py judge <file.md> [--fix]"""
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    if not args:
        print("Usage: python agent.py judge <file.md> [--fix]")
        return 1
    path = args[0]
    if not os.path.exists(path):
        print(f"No such file: {path}")
        return 1
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    title = next((l.lstrip("# ").strip() for l in text.splitlines()
                  if l.startswith("# ")), os.path.basename(path))
    ctx = {"title": title, "allowed_urls": judge._URL_RE.findall(text), "evidence_text": []}

    if "--fix" in sys.argv:
        fixed, history = judge.review_loop(text, ctx, ask_ai)
        if fixed != text:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(fixed)
            print(f"[judge] wrote revision to {path}")
        v = history[-1]
    else:
        v = judge.judge(text, ctx, ask_ai)

    print(f"\n{v.summary()}\n")
    for k, s in sorted(v.scores.items(), key=lambda kv: kv[1]):
        print(f"  {s:2d}/10  {k}")
    print()
    print(judge.format_findings(v))
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# EDUCATIONAL DROP — short-form: hooks + tips + step-by-step.
# Output is one Markdown file ready to paste into Twitter / LinkedIn / Notes.
# Invoked via CLI: `python agent.py educational <topic>`
# Or via Telegram by prefixing your message with `edu:`
# ═══════════════════════════════════════════════════════════════════════════════
def educational_single(topic: str) -> str:
    print(f"[educational] Topic: {topic}")
    send_tg(f"📚 *Educational drop incoming*\n_{topic}_\nGenerating hooks + tips + steps...")

    try:
        raw = ask_ai(f"""You are creating a short-form educational drop for {AUTHOR_NAME} — {AUTHOR_CONTEXT}.
Voice: {AUTHOR_VIBE}

TOPIC: "{topic}"

Output ONLY a JSON object with this exact shape — no markdown fences, no preamble:

{{
  "title": "punchy title under 70 chars, no buzzwords, leads with the topic keyword",
  "subtitle": "one-line teaser, max 120 chars",
  "hooks": [
    "5 distinct hook openers — each 1-2 sentences, scroll-stopping, written like a real dev would post on X. No emojis at the start. No 'Did you know'."
  ],
  "tips": [
    {{ "tip": "actionable specific tip — name a tool, command, or pattern", "why": "one-sentence reason it matters", "example": "tiny code snippet OR concrete example, max 3 lines" }}
  ],
  "steps": [
    {{ "step": "Step 1 imperative title", "detail": "1-2 sentences on what to do", "code": "optional code, leave empty string if not needed" }}
  ],
  "common_mistake": "one specific gotcha most people hit when trying this, and the fix",
  "tweet_thread": [
    "Tweet 1 — hook + promise (1 line)",
    "Tweet 2 — context (1-2 lines)",
    "Tweet 3 — first concrete tip",
    "Tweet 4 — second concrete tip",
    "Tweet 5 — third concrete tip",
    "Tweet 6 — payoff line + soft CTA"
  ],
  "linkedin_post": "5-paragraph LinkedIn post version with line breaks. Story-driven. No hashtags inside, list 3-5 hashtags at the end on their own line.",
  "tags": ["4 lowercase tags, no spaces, no hashes"]
}}

RULES:
- Exactly 5 hooks, 7 tips, 5-7 steps
- Every tip names a real tool/library/command — no abstract advice
- Every example must be runnable or directly copyable
- No banned words: delve, leverage, robust, seamless, unleash, empower, game-changer, revolutionize, master, unlock
- Use contractions, em-dashes, and a casual dev voice
- Steps build progressively — Step 5 should be a concrete result the reader can verify
""", max_tokens=3500)
    except Exception as e:
        send_tg(f"❌ Educational generation failed: {str(e)[:300]}")
        raise

    try:
        data = extract_json(raw, want=dict)
    except Exception as e:
        print(f"[educational] JSON parse failed: {e} — raw start: {raw[:300]}")
        send_tg(f"❌ Educational JSON parse failed:\n`{str(e)[:200]}`")
        raise

    def _g(k, fallback=""):
        v = data.get(k)
        if isinstance(v, str): return v.strip()
        return fallback

    title    = _g("title", topic)
    subtitle = _g("subtitle", "")
    hooks    = data.get("hooks") or []
    tips     = data.get("tips") or []
    steps    = data.get("steps") or []
    mistake  = _g("common_mistake", "")
    thread   = data.get("tweet_thread") or []
    linkedin = _g("linkedin_post", "")
    tags     = data.get("tags") or ["python", "tutorial", "ai", "developer"]
    if isinstance(tags, list):
        tags = [str(t).lower().replace("#", "").replace(" ", "").replace("-", "")[:25] for t in tags if t][:6]

    md_lines = [f"# {title}", ""]
    if subtitle:
        md_lines += [f"_{subtitle}_", ""]

    md_lines += ["## Scroll-stopping hooks", ""]
    for i, h in enumerate(hooks[:5], 1):
        md_lines.append(f"**Hook {i}.** {str(h).strip()}")
        md_lines.append("")

    md_lines += ["## 7 tips that actually move the needle", ""]
    for i, t in enumerate(tips[:7], 1):
        if isinstance(t, dict):
            tip = str(t.get("tip", "")).strip()
            why = str(t.get("why", "")).strip()
            ex  = str(t.get("example", "")).strip()
            md_lines.append(f"### Tip {i}. {tip}")
            if why:
                md_lines.append(f"_Why it matters:_ {why}")
            if ex:
                fence_lang = "python" if any(k in ex for k in ("def ", "import ", "print(")) else ""
                md_lines.append("")
                md_lines.append(f"```{fence_lang}")
                md_lines.append(ex)
                md_lines.append("```")
            md_lines.append("")
        else:
            md_lines.append(f"### Tip {i}. {str(t).strip()}")
            md_lines.append("")

    md_lines += ["## Step-by-step procedure", ""]
    for i, s in enumerate(steps, 1):
        if isinstance(s, dict):
            step   = str(s.get("step", f"Step {i}")).strip()
            detail = str(s.get("detail", "")).strip()
            code   = str(s.get("code", "")).strip()
            md_lines.append(f"### {i}. {step}")
            if detail:
                md_lines.append(detail)
            if code:
                fence_lang = "python" if any(k in code for k in ("def ", "import ", "print(", "pip ")) else ("bash" if code.startswith(("$", "git ", "npm ", "pip ", "curl ")) else "")
                md_lines.append("")
                md_lines.append(f"```{fence_lang}")
                md_lines.append(code)
                md_lines.append("```")
            md_lines.append("")
        else:
            md_lines.append(f"### {i}. {str(s).strip()}")
            md_lines.append("")

    if mistake:
        md_lines += ["## The mistake almost everyone makes", "", f"> ⚠️  {mistake}", ""]

    if thread:
        md_lines += ["## X / Twitter thread (copy-paste ready)", ""]
        for i, tw in enumerate(thread, 1):
            md_lines.append(f"**{i}/** {str(tw).strip()}")
            md_lines.append("")

    if linkedin:
        md_lines += ["## LinkedIn version", "", linkedin, ""]

    md_lines += [f"_Tags: {', '.join(tags)}_", ""]
    md_lines += ["---", f"*By {AUTHOR_NAME} — built with the CoderFact engine.*"]

    md = "\n".join(md_lines)

    slug    = draft_slug(title, fallback="drop")
    md_path = f"educational/{slug}.md"
    url     = save_file_to_github(md_path, md, f"docs: educational drop — {title[:50]}")

    preview = "\n".join(md_lines[:14])
    msg = (
        f"✅ *Educational drop ready*\n\n"
        f"📝 _{title}_\n"
        f"🪝 {len(hooks[:5])} hooks · 💡 {len(tips[:7])} tips · 🪜 {len(steps)} steps\n"
    )
    if url:
        msg += f"💾 [GitHub .md file]({url})\n"
    msg += f"\n_Preview:_\n```\n{preview[:500]}\n```"
    send_tg(msg)
    print(f"[educational] Saved {md_path} ({len(md)} chars)")
    return md


def social_media_single(topic: str) -> str:
    print(f"[social] Topic: {topic}")
    send_tg(f"📣 *Social media pack incoming*\n_{topic}_\nGenerating viral posts for Instagram, LinkedIn, Twitter, Facebook, and YouTube...")

    try:
        raw = ask_ai(f"""You are a senior social media growth writer for developer content.
Your client is Suman Giri — a Kolkata-based frontend developer and automation tinkerer.
Write platform-specific short-form content for the topic below.

TOPIC: "{topic}"

Return ONLY a JSON object with this exact shape — no markdown fences, no explanation:
{{
  "instagram": {{
    "caption": "Instagram caption under 2200 chars, hook first, includes 3 strong hashtags, one carousel text hint, and one visual prompt.",
    "carousel": [
      "5 carousel slide captions. Each slide is 1-2 sentences, easy to skim, one slide may include a tiny code snippet or tech tip."
    ],
    "hashtags": ["#topic"],
    "visual_prompt": "short image prompt for a carousel or single Instagram post that matches the topic"
  }},
  "linkedin": {{
    "post": "LinkedIn post with 4-5 short paragraphs, first-person story, clear developer lesson, and a final soft CTA.",
    "hashtags": ["developer", "python", "automation"],
    "visual_prompt": "image prompt for a LinkedIn post graphic or diagram"
  }},
  "twitter": {{
    "thread": [
      "6 tweets. Tweet 1 is a hook, Tweet 2 gives the problem, Tweets 3-5 share micro-value or code snippet, Tweet 6 is a wrap + CTA."
    ],
    "visual_prompt": "image prompt for a Twitter graphic or code screenshot",
    "hashtags": ["dev", "ai", "automation"]
  }},
  "facebook": {{
    "post": "Facebook post with a strong opening, result-oriented bullet list, and a shareable question at the end.",
    "visual_prompt": "image prompt for a Facebook post or story",
    "hashtags": ["developer", "coding", "tech"]
  }},
  "youtube": {{
    "title": "YouTube video title under 70 chars, SEO-optimized, not clickbait.",
    "description": "SEO-friendly description with 2 hashtags, 2 short paragraphs, and a clear watch/learn CTA.",
    "script_outline": [
      "5 bullet points for a short video script — hook, problem, solution, demo, CTA."
    ],
    "thumbnail_prompt": "thumbnail prompt for a dark tech video thumbnail with code, laptop, and developer energy"
  }}
}}

REQUIREMENTS:
- Analyze the platform rules and write each section to feel native to that platform.
- Instagram: visual, carousel-ready, snackable, share-worthy.
- LinkedIn: story + lesson + credibility, no long marketing copy.
- Twitter: thread format, use code snippet text if technical, end with one strong CTA.
- Facebook: conversational, digestible, with a clear question or share prompt.
- YouTube: title + description + script bullets + thumbnail prompt.
- Include visuals, animations, or image ideas in every platform section.
- Use a real developer voice, not marketing hype.
- Use the topic naturally and keep the content viral-ready.
""", max_tokens=3600)
    except Exception as e:
        send_tg(f"❌ Social media generation failed: {str(e)[:300]}")
        raise

    try:
        data = extract_json(raw, want=dict)
    except Exception as e:
        print(f"[social] JSON parse failed: {e} — raw start: {raw[:300]}")
        send_tg(f"❌ Social JSON parse failed:\n`{str(e)[:200]}`")
        raise

    def _s(val, fallback=""):
        if isinstance(val, str):
            return val.strip()
        return fallback

    instagram = data.get("instagram", {}) or {}
    linkedin = data.get("linkedin", {}) or {}
    twitter = data.get("twitter", {}) or {}
    facebook = data.get("facebook", {}) or {}
    youtube = data.get("youtube", {}) or {}

    md_lines = [f"# Social media content pack — {topic}", ""]
    md_lines += ["## Instagram", "", f"**Caption:** {instagram.get('caption','')}", ""]
    for i, slide in enumerate(instagram.get('carousel', [])[:5], 1):
        md_lines += [f"**Slide {i}:** {slide}", ""]
    if instagram.get('hashtags'):
        md_lines += [f"**Hashtags:** {' '.join(instagram.get('hashtags', []))}", ""]
    if instagram.get('visual_prompt'):
        md_lines += [f"**Visual prompt:** {instagram.get('visual_prompt')}", ""]

    md_lines += ["## LinkedIn", "", linkedin.get('post', ''), ""]
    if linkedin.get('hashtags'):
        md_lines += [f"**Hashtags:** {' '.join(linkedin.get('hashtags', []))}", ""]
    if linkedin.get('visual_prompt'):
        md_lines += [f"**Visual prompt:** {linkedin.get('visual_prompt')}", ""]

    md_lines += ["## Twitter thread", ""]
    for i, tweet in enumerate(twitter.get('thread', [])[:6], 1):
        md_lines += [f"**Tweet {i}:** {tweet}", ""]
    if twitter.get('hashtags'):
        md_lines += [f"**Hashtags:** {' '.join(twitter.get('hashtags', []))}", ""]
    if twitter.get('visual_prompt'):
        md_lines += [f"**Visual prompt:** {twitter.get('visual_prompt')}", ""]

    md_lines += ["## Facebook", "", facebook.get('post', ''), ""]
    if facebook.get('hashtags'):
        md_lines += [f"**Hashtags:** {' '.join(facebook.get('hashtags', []))}", ""]
    if facebook.get('visual_prompt'):
        md_lines += [f"**Visual prompt:** {facebook.get('visual_prompt')}", ""]

    md_lines += ["## YouTube", "", f"**Title:** {youtube.get('title', '')}", "", f"**Description:** {youtube.get('description', '')}", ""]
    for i, point in enumerate(youtube.get('script_outline', [])[:5], 1):
        md_lines += [f"**Bullet {i}:** {point}", ""]
    if youtube.get('thumbnail_prompt'):
        md_lines += [f"**Thumbnail prompt:** {youtube.get('thumbnail_prompt')}", ""]

    md_lines += ["---", f"*By {AUTHOR_NAME} — social pack generated by the CoderFact engine.*"]

    md = "\n".join(md_lines)
    slug = draft_slug(topic, fallback="social-pack")
    md_path = f"social/{slug}.md"
    url = save_file_to_github(md_path, md, f"docs: social content pack — {topic[:50]}")

    preview = "\n".join(md_lines[:18])
    msg = (
        f"✅ *Social media pack ready*\n\n"
        f"📝 _{topic}_\n"
    )
    if url:
        msg += f"💾 [GitHub .md file]({url})\n"
    msg += f"\n_Preview:_\n```\n{preview[:500]}\n```"
    send_tg(msg)
    print(f"[social] Saved {md_path} ({len(md)} chars)")
    return md


def social():
    """CLI entrypoint: python agent.py social <topic>"""
    topic = " ".join(sys.argv[2:]).strip()
    if not topic:
        reply = get_reply()
        if reply and reply.get("type") == "custom":
            topic = reply["topic"]
        else:
            topic = "Building a viral AI developer social post pack"
            print(f"[social] No topic provided — defaulting to '{topic}'")
    social_media_single(topic)


def educational():
    """CLI entrypoint: python agent.py educational <topic>"""
    topic = " ".join(sys.argv[2:]).strip()
    if not topic:
        # Pull from telegram reply if no CLI arg
        reply = get_reply()
        if reply and reply.get("type") == "custom":
            topic = reply["topic"]
        else:
            topic = "Building your first AI agent in Python"
            print(f"[educational] No topic provided — defaulting to '{topic}'")
    educational_single(topic)


def draft():
    """Orchestrator: reads reply, handles numbered choices + custom topics."""
    reply = get_reply()
    if reply is None:
        return print("No reply yet.")

    rtype = reply.get("type")

    if rtype == "skip":
        return send_tg("👌 Skipping today. See you tomorrow!")

    if rtype == "custom":
        custom_topic = reply["topic"]
        # `edu: <topic>` triggers educational drop instead of full article
        if custom_topic.lower().startswith("edu:"):
            edu_topic = custom_topic.split(":", 1)[1].strip()
            if not edu_topic:
                return send_tg("⚠️ `edu:` prefix needs a topic. Try `edu: building your first AI agent`.")
            try:
                educational_single(edu_topic)
            except Exception as e:
                send_tg(f"❌ Educational drop failed: {str(e)[:300]}")
            return
        if custom_topic.lower().startswith("social:"):
            social_topic = custom_topic.split(":", 1)[1].strip()
            if not social_topic:
                return send_tg("⚠️ `social:` prefix needs a topic. Try `social: building an AI agent promo`.")
            try:
                social_media_single(social_topic)
            except Exception as e:
                send_tg(f"❌ Social pack failed: {str(e)[:300]}")
            return
        send_tg(f"✍️ Got your custom topic:\n*`{custom_topic}`*\n\nDrafting now...")
        try:
            draft_single(custom_topic, 1, 1)
        except Exception as e:
            send_tg(f"❌ Custom draft failed: {str(e)[:300]}")
        return

    choices = reply.get("choices", [])
    state = load_state()
    topics = state.get("topics", [])
    state_date = state.get("date", "")
    today_str = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).strftime("%B %d, %Y")

    print(f"[draft] choices={choices} state_date='{state_date}' today='{today_str}'")

    if not topics:
        return send_tg("⚠️ No topics found. Run the morning researcher first, or reply with your own topic text.")
    if state_date and state_date != today_str:
        return send_tg(
            f"⚠️ Saved topics are from {state_date}. Morning brief not run yet today.\n"
            f"You can still reply with your own topic as free text to draft it directly."
        )

    valid = [c for c in choices if c.isdigit() and int(c) <= len(topics)]
    if not valid:
        return send_tg("⚠️ Invalid choice. Topics 1–3 only, or type your own topic.")

    total = len(valid)
    if total > 1:
        titles_list = "\n".join(f"{c}. {topics[int(c)-1]}" for c in valid)
        send_tg(f"📋 Drafting *{total} articles*:\n{titles_list}\n\n~{total * 90}s total...")

    for idx, choice in enumerate(valid, 1):
        title = topics[int(choice) - 1]
        try:
            draft_single(title, idx, total)
        except Exception as e:
            send_tg(f"❌ Article {idx}/{total} failed: {str(e)[:200]}\nMoving to next...")
            print(f"[draft] draft_single failed for '{title}': {e}")

    if total > 1:
        send_tg(f"🎉 All {total} drafts done! Check your Dev.to dashboard.")


def doctor():
    """Probe every signal source and every configured API key. No AI calls, no
    publishing — safe to run any time to find out what is actually broken."""
    print("=" * 68)
    print("CONFIG")
    print("=" * 68)
    for label, val in (("OPENROUTER_API_KEY", OPENROUTER_KEY), ("GEMINI_API_KEY", GEMINI_KEY),
                       ("GROQ_API_KEY", GROQ_KEY), ("DEVTO_API_KEY", DEVTO_KEY),
                       ("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT), ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT),
                       ("GITHUB_TOKEN", GITHUB_TOKEN), ("GITHUB_REPOSITORY", GITHUB_REPO)):
        print(f"  {'SET ' if val else 'MISS'}  {label}")
    if not (OPENROUTER_KEY or GEMINI_KEY or GROQ_KEY):
        print("\n  !! No AI provider configured — research/draft cannot run.")

    # Model IDs go stale: this pipeline sat on gemini-2.0-flash for months after
    # Google shut it down, and the only symptom was the Gemini leg quietly
    # falling through to the next provider. Resolve each configured model
    # against the live API so a retired one is visible here, not in a run log.
    if GEMINI_KEY:
        print(f"\n  Gemini models ({', '.join(GEMINI_MODELS)}):")
        for m in GEMINI_MODELS:
            try:
                r = requests.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{m}",
                    headers={"x-goog-api-key": GEMINI_KEY}, timeout=15)
                if r.ok:
                    print(f"    OK    {m}")
                else:
                    detail = (r.json().get("error", {}).get("message", "") or r.text)[:70]
                    print(f"    FAIL  {m} — HTTP {r.status_code}: {detail}")
            except Exception as e:
                print(f"    FAIL  {m} — {str(e)[:70]}")

    samples = humanizer.load_voice_samples()
    print(f"\n  voice samples: {len(samples)} "
          f"({'fingerprint active' if samples else 'none — using persona text'})")
    print(f"  research library: {len(rx.library_read())} past run(s) at {rx.LIBRARY_PATH}")
    _brain = brain.load()
    print(f"  brain: {_brain.summary() if _brain else 'empty — run: python agent.py brain init'}")

    print("\n" + "=" * 68)
    print("SOURCES")
    print("=" * 68)
    _items, health = rx.fetch_all()
    print()
    print(rx.format_health(health))
    return 1 if [h for h in health if h.status in ("failed", "timeout")] else 0


def try_cli():
    """python agent.py try "<topic>" — draft one article end to end, locally.

    The normal draft path waits on a Telegram reply, so there was no way to
    exercise the pipeline on a topic you name. This runs every stage — brain
    pull, outline, article, humanize loop, judge loop, claims map, promo pack —
    and writes the output to disk. It never publishes: Dev.to only ever receives
    published:false, and without DEVTO_API_KEY it is not called at all.
    """
    topic = " ".join(sys.argv[2:]).strip()
    if not topic:
        print('Usage: python agent.py try "your topic here"')
        return 1
    if not (GEMINI_KEY or GROQ_KEY or OPENROUTER_KEY):
        print("No AI provider configured. Put a key in .env "
              "(cp .env.example .env) or export GEMINI_API_KEY.")
        return 1

    print("=" * 68)
    print(f"DRY RUN — {topic}")
    print("=" * 68)
    print(f"  provider chain : Gemini {GEMINI_MODELS if GEMINI_KEY else '(no key)'}")
    print(f"  Dev.to         : {'draft only (published:false)' if DEVTO_KEY else 'not configured — skipped'}")
    print(f"  GitHub         : {'configured' if (GITHUB_TOKEN and GITHUB_REPO) else 'not configured — saving locally'}")
    print(f"  Telegram       : {'configured' if (TELEGRAM_BOT and TELEGRAM_CHAT) else 'not configured — messages skipped'}")
    b = brain.load()
    print(f"  brain          : {b.summary() if b else 'empty'}")
    print()

    try:
        draft_single(topic, 1, 1)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\nDRY RUN FAILED: {e}")
        return 1

    slug = draft_slug(topic)
    print("\n" + "=" * 68)
    print("OUTPUT")
    print("=" * 68)
    for p in (f"medium_drafts/{slug}.md", f"medium_drafts/{slug}.claims.md",
              f"social/{slug}-promo.md"):
        print(f"  {'OK  ' if os.path.exists(p) else 'MISS'} {p}")
    print("\nScore the result:")
    print(f"  python humanizer.py medium_drafts/{slug}.md")
    print(f"  python claims.py    medium_drafts/{slug}.md")
    print(f"  python agent.py judge medium_drafts/{slug}.md")
    return 0


def models_cli():
    """python agent.py models — resolve every configured model against the live
    provider catalogues. Model IDs rot silently: a retired slug just 404s and the
    chain falls through, so a run 'succeeds' on a worse model, or not at all."""
    bad = 0

    print("=" * 68)
    print("OPENROUTER")
    print("=" * 68)
    try:
        data = requests.get("https://openrouter.ai/api/v1/models", timeout=30).json()["data"]
        cat = {m["id"]: m for m in data}
        for mid in OPENROUTER_MODELS:
            m = cat.get(mid)
            if not m:
                print(f"  GONE  {mid}"); bad += 1
                continue
            p = m.get("pricing") or {}
            is_free = str(p.get("prompt")) in ("0", "0.0") and str(p.get("completion")) in ("0", "0.0")
            print(f"  {'FREE' if is_free else 'PAID'}  {mid:<48} "
                  f"ctx={m.get('context_length', '?')}")
            if not is_free:
                print(f"        !! bills {p.get('prompt')}/{p.get('completion')} per token")
        free_now = sorted(m["id"] for m in data if m["id"].endswith(":free"))
        print(f"\n  {len(free_now)} ':free' models currently on OpenRouter:")
        for f in free_now:
            print(f"    {f}")
    except Exception as e:
        print(f"  could not reach OpenRouter: {str(e)[:90]}")

    print("\n" + "=" * 68)
    print("GEMINI (direct API — the only free path to a Flash model)")
    print("=" * 68)
    if not GEMINI_KEY:
        print("  GEMINI_API_KEY not set — cannot resolve model IDs")
    else:
        for mid in GEMINI_MODELS:
            try:
                r = requests.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{mid}",
                    headers={"x-goog-api-key": GEMINI_KEY}, timeout=15)
                if r.ok:
                    print(f"  OK    {mid}")
                else:
                    detail = (r.json().get("error", {}).get("message", "") or r.text)[:70]
                    print(f"  FAIL  {mid} — HTTP {r.status_code}: {detail}"); bad += 1
            except Exception as e:
                print(f"  FAIL  {mid} — {str(e)[:70]}"); bad += 1

    print(f"\n  Groq: {GROQ_MODEL} ({'key set' if GROQ_KEY else 'no key'})")
    print(f"  openrouter/auto fallback: {'ENABLED (can bill)' if OPENROUTER_ALLOW_PAID else 'off'}")
    if bad:
        print(f"\n  {bad} configured model(s) unusable — override with "
              f"GEMINI_MODELS / OPENROUTER_MODELS")
    return 1 if bad else 0


def humanize_cli():
    """python agent.py humanize <file.md> — run the full rewrite/repair loop on
    an existing draft and write it back."""
    paths = sys.argv[2:]
    if not paths:
        return print("Usage: python agent.py humanize <file.md> [more.md ...]")
    voice_ctx = f"{AUTHOR_NAME} — {AUTHOR_CONTEXT}. Vibe: {AUTHOR_VIBE}"
    for path in paths:
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except Exception as e:
            print(f"!! {path}: {e}")
            continue
        words = humanizer.prose_word_count(text)
        fixed, report = humanizer.humanize(text, ask_ai, voice_context=voice_ctx,
                                           target_words=max(words, 600))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(fixed)
        print(f"{path}: {report.summary()}")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    COMMANDS = {"research": research, "draft": draft, "educational": educational,
                "social": social, "doctor": doctor, "humanize": humanize_cli,
                "judge": judge_cli, "promo": promo_cli,
                "claims": claims_cli, "brain": brain_cli,
                "models": models_cli, "try": try_cli}
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print("Usage: python agent.py <command>\n"
              "  research              pick + score today's topics, send the Telegram brief\n"
              "  draft                 read the Telegram reply and write the chosen article(s)\n"
              "  educational <topic>   short-form drop (hooks + tips + steps)\n"
              "  social <topic>        per-platform social pack from a topic\n"
              "  humanize <file.md>    rewrite/repair an existing draft in place\n"
              "  judge <file.md>       editorial review; --fix applies the findings\n"
              "  promo <file.md> [url] LinkedIn + X posts from a finished article\n"
              "  claims <file.md>      map every factual claim to its receipt\n"
              "  brain [init|list|check <topic>]  the author's own sourced material\n"
              "  try \"<topic>\"         draft one article end to end, locally, publish nothing\n"
              "  models                resolve every configured model against the provider\n"
              "  doctor                probe every source and key, publish nothing")
        sys.exit(2)
    sys.exit(COMMANDS[cmd]() or 0)