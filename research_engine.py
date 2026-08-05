"""
research_engine.py — parallel multi-source signal collection with computed ranking.

Design borrowed from mvanhorn/last30days-skill, adapted to this repo:

  * PARALLEL sweeps with per-source timeouts and graceful degradation. The old
    fetch_trends() ran ~40 HTTP calls serially (15 of them one-at-a-time Hacker
    News item lookups) and a single slow source stalled the whole morning run.
  * HONEST HEALTH REPORTING. Every source reports ok/empty/failed with a reason,
    so a silently-broken scraper stops looking like "no news today".
  * CROSS-SOURCE CLUSTERING computed in Python. agent.py's prompt claimed
    "topic on GitHub + Reddit + Trends = 3x multiplier" but nothing ever
    calculated it — the model was asked to eyeball it from a flat list.
  * WITHIN-SOURCE NORMALISATION. 400 HN points, 2k Reddit upvotes and 90 Dev.to
    reactions are not comparable numbers; each source is converted to a
    percentile rank before scores are combined.
  * A PERSISTENT LIBRARY (research/library.jsonl) so topic novelty is checked
    against every past run, not the last 30 titles in state.json.

CLI:
    python research_engine.py doctor          # probe every source, show health
    python research_engine.py scan            # run a sweep, print ranked clusters
    python research_engine.py search "agents" # offline search of past runs
"""

import os
import re
import io
import json
import html
import time
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CoderFact-Bot/1.0)"}
LIBRARY_DIR = os.getenv("RESEARCH_LIBRARY_DIR", "research")
LIBRARY_PATH = os.path.join(LIBRARY_DIR, "library.jsonl")

# Per-source wall-clock budget. A source that blows it is reported degraded
# rather than being allowed to stall the run.
SOURCE_TIMEOUT = int(os.getenv("SOURCE_TIMEOUT", "45"))


# ═══════════════════════════════════════════════════════════════════════════════
# ITEMS
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class Item:
    source: str          # "hackernews", "reddit", ...
    title: str
    url: str = ""
    engagement: float = 0.0     # raw, source-specific units
    age_hours: float = 24.0
    detail: str = ""            # subreddit, language, tag list...
    meta: dict = field(default_factory=dict)


@dataclass
class SourceHealth:
    name: str
    status: str          # ok | empty | failed | timeout
    count: int = 0
    seconds: float = 0.0
    error: str = ""

    def line(self):
        icon = {"ok": "OK ", "empty": "-- ", "failed": "XX ", "timeout": "TO "}[self.status]
        tail = f" ({self.error[:60]})" if self.error else ""
        return f"  {icon} {self.name:<16} {self.count:>3} items  {self.seconds:5.1f}s{tail}"


# ═══════════════════════════════════════════════════════════════════════════════
# SOURCES — each returns list[Item] or raises. Registered in SOURCES at bottom.
# ═══════════════════════════════════════════════════════════════════════════════


def _get(url, **kw):
    kw.setdefault("timeout", 10)
    kw.setdefault("headers", HEADERS)
    r = requests.get(url, **kw)
    r.raise_for_status()
    return r


