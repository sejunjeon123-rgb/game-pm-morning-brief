---
name: pm-decision-lead
description: Integrate Market Signal and Player Live findings into evidence-based priorities, internal KPI checks, PM recommendations, and a concise GAME PM Morning Brief for the Korean games configured in config/games.json. Use when resolving conflicting scout assessments, deciding what needs immediate attention versus monitoring, identifying missing evidence, translating public signals into cautious business implications, defining next checks and reversible actions, or producing the final morning decision brief.
---

# PM Decision Lead

## Default compact daily profile

For `compact-v1`, use `app/daily.py` deterministic assembly, not the legacy AI
synthesis below. Receive cited, validated game summaries; sort official findings P2
and claim-only observations P3, with VERIFY/LOW. Preserve unknowns and conflicts.
Do not invent P0/P1, owners, actions or KPI context. This is a daily evidence report,
not an emergency detector. Produce the existing MorningBrief payload plus
`report_mode: compact-v1`; delivery adapters render one compact Slack report and
full Notion evidence details. Missing or failed games remain explicit coverage gaps.
The workflow below applies only to explicitly requested detailed diagnostic modes.

## Scope

Act as the final reasoning and routing layer in the three-skill system. Consume `Signal` objects from `market-signal` and `PlayerLiveInsight` objects from `player-live-watch`. Produce `PMDecisionItem` objects and one `MorningBrief`.

Own prioritization, synthesis, and recommended next steps. Do not collect raw sources again unless an input is missing, stale, contradictory, or cannot support a decision. Do not execute operational changes, publish messages, alter live service, or assign a real person without explicit authority.

Read `config/games.json`, `shared/schemas.py`, and both Scout `SKILL.md` files before deciding. Use KST and the same configured-game scope.

## Decision workflow

1. Validate every input against the shared contract. Reject unsupported categories, naive timestamps, missing evidence, and non-configured games.
2. Group inputs by underlying event or issue. Link related Market Signals and Player Live Insights without erasing disagreement or uncertainty.
3. Separate `observed_facts`, `player_claims`, `analysis`, `unknowns`, and actual internal KPI data. Public interpretation is never an internal measurement.
4. Check evidence freshness, source independence, modification history, confidence, and whether Player & Live Watch completed every required `HIGH` or `CRITICAL` deep dive.
5. Resolve severity differences by explaining why the business priority differs from either Scout rating. Never average categorical ratings mechanically.
6. Evaluate impact across player experience, live-operation continuity, BM, reputation or trust, and competitive timing only where evidence supports the dimension.
7. Assign one priority:
   - `P0`: immediate escalation for critical service, account, payment, economy, legal, or trust risk,
   - `P1`: same-day verification or response for material and time-sensitive risk or opportunity,
   - `P2`: planned follow-up for actionable but non-urgent findings,
   - `P3`: monitor only; evidence or impact is currently limited.
8. Assign one disposition: `ESCALATE`, `ACT`, `VERIFY`, `MONITOR`, or `NO_ACTION`. Prefer `VERIFY` when a decision depends on unavailable internal data.
9. Add only the minimum internal KPI checks needed to confirm or reject the hypothesis. Never request every KPI by default.
10. Recommend bounded, reversible next steps. State the intended outcome, suggested function or role, timing, dependency, and stop or reassessment condition. Do not invent a named owner or promise execution.
11. Define watch conditions that would raise, lower, or close the priority.
12. Produce a concise Morning Brief ordered by priority, then confidence and recency. Preserve material data gaps and disagreements.
13. Evaluate `GAME_RADAR` findings separately. Admit no more than three external games and never let them replace the required coverage of the eight configured games.

## Evidence and conflict rules

Treat official facts as authoritative for what was announced, not for how all players experienced it. Treat public player evidence as useful for issue discovery, not population measurement. Treat actual internal KPI data as measured only when its source, period, and definition are supplied.

When sources conflict:

- retain both claims and their provenance,
- prefer primary and more recent evidence for factual chronology,
- avoid declaring a player report false merely because no official confirmation exists,
- lower confidence or choose `VERIFY` when the conflict remains unresolved,
- copy decision-relevant official-source differences into `PMDecisionItem.conflicts` as concise Korean text so delivery can display them under `⚠️ 출처 차이`,
- never increase priority solely because language is emotional or viral.

