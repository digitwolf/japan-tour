#!/usr/bin/env python3
"""Generate data.js from tour/ markdown (website-builder).
Run: python3 gen_data.py  (writes data.js)."""
import re, json, glob, os

TOUR = os.path.join(os.path.dirname(__file__), "tour", "destinations")

# id -> (lat, lng, zoom). Coordinates curated by website-builder (not in md).
COORDS = {
    "tokyo":           (35.6595, 139.7005, 11),  # air gateway (Shinagawa/Tokyo Stn) — NOT on the bike loop
    "osaka":           (34.6937, 135.5023, 12),
    "koyasan":         (34.2131, 135.5844, 14),
    "kumano-interior": (33.8403, 135.7733, 12),
    "kumano":          (33.6259, 135.9412, 13),
    "shirahama":       (33.6853, 135.3378, 13),
    "tokushima":       (34.1722, 134.6093, 12),
    "iya":             (33.8890, 133.8120, 12),
    "kochi":           (33.5597, 133.5311, 13),
    "shimanto":        (32.9914, 132.9338, 12),
    "uwajima":         (33.2233, 132.5606, 13),
    "dogo":            (33.8519, 132.7866, 14),
    "shimanami":       (34.1100, 133.0100, 11),
    "onomichi":        (34.4090, 133.2050, 14),
    "kurashiki":       (34.5957, 133.7718, 14),
    "himeji":          (34.8394, 134.6939, 14),
    "awaji":           (34.4500, 134.9300, 11),
}

# Destination/gallery order (== file order). "tokyo" is a non-route BOOKEND card
# (type "bookend") — it is excluded from the map polyline + riding prev/next by the
# HTML (which filters type !== 'bookend'); the 16 loop stops follow in route order.
ORDER = ["tokyo","osaka","koyasan","kumano-interior","kumano","shirahama","tokushima",
         "iya","kochi","shimanto","uwajima","dogo","shimanami","onomichi",
         "kurashiki","himeji","awaji"]

def md_inline(s):
    """Convert markdown bold/links to HTML, drop [KID] markers."""
    s = s.replace("**[KID]**", "").replace("[KID]", "")
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
               r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", s)
    return re.sub(r"\s+", " ", s).strip()

def plain(s):
    s = s.replace("**[KID]**", "").replace("[KID]", "")
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()

def sections(text):
    """Split a md file into {header: [lines]} on '## '."""
    out, cur = {}, "_top"
    out[cur] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        else:
            out[cur].append(line)
    return out

def parse_dest(path):
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    d = {}
    # title + jp
    m = re.match(r"^#\s+(.*)$", lines[0])
    title = m.group(1).strip()
    jm = re.search(r"([　-鿿＀-￯]+)\s*$", title)
    if jm:
        d["jp"] = jm.group(1)
        d["name"] = title[:jm.start()].strip()
    else:
        d["jp"] = ""
        d["name"] = title
    # tagline = first blockquote
    for ln in lines:
        if ln.startswith("> "):
            d["tagline"] = plain(ln[2:].strip())
            break
    # front-matter bullets
    def field(label):
        for ln in lines:
            m = re.match(r"^- \*\*%s:?\*\*\s*(.*)$" % re.escape(label), ln)
            if m:
                return m.group(1).strip()
        return ""
    d["region"] = plain(field("Region"))
    d["days"] = plain(field("Itinerary"))
    d["type"] = plain(field("Stop type")).lower()
    ride = field("Ride to here (direct)")
    rm = re.search(r"(\d+)\s*mi", ride)
    d["legMiles"] = int(rm.group(1)) if rm else 0

    secs = sections(text)
    # About -> intro paragraphs (skip blockquotes)
    intro, buf = [], []
    for ln in secs.get("About", []):
        if ln.startswith(">"):
            continue
        if ln.strip() == "":
            if buf:
                intro.append(md_inline(" ".join(buf)))
                buf = []
        else:
            buf.append(ln.strip())
    if buf:
        intro.append(md_inline(" ".join(buf)))
    d["intro"] = intro

    # Things to see & do -> highlights
    hi = []
    for ln in secs.get("Things to see & do", []):
        m = re.match(r"^-\s+(.*)$", ln)
        if m:
            hi.append(md_inline(m.group(1)))
    d["highlights"] = hi

    # What to eat -> food
    food = []
    for ln in secs.get("What to eat", []):
        m = re.match(r"^-\s+(.*)$", ln)
        if not m:
            continue
        body = m.group(1)
        mm = re.match(r"\*\*(.+?)\*\*\s*[—-]\s*(.*)$", body)
        if mm:
            food.append({"n": plain(mm.group(1)), "d": plain(mm.group(2))})
        else:
            food.append({"n": plain(body), "d": ""})
    d["food"] = food

    # Where to stay -> hotels (table)
    hotels = []
    for ln in secs.get("Where to stay", []):
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        prop = cells[0]
        if prop.lower().startswith("property") or set(prop) <= set("-: "):
            continue
        typ, parking, yen, usd, notes = cells[1], cells[2], cells[3], cells[4], cells[5]
        if prop.startswith("_") or typ == "—":
            hotels.append({"n": plain(prop), "t": "Note", "d": plain(notes)})
        else:
            h = {"n": plain(prop), "t": plain(typ), "d": plain(notes)}
            if parking and parking != "—":
                h["park"] = md_inline(parking)
            if yen and yen != "—":
                h["price"] = yen
            hotels.append(h)
    d["hotels"] = hotels

    # Links
    links = []
    for ln in secs.get("Links", []):
        m = re.match(r"^-\s+\[([^\]]+)\]\(([^)]+)\)", ln)
        if m:
            links.append({"l": m.group(1).strip(), "u": m.group(2).strip()})
    d["links"] = links

    # Photos
    photos = []
    photo_key = next((k for k in secs if k.startswith("Photos")), None)
    for ln in secs.get(photo_key, []):
        m = re.match(r"^-\s+!\[[^\]]*\]\(([^)]+)\)\s*(?:—\s*(.*))?$", ln)
        if m:
            photos.append({"src": m.group(1).strip(), "cap": plain(m.group(2) or "")})
    d["photos"] = photos
    return d

DESTS = {}
for path in sorted(glob.glob(os.path.join(TOUR, "*.md"))):
    d = parse_dest(path)
    # id from filename: NN-id.md
    fid = re.match(r"\d+-(.*)\.md", os.path.basename(path)).group(1)
    d["id"] = fid
    lat, lng, zoom = COORDS[fid]
    d["lat"], d["lng"], d["zoom"] = lat, lng, zoom
    DESTS[fid] = d

# ---- helper to pick a verified photo from a destination ----
def P(did, idx):
    ph = DESTS[did]["photos"]
    return ph[idx % len(ph)]["src"]

# Extra verified images (Commons-resolved, batch-verified separately)
IMG = {
    "kaiyukan": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/51/Entrance_of_Osaka_Aquarium_%22Kaiyukan%22.jpg/960px-Entrance_of_Osaka_Aquarium_%22Kaiyukan%22.jpg",
    "fushimi": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8e/Fushimi_Inari-taisha%2C_Kyoto%2C_20240818_1343_4411.jpg/960px-Fushimi_Inari-taisha%2C_Kyoto%2C_20240818_1343_4411.jpg",
    "wakayama": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/05/Wakayama_Castle_Keep_Tower_20210724-1.jpg/960px-Wakayama_Castle_Keep_Tower_20210724-1.jpg",
    "ferry": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/db/Oct2025._Onboard_a_ferry_from_Wakayama_to_Tokushima%2C_Japan_01.jpg/960px-Oct2025._Onboard_a_ferry_from_Wakayama_to_Tokushima%2C_Japan_01.jpg",
    "tokyo": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b7/Marunouchi_%26_Tokyo_Station_3.jpg/960px-Marunouchi_%26_Tokyo_Station_3.jpg",
    "shinkansen": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/Mount_Fuji_and_Shinkansen_N700.jpg/960px-Mount_Fuji_and_Shinkansen_N700.jpg",
    # New verified Commons thumbs for the Tokyo museum day + USJ day (HTTP 200, batch-verified)
    "ghibli": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/44/Ghibli_Museum%2C_Mitaka%2C_Tokyo%2C_20240823_1131_5545.jpg/960px-Ghibli_Museum%2C_Mitaka%2C_Tokyo%2C_20240823_1131_5545.jpg",
    "teamlab": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/ff/Photos_at_teamlab_planets_tokyo.jpg/960px-Photos_at_teamlab_planets_tokyo.jpg",
    "nintendo": "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fc/Shibuya_PARCO_2.jpg/960px-Shibuya_PARCO_2.jpg",
    "shibuya": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c5/Tokyo_Shibuya_Scramble_Crossing_2018-10-09.jpg/960px-Tokyo_Shibuya_Scramble_Crossing_2018-10-09.jpg",
    "usj_castle": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/Peach%27sCastle_at_Universal_Studios_Japan_20220814.jpg/960px-Peach%27sCastle_at_Universal_Studios_Japan_20220814.jpg",
    "usj_bands": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c4/Power_up_bands_at_Super_Nintendo_World_%28Universal_Studios_Japan%29.png/960px-Power_up_bands_at_Super_Nintendo_World_%28Universal_Studios_Japan%29.png",
    "haneda": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Shinagawa_Station_-01.jpg/960px-Shinagawa_Station_-01.jpg",
}

