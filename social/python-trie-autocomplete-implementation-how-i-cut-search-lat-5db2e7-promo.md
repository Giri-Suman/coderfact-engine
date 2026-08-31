# Promo pack — Python Trie Autocomplete Implementation: How I Cut Search Latency to P99 0ms

Article: https://github.com/Giri-Suman/coderfact-engine/blob/main/medium_drafts/python-trie-autocomplete-implementation-how-i-cut-search-lat-5db2e7.md

> **Check before posting**
> - X posts still over 280 chars: [6]

## LinkedIn

_Hook (173 chars — fits):_ At 02:14 on Tuesday, a linear scan over a 2MB dictionary file pushed P99 latency to 820ms under load, triggering HTTP 504 gateway timeouts on our CoderFact FastAPI endpoint.

_Full post — 1012 / 3000 chars_

```text
At 02:14 on Tuesday, a linear scan over a 2MB dictionary file pushed P99 latency to 820ms under load, which triggered immediate HTTP 504 gateway timeouts on the CoderFact FastAPI endpoint and proved that the linear scan autocomplete approach completely fell apart under load.

The system required a complete rebuild around a dedicated prefix tree structure.

The implementation used a flat `__slots__` based Trie using `list[int]` child indices to avoid dictionary overhead—a design choice combined with a pickle-based disk cache.

Defining `__slots__ = ('children', 'is_end_of_word', 'weight')` on Trie nodes in Python 3.11 avoids the memory overhead of instance dictionaries and keeps lookups fast.

This optimization dropped search P99 latency from 820ms to 0.4ms, while using 60% less RAM and increasing throughput by 12x.

Read the full implementation details here: https://github.com/Giri-Suman/coderfact-engine/blob/main/medium_drafts/python-trie-autocomplete-implementation-how-i-cut-search-lat-5db2e7.md
```

Hashtags: #python #backend #performance

## X / Twitter thread

**1/6** _(205/280)_

```text
A linear scan over a 2MB dictionary file pushed P99 latency to 820ms under 200 concurrent users, triggering HTTP 504 gateway timeouts on our FastAPI endpoint. Here is how we rebuilt it to run in under 1ms.
```

**2/6** _(180/280)_

```text
Our initial autocomplete relied on a simple linear scan. Under concurrent load testing, this list-comprehension-based approach choked, forcing us to abandon linear search entirely.
```

**3/6** _(191/280)_

```text
The root cause was the overhead of scanning the raw dataset repeatedly. We needed a dedicated prefix tree structure that could handle high-throughput lookups without consuming massive memory.
```

**4/6** _(161/280)_

```text
We built a flat Trie using `__slots__ = ('children', 'is_end_of_word', 'weight')` and child indices instead of dictionaries, backed by a pickle-based disk cache.
```

**5/6** _(140/280)_

```text
The results: search P99 latency dropped from 820ms to 0.4ms. The optimized Python Trie achieved 12x throughput while consuming 60% less RAM.
```

**6/6** _(333/280)  ⚠️ OVER BY 53_

```text
Read the full step-by-step implementation guide: https://github.com/Giri-Suman/coderfact-engine/blob/main/medium_drafts/python-trie-autocomplete-implementation-how-i-cut-search-lat-5db2e7.md

https://github.com/Giri-Suman/coderfact-engine/blob/main/medium_drafts/python-trie-autocomplete-implementation-how-i-cut-search-lat-5db2e7.md
```

Hashtags: #python #fastapi

## X — single post version

_262/280 chars_

```text
FastAPI linear scan hit 820ms P99 latency. A flat `__slots__` Trie cut it to 0.4ms with 60% less RAM and 12x throughput: https://github.com/Giri-Suman/coderfact-engine/blob/main/medium_drafts/python-trie-autocomplete-implementation-how-i-cut-search-lat-5db2e7.md
```

---
AI-tell scores: linkedin 100/100, x 100/100

---
*Promo pack for Suman Giri, generated from the finished article.*