def _clean_text(s, limit=240):
    """Snippets go straight into the model's prompt, so strip the HTML they
    arrive wrapped in. Algolia returns story_text as raw HTML with escaped
    entities (&#x27;, <p>), and Reddit's RSS path carries markup too — left
    alone it reads as noise to the model and can leak into a draft."""
    if not s:
        return ""
    # Block-level tags become spaces first — HN wraps paragraphs in a bare <p>
    # with no closing tag, so stripping tags blind would glue sentences together.
    s = re.sub(r"<\s*/?\s*(?:br|p|div|li|tr)\s*/?>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()[:limit]


def _age_hours(epoch, fallback=48.0):
    """Real age from a unix timestamp. Floors at 0.5h so a just-posted item
    can't get an unbounded recency weight, and falls back to a neutral 48h
    when the source gives us nothing usable."""
    try:
        return max((time.time() - float(epoch)) / 3600.0, 0.5)
    except (TypeError, ValueError):
        return fallback


def src_github():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(_get("https://github.com/trending").text, "html.parser")
    out = []
    for article in soup.find_all("article", class_="Box-row")[:15]:
        name = article.find("h2")
        if not name:
            continue
        desc = article.find("p")
        lang = article.find("span", itemprop="programmingLanguage")
        stars = article.find("a", href=lambda h: h and "stargazers" in h)
        star_n = 0
        if stars:
            digits = re.sub(r"[^\d]", "", stars.get_text(strip=True))
            star_n = int(digits) if digits else 0
        repo = re.sub(r"\s+", "", name.get_text(strip=True))
        out.append(Item("github", f"{repo} {desc.get_text(strip=True) if desc else ''}".strip(),
                        url=f"https://github.com/{repo}", engagement=star_n, age_hours=24,
                        detail=lang.get_text(strip=True) if lang else "",
                        meta={"repo": repo}))
    return out


def src_hackernews():
    """Top stories. The old code fetched 15 items one at a time; this fans out."""
    ids = _get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=8).json()[:25]
    out = []

    def one(sid):
        return _get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=6).json()

    with ThreadPoolExecutor(max_workers=10) as pool:
        for fut in as_completed([pool.submit(one, s) for s in ids]):
            try:
                it = fut.result()
            except Exception:
                continue
            if not it or it.get("type") != "story" or not it.get("title"):
                continue
            age = max((time.time() - it.get("time", time.time())) / 3600.0, 0.5)
            out.append(Item("hackernews", it["title"],
                            url=it.get("url") or f"https://news.ycombinator.com/item?id={it.get('id')}",
                            engagement=it.get("score", 0), age_hours=age,
                            detail=f"{it.get('descendants', 0)} comments"))
    return out


def _reddit_json(sub, listing, limit, t):
    q = f"https://www.reddit.com/r/{sub}/{listing}.json?limit={limit}" + (f"&t={t}" if t else "")
    data = _get(q, headers={**HEADERS, "Accept": "application/json"}, timeout=10).json()
    out = []
    for p in data.get("data", {}).get("children", []):
        d = p.get("data", {})
        if d.get("stickied") or not d.get("title"):
            continue
        age = max((time.time() - d.get("created_utc", time.time())) / 3600.0, 0.5)
        out.append(Item("reddit", d["title"],
                        url="https://www.reddit.com" + (d.get("permalink") or ""),
                        engagement=d.get("ups", 0), age_hours=age, detail=f"r/{sub}",
                        meta={"sub": sub, "selftext": _clean_text(d.get("selftext"), 400),
                              "comments": d.get("num_comments", 0), "path": "json"}))
    return out


def _reddit_rss(sub, listing, limit):
    """Fallback path. Reddit answers /r/<sub>/<listing>/.rss without auth but
    does not include a score, so these items carry no engagement number and are
    ranked on recency and corroboration alone."""
    import feedparser
    r = _get(f"https://www.reddit.com/r/{sub}/{listing}/.rss?limit={limit}", timeout=10)
    feed = feedparser.parse(r.text)
    out = []
    for e in feed.entries[:limit]:
        title = getattr(e, "title", "").strip()
        if not title:
            continue
        age = 24.0
        if getattr(e, "updated_parsed", None):
            age = max((time.time() - time.mktime(e.updated_parsed)) / 3600.0, 0.5)
        out.append(Item("reddit", title, url=getattr(e, "link", ""),
                        engagement=0, age_hours=age, detail=f"r/{sub}",
                        meta={"sub": sub,
                              "selftext": _clean_text(getattr(e, "summary", ""), 400),
                              "comments": 0, "path": "rss"}))
    return out


# Reddit rate-limits hard on concurrent hits from one IP. Requests to this one
# host are serialised behind a lock and paced; everything else still runs in
# parallel. Without this, six subreddits fan out and all six come back 429.
_REDDIT_LOCK = __import__("threading").Lock()
_REDDIT_JSON_OK = True   # flipped off after the first 403 to halve request volume
_REDDIT_GAP = 2.0