# Verified English-Wikipedia article URLs (HTTP 200, batch-verified) keyed by POI name.
# poi() attaches WIKI[name] as an explicit `wiki` override; everything else falls back
# at render time to a Wikipedia search link via window.wikiLink (always resolves).
WIKI = {
    "Okunoin": "https://en.wikipedia.org/wiki/Okunoin",
    "Kongōbu-ji": "https://en.wikipedia.org/wiki/Kong%C5%8Dbu-ji",
    "Danjo Garan & Konpon Daitō": "https://en.wikipedia.org/wiki/Mount_K%C5%8Dya",
    "Kumano Hongū Taisha & Ōyunohara": "https://en.wikipedia.org/wiki/Kumano_Hong%C5%AB_Taisha",
    "Kumano Hayatama Taisha (Shingū)": "https://en.wikipedia.org/wiki/Kumano_Hayatama_Taisha",
    "Nachi Falls & Kumano Nachi Taisha": "https://en.wikipedia.org/wiki/Nachi_Falls",
    "Engetsu Island": "https://en.wikipedia.org/wiki/Engetsu_Island",
    "Adventure World": "https://en.wikipedia.org/wiki/Adventure_World_(Japan)",
    "Wakayama Castle": "https://en.wikipedia.org/wiki/Wakayama_Castle",
    "Naruto whirlpools": "https://en.wikipedia.org/wiki/Naruto_whirlpools",
    "Iya Valley viewpoint": "https://en.wikipedia.org/wiki/Iya_Valley",
    "Kazurabashi vine bridge": "https://en.wikipedia.org/wiki/Iya_Valley",
    "Anpanman Museum": "https://en.wikipedia.org/wiki/Anpanman",
    "Kochi Castle & Hirome Market": "https://en.wikipedia.org/wiki/K%C5%8Dchi_Castle",
    "Katsurahama": "https://en.wikipedia.org/wiki/Katsurahama",
    "Niyodo Blue river": "https://en.wikipedia.org/wiki/Niyodo_River",
    "Cape Ashizuri": "https://en.wikipedia.org/wiki/Cape_Ashizuri",
    "Uwajima Castle": "https://en.wikipedia.org/wiki/Uwajima_Castle",
    "Uchiko old town": "https://en.wikipedia.org/wiki/Uchiko,_Ehime",
    "Matsuyama Castle": "https://en.wikipedia.org/wiki/Matsuyama_Castle_(Iyo)",
    "Dōgo Onsen Honkan": "https://en.wikipedia.org/wiki/D%C5%8Dgo_Onsen",
    "Ishite-ji": "https://en.wikipedia.org/wiki/Ishite-ji",
    "Imabari Castle": "https://en.wikipedia.org/wiki/Imabari_Castle",
    "Ōyamazumi Shrine, Ōmishima": "https://en.wikipedia.org/wiki/%C5%8Cyamazumi_Shrine",
    "Kōsanji & Hill of Hope": "https://en.wikipedia.org/wiki/K%C5%8Dsan-ji",
    "Fukuyama Castle": "https://en.wikipedia.org/wiki/Fukuyama_Castle",
    "Tomonoura (Ponyo harbour)": "https://en.wikipedia.org/wiki/Tomonoura",
    "Himeji Castle & Kōko-en": "https://en.wikipedia.org/wiki/Himeji_Castle",
    "Akashi Kaikyō Bridge": "https://en.wikipedia.org/wiki/Akashi_Kaiky%C5%8D_Bridge",
    "Osaka Castle": "https://en.wikipedia.org/wiki/Osaka_Castle",
    "Kaiyukan": "https://en.wikipedia.org/wiki/Osaka_Aquarium_Kaiyukan",
    "Kaiyukan Aquarium": "https://en.wikipedia.org/wiki/Osaka_Aquarium_Kaiyukan",
    "Kaiyukan (calm alternative)": "https://en.wikipedia.org/wiki/Osaka_Aquarium_Kaiyukan",
    "Dōtonbori": "https://en.wikipedia.org/wiki/D%C5%8Dtonbori",
    "Fushimi Inari, Kyoto": "https://en.wikipedia.org/wiki/Fushimi_Inari-taisha",
    "Ghibli Museum (Mitaka)": "https://en.wikipedia.org/wiki/Ghibli_Museum",
    "teamLab Planets TOKYO": "https://en.wikipedia.org/wiki/TeamLab",
    "Super Nintendo World": "https://en.wikipedia.org/wiki/Super_Nintendo_World",
    "Universal Studios Japan": "https://en.wikipedia.org/wiki/Universal_Studios_Japan",
}

# ============ DAYS (0..23) ============
# Each: d, id, miles, dmin(optional), rest, rail(optional), region, title, route,
#       desc, tags, gfrom, gto, gvia, poi[]
def poi(name, what, q, slot, img, wiki=None):
    p = {"name": name, "what": what, "q": q, "slot": slot, "img": img}
    w = wiki or WIKI.get(name)
    if w:
        p["wiki"] = w   # explicit verified article; else day.html falls back to a Wikipedia search link
    return p

