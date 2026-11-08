#!/usr/bin/env python3
"""Regenerate playlist.m3u and playlist-all.m3u from playlist.json.

Only channels in the `verified` tier are written, one entry per channel, using
each channel's primary URL. Alternates stay in playlist.json: selftest.py and
autoupdate.py promote a working alternate to primary when the primary dies, so
the TV never needs to see them. (They used to be listed as extra entries, but
an untested alternate can be dead or show a "blocked" slate.)

playlist-all.m3u is the same file under its old name, so TV apps already
pointed at it keep working.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
doc = json.load(open(os.path.join(HERE, "playlist.json"), encoding="utf-8"))
verified = [c for c in doc["channels"] if c["tier"] == "verified"]

# No x-tvg-url: the azepg.ddns.net folder is an HTML listing of per-channel
# files with Unix timestamps, which TV apps can't parse as XMLTV.
HEADER = "#EXTM3U"

# Playlist headers become #EXTVLCOPT:http-<name> lines. VLC (and the IPTV apps
# that copy its syntax) spell the Referer option "http-referrer".
VLC_NAMES = {"referer": "referrer"}


lines = [HEADER]
for c in verified:
    attrs = f'tvg-id="{c["id"]}" tvg-name="{c["name"]}"'
    if c.get("logo"):
        attrs += f' tvg-logo="{c["logo"]}"'
    attrs += f' group-title="{c["group"]}"'
    lines.append(f"#EXTINF:-1 {attrs},{c['name']}")
    for k, v in (c.get("headers") or {}).items():
        lines.append(f"#EXTVLCOPT:http-{VLC_NAMES.get(k.lower(), k.lower())}={v}")
    lines.append(c["url"])
body = "\n".join(lines) + "\n"

for name in ("playlist.m3u", "playlist-all.m3u"):
    open(os.path.join(HERE, name), "w", encoding="utf-8").write(body)
print(f"playlist.m3u, playlist-all.m3u: {len(verified)} channels")
