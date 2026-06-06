# POI store schema (`pois.jsonl`)

One JSON object per line (JSONL — git-diff-friendly, append-friendly). Built by
`build_store.py`; never hand-edit `pois.jsonl` (edit the sources or `overlay.jsonl`).

| Field | Type | Meaning |
|-------|------|---------|
| `id` | string | Stable slug, unique. Itinerary POIs: `<dest>-<name>` (`-dN` on collision). Overlay key. |
| `name` | string | Display name (English). |
| `name_jp` | string\|null | Japanese name if known. |
| `category` | string | `onsen, museum, castle, shrine, temple, market, food, beach, waterfall, gorge, bridge, viewpoint, craft, art, garden, aquarium, themepark, shop, nature, poi…` |
| `lat`,`lng` | number\|null | Coordinates. `null` until geocoded. |
| `geo_source` | enum | `geo-map` (precise, from coords.json GEO) · `geocoded` (Google) · `curated` (overlay) · `dest-approx` (destination centroid — coarse) · `null`. |
| `interest_tags` | string[] | Family-interest vocab: `motorcycles, food, ramen-noodles, ghibli, onsen, nintendo, toys-anime, art, kids, history-culture, nature`. Drives `--score`. |
| `kid_friendly` | bool\|null | Suitable for the 6-year-old. |
| `dwell_min` | int\|null | Typical visit length (minutes). |
| `cost_jpy` | int\|null | Adult admission (¥). |
| `open_days` / `closed_days` | string[]\|null | `Mon…Sun`. `--open <weekday>` filters out POIs closed that day. |
| `reservation` | bool\|null | Needs advance/timed ticket. |
| `fit` | enum | `on-route` · `near-route` · `bookend` (Tokyo/Osaka city days) · `off-route` (listed for awareness). |
| `day` | int\|null | Itinerary day (Day 0–25). For interest POIs, derived from the destination. |
| `destination` | string\|null | Destination id (`osaka, koyasan, kochi, …`). |
| `slot` | string\|null | Itinerary slot (`morning, lunch, activity, scenic, stop, coffee…`). |
| `summary` | string | One/two-line description. |
| `sources` | string[] | Source URLs. |
| `wiki` | string\|null | Verified Wikipedia article. |
| `img` | string\|null | Thumbnail (Wikimedia). |
| `q` | string\|null | Google-Maps query string (used by `geocode.py`). |
| `origin` | string[] | Provenance: `itinerary`, `interests:<file>`, `overlay`. |

## Curation overlay (`overlay.jsonl`)
One JSON object per line, keyed by `id`; every field **overrides** the extracted value
(supplying `lat`/`lng` marks the record `curated`). This is where precise coords, dwell
times, corrected tags, hours, etc. are added without touching the markdown sources, e.g.:

```json
{"id":"himeji-himeji-castle-koko-en","dwell_min":150,"kid_friendly":true,"cost_jpy":1050}
```