DAYS = [
 {"d":0,"id":"tokyo","miles":0,"rest":True,"rail":True,"region":"Tokyo","title":"Tokyo Arrival Night",
  "route":"SEA ✈ Tokyo (Haneda) → Shinagawa","desc":"The nonstop SEA→Tokyo flight crosses the date line and lands mid/late afternoon. From Haneda the Keikyu Line reaches Shinagawa in ~15 min — overnight near the station for a gentle jet-lag reset. There's a full Tokyo museum day tomorrow before the train south, so don't forward the luggage yet; an easy dinner and an early night is the plan.",
  "tags":["rest"],"gfrom":"Haneda Airport, Tokyo","gto":"Shinagawa, Tokyo","gvia":"",
  "poi":[poi("Shinagawa overnight","Easy dinner, early night by the Shinkansen station","Shinagawa Station Tokyo","activity",IMG["haneda"]),
         poi("Optional brief Tokyo look","Only if energy allows after the flight — a gentle evening stroll","Tokyo Station","scenic",IMG["tokyo"])]},

 {"d":1,"id":"tokyo","miles":0,"rest":True,"rail":False,"city":True,"region":"Tokyo","title":"Tokyo Museum Day",
  "route":"Mitaka · Toyosu · Shibuya (train & on foot)","desc":"A full, kid-focused Tokyo day before heading south — three of the city's best family experiences, paced so a jet-lagged 6-year-old isn't overstuffed. Morning at the whimsical Ghibli Museum in Mitaka, afternoon wading through the immersive digital art of teamLab Planets in Toyosu, and an early-evening cap at Nintendo TOKYO in Shibuya PARCO (Pokémon Center next door). Book the Ghibli (Lawson, ~a month ahead, sells out fast) and teamLab timed tickets the moment they release. Still no riding.",
  "tags":["rest","kid"],"gfrom":"Tokyo","gto":"Tokyo","gvia":"",
  "poi":[poi("Ghibli Museum (Mitaka)","Miyazaki's magical, hands-on museum — Totoro, the Catbus, a rooftop robot and a members-only short film. Advance date-and-time tickets only (Lawson); no door sales.","Ghibli Museum Mitaka Tokyo","activity",IMG["ghibli"]),
         poi("teamLab Planets TOKYO","A barefoot, immersive, wade-through world of digital art — mirrored light rooms, knee-deep water and projected flowers that delight every age. Needs a timed online ticket.","teamLab Planets TOKYO","activity",IMG["teamlab"]),
         poi("Nintendo TOKYO (Shibuya PARCO)","The official Nintendo flagship store (Mario, Zelda, Pokémon, Splatoon) with the Pokémon Center Shibuya next door — a gentle finish near Shibuya Crossing.","Nintendo TOKYO Shibuya PARCO","activity",IMG["nintendo"]),
         poi("Shibuya Crossing","The world's busiest scramble crossing, steps from Nintendo TOKYO — pure big-city Tokyo energy before dinner.","Shibuya Crossing","scenic",IMG["shibuya"])]},

 {"d":2,"id":"osaka","miles":0,"rest":True,"rail":True,"region":"Kansai","title":"Shinkansen to Osaka & Bike Pickup",
  "route":"Tokyo 🚄 Shin-Osaka → Suita base","desc":"Strictly no riding. A relaxed late-morning Nozomi (~2h30m) brings you to Shin-Osaka around midday, then to the Suita base for the rental handover: paperwork and insurance, a full walk-around of the Africa Twin and CB400X, fitting the child's gear, pairing intercoms and a slow on-foot shakedown. Cap it with an easy Dōtonbori/Namba evening — the first real ride is Day 3, fresh and rested.",
  "tags":["rest","kid"],"gfrom":"Tokyo Station","gto":"Suita, Osaka","gvia":"",
  "poi":[poi("Suita rental base","Bike pickup, paperwork, gear-fit and a slow on-foot shakedown of the controls","Suita, Osaka","activity",P("osaka",0)),
         poi("Osaka Castle","Moats, park and the keep — an easy first-evening stroll","Osaka Castle","activity",P("osaka",0)),
         poi("Dōtonbori","Welcome dinner under the neon — takoyaki & okonomiyaki","Dotonbori Osaka","lunch",P("osaka",1))]},

 {"d":3,"id":"koyasan","miles":45,"dmin":139,"rest":False,"region":"Kōya, Wakayama","title":"Up to the Sacred Mountain",
  "route":"Osaka → Kōyasan","desc":"The first real ride is gentle and short — slip south out of the Kansai sprawl and pick up the paved Route 480/370 climb into the forested highlands of Kōyasan. An early-afternoon arrival is deliberate: walk the Danjō Garan and the head temple Kongōbu-ji, save lantern-lit Okunoin for the atmospheric dusk walk, then settle into a shukubō for a shōjin-ryōri dinner and a quiet mountain night.",
  "tags":["ride","kid"],"gfrom":"Osaka, Japan","gto":"Koyasan, Wakayama, Japan","gvia":"",
  "poi":[poi("Danjo Garan & Konpon Daitō","The vermilion great pagoda, spiritual heart of the mountain (early-afternoon arrival walk)","Konpon Daito Koyasan","scenic",P("koyasan",0)),
         poi("Kongōbu-ji","Head temple of Shingon Buddhism: the Banryūtei rock garden (Japan's largest) and painted fusuma halls (afternoon)","Kongobu-ji Koyasan","activity",P("koyasan",4)),
         poi("Okunoin","Lantern-lit cedar avenue to Kōbō Daishi's mausoleum (a dusk walk, at its most atmospheric)","Okunoin Cemetery Koyasan","scenic",P("koyasan",1)),
         poi("Shukubō shōjin-ryōri","Temple lodging and a Buddhist vegetarian dinner","Ekoin Koyasan","activity",P("koyasan",3))]},

 {"d":4,"id":"kumano-interior","miles":52,"dmin":122,"rest":False,"region":"Kumano, Wakayama","title":"The Pilgrim Road (Route 168)",
  "route":"Kōyasan → Hongū / Yunomine","desc":"Drop off the mountain and turn south down Route 168, the classic pilgrim road, following the Totsukawa River through deep forested gorges. Pause to walk the swaying Tanise suspension bridge, then roll into the Hongū basin for the head Kumano shrine and the giant Ōyunohara torii. Overnight at the ancient onsen hamlets of Yunomine or Kawayu.",
  "tags":["ride","kid","onsen"],"gfrom":"Koyasan, Wakayama, Japan","gto":"Yunomine Onsen, Wakayama, Japan","gvia":"Totsukawa, Nara, Japan",
  "poi":[poi("Tanise no Tsuribashi","A 297 m swaying pedestrian suspension bridge over the Totsukawa","Tanise no Tsuribashi Totsukawa","stop",P("kumano-interior",7)),
         poi("Totsukawa","River-valley leg-stretch in Japan's largest village","Totsukawa village","coffee",P("kumano-interior",3)),
         poi("Kumano Hongū Taisha & Ōyunohara","Head Kumano shrine and Japan's largest torii","Kumano Hongu Taisha","scenic",P("kumano-interior",0))]},

 {"d":5,"id":"kumano-interior","miles":20,"rest":True,"region":"Kumano, Wakayama","title":"Kumano Interior Rest Day",
  "route":"Yunomine / Kawayu (light riding)","desc":"A slow soak-and-stroll day in the sacred interior — the most restful base of the loop. Bathe in the tiny Tsuboyu (the only World Heritage bath you can enter) and boil eggs in the spring; at Kawayu, scoop your own riverbed bath in the warm gravel. Keep the Kumano Kodō to a gentle 30–40 min Hosshinmon-ōji → Hongū taster (easy for a child), and return to the giant Ōyunohara torii at golden hour. Rain plan: the indoor Kumano Hongū Heritage Center and covered ryokan baths.",
  "tags":["rest","kid","onsen","stay2"],"gfrom":"Yunomine Onsen, Wakayama, Japan","gto":"Kumano Hongu Taisha","gvia":"",
  "poi":[poi("Tsuboyu, Yunomine","Soak in the only World Heritage bath you can bathe in","Tsuboyu Yunomine Onsen","activity",P("kumano-interior",3)),
         poi("Kawayu Onsen","Dig your own bath in the warm riverbed","Kawayu Onsen","activity",P("kumano-interior",4)),
         poi("Ōyunohara & Kumano Kodō walk","Giant torii and a gentle pilgrim-trail stretch","Oyunohara Otorii","scenic",P("kumano-interior",1))]},

 {"d":6,"id":"kumano","miles":52,"dmin":112,"rest":False,"region":"Wakayama","title":"Down to the Sacred Coast",
  "route":"Yunomine → Doro-kyō → Nachi-Katsuura","desc":"A short, scenic descent from the mountains to the Pacific. Drop along the Kitayama River to Doro-kyō, where a jet-boat threads the glass-clear gorge, then continue to Nachi Falls — Japan's tallest waterfall — beside the vermilion pagoda of Kumano Nachi Taisha, reached up the cobbled Daimon-zaka. With the riding done by mid-afternoon, bank the rest of the day in the water at the tuna port of Katsuura — the seaside cave onsen and fresh maguro.",
  "tags":["ride","kid"],"gfrom":"Yunomine Onsen, Wakayama, Japan","gto":"Kii-Katsuura, Wakayama, Japan","gvia":"Doro-kyo Gorge, Japan",
  "poi":[poi("Doro-kyō jet-boat","Glass-clear gorge cruise between sheer cliffs (a kid highlight)","Doro-kyo Gorge Kitayama","stop",P("kumano-interior",5)),
         poi("Daimon-zaka","Short cobbled pilgrim path under giant cedars (kid-friendly)","Daimonzaka Nachi","scenic",P("kumano",2)),
         poi("Nachi Falls & Kumano Nachi Taisha","Waterfall, pagoda and shrine, with lunch","Nachi Falls","lunch",P("kumano",0)),
         poi("Kumano Hayatama Taisha (Shingū)","Optional third Kumano grand shrine and its 1,000-year-old sacred nagi tree, on the way down","Kumano Hayatama Taisha","scenic",P("kumano",3)),
         poi("Katsuura cave onsen","Afternoon soak in Bōki-dō, a natural sea-cave bath over the booming surf","Hotel Urashima Katsuura","activity",P("kumano",5))]},

 {"d":7,"id":"shirahama","miles":56,"dmin":111,"rest":False,"region":"Wakayama","title":"Capes & White Sand",
  "route":"Katsuura → Shirahama","desc":"A short, scenic coastal day around the peninsula's southern tip. Pause at the photogenic sea pillars of Hashigui-iwa and the sheer Sandanbeki cliffs, take a tuna lunch at Tore-Tore Ichiba, and roll into the white-sand resort of Shirahama by early afternoon (~13:30). The early arrival is the whole point — the first beach base, with the afternoon for the resort: white-sand Shirarahama, the tilted Senjōjiki rock platform, a Sakino-yu surf-line soak and a sunset through Engetsu Island's sea arch.",
  "tags":["ride","kid"],"gfrom":"Kii-Katsuura, Wakayama, Japan","gto":"Shirahama, Wakayama, Japan","gvia":"Kushimoto, Wakayama, Japan",
  "poi":[poi("Hashigui-iwa","A line of pillar rocks marching out to sea","Hashigui-iwa Kushimoto","stop",P("shirahama",8)),
         poi("Sandanbeki","50 m cliffs with a sea-cave lift to the waves","Sandanbeki Shirahama","scenic",P("shirahama",2)),
         poi("Tore-Tore Ichiba","Giant seafood market for a tuna lunch","Tore-Tore Ichiba Shirahama","lunch",P("shirahama",1)),
         poi("Shirarahama beach","White-sand beach time on arrival; shallow, gentle swimming for the child (afternoon)","Shirarahama Beach Shirahama","activity",P("shirahama",0)),
         poi("Senjōjiki","Wave-cut '1,000-tatami' rock terrace, fun to clamber on (afternoon)","Senjojiki Shirahama","scenic",P("shirahama",1)),
         poi("Sakino-yu onsen","Rock open-air bath right at the surf line, in use 1,300+ years (afternoon)","Sakinoyu Onsen Shirahama","activity",P("kumano",5)),
         poi("Engetsu Island","Sunset through the 'round-moon' sea arch (early evening)","Engetsu Island Shirahama","scenic",P("shirahama",5))]},

 {"d":8,"id":"shirahama","miles":15,"rest":True,"region":"Wakayama","title":"Shirahama Rest Day",
  "route":"Shirahama (light riding)","desc":"The trip's first beach base — and really the kids' big day out: Adventure World, with giant pandas and a drive-through safari (a full, busy day, so it's energetic rather than truly lazy). For a genuinely low-key alternative, just do Shirarahama beach, the sea-edge Sakino-yu onsen and an Engetsu Island sunset. Rain plan: Adventure World runs mostly under cover, or the indoor Kyoto University Shirahama Aquarium.",
  "tags":["rest","kid","onsen","stay2"],"gfrom":"Shirahama, Wakayama, Japan","gto":"Adventure World, Shirahama","gvia":"",
  "poi":[poi("Adventure World","Pandas, safari and a marine park — a full joyful day","Adventure World Shirahama","activity",P("shirahama",6)),
         poi("Shirarahama beach","White sand and gentle swimming","Shirarahama Beach Shirahama","activity",P("shirahama",0)),
         poi("Sakino-yu onsen","Rock open-air bath right at the surf line","Sakinoyu Onsen Shirahama","scenic",P("shirahama",4))]},

 {"d":9,"id":"tokushima","miles":91,"dmin":166,"rest":False,"region":"Tokushima","title":"Ferry to Shikoku","ferry":True,
  "route":"Shirahama → Wakayama → ferry → Naruto","desc":"Rather than backtrack through Osaka, the loop crosses the water. Ride up to Wakayama Port (a castle stop on the way) and roll the bikes straight onto the Nankai Ferry for the ~2h15m sailing to Tokushima — a restful break and a small adventure for the child. Land beside Naruto, where huge tidal whirlpools churn under the Ōnaruto Bridge.",
  "tags":["ride","kid"],"gfrom":"Shirahama, Wakayama, Japan","gto":"Naruto, Tokushima, Japan","gvia":"Wakayama Port, Japan",
  "poi":[poi("Wakayama Castle","Hilltop keep before the port","Wakayama Castle","stop",IMG["wakayama"]),
         poi("Nankai Ferry","~2h15m crossing to Shikoku, bikes aboard (first-come, no reservations)","Nankai Ferry Wakayama Port","activity",IMG["ferry"]),
         poi("Naruto whirlpools","Uzunomichi glass-floor walkway over the strait","Uzunomichi Naruto","scenic",P("tokushima",0))]},

 {"d":10,"id":"iya","miles":75,"dmin":125,"rest":False,"region":"Shikoku","title":"Into Iya Valley",
  "route":"Naruto → Iya / Oboke","desc":"Follow the Yoshino River up into Shikoku's dramatic gorge country on easy, well-surfaced two-lane roads — a calm, scenic climb to a remote onsen ryokan. The Oboke Gorge is the lunch stop; the Iya valley unfolds above it.",
  "tags":["ride","onsen"],"gfrom":"Naruto, Tokushima, Japan","gto":"Oboke, Tokushima, Japan","gvia":"Tokushima, Japan",
  "poi":[poi("Tokushima riverside","Coffee and a leg-stretch before the hills","Tokushima Station","coffee",P("tokushima",3)),
         poi("Oboke Gorge","Gorge-side lunch and a sightseeing boat option","Oboke Gorge","lunch",P("iya",5)),
         poi("Iya Valley viewpoint","Vine bridge and gorge scenery","Iya Valley","scenic",P("iya",2))]},

 {"d":11,"id":"iya","miles":25,"rest":True,"region":"Shikoku","title":"Iya Rest Day",
  "route":"Iya Valley (light riding)","desc":"Slow mountain time far from any city: the Kazurabashi vine bridge (hold a small child's hand on the slatted gaps), the peeing-boy statue viewpoint, and an Oboke Gorge sightseeing boat, with the scarecrow village of Nagoro a deeper optional drive. Downtime is the riverside onsen ryokan. Rain plan: the indoor Lapis Ōboke rock-and-yōkai museum and a hearth dekomawashi lunch.",
  "tags":["rest","kid","onsen","stay2"],"gfrom":"Oboke, Tokushima, Japan","gto":"Iya Kazurabashi, Japan","gvia":"",
  "poi":[poi("Kazurabashi vine bridge","Cross the swaying vine bridge","Iya Kazurabashi","activity",P("iya",0)),
         poi("Oboke Gorge boat","Sightseeing boat on the Yoshino","Oboke Gorge","activity",P("iya",5)),
         poi("Peeing Boy statue","Cliff-edge viewpoint","Iya no Shobenkozo","scenic",P("iya",4)),
         poi("Nagoro Scarecrow Village","Quirky kid stop","Nagoro Scarecrow Village","scenic",P("iya",7))]},

 {"d":12,"id":"kochi","miles":75,"dmin":180,"rest":False,"region":"Shikoku","title":"Down to the Coast",
  "route":"Iya → Kochi","desc":"River valleys open out to the Pacific. A kid-favourite Anpanman stop, then Kōchi Castle and Katsurahama beach in the evening.",
  "tags":["ride","kid"],"gfrom":"Oboke, Tokushima, Japan","gto":"Kochi, Japan","gvia":"Otoyo, Kochi, Japan",
  "poi":[poi("Otoyo michi-no-eki","Roadside coffee break","Michi-no-Eki Otoyo","coffee",P("kochi",0)),
         poi("Anpanman Museum","Yanase Takashi Memorial Hall in Kami — a sure hit for a 6-year-old","Anpanman Museum Kami Kochi","stop",P("kochi",1)),
         poi("Kochi Castle & Hirome Market","Original keep, market lunch","Kochi Castle","lunch",P("kochi",0)),
         poi("Katsurahama","Pacific beach & Ryōma statue","Katsurahama","scenic",P("kochi",3))]},

 {"d":13,"id":"shimanto","miles":128,"dmin":273,"rest":False,"region":"Shikoku","title":"The Clear River",
  "route":"Kochi → Shimanto River","desc":"The longest riding day of the loop — but well inside the comfort cap and bracketed by rest. Follow the Shimanto, Japan's last free-flowing clear river, past its low submersible bridges, after a stop at the famously translucent Niyodo Blue.",
  "tags":["ride","kid"],"gfrom":"Kochi, Japan","gto":"Shimanto, Kochi, Japan","gvia":"Susaki, Kochi, Japan",
  "poi":[poi("Niyodo Blue river","Famous translucent-blue river","Niyodo River","stop",P("shimanto",6)),
         poi("Susaki","Nabeyaki-ramen coffee stop","Susaki Kochi","coffee",P("shimanto",2)),
         poi("Tatsukushi coast","Seaside lunch","Tatsukushi","lunch",P("shimanto",5)),
         poi("Sada Chinkabashi","Shimanto 'sinking bridge' photo","Sada Chinkabashi Shimanto","scenic",P("shimanto",3))]},

 {"d":14,"id":"shimanto","miles":20,"rest":True,"region":"Shikoku","title":"Shimanto Rest Day",
  "route":"Shimanto River (light riding)","desc":"The best-placed rest of the trip — right after the two hardest riding days. A covered yakatabune river boat glides past the low railless 'sinking bridges'; add an easy riverside stroll or cycle and slow rural time by the water. (Canoeing/SUP is really a summer thing — too cold in late October.) Kid + rain plan: the indoor Akitsuio dragonfly-and-fish museum at Tonbo Kingdom.",
  "tags":["rest","kid","stay2"],"gfrom":"Shimanto, Kochi, Japan","gto":"Shimanto River, Japan","gvia":"",
  "poi":[poi("Shimanto yakatabune boat","Covered river cruise past the sinking bridges","Shimanto River yakatabune","activity",P("shimanto",0)),
         poi("Sinking-bridge cycling","Easy riverside cycle","Shimanto River cycling","activity",P("shimanto",3)),
         poi("Cape Ashizuri","Dramatic cape & lighthouse","Cape Ashizuri","scenic",P("shimanto",5))]},

 {"d":15,"id":"dogo","miles":117,"dmin":210,"rest":False,"region":"Shikoku","title":"Castles & Old Towns",
  "route":"Shimanto → Uwajima / Uchiko → Matsuyama","desc":"Uwajima Castle and Uchiko's preserved merchant streets en route up the Ehime coast to Matsuyama and Dōgo Onsen.",
  "tags":["ride","kid","onsen"],"gfrom":"Shimanto, Kochi, Japan","gto":"Matsuyama, Ehime, Japan","gvia":"Uwajima, Ehime, Japan",
  "poi":[poi("Uwajima Castle","Original hilltop keep","Uwajima Castle","stop",P("uwajima",0)),
         poi("Uwajima taimeshi","Sea-bream-over-rice lunch","Uwajima","lunch",P("uwajima",5)),
         poi("Uchiko old town","Merchant street & kabuki theatre","Uchiko Yokaichi","scenic",P("uwajima",1)),
         poi("Garyū Sansō, Ozu","Riverside villa & garden","Garyu Sanso Ozu","scenic",P("uwajima",4))]},

 {"d":16,"id":"dogo","miles":10,"rest":True,"region":"Shikoku","title":"Dōgo Onsen Rest Day",
  "route":"Matsuyama (light riding)","desc":"Matsuyama Castle by ropeway, then the historic Dōgo Onsen bathhouse. Classic onsen evening.",
  "tags":["rest","onsen","kid","stay2"],"gfrom":"Matsuyama, Ehime, Japan","gto":"Dogo Onsen, Matsuyama, Japan","gvia":"",
  "poi":[poi("Matsuyama Castle","Ropeway to a hilltop original castle","Matsuyama Castle Ehime","activity",P("dogo",1)),
         poi("Dōgo Onsen Honkan","Soak in the historic bathhouse","Dogo Onsen Honkan","activity",P("dogo",0)),
         poi("Botchan Ressha","Retro steam-style tram","Botchan Ressha Matsuyama","scenic",P("dogo",2)),
         poi("Ishite-ji","Atmospheric pilgrimage temple","Ishiteji Temple Matsuyama","scenic",P("dogo",8))]},

 {"d":17,"id":"onomichi","miles":86,"dmin":193,"rest":False,"region":"Setouchi","title":"Shimanami Kaidō",
  "route":"Matsuyama → Shimanami → Onomichi / Setoda","desc":"The famous island-hopping bridge route across the Seto Inland Sea — gentle, scenic, unforgettable, and a highlight ride for the whole family.",
  "tags":["ride","kid"],"gfrom":"Matsuyama, Ehime, Japan","gto":"Onomichi, Hiroshima, Japan","gvia":"Imabari, Ehime, Japan",
  "poi":[poi("Imabari Castle","Sea-water-moat castle","Imabari Castle","stop",P("shimanami",0)),
         poi("Kirosan Observatory","Bridge panorama coffee","Kirosan Observatory Park","coffee",P("shimanami",6)),
         poi("Ōyamazumi Shrine, Ōmishima","Samurai-armour shrine, lunch","Oyamazumi Shrine","lunch",P("shimanami",3)),
         poi("Setoda, Ikuchijima","Lemon gelato & Kōsanji temple","Setoda","scenic",P("onomichi",1))]},

 {"d":18,"id":"onomichi","miles":25,"rest":True,"region":"Setouchi","title":"Island Rest Day",
  "route":"Setoda / Onomichi (light riding)","desc":"Easy pace: Setoda's Kōsanji temple and marble Hill of Hope, lemon groves and gelato, then Onomichi's hillside lanes and cat alley — take the Senkō-ji ropeway up and wander down rather than climbing the full temple stair. Downtime at the waterfront cafés. Rain plan: the covered Onomichi shōtengai arcade and the Onomichi U2 cycle-and-harbour complex.",
  "tags":["rest","kid","stay2"],"gfrom":"Onomichi, Hiroshima, Japan","gto":"Setoda, Ikuchijima, Japan","gvia":"",
  "poi":[poi("Senkōji Ropeway","Hilltop view over the town & sea","Senkoji Temple Onomichi","activity",P("onomichi",1)),
         poi("Temple Walk & cat alley","Lanes, cafés & cats","Onomichi Temple Walk","activity",P("onomichi",0)),
         poi("Kōsanji & Hill of Hope","Ornate temple & marble hilltop","Kosanji Temple Setoda","scenic",P("onomichi",6))]},

 {"d":19,"id":"kurashiki","miles":90,"dmin":195,"rest":False,"region":"Setouchi","title":"Canal Town",
  "route":"Onomichi → Kurashiki","desc":"The plan commits to Kurashiki — its willow-lined Bikan canal quarter and the Ōhara Museum of Art, compact and easy with a child. The ride in calls at Tomonoura, the seaside town that inspired Studio Ghibli's Ponyo.",
  "tags":["ride","kid"],"gfrom":"Onomichi, Hiroshima, Japan","gto":"Kurashiki, Okayama, Japan","gvia":"Tomonoura, Japan",
  "poi":[poi("Fukuyama Castle","Station-side castle","Fukuyama Castle","stop",P("kurashiki",3)),
         poi("Tomonoura (Ponyo harbour)","Stone jetty, lighthouse and the Ponyo hillside","Tomonoura","coffee",P("kurashiki",1)),
         poi("Washūzan Viewpoint","Seto Ōhashi bridge panorama, lunch","Washuzan","lunch",P("kurashiki",2)),
         poi("Kurashiki Bikan","Willow-lined canal quarter","Kurashiki Bikan","scenic",P("kurashiki",0))]},

 {"d":20,"id":"himeji","miles":105,"dmin":169,"rest":False,"region":"Kansai","title":"The Great Castle",
  "route":"Kurashiki → Himeji / Kobe","desc":"A relaxed run east to Japan's most magnificent castle. The shorter drive leaves a proper half-day for Himeji Castle and its Kōko-en garden, then an easy hop into Kobe for the night.",
  "tags":["ride","kid"],"gfrom":"Kurashiki, Okayama, Japan","gto":"Kobe, Japan","gvia":"Himeji, Hyogo, Japan",
  "poi":[poi("Himeji Castle & Kōko-en","White Heron castle + garden, unhurried, with lunch","Himeji Castle","lunch",P("himeji",0)),
         poi("Kobe Harborland","Harbour evening & Kobe beef","Kobe Harborland","scenic",P("himeji",4))]},

 {"d":21,"id":"awaji","miles":64,"dmin":105,"rest":False,"region":"Kansai","title":"Bridge to Awaji & Home",
  "route":"Kobe → Awaji → Osaka","desc":"A short, scenic flourish to close the loop: cross the Akashi Kaikyō Bridge — for years the longest suspension span on earth — onto Awaji Island, loop its gentle, flower-filled north coast, then recross and drop into Osaka. Kept deliberately light so the family arrives unhurried.",
  "tags":["ride","kid","end"],"gfrom":"Kobe, Japan","gto":"Osaka, Japan","gvia":"Awaji Island, Japan",
  "poi":[poi("Akashi Kaikyō Bridge","Ride the ~4 km span; photo stop at the Awaji end","Akashi Kaikyo Bridge","stop",P("awaji",0)),
         poi("Nijigen no Mori","Anime park (Naruto/Godzilla/Crayon Shin-chan) — a kid magnet","Nijigen no Mori Awaji","activity",P("awaji",1)),
         poi("Awaji Hanasajiki","Hillside flower fields over the Inland Sea","Awaji Hanasajiki","scenic",P("awaji",5))]},

 {"d":22,"id":"osaka","miles":15,"rest":True,"region":"Kansai","title":"Osaka & Bike Return",
  "route":"Osaka (light riding)","desc":"Return the motorcycles at the Suita base and celebrate the journey — a relaxed Osaka recovery day before tomorrow's big USJ outing. Osaka Castle and park, and the food streets of Dōtonbori; the Kaiyukan whale-shark aquarium is the calm option if you'd rather save energy for Super Nintendo World.",
  "tags":["rest","kid","stay2"],"gfrom":"Suita, Osaka","gto":"Osaka Aquarium Kaiyukan","gvia":"",
  "poi":[poi("Osaka Castle","Castle & park","Osaka Castle","activity",P("osaka",0)),
         poi("Dōtonbori","Neon, street food and a celebration dinner","Dotonbori Osaka","activity",P("osaka",1)),
         poi("Kaiyukan (option)","Whale-shark aquarium, if you'd rather save USJ energy for tomorrow","Osaka Aquarium Kaiyukan","scenic",IMG["kaiyukan"])]},

 {"d":23,"id":"osaka","miles":0,"rest":True,"city":True,"region":"Kansai","title":"Super Nintendo World / USJ",
  "route":"Osaka — Universal Studios Japan (no riding)","desc":"With the motorcycles safely back at the Suita base, the family gives a full day to Universal Studios Japan on Osaka Bay and its headline land, Super Nintendo World — a life-size, interactive Mushroom Kingdom. Ride Mario Kart: Koopa's Challenge and the gentle Yoshi's Adventure, and strap on a Power-Up Band to punch ? blocks across the land. The wider park adds Harry Potter, Minion Park and family shows. Buy dated tickets ahead and reserve the Nintendo area / key rides as early as the system allows — this is the busiest day of the trip.",
  "tags":["rest","kid"],"gfrom":"Universal Studios Japan","gto":"Universal Studios Japan","gvia":"",
  "poi":[poi("Super Nintendo World","Life-size Mushroom Kingdom; Mario Kart: Koopa's Challenge + an interactive Power-Up Band to punch ? blocks and collect coins. Normally needs a (free) Area Timed-Entry ticket or a paid Express Pass to enter the land.","Super Nintendo World Osaka","activity",IMG["usj_castle"]),
         poi("Universal Studios Japan","The wider park — The Wizarding World of Harry Potter, Minion Park and family rides and shows. A full day out; pace it and plan rest breaks for the 6-year-old.","Universal Studios Japan","activity",IMG["usj_bands"]),
         poi("Kaiyukan (calm alternative)","Whale-shark aquarium across the bay, indoor and all-weather — the low-key option if a full theme-park day is too much.","Osaka Aquarium Kaiyukan","scenic",IMG["kaiyukan"])]},

 {"d":24,"id":"tokyo","miles":0,"rest":True,"rail":True,"region":"Kansai → Tokyo","title":"Reposition to Tokyo",
  "route":"Osaka / Kyoto 🚄 Tokyo","desc":"Flexible buffer day that also repositions to Tokyo for the flight home. Kyoto sits right on the Tōkaidō line — sightsee in the morning (Fushimi Inari's thousand torii or a last Osaka food stroll), then board an afternoon Nozomi at Kyoto (or Shin-Osaka) → Tokyo (~2h30m) and overnight near Haneda/Shinagawa. The slack here also absorbs any earlier weather day. Forward the cases ahead by takkyūbin so the train is light.",
  "tags":["rest","kid"],"gfrom":"Osaka, Japan","gto":"Tokyo Station","gvia":"Kyoto, Japan",
  "poi":[poi("Fushimi Inari, Kyoto","Thousand vermilion torii gates (board the Shinkansen at Kyoto Station after)","Fushimi Inari Taisha","activity",IMG["fushimi"]),
         poi("Osaka Castle","A last castle & park stroll","Osaka Castle","activity",P("osaka",0)),
         poi("Shinkansen to Tokyo","Afternoon Nozomi to the departure city","Kyoto Station","scenic",IMG["shinkansen"])]},

 {"d":25,"id":"tokyo","miles":0,"rest":True,"rail":True,"region":"Tokyo","title":"Fly Home",
  "route":"Tokyo ✈ Seattle (nonstop)","desc":"Departure bookend. From your Tokyo hotel, head to the airport and fly the nonstop Tokyo → Seattle leg (ANA/Delta from Haneda, JAL from Narita). You re-cross the date line and land in Seattle the same calendar day. The big luggage, forwarded by takkyūbin, is waiting.",
  "tags":["rest"],"gfrom":"Tokyo Station","gto":"Haneda Airport, Tokyo","gvia":"",
  "poi":[poi("Tokyo → Haneda/Narita","To the airport for the nonstop home","Haneda Airport","activity",IMG["tokyo"])]},
]