def _reddit(sub, listing="hot", limit=10, t=""):
    """Reddit blocks unauthenticated .json from most hosts with a 403. The old
    agent.py caught that per-subreddit and shipped an empty list, so the entire
    Reddit signal was missing without anything reporting it. Try JSON once, then
    stay on the RSS path for the rest of the run."""
    global _REDDIT_JSON_OK
    with _REDDIT_LOCK:
        if _REDDIT_JSON_OK:
            try:
                out = _reddit_json(sub, listing, limit, t)
                time.sleep(_REDDIT_GAP)
                return out
            except Exception:
                _REDDIT_JSON_OK = False
        last = None
        for attempt in range(3):
            try:
                out = _reddit_rss(sub, listing, limit)
                time.sleep(_REDDIT_GAP)
                return out
            except Exception as e:
                last = e
                time.sleep(_REDDIT_GAP * (attempt + 2))
        raise last if last else RuntimeError("reddit: no data")


REDDIT_BUDGET = float(os.getenv("REDDIT_BUDGET", "40"))


def _reddit_many(subs, listing="hot", limit=10, t="", label="reddit", deadline=None):
    """Sequential by design — _reddit() serialises on a lock anyway, and a
    thread pool here only burns the per-source timeout budget.

    Stops early once the shared Reddit budget is spent and returns what it has;
    partial Reddit coverage beats blowing the global sweep budget.
    """
    out, errors = [], []
    for sub in subs:
        if deadline and time.time() > deadline:
            errors.append(f"r/{sub}: skipped (budget)")
            continue
        try:
            out.extend(_reddit(sub, listing, limit, t))
        except Exception as e:
            errors.append(f"r/{sub}: {type(e).__name__}")
    # Every subreddit failing is a broken source, not a quiet day.
    if not out and errors:
        raise RuntimeError(f"{label}: all {len(errors)} subs failed — {errors[0]}")
    return out


def src_reddit():
    """Tech subs and indie/income subs in ONE paced sweep.

    These were two registered sources; run concurrently they competed for the
    same anonymous rate limit and the second one lost every time (all subs 429).
    Reddit is one host with one budget, so it gets one source.
    """
    deadline = time.time() + REDDIT_BUDGET
    out = _reddit_many(["programming", "MachineLearning", "LocalLLaMA"], deadline=deadline)
    try:
        raw = _reddit_many(["indiehackers", "SideProject"], listing="top",
                           limit=15, t="month", label="reddit-indie", deadline=deadline)
    except Exception as e:
        print(f"[research] reddit indie leg degraded: {type(e).__name__}")
        raw = []
    for it in raw:
        blob = (it.title + " " + it.meta.get("selftext", "")).lower()
        if not any(k in blob for k in INCOME_KW):
            continue
        # The RSS fallback carries no score, so an upvote floor would drop every
        # item on that path. Only gate when a real number is available.
        if it.meta.get("path") == "json" and it.engagement < 30:
            continue
        it.source = "indie_reddit"
        it.meta["story"] = True
        # This leg only keeps posts matching INCOME_KW, so every survivor is an
        # income-angle citation and should outrank generic launches in the
        # stories block.
        it.meta["income_angle"] = True
        out.append(it)
    return out


def src_devto():
    arts = _get("https://dev.to/api/articles?top=7&per_page=15").json()
    return [Item("devto", a.get("title", ""), url=a.get("url", ""),
                 engagement=a.get("positive_reactions_count", 0), age_hours=48,
                 detail=", ".join(a.get("tag_list", [])[:3]))
            for a in arts if a.get("title")]


def src_producthunt():
    """ProductHunt serves Atom (<feed>/<entry>), not RSS. The old code called
    soup.find_all("item") and therefore always found zero launches."""
    import feedparser
    feed = feedparser.parse(_get("https://www.producthunt.com/feed").text)
    out = []
    for e in feed.entries[:12]:
        title = getattr(e, "title", "").strip()
        if not title:
            continue
        desc = re.sub(r"<[^>]+>", " ", getattr(e, "summary", ""))
        out.append(Item("producthunt", title, url=getattr(e, "link", ""),
                        engagement=0, age_hours=24,
                        detail=re.sub(r"\s+", " ", desc).strip()[:120]))
    return out


