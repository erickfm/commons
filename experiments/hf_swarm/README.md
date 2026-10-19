# Hugging Face "swarm-agent" Spaces (Oct 12 2026)

Our Hugging Face new-repo watcher caught an account, **`outnnnnnn`** (display name "nnnnnn"),
publish **20 Spaces named `swarm-agent-0` … `swarm-agent-19`** within about one minute, at
**07:00:18–07:01:04 UTC on 12 October 2026**.

As of **19 October** the account and all 20 Spaces return 404 — Hugging Face removed them, or
the owner deleted them. The Wayback Machine and archive.today have no captures.

## What we have

`records.jsonl` — the 20 listing records our watcher saved when the Spaces appeared (id, author,
createdAt, tags, sdk, cardData). This is listing metadata only; it does **not** contain the Spaces'
file contents.

## What the code looked like (read live on Oct 12, not saved)

At the time, each Space's `app.py` held Python that:
- targeted a class of networked device over HTTP,
- attempted a known admin-authentication bypass,
- and, on success, retrieved and encrypted that device's stored login credentials.

In plain terms: 20 copies of an autonomous credential-harvesting agent, numbered like a fleet.

## Important caveats

- **Read, never run.** We read the code; we did not execute it and contacted no target. We cannot
  confirm it works or that it collected anything.
- **Declared `static`.** Every Space's card declared `sdk: static`, which means Hugging Face serves
  the files but does **not** run `app.py`. So the code was **staged/hosted** across 20 Spaces rather
  than proven to be executing on Hugging Face's own infrastructure. It may have been pulled and run
  elsewhere, staged for later, or simply dumped there.
- **Operator unknown.** We have no identity, no target list, and no evidence of real-world impact.
- **Code not preserved.** Only the listing metadata survives in our logs; the Spaces are gone.

## Why it mattered for the watch

This is the closest thing the swarm watch found to its target: many agent-shaped artifacts, created
together, built for a single harmful purpose, on live public infrastructure — and not previously
reported. It was caught by the Hugging Face burst detector (one publisher, many new repos at once).