# ============ FLIGHTS ============
FLIGHTS = {
 "intro": "You're starting from Seattle. The motorcycles are an Osaka loop (pick up and return at the Suita base), but the long-haul leg is a simple round-trip nonstop SEA ⇄ Tokyo — then the Tōkaidō Shinkansen (~2h30m) down to Osaka and back. Not an open-jaw / Osaka-airport (KIX) ticket.",
 "season": "Best window: October–early November 2026 (the trip's preferred season). The Osaka riding loop is bracketed by a Tokyo arrival night (Day 0) + a full Tokyo museum day (Day 1) before the Day-2 pickup, and by a Super Nintendo World / USJ day (Day 23) and a reposition-to-Tokyo day (Day 24) before flying home on Day 25 — door-to-door ≈ 26 days (Day 0–25).",
 "legs": [
   {"dir":"Outbound","from":"Seattle · SEA","to":"Tokyo · Haneda (HND)",
    "sample":"Sample: depart Fri 9 Oct 2026 → arrive Sat 10 Oct (next day, crossing the date line)",
    "type":"Nonstop","duration":"≈ 10h 30m–11h","airlines":["ANA","Delta","JAL (Narita)"],
    "fareFrom":"$900",
    "note":"Nonstop to Haneda on ANA/Delta (787) or to Narita on JAL. Prefer Haneda — the Keikyu Line reaches Shinagawa (a Shinkansen stop) in ~15 min. A Tokyo arrival night (Day 0) and a full Tokyo museum day (Day 1) precede the Nozomi to Shin-Osaka for the Day-2 bike pickup.",
    "expedia":"https://www.expedia.com/lp/flights/sea/hnd/seattle-to-tokyo",
    "expediaAlt":"https://www.expedia.com/lp/flights/sea/nrt/seattle-to-tokyo"},
   {"dir":"Return","from":"Tokyo · Haneda (HND)","to":"Seattle · SEA",
    "sample":"Sample: depart ~Wed 4 Nov 2026 (after the Day-24 reposition to Tokyo)",
    "type":"Nonstop","duration":"≈ 9h 30m–10h","airlines":["ANA","Delta","JAL (Narita)"],
    "fareFrom":"$900",
    "note":"Nonstop home — you re-cross the date line and land in Seattle the same calendar day. After the Day-23 USJ day, reposition Osaka→Tokyo by Nozomi on Day 24 (Kyoto sightseeing en route) and overnight near Haneda/Shinagawa for the Day-25 flight.",
    "expedia":"https://www.expedia.com/lp/flights/hnd/sea/tokyo-to-seattle"}
 ],
 "estimate": "Round-trip nonstop economy realistically $900–$1,600 per person for October; premium/business considerably more. Add the Shinkansen Tokyo ⇄ Shin-Osaka — about ¥29,000 / ≈$195 round-trip per adult (≈ half for the child). Buy point-to-point Nozomi tickets, not a JR Pass (Nozomi isn't covered by it).",
 "tips": [
   "Book a single round-trip SEA ⇄ Tokyo nonstop ticket — prefer Haneda for the easy train connection.",
   "Buy point-to-point Nozomi Shinkansen tickets (reserved seats together via smartEX) rather than a JR Pass — a mostly-motorcycle trip won't recoup a pass, and Nozomi isn't covered by it anyway.",
   "Forward the big luggage Tokyo→Osaka (and back) by takkyūbin (~¥2,000–2,500/case) so the train legs stay light.",
   "Keep Day 0 as a genuine jet-lag buffer in Tokyo; don't book a same-day onward Nozomi unless everyone's fresh.",
   "Confirm your 1949 Geneva International Driving Permits (category 'A') and motorcycle-riding travel insurance before you fly."
 ],
 "links": [
   {"l":"Google Flights — SEA ⇄ Tokyo round-trip","u":"https://www.google.com/travel/flights?q=flights%20round%20trip%20Seattle%20to%20Tokyo"},
   {"l":"ANA (SEA–HND)","u":"https://www.ana.co.jp/en/us/"},
   {"l":"Delta (SEA–HND)","u":"https://www.delta.com/"},
   {"l":"JAL (SEA–NRT)","u":"https://www.jal.co.jp/en/"},
   {"l":"smartEX — Tōkaidō Shinkansen reservations","u":"https://smart-ex.jp/en/"},
   {"l":"Keikyu — Haneda access","u":"https://www.keikyu.co.jp/visit/"},
   {"l":"Yamato — Ta-Q-Bin luggage forwarding","u":"https://www.kuronekoyamato.co.jp/ytc/en/"}
 ]
}

