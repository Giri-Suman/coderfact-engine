# Promo pack — Build SaaS With Cursor: How I Built a $19 App in 11 Hours

Article: https://github.com/Giri-Suman/coderfact-engine/blob/main/medium_drafts/build-saas-with-cursor-how-i-built-a-19-app-in-11-hours.md

## LinkedIn

_Hook (47 chars — fits):_ 11 hours. One SaaS. Nineteen dollars a product.

_Full post — 1132 / 3000 chars_

```text
11 hours was all it took to ship one SaaS that charges nineteen dollars a product.

The app is a text-draft scanner that flags 33 distinct AI-writing patterns, useful for anyone cleaning up LLM output before shipping it. Checkout was the real obstacle. Stripe webhooks need to reconcile against a database without manual babysitting, and writing that handler by hand usually eats a full afternoon.

Cursor's Composer mode wrote a working Next.js route handler for Stripe webhooks in under five minutes. The steering prompt that produced it is the actual centerpiece of the writeup, pasted verbatim so you can run it against your own stack.

The build touched the checkout flow, webhook handler, and the pattern-scanning endpoint. Eleven hours from zero to a live, paid product at coderfact.com.

If you are using Stripe in a Next.js app, do not handwrite the webhook signature verification. Pass the raw body to Stripe's constructEvent and verify against your webhook secret. Skip that step and your endpoint silently accepts forged events.

Full breakdown, including the steering prompt and the exact time split, is in the article.
```

Hashtags: #saas #nextjs #stripe #cursor

## X / Twitter thread

**1/6** _(118/280)_

```text
11 hours, one person, one Stripe checkout. Coderfact went from blank repo to a live $19 SaaS—built entirely in Cursor.
```

**2/6** _(192/280)_

```text
The hard part was never the scanner. It was the webhook handler. Stripe needs to reconcile payments against your DB without you babysitting it, and that handler usually eats a whole afternoon.
```

**3/6** _(185/280)_

```text
I opened Cursor's Composer mode and pointed it at the failing webhook. The steering prompt I used is the real takeaway—it's specific, short, and named after the exact thing it produces.
```

**4/6** _(181/280)_

```text
It wrote a working Next.js route handler in under 5 minutes. One line I kept reusing: const event = stripe.webhooks.constructEvent(req.body, sig, process.env.STRIPE_WEBHOOK_SECRET);
```

**5/6** _(161/280)_

```text
End to end: 33 AI-writing patterns detected, Stripe checkout live, webhooks verified. Eleven hours total. The scanner itself was the smallest slice of that time.
```

**6/6** _(237/280)_

```text
Full breakdown, including the steering prompt and the time split, is in the article: https://coderfact.com

https://github.com/Giri-Suman/coderfact-engine/blob/main/medium_drafts/build-saas-with-cursor-how-i-built-a-19-app-in-11-hours.md
```

Hashtags: #saas #cursor #stripe

## X — single post version

_141/280 chars_

```text
11 hours. One person. Cursor's Composer mode wrote a Stripe webhook handler in under 5 minutes. Full build breakdown at https://coderfact.com
```

---
AI-tell scores: linkedin 100/100, x 100/100

---
*Promo pack for Suman Giri, generated from the finished article.*