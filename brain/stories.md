# Stories

Things that actually happened, with numbers I can defend. These are the figures
the writer is allowed to treat as verified — `claims.py` stamps them `BRAIN` and
flags anything else as unsourced.

Rule for this file: if I cannot re-run a command and get the number back, it does
not go in. Every entry below has a check line you can paste into a terminal.

---

## 20 of 25 mermaid diagrams in my own published posts were broken images
- when: 2026-08
- numbers: 20 of 25, 25 diagrams, 80%
- source:
- tags: python, base64, mermaid, markdown, debugging

The engine converts mermaid blocks to mermaid.ink image URLs before publishing.
It encoded the diagram with `base64.b64encode`, which emits `+` and `/`. A `/`
inside a URL path segment does not encode a diagram, it ends the route. Every
diagram whose payload happened to contain one rendered as a dead image, and I
had been shipping them for months without opening a single published post to
look. `base64.urlsafe_b64encode` is the whole fix — same length, different
alphabet. The bug is not that the code was wrong, it is that a broken image
never raises.

Check: `python -c "import re,glob,base64; urls=[u for f in glob.glob('medium_drafts/*.md') for u in re.findall(r'mermaid.ink/img/([^)?\s]+)', open(f,encoding='utf-8').read())]; print(len(urls), sum(1 for u in urls if '+' in u or '/' in u))"`

---

## A Show HN post from 2011 was scored as three-day-fresh trending signal
- when: 2026-08
- numbers: 38 of 40, 5260 days, 1 item, 40 items, 30 days
- source: https://hn.algolia.com/api/v1/search
- tags: python, api, algolia, research, data-quality

Two bugs stacked. Algolia's `/search` sorts by relevance across all time unless
you constrain it, so the "trending launches" query was returning the best Show
HN posts of the last fifteen years — 38 of the 40 results were older than a
month, the oldest 5,260 days. On top of that the code hardcoded `age_hours=72`,
so every one of them was fed to the topic researcher as three days old. The
recency weighting was working perfectly on numbers that were fiction.

It also filtered launches by income keywords in the *title*, which dropped 39 of
40 — "Show HN: I made an open-source laptop from scratch" contains no `$`. The
source returned one item and nobody noticed, because one item looks like a quiet
day rather than a broken query.

Check: `python -c "import research_engine as R; i=R.src_show_hn(); print(len(i), round(max(x.age_hours for x in i)/24), 'days')"`

---

## Every article my own engine had written scored as machine-written
- when: 2026-08
- numbers: 14 of 15, 2 to 48, 33 patterns
- source:
- tags: writing, llm, detection, python

I built a detector for the 33 AI-writing patterns and ran it on my own back
catalogue first, expecting a calibration baseline. Fourteen of fifteen drafts
scored under 35 out of 100. The range was 2 to 48.

The specific failure was funnier than the score. The drafts were full of exact
phrases from an older version of my own prompt — "I spent three hours on this.
THREE hours.", "Sound familiar?", "It was 1am." I had written those into the
prompt as *examples of voice*, and the model had copied them verbatim into every
article. I had been mass-producing my own tell.

Check: `python humanizer.py "medium_drafts/*.md"`

---

## Half my published posts contain numbers with no source at all
- when: 2026-08
- numbers: 8 of 16, 0%, 9 figures
- source:
- tags: writing, fact-checking, llm, credibility

After building a claims map that labels every figure with where it came from,
eight of sixteen drafts came back at 0% sourced. One post claims `$200` saved in
its own title and repeats it four more times in the body; the number exists
nowhere except the model's imagination. Another carries a `47 minutes → 3
minutes` benchmark that turned out to be the placeholder from my own outline
prompt, which the model reused as if it were a measurement.

Nothing about that was malicious. The prompt asked for a specific number and
specificity is what these models are trained to produce. The fix is not a
sterner instruction, it is giving the writer real numbers to reach for.

Check: `python claims.py "medium_drafts/*.md"`