# ============ CHECKLIST ============
CHECKLIST = [
 {"sec":"Documents & licences","icon":"📄","items":[
   "Passport valid 6+ months beyond return",
   "Home-country motorcycle licence (each rider)",
   "1949 Geneva International Driving Permit (IDP), category 'A', for each rider — in the US, AAA issues it; get the physical permit before you fly (valid 1 year)",
   "Travel insurance documents that explicitly cover motorcycle riding (and the child)",
   "Motorcycle rental reservation confirmations (Bike Rental Japan, Suita/Osaka)",
   "Credit card (no foreign-transaction fee ideally) + some backup",
   "Digital + paper copies of all documents"
 ]},
 {"sec":"Motorcycle rental (Osaka loop)","icon":"🏍️","items":[
   "Reserve large ADV bike (Honda Africa Twin / CRF1000L) — Rider 1",
   "Reserve sub-500cc bike (Honda CB400X / NX400) — Rider 2",
   "Confirm it is an Osaka loop — pick up AND return at the Suita base (no Tokyo counter, no one-way drop)",
   "Get the explicit 22-day quote for both bikes + the deposit/hold amount in writing",
   "Confirm passenger riding is allowed — including a CHILD passenger on the Africa Twin",
   "Confirm large-bike + sub-500cc availability for your exact dates",
   "Confirm ETC card per bike (expressway tolls — Himeji/Kobe Day 20, Akashi Kaikyō bridge Day 21)",
   "Panniers/top-box fitted or allowed; ask about the optional support-truck add-on for flight-day bags",
   "Helmets & gear (rent or bring), intercoms paired"
 ]},
 {"sec":"Child-pillion setup (test parked on Day 2)","icon":"🧒","items":[
   "Properly fitting child motorcycle helmet (correct shell size, not an adult hand-me-down)",
   "Armoured jacket, gloves, pants and boots that fit; ear protection for longer legs",
   "Lowered/highway pegs or peg-lowering brackets so feet sit flat",
   "Passenger backrest / top-box backrest so the child can't slide rearward",
   "Proper grab rail or grab strap at the waist",
   "Child–adult tandem safety belt (harness linking child to rider)",
   "Intercom for the child; snacks, water, sun hat and a comfort item",
   "Plan stops every 60–90 minutes; never ride the child overtired or after dark"
 ]},
 {"sec":"Flights & rail","icon":"✈️","items":[
   "Book round-trip nonstop SEA ⇄ Tokyo (prefer Haneda for the train connection)",
   "Buy point-to-point Nozomi Shinkansen tickets Tokyo ⇄ Shin-Osaka (reserved, via smartEX) — not a JR Pass",
   "Keikyu (Haneda→Shinagawa) / N'EX (Narita) for the airport hops",
   "Three Tokyo hotel nights near a Shinkansen station (Day 0 arrival, Day 1 museum day, Day 24 departure)",
   "Book the Tokyo museum-day tickets early — Ghibli Museum (Lawson, ~a month ahead, sells out fast) and a timed teamLab Planets slot",
   "Book the Day-23 USJ dated park tickets + a Super Nintendo World Area Timed-Entry or Express Pass",
   "Arrange takkyūbin luggage forwarding Tokyo→Osaka and Osaka→Tokyo",
   "IC card (Suica/ICOCA) for trains on non-riding days"
 ]},
 {"sec":"Lodging","icon":"🏨","items":[
   "Book all hotels/ryokan — the Kōyasan shukubō night and the six 2-night bases first (Kumano interior, Shirahama, Iya, Shimanto, Dōgo, Onomichi)",
   "Keep the Kii-interior nights (Kōyasan / Hongū-Yunomine / Nachi) cancellable — Routes 168/311 can close after heavy rain",
   "Confirm secure motorcycle parking at every property (narrow onsen-hamlet lanes — ask where to leave the bikes)",
   "Reserve a Tsuboyu bath slot at Yunomine ahead of Day 5",
   "Family room / beds; private or family bath where wanted; dinner included at remote inns",
   "Laundry access every 3–4 days"
 ]},
 {"sec":"Ferry & timed stops","icon":"⛴️","items":[
   "Nankai Ferry (Day 9, Wakayama→Tokushima) is first-come, first-served for motorcycles — no reservation; arrive 30+ min early (deck ~20 bikes)",
   "Check the day's Nankai timetable (~8 sailings each way)",
   "Time the Naruto whirlpools to a spring-tide / slack window (full or new moon)",
   "Check road & river status daily in the typhoon-exposed Kii interior (Days 3–9)"
 ]},
 {"sec":"Insurance & health","icon":"🛡️","items":[
   "Travel + medical insurance covering motorcycling and the child",
   "Roadside-assistance / breakdown cover or rental add-on",
   "Personal medications + small first-aid kit",
   "Note nearest hospitals along the route"
 ]},
 {"sec":"Rider gear & packing","icon":"🧥","items":[
   "Armoured jacket & pants, gloves, riding boots (each rider)",
   "Rain layers and warm base layers (Kōyasan at ~800 m is cold in the evening)",
   "Sun protection, earplugs, neck tube",
   "Pack light — soft luggage / dry bags; big cases ride the takkyūbin, not the bikes",
   "Comfortable off-bike shoes & evening clothes"
 ]},
 {"sec":"Bike kit (carried by lead rider)","icon":"🔧","items":[
   "Basic tools + tyre repair/inflator",
   "First-aid kit",
   "Spare gloves / layers",
   "Phone mount + chargers / power bank",
   "Zip ties, tape, bungees"
 ]},
 {"sec":"Money & connectivity","icon":"📱","items":[
   "Cash — Japan is cash-heavy at rural inns, ferries and roadside stations",
   "eSIM or pocket Wi-Fi",
   "Offline Google Maps for the route regions",
   "Translation app (the family speaks English)"
 ]},
 {"sec":"Final week / day before","icon":"✅","items":[
   "Check the forecast — avoid typhoon/heavy-rain windows on the Kii side",
   "Reconfirm bikes, hotels, flights and Shinkansen seats",
   "Charge intercoms, phones, cameras, power banks",
   "Gear check + parked child-pillion setup test + gentle on-foot shakedown on Day 2",
   "Share the itinerary with family/contacts back home"
 ]}
]

