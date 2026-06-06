#!/usr/bin/env python3
"""Query the POI store (poidb/pois.jsonl) — the tour-expert's planning tool.

Composable filters + geo + lexical search + family-fit scoring. Dependency-free.

Examples
--------
  # Onsen on/near the Day-13 route, kid-friendly, sorted by distance to that day:
  python3 poidb/query.py --tags onsen --near-day 13 --radius 40 --kid

  # Best family-fit POIs around the Iya base, top 8 as a table:
  python3 poidb/query.py --near-dest iya --radius 30 --score --limit 8

  # Lexical "semantic" search the agent can reason over:
  python3 poidb/query.py --text "hands-on craft a 6-year-old can do" --limit 10

  # What ramen/noodle spots are on-route? (ids only, to feed another step)
  python3 poidb/query.py --tags ramen-noodles --fit on-route --format ids

  # Everything within 25 km of a raw point, as JSON:
  python3 poidb/query.py --near 34.59,133.77 --radius 25 --format json
"""
import os, sys, json, math, argparse, re

HERE = os.path.dirname(__file__)
STORE = os.path.join(HERE, "pois.jsonl")
COORDS = json.load(open(os.path.join(HERE, "coords.json"), encoding="utf-8"))

# Family-fit weights, derived from tour/00-family.md (Galiya: food/ghibli/onsen/art;
# Aslan: nintendo/toys/kids; Ruslan: motorcycles/riding). Override with --weights.
WEIGHTS = {"food": 3, "ramen-noodles": 3, "ghibli": 3, "onsen": 3, "nintendo": 3,
           "art": 2, "toys-anime": 2, "motorcycles": 2, "kids": 2,
           "history-culture": 1, "nature": 1}

def load():
    return [json.loads(l) for l in open(STORE, encoding="utf-8") if l.strip()]

def haversine(a, b):
    (la1, lo1), (la2, lo2) = a, b
    R = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))

