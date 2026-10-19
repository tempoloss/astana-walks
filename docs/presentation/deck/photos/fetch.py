# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11"]
# ///
"""The photographs of the deck: Wikimedia Commons originals, cropped and sized for their slides.

    uv run docs/presentation/deck/photos/fetch.py

credits.json holds every photo: the Commons file, its page, author and licence (all CC0 or CC BY-SA, credited on the
sources slide), the crop as fractions of the original (left, top, right, bottom) and the output size. The originals are
kept in photos/.cache (not in git); the cropped JPEGs next to this file are what slides.html shows.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache"
UA = {"User-Agent": "anyq-deck/1.0 (https://anyq.an8kk.dev; photo credits on the sources slide)"}
API = "https://commons.wikimedia.org/w/api.php"


def original(title: str) -> Path:
    dst = CACHE / (title.removeprefix("File:").replace(" ", "_"))
    if dst.exists():
        return dst
    q = urllib.parse.urlencode({"action": "query", "titles": title, "prop": "imageinfo", "iiprop": "url",
                                "format": "json", "formatversion": "2"})
    with urllib.request.urlopen(urllib.request.Request(f"{API}?{q}", headers=UA), timeout=60) as r:
        url = json.loads(r.read())["query"]["pages"][0]["imageinfo"][0]["url"]
    CACHE.mkdir(exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        dst.write_bytes(r.read())
    return dst


def main() -> None:
    for name, c in json.loads((HERE / "credits.json").read_text(encoding="utf-8")).items():
        im = Image.open(original(c["commons"])).convert("RGB")
        l, t, r, b = c["crop"]
        box = (round(l * im.width), round(t * im.height), round(r * im.width), round(b * im.height))
        out = im.crop(box).resize(tuple(c["size"]), Image.LANCZOS)
        out.save(HERE / f"{name}.jpg", "JPEG", quality=84, optimize=True, progressive=True)
        print(f"{name}.jpg {out.size[0]}x{out.size[1]} from {box} of {im.width}x{im.height}")


if __name__ == "__main__":
    main()