# ============ GEO (routing points) ============
GEO = {
 "Haneda Airport, Tokyo":"35.54830,139.77800",
 "Haneda Airport":"35.54830,139.77800",
 "Shinagawa, Tokyo":"35.62876,139.73876",
 "Shinagawa Station Tokyo":"35.62876,139.73876",
 "Tokyo Station":"35.68123,139.76712",
 "Tokyo":"35.67620,139.65030",
 "Ghibli Museum Mitaka Tokyo":"35.69625,139.57028",
 "teamLab Planets TOKYO":"35.64944,139.79000",
 "Nintendo TOKYO Shibuya PARCO":"35.66230,139.69884",
 "Shibuya Crossing":"35.65950,139.70060",
 "Suita, Osaka":"34.75953,135.51676",
 "Universal Studios Japan":"34.66556,135.43250",
 "Super Nintendo World Osaka":"34.66694,135.43000",
 "Osaka, Japan":"34.69372,135.50225",
 "Osaka Castle":"34.68726,135.52585",
 "Osaka Aquarium Kaiyukan":"34.65452,135.42896",
 "Dotonbori Osaka":"34.66865,135.50310",
 "Koyasan, Wakayama, Japan":"34.21310,135.58440",
 "Okunoin Cemetery Koyasan":"34.21556,135.61089",
 "Konpon Daito Koyasan":"34.21305,135.58066",
 "Kongobu-ji Koyasan":"34.21290,135.58480",
 "Totsukawa, Nara, Japan":"33.99155,135.79170",
 "Totsukawa village":"33.99155,135.79170",
 "Tanise no Tsuribashi Totsukawa":"34.05540,135.74660",
 "Yunomine Onsen, Wakayama, Japan":"33.82680,135.77360",
 "Tsuboyu Yunomine Onsen":"33.82680,135.77360",
 "Kawayu Onsen":"33.83889,135.78889",
 "Kumano Hongu Taisha":"33.84030,135.77330",
 "Oyunohara Otorii":"33.83806,135.77139",
 "Doro-kyo Gorge, Japan":"33.79500,135.92000",
 "Doro-kyo Gorge Kitayama":"33.79500,135.92000",
 "Daimonzaka Nachi":"33.66556,135.89167",
 "Nachi Falls":"33.66989,135.89047",
 "Kii-Katsuura, Wakayama, Japan":"33.62587,135.94123",
 "Kumano Hayatama Taisha":"33.73389,135.99139",
 "Hotel Urashima Katsuura":"33.62806,135.95306",
 "Kushimoto, Wakayama, Japan":"33.47222,135.78500",
 "Hashigui-iwa Kushimoto":"33.48389,135.79361",
 "Sandanbeki Shirahama":"33.66694,135.34556",
 "Tore-Tore Ichiba Shirahama":"33.69861,135.37389",
 "Shirahama, Wakayama, Japan":"33.68530,135.33780",
 "Adventure World, Shirahama":"33.66250,135.37083",
 "Adventure World Shirahama":"33.66250,135.37083",
 "Shirarahama Beach Shirahama":"33.68722,135.33611",
 "Senjojiki Shirahama":"33.68389,135.33472",
 "Engetsu Island Shirahama":"33.68861,135.33806",
 "Sakinoyu Onsen Shirahama":"33.68500,135.33444",
 "Wakayama Port, Japan":"34.21806,135.14528",
 "Wakayama Castle":"34.22750,135.17139",
 "Nankai Ferry Wakayama Port":"34.21806,135.14528",
 "Naruto, Tokushima, Japan":"34.17220,134.60930",
 "Uzunomichi Naruto":"34.23617,134.64198",
 "Tokushima, Japan":"34.07423,134.55116",
 "Tokushima Station":"34.07423,134.55116",
 "Oboke, Tokushima, Japan":"33.87669,133.76722",
 "Oboke Gorge":"33.89327,133.75698",
 "Iya Valley":"33.90472,133.92436",
 "Iya Kazurabashi, Japan":"33.87513,133.83540",
 "Iya Kazurabashi":"33.87513,133.83540",
 "Iya no Shobenkozo":"33.86790,133.83780",
 "Nagoro Scarecrow Village":"33.85654,134.01941",
 "Kochi, Japan":"33.55888,133.53124",
 "Otoyo, Kochi, Japan":"33.76429,133.66433",
 "Michi-no-Eki Otoyo":"33.76429,133.66433",
 "Anpanman Museum Kami Kochi":"33.65560,133.71870",
 "Kochi Castle":"33.56081,133.53148",
 "Katsurahama":"33.49818,133.57443",
 "Susaki, Kochi, Japan":"33.40084,133.28294",
 "Susaki Kochi":"33.40084,133.28294",
 "Niyodo River":"33.53277,133.27345",
 "Tatsukushi":"32.78848,132.86744",
 "Sada Chinkabashi Shimanto":"33.01729,132.88750",
 "Shimanto, Kochi, Japan":"32.99139,132.93379",
 "Shimanto River, Japan":"33.19173,132.98024",
 "Shimanto River canoe":"33.19173,132.98024",
 "Shimanto River cycling":"33.19173,132.98024",
 "Cape Ashizuri":"32.72384,133.02032",
 "Uwajima, Ehime, Japan":"33.22357,132.56038",
 "Uwajima":"33.22357,132.56038",
 "Uwajima Castle":"33.21945,132.56528",
 "Uchiko Yokaichi":"33.53257,132.65981",
 "Garyu Sanso Ozu":"33.50631,132.55008",
 "Matsuyama, Ehime, Japan":"33.83551,132.76399",
 "Matsuyama Castle Ehime":"33.84558,132.76553",
 "Dogo Onsen, Matsuyama, Japan":"33.85207,132.78641",
 "Dogo Onsen Honkan":"33.85207,132.78641",
 "Botchan Ressha Matsuyama":"33.85058,132.78497",
 "Ishiteji Temple Matsuyama":"33.84790,132.79647",
 "Imabari, Ehime, Japan":"34.06600,132.99770",
 "Imabari Castle":"34.06339,133.00675",
 "Kirosan Observatory Park":"34.11993,133.03346",
 "Oyamazumi Shrine":"34.24792,133.00573",
 "Setoda":"34.30521,133.08625",
 "Setoda, Ikuchijima, Japan":"34.30521,133.08625",
 "Onomichi, Hiroshima, Japan":"34.40890,133.20491",
 "Senkoji Temple Onomichi":"34.41045,133.19871",
 "Onomichi Temple Walk":"34.40890,133.20491",
 "Kosanji Temple Setoda":"34.30139,133.08833",
 "Tomonoura, Japan":"34.38287,133.38120",
 "Tomonoura":"34.38287,133.38120",
 "Fukuyama Castle":"34.49114,133.36108",
 "Washuzan":"34.43555,133.81244",
 "Kurashiki, Okayama, Japan":"34.58498,133.77198",
 "Kurashiki Bikan":"34.59574,133.77177",
 "Himeji, Hyogo, Japan":"34.81542,134.68555",
 "Himeji Castle":"34.83945,134.69390",
 "Kobe, Japan":"34.68000,135.18000",
 "Kobe Harborland":"34.68007,135.18351",
 "Awaji Island, Japan":"34.32571,134.81311",
 "Akashi Kaikyo Bridge":"34.62294,135.02682",
 "Nijigen no Mori Awaji":"34.49417,134.93333",
 "Awaji Hanasajiki":"34.55355,134.97803",
 "Kyoto, Japan":"35.01156,135.76815",
 "Fushimi Inari Taisha":"34.96769,135.77919",
 "Kyoto Station":"34.98556,135.75861",
}