def resolve_point(spec, pois):
    """--near accepts 'lat,lng', a POI id, or a place/dest name."""
    if re.match(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?$", spec):
        la, lo = spec.split(","); return float(la), float(lo)
    if spec in COORDS["dest_coords"]:
        la, lo, _ = COORDS["dest_coords"][spec]; return la, lo
    for p in pois:
        if p["id"] == spec and p["lat"] is not None:
            return p["lat"], p["lng"]
    if spec in COORDS["geo"]:
        la, lo = COORDS["geo"][spec].split(","); return float(la), float(lo)
    return None

def day_point(n, pois):
    """Centroid of a day's geolocated POIs, else its destination coords."""
    pts = [(p["lat"], p["lng"]) for p in pois if p.get("day") == n and p["lat"] is not None]
    if pts:
        return sum(x for x, _ in pts) / len(pts), sum(y for _, y in pts) / len(pts)
    for p in pois:
        if p.get("day") == n and p.get("destination") in COORDS["dest_coords"]:
            la, lo, _ = COORDS["dest_coords"][p["destination"]]; return la, lo
    return None

def lexical_score(p, terms):
    hay_name = (p["name"] + " " + (p.get("name_jp") or "")).lower()
    hay_body = ((p.get("summary") or "") + " " + " ".join(p["interest_tags"]) + " " +
                (p.get("category") or "")).lower()
    s = 0.0
    for t in terms:
        s += 3 * hay_name.count(t) + hay_body.count(t)
    return s

def fit_score(p, weights):
    s = sum(weights.get(t, 0) for t in p["interest_tags"])
    if p.get("kid_friendly"): s += 1
    s += {"on-route": 2, "near-route": 1}.get(p["fit"], 0)
    return s

def main():
    ap = argparse.ArgumentParser(description="Query the trip POI store.")
    ap.add_argument("--tags", help="comma list; POI must carry ANY (or ALL with --all-tags)")
    ap.add_argument("--all-tags", action="store_true", help="require ALL --tags")
    ap.add_argument("--category", help="comma list of categories")
    ap.add_argument("--fit", help="comma list: on-route,near-route,bookend,off-route")
    ap.add_argument("--day", type=int, help="exact itinerary day")
    ap.add_argument("--dest", help="destination id")
    ap.add_argument("--kid", action="store_true", help="kid_friendly only")
    ap.add_argument("--open", dest="open_day", help="open on this weekday (Mon..Sun)")
    ap.add_argument("--max-cost", type=int, help="adult cost <= yen (unknown cost passes)")
    ap.add_argument("--text", help="lexical relevance search over name/summary/tags")
    ap.add_argument("--near", help="'lat,lng' | POI id | dest id — distance anchor")
    ap.add_argument("--near-day", type=int, help="anchor = that day's POI centroid")
    ap.add_argument("--near-dest", help="anchor = destination coords")
    ap.add_argument("--radius", type=float, help="km cap from the anchor")
    ap.add_argument("--score", action="store_true", help="rank by family-fit score")
    ap.add_argument("--sort", choices=["dist", "score", "name", "day"], help="sort key")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--format", choices=["table", "json", "ids"], default="table")
    args = ap.parse_args()

    pois = load()
    res = list(pois)

    if args.tags:
        want = [t.strip() for t in args.tags.split(",")]
        f = (lambda p: all(t in p["interest_tags"] for t in want)) if args.all_tags \
            else (lambda p: any(t in p["interest_tags"] for t in want))
        res = [p for p in res if f(p)]
    if args.category:
        cats = {c.strip() for c in args.category.split(",")}
        res = [p for p in res if p.get("category") in cats]
    if args.fit:
        fits = {x.strip() for x in args.fit.split(",")}
        res = [p for p in res if p["fit"] in fits]
    if args.day is not None:
        res = [p for p in res if p.get("day") == args.day]
    if args.dest:
        res = [p for p in res if p.get("destination") == args.dest]
    if args.kid:
        res = [p for p in res if p.get("kid_friendly")]
    if args.open_day:
        d = args.open_day.capitalize()[:3]
        res = [p for p in res if not (p.get("closed_days") and d in p["closed_days"])]
    if args.max_cost is not None:
        res = [p for p in res if p.get("cost_jpy") is None or p["cost_jpy"] <= args.max_cost]

    anchor = None
    if args.near: anchor = resolve_point(args.near, pois)
    elif args.near_day is not None: anchor = day_point(args.near_day, pois)
    elif args.near_dest:
        if args.near_dest in COORDS["dest_coords"]:
            la, lo, _ = COORDS["dest_coords"][args.near_dest]; anchor = (la, lo)
    if anchor:
        for p in res:
            p["_dist"] = round(haversine(anchor, (p["lat"], p["lng"])), 1) if p["lat"] is not None else None
        if args.radius is not None:
            res = [p for p in res if p.get("_dist") is not None and p["_dist"] <= args.radius]

    if args.text:
        terms = [t for t in re.split(r"\W+", args.text.lower()) if len(t) > 2]
        for p in res: p["_lex"] = lexical_score(p, terms)
        res = [p for p in res if p["_lex"] > 0]
        res.sort(key=lambda p: -p["_lex"])
    if args.score:
        for p in res: p["_score"] = fit_score(p, WEIGHTS)
    sort = args.sort or ("score" if args.score else "dist" if anchor else "text" if args.text else "day")
    if sort == "dist" and anchor:
        res.sort(key=lambda p: (p.get("_dist") is None, p.get("_dist") or 1e9))
    elif sort == "score":
        res.sort(key=lambda p: -fit_score(p, WEIGHTS))
    elif sort == "name":
        res.sort(key=lambda p: p["name"].lower())
    elif sort == "day":
        res.sort(key=lambda p: (p.get("day") if p.get("day") is not None else 99, p["name"].lower()))

    res = res[:args.limit]

    if args.format == "ids":
        print("\n".join(p["id"] for p in res)); return
    if args.format == "json":
        print(json.dumps(res, ensure_ascii=False, indent=2)); return
    # table
    print(f"{len(res)} result(s)" + (f"  (anchor {anchor})" if anchor else ""))
    for p in res:
        bits = [f"D{p['day']}" if p.get("day") is not None else "—", p["fit"]]
        if p.get("_dist") is not None: bits.append(f"{p['_dist']}km")
        if args.score: bits.append(f"fit={fit_score(p, WEIGHTS)}")
        if p.get("cost_jpy"): bits.append(f"¥{p['cost_jpy']}")
        if p.get("closed_days"): bits.append("closed:" + "".join(p["closed_days"]))
        if p.get("kid_friendly"): bits.append("KID")
        tags = ",".join(p["interest_tags"][:4])
        print(f"  • {p['name']}  [{' · '.join(bits)}]")
        print(f"      {p.get('category')} | {tags} | {p['id']}")

if __name__ == "__main__":
    main()