RSS_FEEDS = [
    ("https://towardsdatascience.com/feed", "Towards Data Science"),
    ("https://medium.com/feed/better-programming", "Better Programming"),
    ("https://medium.com/feed/towards-artificial-intelligence", "Towards AI"),
    ("https://medium.com/feed/hackernoon", "HackerNoon"),
    ("https://medium.com/feed/level-up-coding", "Level Up Coding"),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "TechCrunch AI"),
    ("https://www.technologyreview.com/feed/", "MIT Tech Review"),
    ("https://freecodecamp.org/news/rss/", "freeCodeCamp"),
    ("https://hnrss.org/frontpage", "HN RSS"),
    ("https://rss.arxiv.org/rss/cs.AI", "arXiv CS.AI"),
    ("https://stackoverflow.blog/feed/", "Stack Overflow Blog"),
]


def src_rss():
    import feedparser
    out = []

    def one(url, label):
        feed = feedparser.parse(url)
        return [Item("rss", getattr(e, "title", ""), url=getattr(e, "link", ""),
                     engagement=0, age_hours=36, detail=label)
                for e in feed.entries[:4] if getattr(e, "title", "")]

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(one, u, l) for u, l in RSS_FEEDS]
        for fut in as_completed(futs):
            try:
                out.extend(fut.result())
            except Exception:
                continue
    return out


def src_google_trends():
    from pytrends.request import TrendReq
    pt = TrendReq(hl="en-US", tz=330, timeout=(10, 20), retries=1, backoff_factor=0.4)
    out = []
    for seed in ("python automation", "AI coding", "ai agents"):
        try:
            pt.build_payload([seed], timeframe="now 7-d", geo="")
            rising = pt.related_queries().get(seed, {}).get("rising")
            if rising is not None and not rising.empty:
                for _, row in rising.head(5).iterrows():
                    out.append(Item("google_trends", str(row["query"]),
                                    engagement=float(row.get("value", 0) or 0),
                                    age_hours=84, detail="rising query"))
        except Exception:
            continue
    return out


INCOME_KW = ("$", " mrr", " arr", "revenue", "made $", "earned", "passive income",
             "side project", "side hustle", "launched", "shipped", "first sale",
             "first customer", "indie hacker", "solo founder", "ai automation",
             "ai agent", "vibe coding", "built with cursor", "saas")


SHOW_HN_WINDOW_DAYS = int(os.getenv("SHOW_HN_WINDOW_DAYS", "30"))


def src_show_hn():
    """Recent Show HN launches — the builder/launch signal.

    Two bugs lived here. Algolia's default sort is by relevance across ALL TIME,
    so this returned the top Show HN posts of the last fifteen years; combined
    with a hardcoded age_hours=72 a 2011 post was scored as three-day-fresh
    signal. Now the window is enforced server-side and the real age is used.

    The income-keyword filter was also applied to the title alone, which dropped
    39 of every 40 launches ("Show HN: I made an open-source laptop" contains no
    income keyword). Show HN *is* the launch signal, so everything in the window
    is kept; the keywords now only flag the income angle.
    """
    cutoff = int(time.time()) - SHOW_HN_WINDOW_DAYS * 86400
    r = _get("https://hn.algolia.com/api/v1/search",
             params={"tags": "show_hn", "hitsPerPage": 40,
                     "numericFilters": f"points>20,created_at_i>{cutoff}"})
    out = []
    for hit in r.json().get("hits", []):
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        blob = (title + " " + (hit.get("story_text") or "")).lower()
        out.append(Item("show_hn", title,
                        url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID','')}",
                        engagement=hit.get("points", 0),
                        age_hours=_age_hours(hit.get("created_at_i")),
                        detail=f"{hit.get('points',0)} points · {hit.get('num_comments',0)} comments",
                        meta={"story": True,
                              "income_angle": any(k in blob for k in INCOME_KW),
                              "snippet": _clean_text(hit.get("story_text"), 200)}))
    return out



SOURCES = {
    "github": src_github,
    "hackernews": src_hackernews,
    "reddit": src_reddit,
    "devto": src_devto,
    "producthunt": src_producthunt,
    "rss": src_rss,
    "google_trends": src_google_trends,
    "show_hn": src_show_hn,
}


