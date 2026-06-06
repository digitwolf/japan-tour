# POI database — design

A system for storing the trip's points of interest with their **GPS locations** and the
**metadata that drives planning decisions**, so the tour-planning agent can *query* the
trip instead of re-reading prose. Implemented under [`../poidb/`](../poidb/README.md).

## Problem

Before this, POI knowledge was scattered and not queryable:

- **`gen_data.py`** held the machine data — but POIs (`DAYS[].poi[]`) carried only a `q`
  *text* string that geocodes at *runtime* via Google Maps; there were **no stored
  coordinates**, so "what's within 20 km of the Day-13 route?" was unanswerable.
- **`research/` and `interests/`** hold rich POI facts (opening/closed days, reservations,
  kid flags, interest tags, fit tags, sources) — but as **prose** across many files. The
  agent had to read everything and reason; nothing was filterable or geo-aware.
- **Family-fit** (food / Ghibli / onsen / Nintendo / riding) was scored by hand each time.

## Design choices (decided with the user)

1. **Full build, structured-first.** Build the store *and* a semantic layer now — but the
   semantic layer is **structured tags + lexical relevance search that the agent reasons
   over**, *not* an embedding/vector service. Rationale below.
2. **Agent + build-pipeline only.** The store is a planning/generation asset. The website
   stays 100% static — nothing new is shipped to the browser.
3. **Single source of truth for coordinates.** Coordinates + wiki links live in
   `poidb/coords.json`, consumed by **both** `gen_data.py` (→ `data.js`) and the store.

## Architecture

```
                 ┌─────────────────────────────────────────────┐
  SOURCES        │  tour/*.md  ·  interests/*.md  ·  gen_data.DAYS│   (markdown = source of record)
                 └───────────────┬───────────────┬──────────────┘
                                 │               │
   poidb/coords.json  ◀──────────┘               │   (canonical coords + wiki)
        │   │                                     │
        │   └──────────────► gen_data.py ─────────┼─────────► data.js ───► static site (unchanged)
        │                                         │
        ▼                                         ▼
  build_store.py  ◀── overlay.jsonl  ◀────  interests/*.md  +  DAYS[].poi[]
        │
        ▼
   poidb/pois.jsonl  ──────►  query.py  ──────►  tour-expert agent (plans)
                                 ▲
                          validate.py / geocode.py
```

- The store is a **derived, enriched index** over the markdown sources — it never competes
  with them. Re-running `build_store.py` reproduces it; `gen_data.py` still emits a
  **byte-identical `data.js`** (verified).
- **One record per POI**, normalized to a [schema](../poidb/SCHEMA.md): id, name, coords +
  `geo_source`, **interest tags** (mapped to `tour/00-family.md`), kid flag, open/closed
  days, reservation, cost, dwell, **fit** (`on-route`/`near-route`/`bookend`/`off-route`),
  day + destination, sources, provenance.
- **Coordinates** come from `coords.json`'s `GEO` map where the POI's query string is known
  (precise), else the destination centroid (`dest-approx`, coarse but enough for
  region/day queries). `geocode.py` upgrades coarse points to precise ones when a Google
  key + network are available.

## Why structured-first, not a vector database

A vector DB was considered and deliberately deferred:

- **Scale doesn't need it.** ~120 POIs. Brute-force filtering + lexical scoring is instant;
  a vector index earns its keep at 10⁴–10⁶ items, not 10².
- **The reasoner is already semantic.** The consumer is Claude (the tour-expert). Given
  well-structured tags + filtered candidates, it does the fuzzy interest-matching far
  better than cosine similarity over a fixed embedding — and explains its picks.
- **No new dependencies / offline.** Embeddings need a provider (Anthropic has no embedding
  API; Voyage AI would need a key + network) and a build step — both cut against this
  project's static, no-build, no-dependency ethos.
- **The hard win was geometry + clean attributes, not similarity.** Stored lat/lng + tags +
  hours unlock the queries that were actually missing.

`query.py --text` provides a lexical-relevance search (term frequency over name/summary/
tags) as the lightweight semantic entry point. **If** the corpus grows (merge all of
`research/`, add hundreds of candidate POIs) and lexical search starts missing paraphrases,
Phase 4 below adds an **offline embedding index** (precompute vectors to a flat file,
brute-force cosine in Python) — still no server, no runtime dependency.

## Roadmap

- **Phase 1 — store + coords (done).** Coordinates extracted to `coords.json`; `gen_data.py`
  consumes it; `data.js` unchanged.
- **Phase 2 — migration + tooling (done).** 124 POIs from the itinerary + `interests/`;
  `query.py`, `validate.py`, `overlay.jsonl`.
- **Phase 3 — refine (incremental).** Run `geocode.py` to make all coords precise; curate
  `dwell_min`/`cost_jpy`/`open_days` in `overlay.jsonl`; ingest `research/places-to-visit.md`.
- **Phase 4 — optional vectors.** Only if the corpus outgrows lexical search: an offline
  embedding index, loaded by `query.py --semantic`. No service.
- **Phase 5 — deeper pipeline use.** Let `gen_data.py` source day POIs from the store so
  per-day luggage notes / new stops flow to the site automatically (keeps the site static).

## For the planning agent

Query the store **before** adding or rerouting content — see
[`../poidb/README.md`](../poidb/README.md) for commands. The store answers "what's near
here, open then, kid-ok, and does this family love it?"; the agent still owns the judgement.
