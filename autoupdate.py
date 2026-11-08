#!/usr/bin/env python3
"""Daily job: re-check every channel, rebuild the playlists, push if anything changed.

Runs on GitHub Actions (.github/workflows/update.yml), whose runners are
outside Azerbaijan. Each run:

1. Looks in iptv-org's Azerbaijan list for new URLs of channels already in
   playlist.json, and adds any that play as alternates.
2. Checks every channel; re-checks the failures a few minutes later so a short
   outage doesn't drop a channel.
3. Channels marked `"geo": "AZ"` only answer from inside Azerbaijan. From
   anywhere else they are only demoted on an unambiguous failure (404, 410,
   domain gone, stream stopped); a 403 or timeout is left alone.
4. Gives up without touching anything if most checkable working channels fail
   at once (that's the runner's network, not the streams).
5. Promotes, demotes or switches channels to a working alternate, rebuilds the
   .m3u files, commits and pushes. With nothing to commit for 50 days it pushes
   an empty keepalive commit, because GitHub disables scheduled workflows in
   repos with no activity for 60 days.

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
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import selftest  # noqa: E402

IPTV_ORG = "https://iptv-org.github.io/iptv/countries/az.m3u"
RETRY_DELAY = 180          # seconds before re-checking failures
MIN_PASS_RATIO = 0.5       # of checkable verified channels; below this, assume the runner's network is broken
KEEPALIVE_DAYS = 50
PLAYLIST = os.path.join(HERE, "playlist.json")
TRANSLIT = str.maketrans("əƏıİçÇşŞğĞöÖüÜ", "eEiIcCsSgGoOuU")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=HERE, check=True,
                          capture_output=True, text=True).stdout.strip()


def summary(lines):
    """Append markdown to the GitHub Actions job summary, if there is one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def norm(name):
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)   # "(1080p)", "[Not 24/7]"
    return re.sub(r"[^a-z0-9]", "", name.translate(TRANSLIT).lower())


def excluded(url, hosts):
    host = urllib.parse.urlsplit(url).hostname or ""
    return any(host == h or host.endswith("." + h) for h in hosts)


def discover(doc):
    """Add working URLs from iptv-org as alternates of channels we already have."""
    try:
        req = urllib.request.Request(IPTV_ORG, headers={"User-Agent": selftest.UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception as e:
        log(f"iptv-org skipped: {e}")
        return []
    skip_hosts = doc.get("exclude_hosts") or []
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
        if url in known or excluded(url, skip_hosts):
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
    here = selftest.country()
    log(f"run started from {here or 'an unknown country'}" + (" (dry run)" if a.dry_run else ""))

    if not a.dry_run:
        git("fetch", "-q", "origin")
        git("reset", "-q", "--hard", "origin/main")

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

    verified = [r for r in res if r["ch"]["tier"] == "verified"]
    checkable = [r for r in verified if not r["ch"].get("geo") or r["ch"]["geo"] == here]
    passing = [r for r in checkable if r["ok"]]
    unjudged = [r for r in verified if not selftest.can_judge(r["ch"], r, here)]
    log(f"{len(passing)}/{len(checkable)} checkable working channels pass; "
        f"{sum(r['ok'] for r in res)}/{len(res)} overall")
    for r in unjudged:
        log(f"can't check {r['ch']['name']} from {here} (geo {r['ch']['geo']}): {r['detail']}")

    rows = ["| Channel | Status | Result |", "|---|---|---|"]
    for r in sorted(res, key=lambda r: (r["ch"]["tier"] != "verified", not r["ok"], r["ch"]["name"])):
        state = ("works" if r["ok"] else
                 "can't check from here" if r in unjudged else "fails")
        rows.append(f"| {r['ch']['name']} | {r['ch']['tier']} | {state}: {r['detail']} |")

    if checkable and len(passing) < MIN_PASS_RATIO * len(checkable):
        log("aborted: too many channels failed at once; looks like the runner's network")
        summary([f"### Aborted from {here}", "Too many channels failed at once; nothing changed.", "", *rows])
        return 1

    changes += selftest.apply_results(doc, res, source=f"autoupdate.py from {here}", here=here)
    summary([f"### {doc['counts']['verified']} channels in the playlist (checked from {here})", "",
             *(f"- {c}" for c in changes or ["no changes"]), "", *rows])

    if not changes:
        log("no changes")
        if not a.dry_run:
            age = time.time() - int(git("log", "-1", "--format=%ct"))
            if age > KEEPALIVE_DAYS * 86400:
                git("commit", "-q", "--allow-empty", "-m",
                    "chore: keepalive (GitHub disables scheduled workflows after 60 idle days)")
                git("push", "-q", "origin", "HEAD:main")
                log("pushed keepalive commit")
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
    git("add", "playlist.json", "playlist.m3u", "playlist-all.m3u")
    git("commit", "-q", "-m", f"auto: {subject}", "-m", "\n".join(f"- {c}" for c in changes))
    git("push", "-q", "origin", "HEAD:main")
    log(f"pushed {git('rev-parse', '--short', 'HEAD')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