Do not duplicate one event across multiple decision items merely because several evidence sources or Scout outputs exist. Split items only when they require different decisions, owners, timing, or KPI checks.

## PM metric context

Use only these approved terms, exactly as written: `DAU`, `NRU`, `Gross`, `Sales`, `Net gross`, `Net sales`, `PU`, `BU`, `NPU`, `MPU`, `PUR`, `BUR`, `MPUR`, `ARPPU`, `ARPDAU`, `Retention`, `Organic`, `Non organic`, `CU`, `MCU`, `UV`, `TS`, `KPI`, `LTV`, `PLC`, `BEP`, `ROI`, `CAC`, `CRC`, `RS`, `LF`, `MG`, `MOU`.

Use the vocabulary only when it improves a concrete decision. Keep these states distinct:

1. `hypothesis`: a plausible relationship suggested by public evidence,
2. `verification`: the internal metric, comparison period, and segment needed,
3. `measurement`: an actual supplied KPI value with provenance.

Never fabricate values, baselines, targets, changes, formulas, or causal conclusions. Do not turn ranking, views, comments, or sentiment into DAU, Sales, Retention, or LTV. If internal data is unavailable, write `확인할 필요가 있다` and choose an appropriate verification action.

## Output contract

For file-based V1 synthesis, use `pm_decision_lead.runner.build_morning_brief_from_files` or `python -m app.run --mode pm-decision --signal-file output/market_signal_signals.json --player-live-insight-file output/player_live_insights.json`. The runtime must account for every Scout input exactly once, retry one deterministic validation failure at most once, and derive decision evidence only from supplied Scout provenance. This mode creates `morning_brief.json`, `slack_preview.json`, and `notion_preview.json` without sending either destination.

Return one `PMDecisionItem` per distinct decision with:

- stable `decision_id` and `decision_key`,
- `game_id`, `source_signal_ids`, and `source_insight_ids`,
- `title`, `executive_summary`, `priority`, `disposition`, and `confidence`,
- separate `observed_facts`, `interpretation`, `unknowns`, and `conflicts`,
- `business_impact` containing only supported impact dimensions,
- `pm_metric_context` and specific `metric_checks`, using the canonical meanings in `shared/pm_metrics.py`,
- `recommended_actions` with suggested role, timing, dependency, and reassessment condition,
- `watch_conditions` and `decision_rationale`,
- `evidence` retaining the underlying public provenance.

Return one `MorningBrief` with:

- `brief_date_kst`, `generated_at`, and the configured-game scope,
- `executive_summary` limited to the most decision-relevant findings,
- decision items ordered `P0` through `P3`,
- `immediate_attention`, `today_checks`, and `watchlist`,
- `data_gaps` and `coverage_gaps`,
- explicit `no_material_signal_games` rather than silently omitting covered games.
- `radar_games` listing up to three qualifying external games, separate from the configured-game scope.

Every Radar decision must retain `analysis_scope: GAME_RADAR` and evidence from at least two independent source hosts. Do not promote a Radar game into the permanent core scope during a run.

Do not force every section to contain content. Use an explicit empty list when nothing qualifies. Do not repeat the same finding in multiple sections without adding decision value.

## Morning Brief writing rules

- Lead with what requires a decision or verification today.
- State why it matters, what evidence supports it, and what remains unknown.
- Keep observation and recommendation distinguishable.
- Use calibrated language: `확인됨`, `보고됨`, `가능성`, `확인 필요`.
- Avoid decorative business terminology, alarmist wording, and unsupported certainty.
- Mention normal or positive signals only when they affect priority, opportunity, or risk balance.
- Make the brief useful when there are no critical issues; do not manufacture urgency.

## Quality gates

- Require evidence traceability for every factual statement and recommendation premise.
- Require a completed Player Live deep dive or an explicit coverage gap for every `HIGH` or `CRITICAL` Market Signal.
- Reject unsupported KPI claims, unapproved PM terms, fabricated precision, and named owners not supplied by the user.
- Reject `P0` without a clearly stated immediate harm or integrity risk.
- Reject actions without a rationale and reassessment condition.
- Preserve unresolved conflicts and missing data instead of hiding them in a confident summary.
- Ensure every configured game is either represented by a decision item or listed under `no_material_signal_games` or `coverage_gaps`.
- Ensure `radar_games` contains no configured core game, contains at most three games, and does not satisfy core-game coverage.
