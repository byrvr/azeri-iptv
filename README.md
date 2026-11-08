# Azərbaycan IPTV

Free-to-air Azerbaijani TV channels as a public HLS playlist, in both JSON and
M3U form, for loading into a TV app (built for cub.best / Lampa).

```
playlist-all.m3u  # 13 channels, one entry each (same as playlist.m3u; old name)
playlist.m3u      # 13 channels, one entry each
playlist.json     # everything: working channels, dead ones with the reason,
                  # alternate URLs, headers, logos
selftest.py       # re-check every channel from your own network
build_m3u.py      # regenerate both .m3u files from playlist.json
autoupdate.py     # daily job: check, rebuild, push (see "Automatic updates")
.github/workflows/update.yml  # runs autoupdate.py on GitHub Actions every day
```

**Raw URLs** (what you point the TV app at):

```
https://raw.githubusercontent.com/byrvr/azeri-iptv/main/playlist-all.m3u
https://raw.githubusercontent.com/byrvr/azeri-iptv/main/playlist.m3u
https://raw.githubusercontent.com/byrvr/azeri-iptv/main/playlist.json
```

## 13 working channels

Last checked 2026-11-08 from Baku (AG Telekom), three separate passes.

| Channel | Group | Source | Notes |
|---|---|---|---|
| AzTV | General | `stream1.cinerama.uz`, alts `stream2/3/8` | stream8 currently redirects to a "blocked" slate |
| Baku TV | News | `rtmp.baku.tv` | |
| İctimai TV | General | `live.itv.az` | |
| APA TV | News | `stream.apa.tv` | HTTP only |
| ATV | General | `lives.atv.az:5443` | port 5443 |
| Kanal S | General | `lives.atv.az:5443` | port 5443 |
| Ayaz TV | General | `vgcdn.net` | |
| AzStar TV | General | `livestreamtv.ca`, alt `live.azstartv.com` | diaspora, broadcast from Canada; alt is HTTP only |
| KN Music TV | Music | `yayin.com.tr` | |
| GunAz TV | General | `tv.gunaz.tv` | South Azerbaijani (Iranian Azeri) diaspora |
| Vilayət TV | General | `livekadeh.com` | South Azerbaijani (Iranian Azeri) |
| EL TV | General | `live.eltv.az` | 360p only |
| Kəpəz TV | Regional | `85.132.78.122:8050` | HTTP only, bare IP that can change |

**HTTP-only** streams play fine in the TV app but can be blocked as mixed content
in cub.best's web version. **Port 5443** is refused by a few networks and TV apps.

## What's gone, and why

17 channels have no working free stream. They stay in `playlist.json` with
`tier: "unreachable"` and a `reason`, so `selftest.py` keeps re-checking them
and `--promote` brings back any that recover.

- **ARB, ARB 24, ARB Günəş, Space, Real, İdman, Qafqaz, MTV, VIP HD, SH TV, TMB,
  Biznes, Mədəniyyət, Naxçıvan** all streamed from the `yoda.az` platform's CDN
  (`str*.yodacdn.net`). It now refuses any request without a per-viewer token
  (`x-deny-reason: deny_backend`), from inside Azerbaijan too. The official
  player issues that token bound to the viewer's IP and user agent, valid for
  24 hours, so no fixed URL in a playlist can work. Watch these in the yoda.az
  app or on the broadcasters' own sites, which embed the same player.
- **CBC**: the castr stream ID changed (404); the yodacdn copy needs a token.
- **Xəzər TV**: 410 Gone.
- **Show Plus**: 404.

An earlier version of this playlist called the yodacdn channels geo-locked and
"working from Azerbaijan". As of November 2026 that's no longer true.

## What "verified" means

A stream counts as working only if **all** of these hold:

1. The manifest returns 200 and parses as HLS, not an HTML error page
2. A media playlist resolves (via the highest-bandwidth variant, for masters)
3. It is live — no `#EXT-X-ENDLIST`
4. A real segment downloads with meaningful bytes
5. **The live edge advances on re-fetch** — the media sequence moves forward

Step 5 is the one that matters most. A dead channel's manifest often keeps
returning 200 long after the encoder stops, so "the URL responds" is not
evidence that anything is playing. The middle segment is sampled rather than
the first, which can roll off a short DVR window between fetches and 404 on a
healthy stream.

## Automatic updates

The **Update playlist** workflow runs `autoupdate.py` on GitHub Actions every
day at 03:17 UTC (07:17 in Baku). Each run:

- adds new working URLs from iptv-org's Azerbaijan list as alternates of
  channels already here (matched by name or `aliases`), skipping hosts in
  `exclude_hosts` (yodacdn.net needs tokens; cinerama.uz inserts Uzbek ads)
- checks every channel, then re-checks failures 3 minutes later so a short
  outage doesn't drop anything
- marks channels working or dead, switches a channel to its alternate when the
  primary dies, rebuilds the .m3u files, and commits only if something changed
- gives up without changing anything if most channels fail at once
- writes a per-channel table to the run's summary page

New channels it finds on iptv-org are only logged, never added by itself.

**Geo-locked channels.** Actions runners are in the US, and some sources only
answer from inside Azerbaijan. Those channels carry `"geo": "AZ"`. From outside
Azerbaijan they're only dropped on an unambiguous failure (404, 410, the domain
no longer exists, the stream stopped); a 403 or a timeout from the US says
nothing about whether they work in Baku, so they're left alone. To re-check
them properly, run `python3 selftest.py --promote` from an Azerbaijani
connection.

Run it by hand from the repo's **Actions** tab → *Update playlist* → *Run
workflow* (tick *dry run* to only see what would change). GitHub emails you if
a run fails.

## Checking by hand

Run the check from an Azerbaijani connection, ideally the TV's own network.

```bash
python3 selftest.py                     # pass/fail per channel
python3 selftest.py --tier unreachable  # just the dead ones
python3 selftest.py --promote           # update tiers in playlist.json
python3 build_m3u.py                    # rebuild the .m3u files
```

## Sources

Candidates came from the [iptv-org](https://github.com/iptv-org/iptv) playlists,
the official broadcaster sites, and the `yoda.az` platform. Only free-to-air
sources are included: no subscription-portal scrapes, no credential-bearing
Xtream URLs, and no token-scraping proxies.

**Kanal 35** appears in several public playlists tagged `group-title="Azerbaijan"`.
It is an **İzmir regional channel**, not Azerbaijani, and is excluded.
