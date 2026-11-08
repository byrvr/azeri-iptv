#!/usr/bin/env python3
"""Daily job: re-check every channel, rebuild the playlists, push if anything changed.

Meant to run from launchd on a Mac on an Azerbaijani connection; install it
with install-mac.sh. Each run:

1. Skips itself unless this network exits in Azerbaijan (VPN, travel), since
   some sources only answer from inside the country.
2. Resets its clone to origin/main.
3. Looks in iptv-org's Azerbaijan list for new URLs of channels already in
   playlist.json, and adds any that play as alternates.
4. Checks every channel; re-checks the failures a few minutes later so a short
   outage doesn't drop a channel.
5. Gives up without touching anything if most working channels fail at once
   (that's this network, not the streams).
6. Promotes, demotes or switches channels to a working alternate, rebuilds the
   .m3u files, commits and pushes, and posts a macOS notification.

    python3 autoupdate.py            # full run
    python3 autoupdate.py --dry-run  # check and print what would change; no git, no writes
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import selftest  # noqa: E402

IPTV_ORG = "https://iptv-org.github.io/iptv/countries/az.m3u"
RETRY_DELAY = 180          # seconds before re-checking failures
MIN_PASS_RATIO = 0.5       # of currently verified channels; below this, assume our network is broken
PLAYLIST = os.path.join(HERE, "playlist.json")
TRANSLIT = str.maketrans("əƏıİçÇşŞğĞöÖüÜ", "eEiIcCsSgGoOuU")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, check=True,
                          capture_output=True, text=True).stdout.strip()


def notify(title, body):
    script = (f"display notification {json.dumps(body[:240], ensure_ascii=False)} "
              f"with title {json.dumps(title, ensure_ascii=False)}")
    subprocess.run(["osascript", "-e", script], capture_output=True)


def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": selftest.UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def country(attempts=5):
    """Two-letter country this network exits from, or None. Retries: the Mac
    may have just woken up and not be online yet."""
    for i in range(attempts):
        try:
            trace = get("https://www.cloudflare.com/cdn-cgi/trace", timeout=10)
            m = re.search(r"^loc=(\w+)$", trace, re.M)
            if m:
                return m.group(1)
        except Exception:
            pass
        if i < attempts - 1:
            time.sleep(60)
    return None


def norm(name):
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)   # "(1080p)", "[Not 24/7]"
    return re.sub(r"[^a-z0-9]", "", name.translate(TRANSLIT).lower())


def discover(doc):
    """Add working URLs from iptv-org as alternates of channels we already have."""
    try:
        text = get(IPTV_ORG, timeout=20)
    except Exception as e:
        log(f"iptv-org skipped: {e}")
        return []
    known, index = set(), {}
    for c in doc["channels"]:
        known.add(c["url"])
        known.update(c.get("alt") or [])
        for n in [c["name"], *(c.get("aliases") or [])]:
            index[norm(n)] = c
    changes, unmatched, name = [], [], None
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("#EXTINF"):
            name = ln.rsplit(",", 1)[-1]
            continue
        if not ln or ln.startswith("#") or not name:
            continue
        url, label, name = ln, name, None
        if url in known:
            continue
        c = index.get(norm(label))
        if not c:
            unmatched.append(label)
            continue
        ok, detail = selftest.probe(url, None)
        if ok:
            c.setdefault("alt", []).append(url)
            known.add(url)
            changes.append(f"{c['name']}: new source {selftest.host(url)} (from iptv-org)")
        else:
            log(f"iptv-org candidate for {c['name']} doesn't play: {detail}")
    if unmatched:
        log("iptv-org channels not in playlist.json (add by hand if wanted): "
            + ", ".join(sorted(set(unmatched))))
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="check and report only; don't touch git or any file")
    a = ap.parse_args()
    log("run started" + (" (dry run)" if a.dry_run else ""))

    loc = country()
    if loc != "AZ":
        log(f"skipped: this network exits in {loc or 'an unknown country'}, not AZ")
        return 0

    if not a.dry_run:
        try:
            git("fetch", "-q", "origin")
            git("reset", "-q", "--hard", "origin/main")
            git("push", "--dry-run", "-q", "origin", "main")
        except subprocess.CalledProcessError as e:
            log(f"git failed, nothing changed: {e.stderr.strip()}")
            notify("Azeri IPTV: update failed", "git fetch/push isn't working; see the log")
            return 1

    doc = json.load(open(PLAYLIST, encoding="utf-8"))
    changes = discover(doc)

    chans = doc["channels"]
    res = selftest.check_all(chans)
    failed = [r["ch"] for r in res if not r["ok"]]
    if failed:
        log(f"{len(failed)} failed the first check; re-checking in {RETRY_DELAY}s")
        time.sleep(RETRY_DELAY)
        retry = {r["ch"]["id"]: r for r in selftest.check_all(failed)}
        res = [retry.get(r["ch"]["id"], r) for r in res]

    verified = [c for c in chans if c["tier"] == "verified"]
    passing = [r for r in res if r["ok"] and r["ch"]["tier"] == "verified"]
    log(f"{len(passing)}/{len(verified)} working channels still pass; "
        f"{sum(r['ok'] for r in res)}/{len(res)} overall")
    if verified and len(passing) < MIN_PASS_RATIO * len(verified):
        log("aborted: too many channels failed at once; looks like this network, not the streams")
        notify("Azeri IPTV: check skipped",
               f"only {len(passing)}/{len(verified)} channels answered; nothing changed")
        return 1

    changes += selftest.apply_results(doc, res, source="autoupdate.py from Azerbaijan")
    if not changes:
        log("no changes")
        return 0
    for ch in changes:
        log(" - " + ch)
    if a.dry_run:
        log("dry run: nothing written")
        return 0

    doc["updated"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    selftest.save(doc, PLAYLIST)
    subprocess.run([sys.executable, os.path.join(HERE, "build_m3u.py")], cwd=HERE, check=True)
    subject = changes[0] if len(changes) == 1 else f"{changes[0]} (+{len(changes) - 1} more)"
    try:
        git("add", "playlist.json", "playlist.m3u", "playlist-all.m3u")
        git("commit", "-q", "-m", f"auto: {subject}", "-m", "\n".join(f"- {c}" for c in changes))
        git("push", "-q", "origin", "HEAD:main")
    except subprocess.CalledProcessError as e:
        log(f"commit/push failed: {e.stderr.strip()}")
        notify("Azeri IPTV: push failed", subject)
        return 1
    log(f"pushed {git('rev-parse', '--short', 'HEAD')}")
    notify(f"Azeri IPTV: {doc['counts']['verified']} channels", "; ".join(changes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
