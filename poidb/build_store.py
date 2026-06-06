#!/usr/bin/env python3
"""Build the POI store (poidb/pois.jsonl) from the canonical sources.

Sources, in priority order:
  1. The itinerary  — gen_data.DAYS[].poi[]  (authoritative; real day/slot, coords via coords.json GEO)
  2. interests/*.md — family-mapped candidate POIs (### entries with [FIT] tags)
  3. overlay.jsonl  — hand-curated attribute overrides/additions, keyed by id (always wins)

Run:  python3 poidb/build_store.py      (writes poidb/pois.jsonl)
Re-runnable and deterministic. The store is a queryable INDEX over the markdown
source of record — never a competing source. See poidb/README.md and SCHEMA.md.
"""
import os, re, json, glob, unicodedata, importlib.util

HERE = os.path.dirname(__file__)
ROOT = os.path.dirname(HERE)

# ---- load the build pipeline's data (no side effects: gen_data guards its write) ----
spec = importlib.util.spec_from_file_location("gen_data", os.path.join(ROOT, "gen_data.py"))
gd = importlib.util.module_from_spec(spec); spec.loader.exec_module(gd)
COORDS = gd.COORDS            # dest id -> (lat,lng,zoom)
GEO    = gd.GEO               # google-maps query string -> "lat,lng"
DAYS   = gd.DAYS

# destination id for each day
DAY_DEST = {d["d"]: d["id"] for d in DAYS}
# representative riding day per destination (first non-rail day with that id)
DEST_DAY = {}
for d in DAYS:
    DEST_DAY.setdefault(d["id"], d["d"])

THEME_TAGS = {
    "motorcycles": ["motorcycles"],
    "food-ramen-noodles": ["food", "ramen-noodles"],
    "ghibli-miyazaki": ["ghibli"],
    "onsen-sento": ["onsen"],
    "nintendo-mario": ["nintendo"],
    "toys-anime-transformers": ["toys-anime"],
    "art-museums": ["art"],
}
# place words (in a FIT tag or name) -> destination id, to anchor non-itinerary POIs
PLACE_DEST = {
    "tokyo": "tokyo", "osaka": "osaka", "kyoto": "osaka", "koya": "koyasan",
    "yunomine": "kumano-interior", "hongu": "kumano-interior", "kumano interior": "kumano-interior",
    "nachi": "kumano", "katsuura": "kumano", "shingu": "kumano", "kushimoto": "shirahama",
    "shirahama": "shirahama", "naruto": "tokushima", "tokushima": "tokushima",
    "iya": "iya", "oboke": "iya", "kochi": "kochi", "kōchi": "kochi", "konan": "kochi", "kōnan": "kochi",
    "shimanto": "shimanto", "uwajima": "uwajima", "uchiko": "uwajima",
    "matsuyama": "dogo", "dogo": "dogo", "dōgo": "dogo", "imabari": "shimanami",
    "shimanami": "shimanami", "setoda": "onomichi", "onomichi": "onomichi",
    "kurashiki": "kurashiki", "bizen": "kurashiki", "okayama": "kurashiki", "tomonoura": "kurashiki",
    "himeji": "himeji", "kobe": "himeji", "naoshima": "kurashiki", "takamatsu": "shimanami",
    "awaji": "awaji",
}
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CATEGORY_RULES = [
    ("onsen", ["onsen", "sento", "sentō", "bath", "yu ", "-yu", "spa"]),
    ("museum", ["museum", "kaikan", "memorial hall", "collection hall"]),
    ("themepark", ["universal studios", "usj", "nintendo world", "adventure world", "anpanman",
                   "nijigen", "world ("]),
    ("shop", ["nintendo tokyo", "nintendo osaka", "pokémon", "pokemon", "den den", "donguri",
              "kiddyland", "store", "shop", "parco", "super potato"]),
    ("castle", ["castle", "-jō", "keep"]),
    ("shrine", ["taisha", "jingu", "jingū", "shrine", "torii", "inari"]),
    ("temple", ["-ji ", "temple", "okunoin", "kosanji", "kōsanji", "ishite", "shukubo", "shukubō"]),
    ("market", ["market", "ichiba", "hirome"]),
    ("food", ["ramen", "udon", "soba", "sushi", "izakaya", "gelato", "lunch", "katsuo",
              "okonomiyaki", "takoyaki", "dōtonbori", "dotonbori", "kuromon", "food"]),
    ("aquarium", ["aquarium", "kaiyukan"]),
    ("garden", ["garden", "kōraku", "ritsurin", "kōko-en", "koko-en", "-en ("]),
    ("beach", ["beach", "-hama", "sand"]),
    ("waterfall", ["falls", "waterfall", "taki"]),
    ("gorge", ["gorge", "valley", "-kyō", "kazurabashi", "vine bridge"]),
    ("bridge", ["bridge", "kaikyō", "ōhashi", "ohashi"]),
    ("viewpoint", ["observatory", "ropeway", "viewpoint", "view", "skyline", "cape", "-misaki"]),
    ("craft", ["washi", "indigo", "aizome", "pottery", "-yaki", "towel", "lacquer", "workshop", "craft"]),
    ("art", ["art", "teamlab", "noguchi", "ōhara", "ohara", "ōtsuka", "otsuka", "ghibli"]),
    ("nature", ["whirlpool", "island", "river", "park", "grove"]),
]

