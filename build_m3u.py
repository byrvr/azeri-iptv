#!/usr/bin/env python3
"""Regenerate playlist.m3u and playlist-all.m3u from playlist.json.

Only channels in the `verified` tier are written. Run this after
`selftest.py --promote` so the .m3u files pick up whatever changed.

    playlist.m3u      one entry per channel
    playlist-all.m3u  same, plus each working alternate URL as its own entry
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
doc = json.load(open(os.path.join(HERE, "playlist.json"), encoding="utf-8"))
verified = [c for c in doc["channels"] if c["tier"] == "verified"]

# No x-tvg-url: the azepg.ddns.net folder is an HTML listing of per-channel
# files with Unix timestamps, which TV apps can't parse as XMLTV.
HEADER = "#EXTM3U"


def entry(c, url, label):
    attrs = f'tvg-id="{c["id"]}" tvg-name="{label}"'
    if c.get("logo"):
        attrs += f' tvg-logo="{c["logo"]}"'
    attrs += f' group-title="{c["group"]}"'
    lines = [f"#EXTINF:-1 {attrs},{label}"]
    # Headers belong to the primary URL; alternates are separate hosts.
    if url == c["url"]:
        for k, v in (c.get("headers") or {}).items():
            lines.append(f"#EXTVLCOPT:http-{k.lower()}={v}")
    lines.append(url)
    return lines


def write(name, entries):
    lines = [HEADER]
    for c, url, label in entries:
        lines += entry(c, url, label)
    open(os.path.join(HERE, name), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{name}: {len(entries)} entries")


write("playlist.m3u", [(c, c["url"], c["name"]) for c in verified])

allc = []
for c in verified:
    allc.append((c, c["url"], c["name"]))
    alts = c.get("alt") or []
    for i, u in enumerate(alts):
        label = f"{c['name']} (alt)" if len(alts) == 1 else f"{c['name']} (alt {i + 1})"
        allc.append((c, u, label))
write("playlist-all.m3u", allc)
