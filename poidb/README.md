# `poidb/` — the trip's POI knowledge base

A queryable, geo-aware index of every point of interest on (and near) the tour, mapped
to **what this family loves**. It exists so the **tour-expert** agent can *query* instead
of re-reading prose — "onsen within 40 km of the Day-13 route that's open Mondays and
kid-friendly," "best family-fit stops around the Iya base," "all on-route ramen."

It is a **planning / build-time asset** — it is **not shipped to the browser**; the
website stays exactly as static as before. See [`../docs/POI-DATABASE.md`](../docs/POI-DATABASE.md)
for the full design and the (no-)vector-DB decision.

## Files
| File | Role |
|------|------|
| `coords.json` | **Single source of truth for coordinates + wiki links.** Consumed by `../gen_data.py` (→ `data.js`) *and* `build_store.py`. |
| `pois.jsonl` | The built store (one POI per line). **Generated — don't hand-edit.** |
| `overlay.jsonl` | Hand-curated attribute overrides/additions, keyed by `id`. **Edit this** to enrich. |
| `build_store.py` | Builds `pois.jsonl` from the itinerary (`gen_data.DAYS`) + `interests/*.md` + `overlay.jsonl`. |
| `query.py` | The agent's query tool (geo + filters + lexical search + family-fit score). |
| `validate.py` | Schema / vocab / coverage checks. Run after building. |
| `geocode.py` | Upgrades coarse coords to precise lat/lng via Google Geocoding (needs key + network). |
| `SCHEMA.md` | Field reference + controlled vocabulary. |

## Workflow
```bash
python3 poidb/build_store.py     # (re)build pois.jsonl from the sources
python3 poidb/validate.py        # verify (0 errors expected)
python3 poidb/geocode.py --dry-run   # see which POIs are still coarse
python3 poidb/geocode.py         # later, where a key+network exist: refine coords
```
`build_store.py` is deterministic — a clean checkout rebuilds the same store, and
`gen_data.py` still emits a byte-identical `data.js`.

## Querying (what the agent runs)
```bash
# Onsen on/near the Day-13 route, open Mondays, kid-friendly:
python3 poidb/query.py --tags onsen --near-day 13 --radius 50 --open Mon --kid

# Best family-fit POIs around a base, ranked:
python3 poidb/query.py --near-dest dogo --radius 25 --score --limit 8

# Lexical search the agent reasons over (structured-first "semantic"):
python3 poidb/query.py --text "make your own craft for a child"

# On-route ramen/noodles, ids only (to feed another step):
python3 poidb/query.py --tags ramen-noodles --fit on-route --format ids

# Off-route/bookend options for an interest (know what exists & where):
python3 poidb/query.py --tags motorcycles --fit off-route,bookend --format table
```
Filters compose: `--tags --category --fit --day --dest --kid --open --max-cost`,
geo (`--near | --near-day | --near-dest` + `--radius`), `--text`, `--score`,
`--sort dist|score|name|day`, `--format table|json|ids`.

## How to enrich
1. **New trip facts** → edit the markdown source of record (`tour/`, `interests/`), then
   `build_store.py`. The store mirrors the sources; it never competes with them.
2. **Structured attributes that aren't in prose** (precise coords, dwell, hours, tag
   fixes) → add a line to `overlay.jsonl` (keyed by `id`), then rebuild. Overlay always wins.
