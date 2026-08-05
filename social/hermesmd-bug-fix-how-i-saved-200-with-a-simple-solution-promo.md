# Promo pack — The HERMES.md config flag that cost me 40 minutes per run

Article: https://coderfact.com

## LinkedIn

_Hook (74 chars — fits):_ HERMES.md returned null for forty minutes and never raised a single error.

_Full post — 733 / 3000 chars_

```text
HERMES.md returned null for forty minutes and never raised a single error.

The parser accepted the file, ran to completion, and handed back nothing. No exception, no warning, no non-zero exit. So I did what you do: reparsed by hand, checked the file encoding, blamed the markdown.

It was parseMarkdown: true in the config.

That flag makes the parser hand off to an internal path that fails silently on files it does not recognise. Flip it off and the same file parses in 90 seconds instead of the 40-minute manual round trip.

The lesson is not about HERMES.md. It is that a library returning null without an error is a library telling you to read its config, not your data.

Writeup with the before-and-after config on CoderFact.
```

Hashtags: #javascript #debugging #webdev

## X / Twitter thread

**1/6** _(100/280)_

```text
HERMES.md parsed my file, returned null, and raised nothing. No error, no warning, no non-zero exit.
```

**2/6** _(95/280)_

```text
So I reparsed by hand, checked the file encoding, and spent forty minutes blaming the markdown.
```

**3/6** _(36/280)_

```text
It was one line: parseMarkdown: true
```

**4/6** _(88/280)_

```text
That flag routes to an internal path that fails silently on files it does not recognise.
```

**5/6** _(76/280)_

```text
Flipped it off. Same file, 90 seconds. The manual round trip was 40 minutes.
```

**6/6** _(123/280)_

```text
A library returning null without an error is telling you to read its config, not your data. Writeup:

https://coderfact.com
```

Hashtags: #javascript #debugging

## X — single post version

_144/280 chars_

```text
HERMES.md returned null for 40 minutes with no error. The cause was parseMarkdown: true routing to a path that fails silently. Off = 90 seconds.
```

---
AI-tell scores: linkedin 100/100, x 100/100

---
*Promo pack for Suman Giri, generated from the finished article.*