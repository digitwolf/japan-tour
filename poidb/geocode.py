#!/usr/bin/env python3
"""Refine POI coordinates to precise per-POI lat/lng via the Google Geocoding API,
writing results into poidb/coords.json's `geo` map (which both gen_data.py and
build_store.py consume). Run in an environment that has network + the key.

  python3 poidb/geocode.py --dry-run     # list POIs that would be geocoded
  python3 poidb/geocode.py               # geocode dest-approx / missing-coord POIs

Key: read from ~/google_maps.key (never committed). Coarse 'dest-approx' coords are
fine for region/day queries; geocoding upgrades them to real points for radius
searches. After running, re-run build_store.py and validate.py.
"""
import os, sys, json, time, urllib.parse, urllib.request

HERE = os.path.dirname(__file__)
CJSON = os.path.join(HERE, "coords.json")
KEYFILE = os.path.expanduser("~/google_maps.key")

def load_key():
    if not os.path.exists(KEYFILE):
        sys.exit(f"no key at {KEYFILE} — geocoding needs the Google Maps key (see CLAUDE.md)")
    return open(KEYFILE).read().strip()

def geocode(query, key):
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(
        {"address": query + ", Japan", "key": key, "region": "jp"})
    with urllib.request.urlopen(url, timeout=15) as r:
        j = json.load(r)
    if j.get("status") == "OK":
        loc = j["results"][0]["geometry"]["location"]
        return f"{loc['lat']:.5f},{loc['lng']:.5f}"
    return None

def main():
    dry = "--dry-run" in sys.argv
    recs = [json.loads(l) for l in open(os.path.join(HERE, "pois.jsonl"), encoding="utf-8") if l.strip()]
    coords = json.load(open(CJSON, encoding="utf-8"))
    # candidates: coarse or missing coords, with something searchable
    todo = []
    for r in recs:
        if r.get("geo_source") in ("dest-approx", None):
            q = r.get("q") or f"{r['name']}"
            if q and q not in coords["geo"]:
                todo.append((q, r["name"]))
    todo = sorted(set(todo))
    print(f"{len(todo)} POI(s) to geocode")
    if dry:
        for q, n in todo: print(f"  would geocode: {q}   ({n})")
        return
    key = load_key()
    added = 0
    for q, n in todo:
        try:
            ll = geocode(q, key)
        except Exception as e:
            print(f"  ! {q}: {e}"); continue
        if ll:
            coords["geo"][q] = ll; added += 1
            print(f"  + {q} -> {ll}")
        else:
            print(f"  ? {q}: no result")
        time.sleep(0.2)
    json.dump(coords, open(CJSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"wrote {added} new coords to coords.json — now re-run build_store.py && validate.py")

if __name__ == "__main__":
    main()