def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def norm(s):
    return re.sub(r"[^a-z0-9]", "", strip_accents(s).lower())

def slug(s):
    s = re.sub(r"\([^)]*\)", "", s)            # drop parenthetical (jp) names
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60]

def categorize(name, summary):
    t = (name + " " + (summary or "")).lower()
    for cat, kws in CATEGORY_RULES:
        if any(k in t for k in kws):
            return cat
    return "poi"

def infer_tags(name, summary):
    t = (name + " " + (summary or "")).lower()
    tags = set()
    pairs = {
        "motorcycles": ["motorcycle", "kawasaki", "yamaha", "honda", "suzuki", "bike museum"],
        "food": ["ramen", "udon", "soba", "sushi", "market", "ichiba", "katsuo", "gelato",
                 "okonomiyaki", "takoyaki", "seafood", "food", "lunch", "eel", "ayu"],
        "ramen-noodles": ["ramen", "udon", "soba", "noodle"],
        "ghibli": ["ghibli", "ponyo", "miyazaki", "totoro", "spirited away"],
        "onsen": ["onsen", "sento", "bath", "-yu", "hot spring"],
        "nintendo": ["nintendo", "mario", "pokémon", "pokemon"],
        "toys-anime": ["toy", "anime", "transformers", "figure", "gachapon", "den den", "kiddyland", "character"],
        "art": ["art", "museum of art", "teamlab", "noguchi", "ōhara", "ohara", "ōtsuka", "otsuka"],
        "kids": ["[kid]", "child", "kids", "family", "panda", "aquarium", "playground"],
        "nature": ["gorge", "valley", "falls", "river", "whirlpool", "cape", "beach", "island", "park"],
        "history-culture": ["castle", "shrine", "temple", "taisha", "pilgrim", "kodō", "kodo",
                            "preserved", "merchant", "old town", "sake", "craft", "washi", "indigo", "pottery"],
    }
    for tag, kws in pairs.items():
        if any(k in t for k in kws):
            tags.add(tag)
    return sorted(tags)

def coords_for(q, name, dest):
    for key in (q, name):
        if key and key in GEO:
            lat, lng = GEO[key].split(",")
            return float(lat), float(lng), "geo-map"
    if dest and dest in COORDS:
        lat, lng, _ = COORDS[dest]
        return lat, lng, "dest-approx"
    return None, None, None

# ---------- 1) itinerary POIs (authoritative) ----------
records = {}   # id -> record
def add(rec):
    records[rec["id"]] = rec

for d in DAYS:
    dest = d["id"]
    for p in d["poi"]:
        name = p["name"]
        rid = slug(f"{dest}-{name}")
        if rid in records:                       # disambiguate same dest+name across days
            rid = slug(f"{dest}-{name}-d{d['d']}")
        lat, lng, gsrc = coords_for(p.get("q"), name, dest)
        rec = {
            "id": rid, "name": name, "name_jp": None,
            "category": categorize(name, p.get("what")),
            "lat": lat, "lng": lng, "geo_source": gsrc,
            "interest_tags": infer_tags(name, p.get("what")),
            "kid_friendly": None, "dwell_min": None, "cost_jpy": None,
            "open_days": None, "closed_days": None, "reservation": None,
            "fit": "on-route", "day": d["d"], "destination": dest, "slot": p.get("slot"),
            "summary": p.get("what"), "sources": [], "wiki": p.get("wiki"),
            "img": p.get("img"), "q": p.get("q"), "origin": ["itinerary"],
        }
        add(rec)

ITIN_BY_NORM = {norm(r["name"]): r for r in records.values()}

