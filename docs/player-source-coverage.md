# Player source coverage — 2026-09-04

The September 2 GitHub artifact exposed no post row markers for seven galleries.
This is an access/HTML coverage gap, not proof of no player reaction. Current local
reads of all eight configured URLs exposed dated recent posts; no URL replacement
is justified by that evidence. Existing prefetch-all-games and request pacing remain.

Collector changes preserve earlier candidates after later listing failures,
distinguish missing/invalid rows from parsed but old posts, tolerate row-class order
in diagnostics, and flag readable-title-only samples. Daily analysis now receives
content_availability and instructions not to infer unseen bodies/video speech.
No extra paid call, state schema change, source scope change or increased daily cap.

Local live validation used one listing and one detail per game, no paid analysis
or persistent state. Seven selected posts had readable body text; Seven Knights
Rebirth's selected post had title only. This does not certify GitHub access.

`python -m player_live_watch.diagnostics` checks the same bounded eight-game scope.
The manual player-source-diagnostic workflow has read-only permissions, no secrets,
no persistent state and no AI/delivery. Upload and GitHub execution remain pending.
Output contains only game IDs, counts and controlled gap codes, not author data.

Historical note (superseded by docs/creator-youtube.md after user provided links):
Creator YouTube: user permits creator title/description and accessible captions as
reaction evidence. No creator source is registered yet; request game + channel/video
URL, verify channel identity and publication time, then implement/validate its adapter.
Do not treat this permission or prompt guidance as a completed creator collector.
Captions are not guaranteed accessible; do not use a relay, paid transcription or
invent video speech. Creator opinion must not become official fact or whole-population
sentiment. No automatic creator discovery or Game Radar activation in this change.

Rollback: revert collector/daily changes and remove the standalone diagnostic module
and workflow. No state migration is necessary. Existing offline tests cover all-eight
candidate retention and missing-row classification, plus Slack/Notion preview gates.
