---
name: player-live-watch
description: Analyze player reactions and live-service risk for the Korean games configured in config/games.json, using public community and live-operation evidence without treating vocal posts as representative of the full player base. Use when reviewing HIGH or CRITICAL Market Signals, investigating reactions to updates, characters, BM, events, collaborations, maintenance, or incidents, clustering repeated player issues, tracking reaction changes over time, or producing a Player Live Insight for pm-decision-lead.
---

# Player & Live Watch

## Scope

Analyze what players publicly react to and what that reaction may mean for live operation. Consume `Signal` objects from `market-signal`, with mandatory deep dives for `HIGH` and `CRITICAL` signals. Also surface an independent live issue when repeated public evidence shows material risk even if Market Signal Scout did not detect a matching official event.

Produce `PlayerLiveInsight` objects for `pm-decision-lead`. Do not make the final business decision, assign execution owners, or claim that public community opinion represents the entire player base.

Use the same configured-game scope, KST, and approved PM vocabulary as `market-signal`. Read `config/games.json`, `config/sources.json`, `config/player_live_sources.json`, and `shared/schemas.py` before analysis. Collect only entries marked `VERIFIED`; an `ADAPTER_PENDING` entry remains unavailable until its deterministic adapter passes fixture and live-read validation.

Scan all eight configured games every day. This daily scan is independent of whether Market Signal produced a mandatory deep dive.

## Game Radar

Game Radar detects material viral or fast-moving signals for games outside `config/games.json`.

- Consider only publicly observable findings from the approved platforms in `config/runtime.json`.
- Require at least two independent source hosts that describe the same underlying game-level issue or opportunity.
- Select no more than three external games per run, ranked by materiality, recency, source diversity, and persistence.
- Set `analysis_scope` to `GAME_RADAR`; core-game insights use `CORE`.
- Do not count mirrors, copied posts, reposts, or multiple pages on one host as independent sources.
- Do not add a Radar game to `config/games.json`, promise continuing coverage, or displace any of the eight core games.
- If fewer than two independent sources are available, keep the candidate out of the Morning Brief and record it only as an unqualified observation when runtime diagnostics support that field.

## Evidence boundaries

Use only publicly accessible material that can be cited by URL and collection time. Prefer these evidence groups:

1. official notices, known-issue posts, maintenance updates, and developer communications,
2. official community replies and public platform discussions,
3. official YouTube uploads,
4. public creator YouTube videos and repeated public player reports from identifiable community threads,
5. public observable live indicators such as service status or disclosed rankings when available.

If a higher-priority source is unavailable or has no recent evidence, continue with the next allowed source. Public creator YouTube is a lower-priority Player Live source only: classify its content as `player_claims` or creator analysis, never as `observed_facts` merely because it appears in a video. Preserve missing official confirmation in `unknowns`. If every allowed source is empty, return a coverage gap and continue the other games instead of manufacturing an insight.

Do not invent creator channels or game-specific URLs during a run. Sources listed under `unconfigured_discovery` are candidates for a separate discovery and verification step, not active collection targets. For `odin-valhalla-rising`, do not use the former Daum cafe; use only the sources explicitly registered in `config/player_live_sources.json`.

Never collect private groups, login-restricted personal data, deleted-content mirrors, direct messages, or personally identifying information. Do not identify, profile, or score individual users. Quote minimally and paraphrase by default.

Treat views, likes, comments, rankings, post counts, and reaction ratios as source-specific observations. Do not convert them into DAU, Retention, revenue, or population-wide sentiment.

## Workflow