# --- Single source of truth for coordinates + wiki: poidb/coords.json ---
# The inline COORDS/GEO/WIKI above are the fallback/authoring default; when the
# POI database's coords file exists it OVERRIDES them, so refinements made by
# poidb/geocode.py (precise per-POI lat/lng) flow straight into data.js. The file
# is generated from these same dicts, so a clean checkout regenerates identically.
_COORDS_JSON = os.path.join(os.path.dirname(__file__), "poidb", "coords.json")
if os.path.exists(_COORDS_JSON):
    _cj = json.load(open(_COORDS_JSON, encoding="utf-8"))
    COORDS = {k: tuple(v) for k, v in _cj.get("dest_coords", {}).items()} or COORDS
    GEO = _cj.get("geo") or GEO
    WIKI = _cj.get("wiki") or WIKI

# ============ DAYART (region-matched ukiyo-e, keyed by day.d) ============
A = {
 "nihonbashi":"https://upload.wikimedia.org/wikipedia/commons/b/b8/Brooklyn_Museum_-_Nihonbashi_-_Utagawa_Hiroshige_%28Ando%29_-_overall.jpg",
 "fuji_train":"https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/Hokusai42_fuji-lake.jpg/1280px-Hokusai42_fuji-lake.jpg",
 "wave":"https://upload.wikimedia.org/wikipedia/commons/c/ca/%27The_Great_Wave_off_Kanagawa%27_by_Hokusai%2C_Honolulu_Museum_of_Art.jpg",
 "mist":"https://upload.wikimedia.org/wikipedia/commons/thumb/b/b9/Hiroshige%2C_A_family_in_a_misty_landscape.jpg/1280px-Hiroshige%2C_A_family_in_a_misty_landscape.jpg",
 "falls":"https://upload.wikimedia.org/wikipedia/commons/a/a2/Falls_of_Kirifuri_at_Mt._Kurokami%2C_Shimotsuke_Province_LACMA_M.2011.135.2_%281_of_2%29.jpg",
 "coast":"https://upload.wikimedia.org/wikipedia/commons/thumb/c/c6/Flickr_-_%E2%80%A6trialsanderrors_-_Hiroshige%2C_The_coast_at_Hota_in_Awa_province%2C_1858.jpg/1280px-Flickr_-_%E2%80%A6trialsanderrors_-_Hiroshige%2C_The_coast_at_Hota_in_Awa_province%2C_1858.jpg",
 "naruto":"https://upload.wikimedia.org/wikipedia/commons/thumb/6/68/Awa%2C_Naruto_Whirlpools%2C_ca_1855.jpg/1280px-Awa%2C_Naruto_Whirlpools%2C_ca_1855.jpg",
 "tosa":"https://upload.wikimedia.org/wikipedia/commons/7/7e/58_Tosa.jpg",
 "river":"https://upload.wikimedia.org/wikipedia/commons/thumb/4/46/Brooklyn_Museum_-_Kajikazawa_in_Kai_Province_-_Katsushika_Hokusai.jpg/1280px-Brooklyn_Museum_-_Kajikazawa_in_Kai_Province_-_Katsushika_Hokusai.jpg",
 "iyo":"https://upload.wikimedia.org/wikipedia/commons/5/5c/Hiroshige_Iyo_Saij%C5%8D.jpg",
 "sanuki":"https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Sanuki_Province%2C_Distant_View_of_Mount_Zozu_%285765892320%29.jpg/1280px-Sanuki_Province%2C_Distant_View_of_Mount_Zozu_%285765892320%29.jpg",
 "aki":"https://upload.wikimedia.org/wikipedia/commons/thumb/e/ee/Brooklyn_Museum_-_Itsukushima_in_Aki_Province_-_Utagawa_Hiroshige_%28Ando%29.jpg/1280px-Brooklyn_Museum_-_Itsukushima_in_Aki_Province_-_Utagawa_Hiroshige_%28Ando%29.jpg",
 "bingo":"https://upload.wikimedia.org/wikipedia/commons/f/fc/Bingo_Province%2C_Abuto%2C_Kannon_Temple_%285765891938%29.jpg",
 "bizen":"https://upload.wikimedia.org/wikipedia/commons/thumb/b/b6/Bizen_Province%2C_Tanokuchi_Coast%2C_Yugasan_torii_%285765891374%29.jpg/1280px-Bizen_Province%2C_Tanokuchi_Coast%2C_Yugasan_torii_%285765891374%29.jpg",
 "harima":"https://upload.wikimedia.org/wikipedia/commons/a/ad/45_-_Harima_Province%2C_Maiko_Beach%2C_from_the_series_Famous_Places_in_the_Sixty-odd_Provinces%2C_MFAB_11.26243.jpg",
 "settsu":"https://upload.wikimedia.org/wikipedia/commons/c/ce/05_Settsu_n.jpg",
 "kyoto":"https://upload.wikimedia.org/wikipedia/commons/thumb/6/60/Hiroshige-53-Stations-Hoeido-55-Kyoto-MFA-01.jpg/1280px-Hiroshige-53-Stations-Hoeido-55-Kyoto-MFA-01.jpg",
}
DAYART = {
 "0":A["nihonbashi"],"1":A["nihonbashi"],"2":A["fuji_train"],"3":A["mist"],"4":A["mist"],
 "5":A["falls"],"6":A["falls"],"7":A["coast"],"8":A["wave"],"9":A["naruto"],
 "10":A["river"],"11":A["mist"],"12":A["tosa"],"13":A["river"],"14":A["river"],
 "15":A["iyo"],"16":A["iyo"],"17":A["aki"],"18":A["bingo"],"19":A["bizen"],
 "20":A["harima"],"21":A["settsu"],"22":A["settsu"],"23":A["settsu"],"24":A["kyoto"],
 "25":A["nihonbashi"],
}