def find_itinerary_match(name):
    n = norm(name)
    if n in ITIN_BY_NORM:
        return ITIN_BY_NORM[n]
    for k, r in ITIN_BY_NORM.items():
        if len(k) > 7 and len(n) > 7 and (k in n or n in k):  # both substantial -> avoid "osaka" in "osakacastle"
            return r
    return None

# ---------- 2) interests/*.md candidate POIs ----------
FIT_RE = re.compile(r"\*\*\[([^\]]*(?:ON-ROUTE|NEAR-ROUTE|OFF-ROUTE|BOOKEND)[^\]]*)\]\*\*")
URL_RE = re.compile(r"https?://[^\s)\]]+")
YEN_RE = re.compile(r"¥\s?([\d,]{2,})")

def parse_fit(tagtext):
    t = tagtext.upper()
    if t.startswith("ON-ROUTE"):
        return "on-route"
    if t.startswith("NEAR-ROUTE"):
        return "near-route"
    if t.startswith("OFF-ROUTE"):
        return "off-route"
    if "BOOKEND" in t:
        return "bookend"
    return "off-route"

def split_title(title):
    """'Name (jp) — Location' -> (name, jp_or_None, location)."""
    title = title.strip(" *—-")
    name = title.split(" — ")[0].strip()
    loc = title.split(" — ", 1)[1].strip() if " — " in title else ""
    # section headings like "The big one — Super Nintendo World" put the real
    # POI after the dash; swap when the pre-dash chunk is a generic lead-in
    if loc and re.match(r"^(the|other|more|retro)\b", name, re.I):
        name, loc = loc, name
    jp = None
    jm = re.search(r"\(([^)]*[一-龯ぁ-んァ-ン][^)]*)\)", name)
    if jm:
        jp = jm.group(1)
        name = re.sub(r"\s*\([^)]*\)", "", name).strip()
    return name, jp, loc

def dest_from_text(text):
    tl = strip_accents(text).lower()
    for word, dest in PLACE_DEST.items():
        if strip_accents(word).lower() in tl:
            return dest
    return None

def closed_from(text):
    out = [dow for dow in DOW if re.search(rf"closed[^.;]*\b{dow}", text, re.I)]
    return out or None

def parse_interest_file(path):
    """Extract POIs from one interests/*.md file across three unit types:
    (A) ##/###/#### headings, (B) markdown table rows, (C) standalone '- **Name**' bullets
    — keeping only units that carry a **[FIT]** tag. New records are returned; units that
    match an existing itinerary POI enrich it in place."""
    theme = os.path.splitext(os.path.basename(path))[0]
    base_tags = THEME_TAGS.get(theme, [])
    lines = open(path, encoding="utf-8").read().split("\n")
    out = []

    def emit(name, jp, fit_tag, summary, body, loc=""):
        if not name or name.upper().startswith("DAY N"):
            return
        fit = parse_fit(fit_tag)
        summary = re.sub(r"\s+", " ", summary or "").strip()[:600]
        sources = sorted(set(URL_RE.findall(body)))
        yen = YEN_RE.search(body)
        cost = int(yen.group(1).replace(",", "")) if yen else None
        reservation = bool(re.search(r"reserv|advance|timed[- ]entry|book ahead|lottery|sell out", body, re.I)) or None
        kid = ("[KID]" in body or "[KID]" in name) or None
        dest = dest_from_text(fit_tag) or dest_from_text(loc) or dest_from_text(name) or dest_from_text(summary)
        tags = sorted(set(base_tags) | set(infer_tags(name + " " + loc, summary)))

        match = find_itinerary_match(name)
        if match:                         # enrich the authoritative itinerary record
            for t in tags:
                if t not in match["interest_tags"]:
                    match["interest_tags"].append(t)
            match["interest_tags"].sort()
            match["sources"] = sorted(set(match.get("sources", []) + sources))
            if match.get("cost_jpy") is None: match["cost_jpy"] = cost
            if match.get("reservation") is None: match["reservation"] = reservation
            if match.get("closed_days") is None: match["closed_days"] = closed_from(body)
            if match.get("kid_friendly") is None and kid: match["kid_friendly"] = True
            if not match.get("name_jp") and jp: match["name_jp"] = jp
            if f"interests:{theme}" not in match["origin"]:
                match["origin"].append(f"interests:{theme}")
            return
        lat, lng, gsrc = coords_for(None, name, dest)
        out.append({
            "id": slug(name), "name": name, "name_jp": jp,
            "category": categorize(name, summary),
            "lat": lat, "lng": lng, "geo_source": gsrc,
            "interest_tags": tags, "kid_friendly": kid, "dwell_min": None, "cost_jpy": cost,
            "open_days": None, "closed_days": closed_from(body), "reservation": reservation,
            "fit": fit, "day": DEST_DAY.get(dest) if fit in ("on-route", "near-route") else None,
            "destination": dest, "slot": None, "summary": summary,
            "sources": sources, "wiki": None, "img": None, "q": None,
            "origin": [f"interests:{theme}"],
        })

    # (A) heading entries (heading line + following lines as body)
    entries, cur = [], None
    for l in lines:
        if re.match(r"^#{2,4} ", l):
            if cur: entries.append(cur)
            cur = [l]
        elif cur is not None:
            cur.append(l)
    if cur: entries.append(cur)
    for ent in entries:
        head, m = ent[0], FIT_RE.search(ent[0])
        if not m:
            continue
        title = FIT_RE.sub("", head).lstrip("#").strip()
        name, jp, loc = split_title(title)
        body = "\n".join(ent[1:])
        sm = re.search(r"\*\*What[^:]*:\*\*\s*(.+)", body) or re.search(r"\*\*Where:\*\*\s*(.+)", body)
        emit(name, jp, m.group(1), sm.group(1) if sm else loc, body, loc)

    # (B) table rows:  | **Name** | … | **[FIT]** | desc |
    for l in lines:
        if not l.lstrip().startswith("|") or not FIT_RE.search(l):
            continue
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        nm = next((re.match(r"\*\*(.+?)\*\*", c).group(1) for c in cells if re.match(r"\*\*(.+?)\*\*", c)), None)
        if not nm:
            continue
        name, jp, _ = split_title(nm)
        desc = max((FIT_RE.sub("", c) for c in cells), key=len)
        emit(name, jp, FIT_RE.search(l).group(1), desc, l)

    # (C) standalone bullets:  - **Name** — desc … **[FIT]**
    for l in lines:
        s = l.strip()
        if not s.startswith("- **") or not FIT_RE.search(s):
            continue
        nm = re.match(r"- \*\*(.+?)\*\*", s)
        if not nm:
            continue
        name, jp, _ = split_title(nm.group(1))
        desc = re.sub(r"^- \*\*.+?\*\*[\s—–-]*", "", FIT_RE.sub("", s)).strip()
        emit(name, jp, FIT_RE.search(s).group(1), desc, s)

    return out