# ═══════════════════════════════════════════════════════════════════════════════
# PARALLEL SWEEP
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_all(only=None, timeout=SOURCE_TIMEOUT, quiet=False):
    """Run every source concurrently. Returns (items, health).

    One dead source degrades coverage; it never fails the run.
    """
    names = [n for n in SOURCES if not only or n in only]
    items, health = [], []

    pool = ThreadPoolExecutor(max_workers=len(names))
    try:
        started = {pool.submit(SOURCES[n]): (n, time.time()) for n in names}
        pending = dict(started)
        try:
            for fut in as_completed(started, timeout=timeout * 2):
                name, t0 = pending.pop(fut)
                elapsed = time.time() - t0
                try:
                    got = [i for i in fut.result() if i.title and i.title.strip()]
                    health.append(SourceHealth(name, "ok" if got else "empty",
                                               len(got), elapsed))
                    items.extend(got)
                except Exception as e:
                    kind = "timeout" if "timeout" in type(e).__name__.lower() else "failed"
                    health.append(SourceHealth(name, kind, 0, elapsed,
                                               f"{type(e).__name__}: {e}"))
        except TimeoutError:
            # A source blowing the global budget degrades coverage. It must never
            # abort the sweep and throw away the sources that did come back.
            pass
        for fut, (name, t0) in pending.items():
            fut.cancel()
            health.append(SourceHealth(name, "timeout", 0, time.time() - t0,
                                       f"exceeded {timeout * 2}s global budget"))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    health.sort(key=lambda h: h.name)
    if not quiet:
        print(f"[research] swept {len(names)} sources -> {len(items)} items")
        for h in health:
            print(h.line())
    return items, health


# ═══════════════════════════════════════════════════════════════════════════════
# NORMALISATION + CLUSTERING + SCORING
# ═══════════════════════════════════════════════════════════════════════════════

STOP = set("""a an and the of to in for on with at by from as is are was were be been it its this
that these those you your i my we our they their he she them then than so not no do does did have
has had will would can could should there here what when where which who how why all any some more
most other into out up down over new using use used your top best via just get make made new
show ask tell why how what""".split())


def tokens(text):
    return {w for w in re.findall(r"[a-z][a-z0-9+#.]{2,}", text.lower()) if w not in STOP}


# Several feeds are re-publications of a platform already swept directly. Counting
# them as separate sources manufactured cross-source corroboration: an HN story
# echoed by hnrss.org looked like a 2-platform story and got a breadth bonus.
FEED_PLATFORM = {
    "HN RSS": "hackernews",
    "Towards Data Science": "medium",
    "Better Programming": "medium",
    "Towards AI": "medium",
    "HackerNoon": "medium",
    "Level Up Coding": "medium",
}


def platform_of(item):
    if item.source == "rss":
        return FEED_PLATFORM.get(item.detail, "rss:" + (item.detail or "misc"))
    if item.source in ("show_hn", "hackernews"):
        return "hackernews"
    if item.source in ("indie_reddit", "reddit"):
        return "reddit"
    return item.source


def _percentile_ranks(values):
    """Map raw engagement to 0..1 within its own source. Ties share a rank."""
    if not values:
        return {}
    ordered = sorted(set(values))
    if len(ordered) == 1:
        return {ordered[0]: 0.5}
    return {v: i / (len(ordered) - 1) for i, v in enumerate(ordered)}


def normalize(items):
    """Attach .meta['norm'] — engagement as a within-source percentile, so HN
    points and Dev.to reactions become comparable."""
    by_source = {}
    for it in items:
        by_source.setdefault(it.source, []).append(it.engagement)
    ranks = {s: _percentile_ranks(v) for s, v in by_source.items()}
    for it in items:
        it.meta["norm"] = ranks.get(it.source, {}).get(it.engagement, 0.5)
    return items


