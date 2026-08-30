---
name: market-signal
description: Collect, normalize, deduplicate, and assess public official signals for the Korean live-service games configured in config/games.json. Use when producing the Market Signal Scout portion of GAME PM Morning Brief, checking recent official notices or YouTube activity, detecting edits to a previously collected notice, merging multiple official evidence items into one event, adding cautious PM metric context, or deciding whether a signal needs player-live-watch follow-up.
---

# Market Signal Scout

## Scope

Run only the `market-signal` responsibility in the three-skill system. Treat `player-live-watch` as the deep-dive consumer and `pm-decision-lead` as the final router and decision owner. Read `config/games.json`, `config/sources.json`, and `shared/schemas.py` before collecting.

Use Python 3.12+. Use the standard library for HTTP, parsing, dates, hashing, serialization, and orchestration. Permit an external package only for an unavoidable infrastructure adapter such as PostgreSQL; isolate that adapter and document it. Never store secrets, tokens, cookies, private data, or machine-specific paths.

## Workflow

1. Set the collection window to the most recent seven days in `Asia/Seoul`. Expand it only when explicitly requested or when older evidence is necessary to understand a recent event.
2. Collect only configured primary sources. Apply this authority order: `OFFICIAL_HOMEPAGE`, then a community directly linked by that homepage as `OFFICIAL_COMMUNITY`, then `OFFICIAL_YOUTUBE`. Do not invent or silently replace a URL. Stop collection for a source that cannot be verified as official and report the gap.
3. Preserve the source URL, title, publication time, collection time, normalized text, and a SHA-256 content hash. Use timezone-aware timestamps.
4. Compare the current normalized content hash with the prior hash for the same canonical notice URL. Record a modification when hashes differ; preserve both hashes and the latest official modification time when exposed.
5. Apply One Event + Multiple Evidence: merge official pages, notices, and videos describing the same underlying event into one `Signal`; retain every `Evidence`. Do not merge merely because dates or keywords overlap.
   Use the highest-priority available source as the representative chronology and wording, but never discard valid lower-priority evidence. When sources materially differ in schedule, eligibility, reward, product composition, maintenance status, or another decision-relevant fact, record a short factual comparison in `source_conflicts`. Do not treat harmless wording or level-of-detail differences as conflicts.
6. Assign exactly one primary category: `UPDATE`, `CHARACTER`, `BM`, `EVENT`, `WEB_EVENT`, `COLLAB`, `MARKETING`, `MAINTENANCE`, or `NOTICE`.
7. For `BM`, assign types only from `GROWTH`, `GACHA`, `CURRENCY`, `EQUIPMENT`, `CHARACTER`, `CONVENIENCE`, `CONTENT_ACCESS`, `COSMETIC`, or `OTHER`.
8. Assess severity as `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` from public evidence. Explain the rating; do not turn uncertainty into severity.
9. Add `pm_metric_context` only under the rules below.
10. Mark every `HIGH` or `CRITICAL` signal for `player-live-watch` deep dive. Leave final routing and prioritization to `pm-decision-lead`.

## PM metric context

Use only these approved terms, exactly as written: `DAU`, `NRU`, `Gross`, `Sales`, `Net gross`, `Net sales`, `PU`, `BU`, `NPU`, `MPU`, `PUR`, `BUR`, `MPUR`, `ARPPU`, `ARPDAU`, `Retention`, `Organic`, `Non organic`, `CU`, `MCU`, `UV`, `TS`, `KPI`, `LTV`, `PLC`, `BEP`, `ROI`, `CAC`, `CRC`, `RS`, `LF`, `MG`, `MOU`.

Use a term only when the observed signal has a reasonable business relationship to it. Separate:

1. public observation,
2. internal metric worth checking,
3. actual measured KPI.

Never fabricate, estimate, or imply unavailable KPI values or movements. Phrase unmeasured implications as a verification task, for example: `NPU 및 PUR 변화와 함께 확인할 필요가 있다.` Keep `terms` empty when no metric relationship is useful.

## Quality gates

- Reject naive datetimes, non-HTTP evidence URLs, unknown categories, unknown BM types, and unapproved PM terms.
- Require at least one official evidence item per signal.
- Require `player-live-watch` routing on `HIGH` and `CRITICAL` signals.
- Keep facts, interpretation, uncertainty, and internal verification needs distinguishable.
- Preserve material official-source differences as concise Korean text; never silently resolve them from source priority alone.
- Prefer omission to speculation. Never infer official URLs, KPI values, player sentiment, or commercial outcomes.

## V1 deterministic scripts

Use `scripts/run.py` for the deterministic collection path. The `collect` mode scans all eight configured official YouTube feeds and the implemented official-notice adapters. If a public page does not expose stable notice links in HTML, return a source-level coverage gap rather than guessing an internal endpoint. Add a new site adapter only after verifying its official URL and fixture behavior.