def name_jp_missing(r):
    return not r.get("name_jp")

for path in sorted(glob.glob(os.path.join(ROOT, "interests", "*.md"))):
    if os.path.basename(path) == "README.md":
        continue
    for rec in parse_interest_file(path):
        if rec["id"] in records:        # merge duplicate candidate (e.g. same POI in two themes)
            ex = records[rec["id"]]
            ex["interest_tags"] = sorted(set(ex["interest_tags"]) | set(rec["interest_tags"]))
            ex["sources"] = sorted(set(ex["sources"]) | set(rec["sources"]))
            ex["origin"] = sorted(set(ex["origin"]) | set(rec["origin"]))
        else:
            add(rec)

# ---------- 3) overlay.jsonl (hand-curated overrides, always win) ----------
ov_path = os.path.join(HERE, "overlay.jsonl")
n_overlay = 0
if os.path.exists(ov_path):
    for line in open(ov_path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        o = json.loads(line); n_overlay += 1
        rid = o["id"]
        rec = records.get(rid, {"id": rid, "origin": []})
        for k, v in o.items():
            if k == "id":
                continue
            rec[k] = v
        if "overlay" not in rec.get("origin", []):
            rec.setdefault("origin", []).append("overlay")
        # refresh geo_source when overlay supplies coords
        if "lat" in o and "geo_source" not in o:
            rec["geo_source"] = "curated"
        records[rid] = rec

# ---------- write pois.jsonl ----------
recs = sorted(records.values(), key=lambda r: (r.get("day") if r.get("day") is not None else 99,
                                               r.get("destination") or "zz", r["name"].lower()))
with open(os.path.join(HERE, "pois.jsonl"), "w", encoding="utf-8") as f:
    for r in recs:
        f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

# ---------- report ----------
from collections import Counter
by_fit = Counter(r["fit"] for r in recs)
by_geo = Counter(r["geo_source"] for r in recs)
with_coords = sum(1 for r in recs if r["lat"] is not None)
print(f"pois.jsonl: {len(recs)} records  (overlay rows applied: {n_overlay})")
print("  fit:", dict(by_fit))
print("  geo_source:", dict(by_geo), f"| with coords: {with_coords}/{len(recs)}")
print("  interest-tag coverage:", dict(Counter(t for r in recs for t in r["interest_tags"])))
