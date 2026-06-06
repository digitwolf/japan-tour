#!/usr/bin/env python3
"""Validate poidb/pois.jsonl: schema, controlled vocab, uniqueness, and coverage of
the itinerary POIs. Exit non-zero on any error. Run after build_store.py.

  python3 poidb/validate.py
"""
import os, sys, json, importlib.util

HERE = os.path.dirname(__file__); ROOT = os.path.dirname(HERE)
FIT = {"on-route", "near-route", "bookend", "off-route"}
GEO_SRC = {"geo-map", "dest-approx", "geocoded", "curated", None}
DOW = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
TAGS = {"motorcycles", "food", "ramen-noodles", "ghibli", "onsen", "nintendo",
        "toys-anime", "art", "kids", "history-culture", "nature"}
REQUIRED = {"id", "name", "category", "lat", "lng", "geo_source", "interest_tags",
            "fit", "day", "destination", "summary", "sources", "origin"}

def main():
    recs = [json.loads(l) for l in open(os.path.join(HERE, "pois.jsonl"), encoding="utf-8") if l.strip()]
    errors, warns = [], []
    seen = set()
    for r in recs:
        rid = r.get("id", "?")
        miss = REQUIRED - r.keys()
        if miss: errors.append(f"{rid}: missing fields {sorted(miss)}")
        if rid in seen: errors.append(f"{rid}: duplicate id")
        seen.add(rid)
        if r.get("fit") not in FIT: errors.append(f"{rid}: bad fit {r.get('fit')!r}")
        if r.get("geo_source") not in GEO_SRC: errors.append(f"{rid}: bad geo_source {r.get('geo_source')!r}")
        for t in r.get("interest_tags", []):
            if t not in TAGS: warns.append(f"{rid}: unknown interest tag '{t}'")
        for d in (r.get("closed_days") or []):
            if d not in DOW: errors.append(f"{rid}: bad closed_day '{d}'")
        if r.get("lat") is not None and not (-90 <= r["lat"] <= 90 and -180 <= r["lng"] <= 180):
            errors.append(f"{rid}: coords out of range ({r['lat']},{r['lng']})")
        if r.get("lat") is None: warns.append(f"{rid}: no coordinates (run geocode.py)")

    # coverage: every itinerary POI must be represented
    spec = importlib.util.spec_from_file_location("gen_data", os.path.join(ROOT, "gen_data.py"))
    gd = importlib.util.module_from_spec(spec); spec.loader.exec_module(gd)
    names = {r["name"] for r in recs}
    for d in gd.DAYS:
        for p in d["poi"]:
            if p["name"] not in names:
                errors.append(f"coverage: itinerary POI not in store: Day {d['d']} '{p['name']}'")

    print(f"records: {len(recs)}  |  with coords: {sum(1 for r in recs if r['lat'] is not None)}"
          f"  |  errors: {len(errors)}  warnings: {len(warns)}")
    for e in errors: print("  ERROR  ", e)
    for w in warns[:12]: print("  warn   ", w)
    if len(warns) > 12: print(f"  … +{len(warns)-12} more warnings")
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