@dataclass
class Cluster:
    key: str
    items: list = field(default_factory=list)
    score: float = 0.0
    sources: set = field(default_factory=set)
    platforms: set = field(default_factory=set)
    key_tokens: set = field(default_factory=set)

    @property
    def title(self):
        # The highest-normalised item is the most representative headline.
        return max(self.items, key=lambda i: i.meta.get("norm", 0)).title

    @property
    def urls(self):
        return [i.url for i in self.items if i.url][:4]

    def as_dict(self):
        return {"title": self.title, "score": round(self.score, 3),
                "sources": sorted(self.sources), "platforms": sorted(self.platforms),
                "size": len(self.items),
                "urls": self.urls,
                "items": [{"source": i.source, "title": i.title, "url": i.url,
                           "engagement": i.engagement, "detail": i.detail}
                          for i in self.items[:6]]}


def cluster(items, threshold=0.34):
    """Greedy single-pass clustering on title-token Jaccard.

    The point is not perfect topic modelling — it is detecting that the same
    story showed up on three platforms, which is the signal the article picker
    actually needs.
    """
    clusters = []
    for it in sorted(items, key=lambda i: -i.meta.get("norm", 0)):
        tk = tokens(it.title)
        if len(tk) < 2:
            continue
        best, best_sim = None, 0.0
        for c in clusters:
            sim = len(tk & c.key_tokens) / max(len(tk | c.key_tokens), 1)
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= threshold:
            best.items.append(it)
            best.sources.add(it.source)
            best.platforms.add(platform_of(it))
            best.key_tokens |= tk
        else:
            clusters.append(Cluster(key=" ".join(sorted(tk)[:6]), items=[it],
                                    sources={it.source}, platforms={platform_of(it)},
                                    key_tokens=set(tk)))
    return clusters


def score_clusters(clusters):
    """Composite score. Weights chosen so cross-source corroboration can lift a
    modest-engagement topic above a single-platform spike — that is the whole
    reason for clustering."""
    for c in clusters:
        engagement = max(i.meta.get("norm", 0) for i in c.items)
        breadth = min(len(c.platforms) / 3.0, 1.0)        # 3+ platforms saturates
        volume = min(len(c.items) / 5.0, 1.0)
        freshest = min(i.age_hours for i in c.items)
        recency = math.exp(-freshest / 48.0)              # half-life ~33h
        story_bonus = 0.12 if any(i.meta.get("story") for i in c.items) else 0.0
        c.score = (0.34 * engagement + 0.30 * breadth
                   + 0.16 * volume + 0.20 * recency + story_bonus)
    clusters.sort(key=lambda c: -c.score)
    return clusters


def research_sweep(only=None, quiet=False):
    """Full pipeline: fetch -> normalise -> cluster -> score."""
    items, health = fetch_all(only=only, quiet=quiet)
    normalize(items)
    clusters = score_clusters(cluster(items))
    if not quiet:
        multi = sum(1 for c in clusters if len(c.platforms) > 1)
        print(f"[research] {len(clusters)} clusters, {multi} corroborated across 2+ platforms")
    return clusters, health, items


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT FORMATTING — a ranked, pre-computed brief instead of a flat dump.
# ═══════════════════════════════════════════════════════════════════════════════


def format_clusters(clusters, limit=18):
    lines = ["RANKED SIGNAL CLUSTERS (score computed from within-source engagement",
             "percentile, cross-source corroboration, item volume and recency —",
             "these numbers are measured, not estimated. Trust the ordering.)", ""]
    for i, c in enumerate(clusters[:limit], 1):
        srcs = "+".join(sorted(c.platforms))
        flag = "  <-- CORROBORATED" if len(c.platforms) >= 3 else ""
        lines.append(f"{i:2d}. [{c.score:.2f}] {c.title[:110]}{flag}")
        lines.append(f"      sources: {srcs} ({len(c.items)} items)")
        for it in sorted(c.items, key=lambda x: -x.meta.get("norm", 0))[:3]:
            eng = f"{int(it.engagement)}" if it.engagement else "-"
            lines.append(f"      · [{it.source}/{it.detail[:22]}] {it.title[:78]} ({eng})")
        if c.urls:
            lines.append(f"      url: {c.urls[0]}")
    return "\n".join(lines)


