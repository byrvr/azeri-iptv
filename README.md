# Azərbaycan IPTV

Free-to-air Azerbaijani TV channels as a public HLS playlist, in both JSON and
M3U form, for loading into a TV app (built for cub.best / Lampa).

```
playlist-all.m3u  # 25 channels, one entry each (same as playlist.m3u; old name)
playlist.m3u      # 25 channels, one entry each
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

## 25 working channels

Last checked 2026-11-08 from Baku (AG Telekom) and from GitHub Actions (US).

| Channel | Group | Source | Notes |
|---|---|---|---|
| İctimai TV | General | `live.itv.az` | only reachable from Azerbaijan (`geo: AZ`) |
| ATV | General | `lives.atv.az:5443` | port 5443 |
| Kanal S | General | `lives.atv.az:5443` | port 5443 |
| Ayaz TV | General | `vgcdn.net` | |
| AzStar TV | General | `livestreamtv.ca`, alt `live.azstartv.com` | diaspora, broadcast from Canada; alt is HTTP only |
| EL TV | General | `live.eltv.az`, alt `85.132.53.162` | 360p only |
| Xəzər TV | General | `xezer.tvstream.az` | needs a Referer header, see below |
| Show Plus TV | General | `rtmp.showplus.tv` | small self-run server |
| Könül TV | General | `yayin.com.tr` | HTTP only; mostly Turkish films and series |
| Baku TV | News | `rtmp.baku.tv` | |
| APA TV | News | `stream.apa.tv` | HTTP only |
| Səs TV | News | `145.239.37.125:20458` | HTTP only, bare IP on a reseller's server |
| CBC Sport | Sports | `mncdn.com` | only reachable from Azerbaijan (`geo: AZ`); shows a slate during domestic football matches |
| KN Music TV | Music | `yayin.com.tr` | |
| KTV Music | Music | `yayin.com.tr` | Könül TV's music channel |
| Yurd FM TV | Music | `restreamer.livetv.az` | visual radio |
| Media FM TV | Music | `restreamer.livetv.az` | visual radio |
| Kəpəz TV | Regional | `85.132.78.122:8050` | HTTP only, bare IP that can change |
| Dünya TV | Regional | `stream.dunyatv.az` | Sumqayıt |
| GunAz TV | South Azerbaijan | `tv.gunaz.tv` | diaspora channel |
| Vilayət TV | South Azerbaijan | `livekadeh.com` | |
| Səhənd TV | South Azerbaijan | `telewebion.ir` | Iranian state TV, Tabriz; Persian and Azerbaijani |
| Savalan TV | South Azerbaijan | `telewebion.ir` | Iranian state TV, Ardabil; Persian and Azerbaijani |
| Qərbi Azərbaycan TV | South Azerbaijan | `telewebion.ir` | Iranian state TV, Urmia; Persian, Azerbaijani and Kurdish |
| Hadi TV | Religious | `zeuscdn724.com` | Azerbaijani-language Shia channel |

**HTTP-only** streams play fine in the TV app but can be blocked as mixed content
in cub.best's web version. **Port 5443** is refused by a few networks and TV apps.

**Xəzər TV** only sends video to requests that carry
`Referer: https://xezerxeber.az/`. The playlist passes it as
`#EXTVLCOPT:http-referrer=...`, which VLC-style players honour. An app that
ignores that line (and any web browser, which can't set a Referer) gets the
channel list entry but no picture.

## Left out on purpose

These play, but aren't really Azerbaijani channels, so they're not in the playlist:

- **Səhər TV (Sahar Azeri)**: Iranian state broadcaster's Azerbaijani-language
  channel aimed at Azerbaijan; Azerbaijan's media regulator has criticised it.
- **TRT Avaz**: Turkish state TV for the Turkic world, mostly in Turkish.
- **İşraq TV**: Iranian provincial channel for Zanjan, mostly in Persian.
- **Kanal 35**: tagged `group-title="Azerbaijan"` in several public playlists,
  but it's an İzmir regional channel.

## What's gone, and why

17 channels have no working free stream. They stay in `playlist.json` with
`tier: "unreachable"` and a `reason`, so the daily check keeps trying them and
brings back any that recover.

- **ARB, ARB 24, ARB Günəş, Space, Real, İdman, Qafqaz, VIP HD, SH TV, TMB,
  Mədəniyyət, Naxçıvan** all streamed from the `yoda.az` platform's CDN
  (`str*.yodacdn.net`). It now refuses any request without a per-viewer token
  (`x-deny-reason: deny_backend`), from inside Azerbaijan too. The official
  player issues that token bound to the viewer's IP and user agent, valid for
  24 hours, so no fixed URL in a playlist can work. Watch these in the yoda.az
  app or on the broadcasters' own sites, which embed the same player.
- **AzTV**: the only open streams are on `cinerama.uz`, an Uzbek OTT service
  that inserts its own ads; the official stream is on yodacdn (token).
- **Biznes TV, MTV Azərbaycan**: their own streams (`biznestv.az`,
  `85.132.78.6:1935`) return 404 for now; the yodacdn copies need a token.
  The playlist points at their own streams, so they come back automatically.
- **CBC**: the castr stream says "Stream Offline"; the yodacdn copy needs a
  token. Also re-checked daily.
- **AnewZ** (English-language news from Baku): the web feed is frozen, so the
  same picture never advances. Re-checked daily.

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
the broadcasters' own sites, other public playlists on GitHub, and the `yoda.az`
platform. Every stream passed the checks under "What verified means" from Baku
before going in. Only free-to-air
sources are included: no subscription-portal scrapes, no credential-bearing
Xtream URLs, and no token-scraping proxies.
