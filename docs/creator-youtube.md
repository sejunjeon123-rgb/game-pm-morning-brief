# User-selected creator YouTube — 2026-09-04

Twelve channels supplied by the user have been directly resolved to channel IDs
and registered in config/player_live_sources.json. Odin intentionally has none.
No additional creators are discovered or added automatically.

## Compact daily implementation

- player_live_watch/creator_youtube.py fetches one RSS per configured channel.
  Channel identity, absolute publication timestamp, seven-day freshness and
  game-specific title/description terms are required. Off-topic videos are excluded.
- RSS failure permits a public HTML fallback: channel page, discovered videos tab,
  and at most one video detail per channel. No proxy, paid service, caption API,
  transcript inference, relative-date approximation or search crawling.
- Select at most one recent matching item per channel, at most two per game.
  Reserve that many slots from the five Player Live samples: DCInside gets three
  with two channels, four with one, five with none. Unused creator slots remain empty.
  Official source caps and thirteen-document AI input cap remain unchanged.
- Convert all metadata to PUBLIC_CREATOR_YOUTUBE / CREATOR_ANALYSIS before it
  enters daily output. No creator data enters official facts or player claims.
  A creator-only report may contain cited interpretation at P3, LOW confidence,
  explicitly prefixed as creator opinion and with a metadata-only caveat.
- Captions are NOT collected in this version. content_availability is
  TITLE_DESCRIPTION_ONLY and caption_status is NOT_COLLECTED. Daily input receives
  the availability field. Never describe unseen video speech or population sentiment.
- No additional paid analysis pass: reuse existing once-per-game/day summary and
  fingerprint handling. Existing saved summaries are not retroactively rewritten.
- Integration is in compact daily/automatic, not the legacy common collector.

## Verification and limitations

All twelve channel identities were verified by public channel metadata. A first RSS
probe exposed recent game-matched metadata for three channels and HTTP404/500 for
nine. A bounded collector live check on Mabinogi, Nikke and Epic Seven selected
two, one and zero items respectively. Public source responses can fluctuate; zero
does not mean no upload. Remaining games' end-to-end fallback and GitHub collection
are not certified by these local checks. Prefer reporting the gap over repeated calls.

Unit tests cover configured counts/Odin exclusion, creator classification, bounds,
failure isolation, creator-only decisions and rejection of creator facts. Existing
Slack/Notion preview tests remain offline. No live delivery or GitHub upload performed.

## Migration / rollback

No persistent state or shared schema migration. Remove creator source entries and
revert daily creator integration to restore five DCInside samples per game. Remove
creator-only decision handling and module if rolling back entirely. No secrets added.
Captions and new creator discovery remain future explicitly scoped work.
