# Voice samples

Drop 2–5 `.md` or `.txt` files here containing prose **you actually wrote** —
not AI drafts, not anything this engine produced. Old blog posts, long Slack
messages, commit-message essays, README sections all work. Each file needs to be
longer than 300 characters or it is ignored.

When files are present, `humanizer.py` measures them and injects a fingerprint
into the rewrite prompt instead of the generic persona description:

- average sentence length, range, and variance
- what share of sentences are five words or shorter
- contractions and first-person density per 1000 words
- which punctuation habit is actually yours (parentheses vs em-dash vs semicolon)
- the non-stopword vocabulary you reach for repeatedly

Numbers beat adjectives here. "Casual dev voice" means nothing to a model;
"average 14 words, range 3–38, 22% of sentences under five words" is
reproducible.

Check it is working:

```bash
python agent.py doctor
```

The config block reports `voice samples: N (fingerprint active)`.

Point it somewhere else with `VOICE_SAMPLES_DIR=/path/to/samples`.

Only this README is committed — sample files are gitignored so your personal
writing does not end up in a public repo.
