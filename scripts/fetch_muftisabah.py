#!/usr/bin/env python3
"""
Fill Sabah months that JAKIM hasn't published yet from the Sabah mufti's
yearly posters (Takwim Waktu Solat 1448H, one poster per zone SBH01-09).

Each poster is one page with the 12 Hijri months as a grid of blocks (4
across, 3 down). In a block, each row is a day and each prayer has its own
column, where one value often covers several days as a merged cell. The cell
borders are horizontal lines across that column, so every day takes the
value of the cell its row falls in.

Checks before writing anything: every day of the Hijri year gets all 8
times, days run on from 1 Muharram without gaps, times are in order, and
every day that JAKIM has already published must match JAKIM (within 1
minute on at most 1% of times: see below).

Writes only whole Gregorian months that have no file yet, and lists them in
sources/provisional.json, so fetch_jakim.py replaces them once JAKIM
publishes. Never overwrites JAKIM's files.

Usage: python3 scripts/fetch_muftisabah.py [--check]
  --check  parse and compare only, write nothing
"""

import calendar
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, timedelta

import pdfplumber
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_YAML = os.path.join(ROOT, "sources", "muftisabah", "sources.yaml")
CACHE_DIR = os.path.join(ROOT, "sources", "muftisabah", "pdfs")
OUT_DIR = os.path.join(ROOT, "data", "prayer-times", "MY")
PROVISIONAL = os.path.join(ROOT, "sources", "provisional.json")
SOURCE_NOTE = "Pejabat Mufti Negeri Sabah, Takwim Waktu Solat 1448H"

COLUMNS = ["Imsak", "Subuh", "Syuruk", "Dhuha", "Zohor", "Asar", "Maghrib", "Isyak"]
FIELDS = ["imsak", "fajr", "syuruk", "dhuha", "dhuhr", "asr", "maghrib", "isha"]
TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


def download(url, path):
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    subprocess.run(["curl", "-sSfL", "-A", "Mozilla/5.0", url, "-o", tmp], check=True)
    with open(tmp, "rb") as f:
        if f.read(5) != b"%PDF-":
            os.remove(tmp)
            raise RuntimeError(f"not a PDF: {url}")
    os.replace(tmp, path)


def to_24h(field, text):
    """The posters print 12-hour times without am/pm."""
    m = TIME.match(text)
    if not m:
        raise ValueError(f"bad time {text!r}")
    h, mi = int(m.group(1)), int(m.group(2))
    if field == "dhuhr":
        if h < 11:
            h += 12
    elif field in ("asr", "maghrib", "isha"):
        h += 12
    return f"{h:02d}:{mi:02d}"


def parse_poster(path):
    """Days of the Hijri year in order: [{field: "HH:MM"}], one per day."""
    page = pdfplumber.open(path).pages[0]
    words = page.extract_words()
    hlines = [l for l in page.lines if abs(l["top"] - l["bottom"]) < 0.5]

    # One block per "Imsak" header; blocks read left to right, top to bottom.
    headers = [w for w in words if w["text"] == "Imsak"]
    if len(headers) != 12:
        raise ValueError(f"{path}: {len(headers)} month blocks, expected 12")
    headers.sort(key=lambda w: (round(w["top"] / 50), w["x0"]))

    days = []
    for block, head in enumerate(headers):
        # Column edges: the header words of the 8 prayer columns.
        row = [w for w in words if abs(w["top"] - head["top"]) < 3 and w["x0"] >= head["x0"] - 2]
        row = [w for w in sorted(row, key=lambda w: w["x0"]) if w["text"] in COLUMNS][:8]
        if [w["text"] for w in row] != COLUMNS:
            raise ValueError(f"{path}: block {block + 1} header {[w['text'] for w in row]}")
        centres = [(w["x0"] + w["x1"]) / 2 for w in row]
        step = (centres[-1] - centres[0]) / 7
        edges = [c - step / 2 for c in centres] + [centres[-1] + step / 2]

        # Day rows: the Hijri day numbers in the block's first column.
        left = head["x0"] - 110
        top = head["bottom"] + 12
        below = [h for h in headers if h["top"] > head["top"] + 50 and abs(h["x0"] - head["x0"]) < 20]
        bottom = min([h["top"] for h in below], default=page.height) - 30
        numbers = sorted(
            (w for w in words if left <= w["x0"] < left + 30 and top < w["top"] < bottom and w["text"].isdigit()),
            key=lambda w: w["top"],
        )
        rows = []
        for w in numbers:
            if int(w["text"]) == len(rows) + 1:
                rows.append((w["top"] + w["bottom"]) / 2)
        if len(rows) not in (29, 30):
            raise ValueError(f"{path}: block {block + 1} has {len(rows)} days")
        pitch = (rows[-1] - rows[0]) / (len(rows) - 1)
        block_top, block_bottom = rows[0] - pitch / 2, rows[-1] + pitch / 2

        values = [dict() for _ in rows]
        for field, x0, x1 in zip(FIELDS, edges, edges[1:]):
            # Cell borders: lines across this column inside the block.
            cuts = sorted(
                {round(l["top"], 1) for l in hlines
                 if l["x0"] <= x0 + 3 and l["x1"] >= x1 - 3 and block_top + 2 < l["top"] < block_bottom - 2}
            )
            bounds = [block_top] + cuts + [block_bottom]
            # Some times come out in pieces ("4:4" + "3"): join the pieces
            # of a cell in reading order.
            texts = [w for w in words if x0 <= (w["x0"] + w["x1"]) / 2 < x1
                     and block_top < w["top"] < block_bottom and re.fullmatch(r"[\d:]+", w["text"])]
            for a, b in zip(bounds, bounds[1:]):
                inside = sorted((w for w in texts if a <= (w["top"] + w["bottom"]) / 2 < b),
                                key=lambda w: (round(w["top"]), w["x0"]))
                text = "".join(w["text"] for w in inside)
                covered = [i for i, y in enumerate(rows) if a <= y < b]
                if not covered:
                    if text:
                        raise ValueError(f"{path}: block {block + 1} {field}: {text} on no day")
                    continue
                if not TIME.match(text):
                    raise ValueError(f"{path}: block {block + 1} {field} days {covered[0] + 1}-{covered[-1] + 1}: {text!r}")
                for i in covered:
                    values[i][field] = to_24h(field, text)
        for i, v in enumerate(values):
            if len(v) != len(FIELDS):
                raise ValueError(f"{path}: block {block + 1} day {i + 1} missing {set(FIELDS) - set(v)}")
        days.extend(values)
    return days


