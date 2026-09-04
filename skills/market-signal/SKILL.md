---
name: market-signal
description: Collect, normalize, deduplicate, and assess public official signals for the Korean live-service games configured in config/games.json. Use when producing the Market Signal Scout portion of GAME PM Morning Brief, checking recent official notices or YouTube activity, detecting edits to a previously collected notice, merging multiple official evidence items into one event, adding cautious PM metric context, or deciding whether a signal needs player-live-watch follow-up.
---

# Market Signal Scout

## Default compact daily profile

For `compact-v1` in `config/runtime.json`, follow the root AGENTS.md compact profile
and `app/daily.py`. Own official collection, source priority, content hashes and the
official-fact fields of one combined game summary. Do not call the legacy Signal
analyzer during a daily run. Summarize new/modified evidence once per game per day;
retain category/BM taxonomy and source differences. KPI context is empty by default.
The detailed Signal workflow below is for explicitly requested legacy diagnostics,
not a second pass or automatic fallback. No new skill or external relay is required.

## Scope

Run only the `market-signal` responsibility in the three-skill system. Treat `player-live-watch` as the deep-dive consumer and `pm-decision-lead` as the final router and decision owner. Read `config/games.json`, `config/sources.json`, and `shared/schemas.py` before collecting.

Use Python 3.12+. Use the standard library for HTTP, parsing, dates, hashing, serialization, and orchestration. Permit an external package only for an unavoidable infrastructure adapter such as PostgreSQL; isolate that adapter and document it. Never store secrets, tokens, cookies, private data, or machine-specific paths.

## Workflow

1. Set the collection window to the most recent seven days in `Asia/Seoul`. Expand it only when explicitly requested or when older evidence is necessary to understand a recent event.
2. Collect only configured primary sources. Apply this authority order: `OFFICIAL_HOMEPAGE`, then a community directly linked by that homepage as `OFFICIAL_COMMUNITY`, then `OFFICIAL_YOUTUBE`. If a source is unavailable or empty, report its source-level gap and continue with the next configured priority. Do not invent or silently replace a URL, add an external relay, or fail the whole game solely because a higher-priority source failed. If all official sources are empty, return an explicit coverage gap without creating a Signal.
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

Treat `shared/pm_metrics.py` as the canonical meaning and semantic-validation contract. In particular, `PU` means daily paying users and never pick-up; `CU` means concurrent users and never content usage. `PUR` is `PU / DAU`, `MPUR` is `MPU / MAU`, `ARPPU` is `Sales / PU`, and `ARPDAU` is `Sales / DAU`. Do not turn learning notes, numerical benchmarks, fixed platform-fee percentages, or personal rules of thumb into definitions or assumptions. Contract terms such as `RS`, `LF`, `MG`, and `MOU` vary by agreement; use them only when the public evidence actually concerns that contract concept.

Write all generated explanatory prose in Korean, including `title`, `summary`, `pm_metric_context.rationale`, routing reasons, exclusions, and `source_conflicts`. Proper nouns, IDs, enum values, and approved PM terms may remain in their defined form.

## Quality gates

- Reject naive datetimes, non-HTTP evidence URLs, unknown categories, unknown BM types, and unapproved PM terms.
- Require at least one official evidence item per signal.
- Require `player-live-watch` routing on `HIGH` and `CRITICAL` signals.
- Keep facts, interpretation, uncertainty, and internal verification needs distinguishable.
- Preserve material official-source differences as concise Korean text; never silently resolve them from source priority alone.
- Prefer omission to speculation. Never infer official URLs, KPI values, player sentiment, or commercial outcomes.
- Treat an empty result as a valid collection outcome. It must not erase successful lower-priority evidence or stop collection for other games.
- Assign every collected input ID exactly once to a Signal event or to an explicit exclusion with a factual reason. Fail closed on missing, duplicated, or unknown IDs.

## V1 deterministic scripts

Use `scripts/run.py` for the deterministic collection path. The `collect` mode scans all eight configured official YouTube feeds and the implemented official-notice adapters independently, so failure or emptiness in one path does not suppress valid evidence from another. Analyze documents in bounded per-game batches so related official notices and videos can become One Event + Multiple Evidence without dropping any collected input. Reuse a validated per-game analysis only when its analyzer version, model, URLs, titles, and content hashes still match. Limit concurrent OpenAI requests to the implementation's bounded worker count and retain timing, batch, API-call, and cache-hit metrics in the analysis report. If a public page does not expose stable notice links in HTML, return a source-level coverage gap rather than guessing an internal endpoint or using a relay. Add a new site adapter only after verifying its official URL and fixture behavior.
