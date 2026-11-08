#!/usr/bin/env python3
"""Self-test every channel in playlist.json from YOUR network.

Channels marked `"geo": "AZ"` only answer from inside Azerbaijan. From any
other country their failures count only when they're unambiguous (404, 410,
the domain no longer exists, the stream stopped); a 403 or timeout there is
treated as "can't tell from here" and the channel is left alone.

    python3 selftest.py                    # tests playlist.json next to this file
    python3 selftest.py --tier unreachable # just re-check the dead ones
    python3 selftest.py --promote          # rewrite playlist.json: passing channels
                                           # become `verified`, failing ones
                                           # `unreachable` with the reason
    python3 build_m3u.py                   # then rebuild the .m3u files

A channel passes only if the manifest parses as HLS, a media playlist
resolves, a real segment downloads, and the live edge advances.
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 15
HERE = os.path.dirname(os.path.abspath(__file__))
# Failures that mean the stream is gone wherever you are, as opposed to a
# geo-block (403, timeouts, resets, an HTML page instead of a playlist).
DEFINITIVE = re.compile(
    r"HTTP Error (404|410)\b|nodename nor servname|Name or service not known"
    r"|No address associated|VOD, not live|manifest frozen")


def fetch(url, headers=None, limit=None):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.status, (r.read(limit) if limit else r.read()), r.geturl()


def seq_of(t):
    m = re.search(r"#EXT-X-MEDIA-SEQUENCE:(\d+)", t)
    return int(m.group(1)) if m else None


def country(attempts=3):
    """Two-letter country this network exits from, or None."""
    for i in range(attempts):
        try:
            req = urllib.request.Request("https://www.cloudflare.com/cdn-cgi/trace",
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                m = re.search(r"^loc=(\w+)$", r.read().decode(), re.M)
                if m:
                    return m.group(1)
        except Exception:
            pass
        if i < attempts - 1:
            time.sleep(10)
    return None


def can_judge(ch, result, here):
    """Whether this result says anything about the channel from network `here`."""
    if result["ok"] or not ch.get("geo") or ch["geo"] == here:
        return True
    return bool(DEFINITIVE.search(result["detail"]))


def probe(url, headers):
    """Return (ok, detail)."""
    try:
        st, body, final = fetch(url, headers)
    except Exception as e:
        return False, f"{type(e).__name__.replace('Error','')}: {e}"[:70]
    if "/blocked/" in final:
        return False, "redirected to a 'blocked' slate"
    text = body.decode("utf-8", "replace")
    if not text.lstrip().startswith("#EXTM3U"):
        return False, "not HLS (error page?)"

    if "#EXT-X-STREAM-INF" in text:
        best, res = None, "?"
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                bw = re.search(r"BANDWIDTH=(\d+)", ln)
                rs = re.search(r"RESOLUTION=([\dx]+)", ln)
                for nx in lines[i + 1:]:
                    if nx.strip() and not nx.startswith("#"):
                        cand = (int(bw.group(1)) if bw else 0,
                                rs.group(1) if rs else "?",
                                urllib.parse.urljoin(final, nx.strip()))
                        if best is None or cand[0] > best[0]:
                            best, res = cand, cand[1]
                        break
        if best is None:
            return False, "master with no variants"
        try:
            _, mb, mfinal = fetch(best[2], headers)
        except Exception as e:
            return False, f"variant: {type(e).__name__}: {e}"[:70]
        mtext, murl = mb.decode("utf-8", "replace"), best[2]
    else:
        mtext, mfinal, murl, res = text, final, url, "single"

    if "#EXT-X-ENDLIST" in mtext:
        return False, "VOD, not live"
    segs = [urllib.parse.urljoin(mfinal if "#EXT-X-STREAM-INF" not in text else murl,
                                 l.strip())
            for l in mtext.splitlines() if l.strip() and not l.startswith("#")]
    if not segs:
        return False, "no segments"
    try:
        sst, sb, _ = fetch(segs[len(segs) // 2], headers, limit=700_000)
    except Exception as e:
        return False, f"segment: {type(e).__name__}: {e}"[:70]
    if len(sb) < 50_000:
        return False, f"segment too small ({len(sb)}B)"

    s1 = seq_of(mtext)
    time.sleep(12)
    try:
        _, b2, _ = fetch(murl, headers)
        s2 = seq_of(b2.decode("utf-8", "replace"))
    except Exception:
        s2 = None
    if s1 is not None and s2 is not None and s2 == s1:
        return False, "manifest frozen (dead feed?)"
    return True, f"{res}, {len(sb)//1024}KB seg"


def check(ch):
    urls = [ch["url"]] + list(ch.get("alt") or [])
    for i, u in enumerate(urls):
        ok, detail = probe(u, ch.get("headers"))
        if ok:
            return dict(ch=ch, ok=True, url=u,
                        detail=detail + ("" if i == 0 else "  [via alt URL]"))
    return dict(ch=ch, ok=False, url=urls[0], detail=detail)


def check_all(chans):
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        return list(ex.map(check, chans))


def host(url):
    return urllib.parse.urlsplit(url).netloc


def apply_results(doc, results, source="self-test from this network", here=None):
    """Update tiers in `doc` from check() results; return what changed.

    A channel that passed only through an alternate gets that URL promoted to
    primary (the old primary moves to the end of `alt`), because the .m3u files
    are built from the primary URL. Geo-locked channels that fail ambiguously
    outside their country (see can_judge) are left as they are.
    """
    changes = []
    by_id = {r["ch"]["id"]: r for r in results}
    for c in doc["channels"]:
        r = by_id.get(c["id"])
        if not r:
            continue
        if r["ok"]:
            if r["url"] != c["url"]:
                c["alt"] = [u for u in (c.get("alt") or []) if u != r["url"]] + [c["url"]]
                c["url"] = r["url"]
                changes.append(f"{c['name']}: switched to {host(r['url'])}")
            if c["tier"] != "verified":
                c["tier"] = "verified"
                c["verified_from"] = source
                c.pop("reason", None)
                changes.append(f"{c['name']}: working again")
        elif c["tier"] == "verified" and can_judge(c, r, here):
            c["tier"] = "unreachable"
            c["reason"] = r["detail"]
            changes.append(f"{c['name']}: stopped working ({r['detail']})")
    doc["counts"] = {t: len([c for c in doc["channels"] if c["tier"] == t])
                     for t in ("verified", "unreachable")}
    doc["counts"]["total"] = len(doc["channels"])
    return changes


def save(doc, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", help="only test this tier")
    ap.add_argument("--playlist", default=os.path.join(HERE, "playlist.json"))
    ap.add_argument("--promote", action="store_true",
                    help="rewrite playlist.json/.m3u with passing channels marked verified")
    a = ap.parse_args()

    doc = json.load(open(a.playlist, encoding="utf-8"))
    chans = [c for c in doc["channels"]
             if not a.tier or c["tier"] == a.tier]
    print(f"testing {len(chans)} channels...\n")
    res = check_all(chans)

    for r in sorted(res, key=lambda x: (not x["ok"], x["ch"]["name"])):
        print(f"{'  OK  ' if r['ok'] else ' FAIL '} {r['ch']['name'][:24]:24} "
              f"{r['ch']['tier']:9} {r['detail']}")
    ok = [r for r in res if r["ok"]]
    print(f"\n{len(ok)}/{len(res)} working from this network")

    if a.promote:
        here = country()
        print(f"\nthis network exits in {here or 'an unknown country'}")
        for change in apply_results(doc, res, here=here):
            print(" -", change)
        save(doc, a.playlist)
        print(f"\nupdated {a.playlist} -> verified={doc['counts']['verified']}")
        print("regenerate the .m3u with:  python3 build_m3u.py")


if __name__ == "__main__":
    main()
