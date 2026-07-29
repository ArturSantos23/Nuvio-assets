#!/usr/bin/env python3
"""
Build a luckynumb3rs-style poster-mosaic backdrop from TMDB stills.

Produces a 3840x2160 WEBP: a grid of 16:9 title stills, rotated 10 degrees,
lit from the upper right -- matching the other International Cinema
backdrops in this repo.

Usage
-----
    export TMDB_TOKEN='<your TMDB v4 Read Access Token>'
    python3 scripts/build_backdrop.py --lang pt --country PT \
        --out international-cinema/portuguese-cinema/backdrop.webp

Options worth knowing:
    --keep-temp     leave the downloaded stills in scripts/tmp-stills/
                    (default: they are kept, so re-runs are instant)
    --clean         delete the temp folder before starting (fresh download)
    --seed N        change the tile shuffle; same seed = same layout
    --dry-run       compose from solid colour placeholders, no network

Requires: pillow, requests   ->   pip install pillow requests
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import time
from pathlib import Path

_HOWTO = """
Missing dependency: {name}

macOS ships a Python that refuses `pip install` (PEP 668), so use a virtualenv
-- from the repo root:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install requests pillow

then re-run this script with .venv active. To leave it later: deactivate
"""

try:
    import requests
except ImportError:
    sys.exit(_HOWTO.format(name="requests"))
try:
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
except ImportError:
    sys.exit(_HOWTO.format(name="pillow"))

REPO = Path(__file__).resolve().parent.parent
TMP = REPO / "scripts" / "tmp-stills"

API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w780"

# ---- canvas / look ----------------------------------------------------------
OUT_W, OUT_H = 3840, 2160
ANGLE = 10.0          # measured off the existing backdrops in this repo
ROW_H = 300           # tile height in px, before rotation
GAP = 16              # gap between tiles
RADIUS = 18           # tile corner radius
OVERSCAN = 1.45       # build bigger, then rotate + centre-crop
DARKEN = 0.72         # global multiply so the flag/logo stays readable on top

# The reference backdrops are not lit evenly: there is a warm light in the
# upper right, with the frame falling away to near-black at the lower left.
LIGHT = (0.76, 0.17)  # light centre, as a fraction of (width, height)
FALLOFF = 1.25        # radius of the brightness falloff (1.0 = half-diagonal)
EDGE = 0.30           # brightness furthest from the light
GLOW = (68, 48, 6)    # peak warm tint added at the light centre
GLOW_R = 0.78         # radius of the warm tint, relative to FALLOFF


# ---- TMDB -------------------------------------------------------------------
def tmdb_get(session: requests.Session, path: str, **params) -> dict:
    for attempt in range(5):
        r = session.get(f"{API}{path}", params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 2)) + 1)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"TMDB kept rate-limiting {path}")


def discover(session, media, lang, country, pages, min_votes):
    """Most popular movies / TV in a given original language."""
    out = []
    for page in range(1, pages + 1):
        params = {
            "include_adult": "false",
            "language": "en-US",
            "page": page,
            "sort_by": "popularity.desc",
            "with_original_language": lang,
            "vote_count.gte": min_votes,
        }
        if country:
            params["with_origin_country"] = country
        data = tmdb_get(session, f"/discover/{media}", **params)
        for item in data.get("results", []):
            if item.get("backdrop_path"):
                out.append(
                    {
                        "id": item["id"],
                        "media": media,
                        "title": item.get("title") or item.get("name") or "?",
                        "path": item["backdrop_path"],
                        "popularity": item.get("popularity", 0),
                    }
                )
        if page >= data.get("total_pages", 1):
            break
    return out


def collect(token, lang, country, want):
    session = requests.Session()
    session.headers.update(
        {"Authorization": f"Bearer {token}", "accept": "application/json"}
    )
    items = []
    # loosen progressively until we have enough: vote floor first, then country
    passes = [(50, country), (10, country), (0, country), (0, None)]
    for min_votes, ctry in passes:
        for media in ("movie", "tv"):
            items += discover(session, media, lang, ctry, pages=5,
                              min_votes=min_votes)
        seen, uniq = set(), []
        for it in items:
            key = (it["media"], it["id"])
            if key not in seen:
                seen.add(key)
                uniq.append(it)
        items = uniq
        print(f"  vote_count>={min_votes:<3} country={ctry or '-':<3} "
              f"-> {len(items)} titles with stills")
        if len(items) >= want:
            break
    items.sort(key=lambda x: -x["popularity"])
    return items[:want], session


def download(session, items):
    TMP.mkdir(parents=True, exist_ok=True)
    files = []
    for i, it in enumerate(items, 1):
        dest = TMP / f"{it['media']}_{it['id']}.jpg"
        if not dest.exists():
            r = session.get(IMG + it["path"], timeout=60)
            if r.status_code != 200:
                print(f"  ! skip {it['title']} ({r.status_code})")
                continue
            dest.write_bytes(r.content)
        files.append(dest)
        if i % 20 == 0:
            print(f"  ...{i}/{len(items)}")
    return files


# ---- composition ------------------------------------------------------------
def rounded(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1],
                                           radius=radius, fill=255)
    out = img.convert("RGBA")
    out.putalpha(mask)
    return out


def tile(path: Path, w: int, h: int) -> Image.Image:
    im = Image.open(path).convert("RGB")
    # cover-fit then centre-crop
    s = max(w / im.width, h / im.height)
    im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))),
                   Image.LANCZOS)
    left = (im.width - w) // 2
    top = (im.height - h) // 3          # bias upward: faces sit high in stills
    return rounded(im.crop((left, top, left + w, top + h)), RADIUS)


def compose(files, seed):
    rng = random.Random(seed)
    cw, ch = int(OUT_W * OVERSCAN), int(OUT_H * OVERSCAN)
    canvas = Image.new("RGB", (cw, ch), (8, 8, 10))

    pool = list(files)
    rng.shuffle(pool)
    if not pool:
        raise SystemExit("no stills to compose")
    cursor = 0

    def take():
        nonlocal cursor
        f = pool[cursor % len(pool)]
        cursor += 1
        return f

    y = -ROW_H // 2
    row = 0
    while y < ch:
        # rows alternate height a little, like the reference collages
        h = ROW_H + rng.choice([-40, -20, 0, 0, 20, 45])
        x = -rng.randint(0, 400)
        while x < cw:
            # most tiles are 16:9, some run wide
            aspect = rng.choice([16 / 9, 16 / 9, 16 / 9, 2.35, 1.5])
            w = int(h * aspect)
            try:
                t = tile(take(), w, h)
                # subtle per-tile brightness variation
                if rng.random() < 0.45:
                    f = rng.uniform(0.72, 0.95)
                    rgb = t.convert("RGB").point(lambda v, f=f: int(v * f))
                    rgb = rgb.convert("RGBA")
                    rgb.putalpha(t.split()[3])
                    t = rgb
                canvas.paste(t, (x, y), t)
            except Exception as e:
                print(f"  ! tile failed: {e}")
            x += w + GAP
        y += h + GAP
        row += 1

    # rotate, then centre-crop back to 4K
    canvas = canvas.rotate(ANGLE, resample=Image.BICUBIC, expand=False)
    left = (cw - OUT_W) // 2
    top = (ch - OUT_H) // 2
    canvas = canvas.crop((left, top, left + OUT_W, top + OUT_H))

    # darken so foreground artwork stays legible
    canvas = canvas.point(lambda v: int(v * DARKEN))

    canvas = light_and_vignette(canvas)
    return canvas


def _falloff_mask(size, radius, gamma=1.0):
    """Radial falloff around LIGHT: 255 at the light, 0 beyond `radius`.

    Built small and upscaled - a smooth gradient needs no numpy this way.
    """
    sw, sh = 256, 144
    small = Image.new("L", (sw, sh))
    px = small.load()
    lx, ly = LIGHT
    for j in range(sh):
        dy = (j + 0.5) / sh - ly
        for i in range(sw):
            dx = (i + 0.5) / sw - lx
            # normalise so 1.0 is roughly half the frame diagonal
            d = math.sqrt((dx * dx) + (dy * dy) * 0.55) / (0.5 * radius)
            f = 1.0 - d * d
            f = 0.0 if f < 0 else (1.0 if f > 1 else f)
            px[i, j] = int(255 * (f ** gamma))
    return small.resize(size, Image.BICUBIC)


def light_and_vignette(img: Image.Image) -> Image.Image:
    # 1. brightness falls away from the light down to EDGE
    lum = _falloff_mask(img.size, FALLOFF)
    lum = lum.point(lambda p: int(255 * (EDGE + (1 - EDGE) * (p / 255.0))))
    img = Image.merge("RGB", [ImageChops.multiply(c, lum) for c in img.split()])

    # 2. warm tint added on top of it, tighter than the brightness falloff
    warm = _falloff_mask(img.size, FALLOFF * GLOW_R, gamma=1.6)
    tint = Image.merge(
        "RGB", [warm.point(lambda p, c=c: int(p * c / 255.0)) for c in GLOW]
    )
    return ImageChops.add(img, tint)


def placeholders(n=60):
    """--dry-run tiles, so the layout can be checked without network."""
    TMP.mkdir(parents=True, exist_ok=True)
    out = []
    rng = random.Random(7)
    for i in range(n):
        p = TMP / f"_placeholder_{i:02d}.jpg"
        if not p.exists():
            c = (rng.randint(30, 190), rng.randint(30, 190), rng.randint(40, 200))
            im = Image.new("RGB", (780, 439), c)
            d = ImageDraw.Draw(im)
            d.rectangle([20, 20, 760, 419], outline=(255, 255, 255), width=6)
            im.save(p, quality=80)
        out.append(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="pt", help="ISO-639-1 original language")
    ap.add_argument("--country", default="PT", help="ISO-3166-1 origin country, '' to disable")
    ap.add_argument("--out", default="international-cinema/portuguese-cinema/backdrop.webp")
    ap.add_argument("--tiles", type=int, default=90, help="how many stills to gather")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--quality", type=int, default=88)
    ap.add_argument("--clean", action="store_true", help="wipe temp stills first")
    ap.add_argument("--keep-temp", action="store_true", default=True)
    ap.add_argument("--dry-run", action="store_true", help="compose from placeholders")
    args = ap.parse_args()

    if args.clean and TMP.exists():
        for f in TMP.iterdir():
            f.unlink()
        print(f"cleaned {TMP}")

    if args.dry_run:
        print("dry run - composing from placeholder tiles")
        files = placeholders()
    else:
        token = os.environ.get("TMDB_TOKEN", "").strip()
        if not token:
            sys.exit("Set TMDB_TOKEN to your TMDB v4 Read Access Token first:\n"
                     "  export TMDB_TOKEN='eyJhbGciOi...'")
        print(f"querying TMDB for lang={args.lang} country={args.country or '-'}")
        items, session = collect(token, args.lang, args.country or None, args.tiles)
        if not items:
            sys.exit("TMDB returned no titles with stills - loosen --country or --lang")
        print(f"downloading {len(items)} stills into {TMP.relative_to(REPO)}/")
        files = download(session, items)
        print(f"  got {len(files)} images")

    print("composing 3840x2160 mosaic ...")
    img = compose(files, args.seed)
    out = REPO / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "WEBP", quality=args.quality, method=6)
    print(f"wrote {out.relative_to(REPO)}  ({out.stat().st_size/1024:.0f} KB)")

    if not args.keep_temp and TMP.exists():
        for f in TMP.iterdir():
            f.unlink()
        TMP.rmdir()
        print("removed temp stills")
    else:
        print(f"temp stills kept in {TMP.relative_to(REPO)}/ (git-ignored)")


if __name__ == "__main__":
    main()