# ============ EMIT ============
def js(v, indent=0):
    pad = "  " * indent
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        if not v:
            return "[]"
        items = [js(x, indent+1) for x in v]
        # inline short lists of scalars/strings
        if all(isinstance(x, (str, int, float, bool)) for x in v):
            joined = ", ".join(items)
            if len(joined) < 100:
                return "[" + joined + "]"
        inner = ",\n".join("  " * (indent+1) + it for it in items)
        return "[\n" + inner + "\n" + pad + "]"
    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            parts.append(json.dumps(k, ensure_ascii=False) + ": " + js(val, indent+1))
        inner = ", ".join(parts)
        if len(inner) < 110 and not any(isinstance(x,(list,dict)) for x in v.values()):
            return "{ " + inner + " }"
        inner = ",\n".join("  " * (indent+1) + json.dumps(k, ensure_ascii=False) + ": " + js(val, indent+1) for k,val in v.items())
        return "{\n" + inner + "\n" + pad + "}"
    raise TypeError(str(type(v)))

def emit_dest(d):
    keys = ["id","name","jp","region","type","days","legMiles"]
    o = []
    o.append("{")
    o.append('  id: %s,' % json.dumps(d["id"]))
    o.append('  name: %s,' % json.dumps(d["name"], ensure_ascii=False))
    o.append('  jp: %s,' % json.dumps(d["jp"], ensure_ascii=False))
    o.append('  region: %s,' % json.dumps(d["region"], ensure_ascii=False))
    o.append('  type: %s,' % json.dumps(d["type"]))
    o.append('  days: %s,' % json.dumps(d["days"], ensure_ascii=False))
    o.append('  legMiles: %d,' % d["legMiles"])
    o.append('  lat: %s, lng: %s, zoom: %d,' % (d["lat"], d["lng"], d["zoom"]))
    o.append('  tagline: %s,' % json.dumps(d.get("tagline",""), ensure_ascii=False))
    o.append('  intro: ' + js(d["intro"], 1) + ',')
    o.append('  highlights: ' + js(d["highlights"], 1) + ',')
    o.append('  food: ' + js(d["food"], 1) + ',')
    o.append('  hotels: ' + js(d["hotels"], 1) + ',')
    o.append('  links: ' + js(d["links"], 1) + ',')
    o.append('  photos: ' + js(d["photos"], 1))
    o.append("}")
    return "\n".join(o)

HEADER = open(os.path.join(os.path.dirname(__file__), "data_header.txt"), encoding="utf-8").read()

out = [HEADER]
out.append("window.DESTINATIONS = [")
out.append(",\n".join(emit_dest(DESTS[i]) for i in ORDER))
out.append("];\n")

out.append('window.HOME = { city: "Seattle", airport: "SEA" };')
out.append("window.FLIGHTS = " + js(FLIGHTS, 0) + ";\n")

out.append("/* Day-by-day schedule (Day 0–25). day.html builds a timed routine per day. */")
out.append("window.DAYS = [")
out.append(",\n".join(js(d, 1) for d in DAYS))
out.append("];\n")

out.append("/* Pre-trip preparation checklist (rendered by checklist.html). */")
out.append("window.CHECKLIST = " + js(CHECKLIST, 0) + ";\n")

out.append("/* Geocoded routing points (lat,lng) so Google Maps always resolves them. */")
out.append("window.GEO = " + js(GEO, 0) + ";\n")

out.append("/* Region-matched public-domain ukiyo-e prints used as each day's hero artwork. */")
out.append("window.DAYART = " + js(DAYART, 0) + ";")

if __name__ == "__main__":
    open(os.path.join(os.path.dirname(__file__), "data.js"), "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("wrote data.js")
    print("DESTINATIONS:", len(ORDER), "DAYS:", len(DAYS))
    print("ids:", ", ".join(ORDER))
    # image url inventory
    urls = set()
    for i in ORDER:
        for ph in DESTS[i]["photos"]:
            urls.add(ph["src"])
    for d in DAYS:
        for p in d["poi"]:
            if p.get("img"): urls.add(p["img"])
    for v in DAYART.values(): urls.add(v)
    urls.add(FLIGHTS and "")
    print("unique image urls:", len([u for u in urls if u]))