def minutes(hhmm):
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def load_month(zone, year, month):
    path = os.path.join(OUT_DIR, zone, f"{year}-{month:02d}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def main():
    check_only = "--check" in sys.argv[1:]
    with open(SOURCES_YAML) as f:
        sources = yaml.safe_load(f)
    first = date.fromisoformat(sources["first_day"])

    provisional = {}
    if os.path.exists(PROVISIONAL):
        with open(PROVISIONAL) as f:
            provisional = json.load(f)

    problems = 0
    for entry in sources["pdfs"]:
        zone = entry["zone"]
        path = os.path.join(CACHE_DIR, str(sources["hijri_year"]), os.path.basename(entry["url"]))
        download(entry["url"], path)
        days = parse_poster(path)

        by_month = defaultdict(list)
        for i, times in enumerate(days):
            d = first + timedelta(days=i)
            if [times[f] for f in FIELDS] != sorted(times[f] for f in FIELDS):
                raise ValueError(f"{zone} {d}: times not in order {times}")
            by_month[(d.year, d.month)].append({"date": d.isoformat(), **{f: times[f] for f in FIELDS}})

        # Every day JAKIM has published must match exactly (except months
        # we wrote ourselves earlier).
        compared, diffs = 0, []
        for (y, m), entries in by_month.items():
            key = f"MY/{zone}/{y}-{m:02d}"
            published = None if key in provisional else load_month(zone, y, m)
            if not published:
                continue
            ours = {e["date"]: e for e in entries}
            for e in published:
                o = ours.get(e["date"])
                if not o:
                    continue
                for f in FIELDS:
                    compared += 1
                    if e.get(f) != o[f]:
                        gap = abs(minutes(e[f]) - minutes(o[f]))
                        diffs.append((gap, f"{e['date']} {f}: JAKIM {e.get(f)}, poster {o[f]}"))
        span = f"{len(days)} days ({first} to {first + timedelta(days=len(days) - 1)})"
        # The posters group days into merged cells, and on a few days at a
        # cell's edge they are 1 minute off e-Solat (1448H: 8 of 14,256
        # times). Anything bigger, or more than 1%, means a parsing problem.
        bad = [d for gap, d in diffs if gap > 1]
        print(f"  {zone}: {span}; {compared} times compared with JAKIM, {len(diffs)} differ by 1 minute")
        for _, d in diffs:
            print(f"    {d}")
        if bad or len(diffs) > compared / 100:
            problems += 1
            print(f"    TOO DIFFERENT: {len(bad)} by more than 1 minute")
            continue

        if check_only:
            continue
        for (y, m), entries in sorted(by_month.items()):
            key = f"MY/{zone}/{y}-{m:02d}"
            if len(entries) != calendar.monthrange(y, m)[1]:
                continue  # partial month at either end of the Hijri year
            if load_month(zone, y, m) is not None and key not in provisional:
                continue  # JAKIM's
            out = os.path.join(OUT_DIR, zone, f"{y}-{m:02d}.json")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w") as f:
                json.dump(entries, f, indent=2)
                f.write("\n")
            provisional[key] = SOURCE_NOTE
            print(f"    wrote {key} (provisional)")

    if not check_only:
        with open(PROVISIONAL, "w") as f:
            json.dump(dict(sorted(provisional.items())), f, indent=2)
            f.write("\n")
    if problems:
        print(f"\n{problems} zone(s) differ from JAKIM: nothing written for them")
        sys.exit(1)


if __name__ == "__main__":
    main()