def format_stories(clusters, limit=12):
    """Clusters containing a real, citable indie-builder post."""
    out = []
    for c in clusters:
        for it in c.items:
            if it.meta.get("story") and it.url:
                out.append(it)
    if not out:
        return ""
    seen, lines = set(), ["REAL DEVELOPER STORIES (real URLs — cite these, never invent numbers):"]
    # Income-angle posts first: this block exists so the writer cites a real
    # revenue/launch number instead of inventing one, and those are the only
    # items that carry one. Engagement breaks the tie within each group.
    for it in sorted(out, key=lambda i: (not i.meta.get("income_angle"),
                                         -i.meta.get("norm", 0))):
        key = it.title.lower()[:70]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  • [{it.source}] {it.title[:110]}")
        if it.meta.get("snippet"):
            lines.append(f"      {it.meta['snippet'][:140]}")
        lines.append(f"      signal: {it.detail}  |  URL: {it.url}")
        if len(seen) >= limit:
            break
    return "\n".join(lines)


def format_health(health):
    ok = [h for h in health if h.status == "ok"]
    bad = [h for h in health if h.status not in ("ok",)]
    out = f"SOURCE HEALTH: {len(ok)}/{len(health)} sources returned data."
    if bad:
        out += " Degraded: " + ", ".join(f"{h.name}({h.status})" for h in bad)
        out += "\nTreat the missing platforms as unknown, not as absent interest."
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# LIBRARY — persistent archive so novelty is checked against every past run.
# ═══════════════════════════════════════════════════════════════════════════════


def library_append(record):
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
    with io.open(LIBRARY_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return LIBRARY_PATH


def library_read(limit=None):
    if not os.path.exists(LIBRARY_PATH):
        return []
    rows = []
    with io.open(LIBRARY_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-limit:] if limit else rows


def library_titles(limit=200):
    out = []
    for row in library_read():
        out.extend(row.get("titles", []))
    return out[-limit:]


def library_search(query, limit=20):
    q = tokens(query)
    if not q:
        return []
    scored = []
    for row in library_read():
        for t in row.get("titles", []):
            overlap = len(q & tokens(t)) / max(len(q), 1)
            if overlap > 0:
                scored.append((overlap, row.get("ts", ""), t))
        for c in row.get("clusters", []):
            overlap = len(q & tokens(c.get("title", ""))) / max(len(q), 1)
            if overlap > 0:
                scored.append((overlap, row.get("ts", ""), c.get("title", "")))
    scored.sort(key=lambda x: (-x[0], x[1]))
    seen, out = set(), []
    for ov, ts, t in scored:
        if t.lower() in seen:
            continue
        seen.add(t.lower())
        out.append({"overlap": round(ov, 2), "ts": ts, "title": t})
        if len(out) >= limit:
            break
    return out


def novelty(title, history=None, threshold=0.55):
    """Return (is_novel, closest_past_title, similarity)."""
    history = library_titles() if history is None else history
    tk = tokens(title)
    if not tk:
        return True, "", 0.0
    best, best_sim = "", 0.0
    for past in history:
        sim = len(tk & tokens(past)) / max(len(tk | tokens(past)), 1)
        if sim > best_sim:
            best, best_sim = past, sim
    return best_sim < threshold, best, round(best_sim, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "doctor":
        print("Probing every source (this is the --doctor equivalent)...\n")
        t0 = time.time()
        _, health = fetch_all()
        print(f"\nTotal {time.time() - t0:.1f}s")
        print(format_health(health))
        broken = [h for h in health if h.status in ("failed", "timeout")]
        for h in broken:
            print(f"\n{h.name}: {h.error}")
        sys.exit(1 if broken else 0)

    elif cmd == "search":
        q = " ".join(sys.argv[2:])
        if not q:
            print("Usage: python research_engine.py search <query>")
            sys.exit(2)
        hits = library_search(q)
        if not hits:
            print(f"No past coverage of '{q}' in {LIBRARY_PATH}")
        for h in hits:
            print(f"  {h['overlap']:.2f}  {h['ts'][:10]}  {h['title']}")

    elif cmd == "scan":
        t0 = time.time()
        clusters, health, items = research_sweep()
        print(f"\nswept in {time.time() - t0:.1f}s\n")
        print(format_clusters(clusters, limit=15))
        stories = format_stories(clusters)
        if stories:
            print("\n" + stories)
        print("\n" + format_health(health))

    else:
        print(__doc__)