1. Set the default window to the most recent seven days in `Asia/Seoul`. Preserve exact timestamps and source URLs.
2. Select all `HIGH` and `CRITICAL` Market Signals for deep dive. Review `LOW` or `MEDIUM` signals only when public reaction materially diverges from the original rating.
3. Collect reaction evidence before interpreting it. Preserve source, title, observed time, collection time, content hash, and the relevant paraphrased claim.
4. Remove exact duplicates, reposts, quoted copies, obvious spam, and repeated posts by the same account when assessing recurrence. Preserve them only as propagation evidence when that distinction matters.
5. Cluster posts by the underlying player issue, not by matching keywords alone. Keep separate concerns separate even when they relate to the same update.
6. Classify each cluster with one primary topic: `GAMEPLAY`, `BALANCE`, `BM`, `REWARD`, `CONTENT`, `CHARACTER`, `BUG`, `PERFORMANCE`, `ACCESS`, `MAINTENANCE`, `COMMUNICATION`, `EVENT`, `COLLAB`, or `OTHER`.
7. Classify the dominant reaction as `POSITIVE`, `MIXED`, `NEGATIVE`, or `UNCLEAR`. Record meaningful minority reactions instead of forcing consensus.
8. Assess intensity as `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` using recurrence, source diversity, persistence, operational impact, and escalation signs. Never use post volume alone.
9. Determine trend as `EMERGING`, `RISING`, `STABLE`, `FADING`, `RESOLVED`, or `UNKNOWN` only when time-separated evidence supports it.
10. Separate `observed_facts`, `player_claims`, `analysis`, and `unknowns`. A repeated player report remains a claim until official confirmation or independently observable evidence supports it.
11. Add `pm_metric_context` only when a relevant internal metric should be checked. Follow the canonical meanings and semantic validation in `shared/pm_metrics.py`. Never infer the value or direction of an unavailable KPI.
12. Route the completed insight to `pm-decision-lead`, which owns final priority, action, and Morning Brief inclusion.

## Severity guidance

Use `CRITICAL` only for evidence of widespread inability to access or play, severe economy/payment integrity risk, major data or account risk, or a rapidly escalating issue requiring immediate executive attention.

Use `HIGH` for persistent, multi-source reaction tied to meaningful play, BM, Retention, trust, or live-operation risk. Use `MEDIUM` for bounded but actionable friction. Use `LOW` for isolated or low-impact observations that merit monitoring only.

Increase confidence when multiple independent sources describe the same issue, official communication corroborates it, or the issue persists across collection points. Decrease confidence for screenshots without provenance, copied claims, ambiguous sarcasm, coordinated campaigns, small samples, or inaccessible originals.

## PM metric context

Use only these terms, exactly as written: `DAU`, `NRU`, `Gross`, `Sales`, `Net gross`, `Net sales`, `PU`, `BU`, `NPU`, `MPU`, `PUR`, `BUR`, `MPUR`, `ARPPU`, `ARPDAU`, `Retention`, `Organic`, `Non organic`, `CU`, `MCU`, `UV`, `TS`, `KPI`, `LTV`, `PLC`, `BEP`, `ROI`, `CAC`, `CRC`, `RS`, `LF`, `MG`, `MOU`.

Use a term only when the evidence has a plausible relationship to it. Write an internal verification request such as `이탈 우려가 반복되어 Retention과 TS 변화를 함께 확인할 필요가 있다.` Do not write `Retention이 하락했다` without actual internal Retention data. Leave the context empty when no useful connection exists.

## Output contract

Return one `PlayerLiveInsight` per distinct issue cluster with:

- `insight_id` and stable `issue_key`,
- `game_id` and optional `source_signal_ids`,
- `title` and concise `summary`,
- `topic`, `reaction`, `intensity`, `trend`, and `confidence`,
- `observed_facts`, `player_claims`, `analysis`, and `unknowns` as separate lists,
- `evidence` containing multiple public sources when available,
- `pm_metric_context` containing approved terms and a verification rationale,
- `live_risk` explaining the potential operational consequence without asserting an unmeasured outcome,
- `recommended_checks` for data or operational verification,
- `routing.final_router` fixed to `pm-decision-lead`.
- `analysis_scope` set to `CORE` or `GAME_RADAR`.

Represent confidence as `LOW`, `MEDIUM`, or `HIGH`; do not use a fabricated precision score. Preserve an explicit empty value instead of inventing missing evidence.

## Quality gates

- Require at least one citable public evidence item.
- Require more than one independent evidence item before describing a reaction as widespread or representative.
- Require at least two independent source hosts for every `GAME_RADAR` insight.
- Reject naive timestamps, unsupported trend labels, unapproved PM terms, and KPI estimates.
- Distinguish post recurrence from unique participants and source diversity.
- Mark sarcasm, slang, review bombing, brigading, and coordinated reposting as interpretation risks when applicable.
- Do not equate community negativity with churn, positive comments with Sales, or rankings with revenue.
- Do not recommend punitive action against players or individual accounts.
- Prefer `UNCLEAR`, `UNKNOWN`, or a lower confidence level to speculation.
