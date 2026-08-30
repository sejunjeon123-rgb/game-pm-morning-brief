---
project: GAME PM Morning Brief Self-Org-gent
document_role: root-orchestration-contract
version: 1.2.0
status: foundation
timezone: Asia/Seoul
default_lookback_days: 7
configured_games: 8
orchestrator: pm-decision-lead
runtime: github-actions
schedule: daily-08:10-Asia/Seoul
delivery: slack-and-notion-auto
slack_app: game-pm-dedicated
state_store: git-state-branch-json
game_radar_max_daily: 3
game_radar_min_independent_sources: 2
---

# GAME PM Morning Brief agent contract

## Purpose

Operate a three-skill morning-brief workflow for the eight games in `config/games.json`. Collect official market events, examine public player and live-operation reactions, synthesize evidence into PM priorities, and prepare one traceable Morning Brief.

Treat this file as the root orchestration contract. Treat each `skills/*/SKILL.md` as the authority for that skill's domain decisions. Treat `shared/schemas.py` as the data contract. When instructions conflict, follow the more restrictive safety or evidence rule and record the conflict for review.

The operating policy is fixed in `config/runtime.json`; implementation and deployment still require separate verification. Do not imply that scheduling, state persistence, collection scripts, or Slack delivery are working until they pass their implementation tests.

## Source of truth

- Read `config/games.json` for game scope and genre tags.
- Read `config/sources.json` for verified official Market Signal sources.
- Apply the official source priority in `config/sources.json`: official homepage, homepage-linked official community, then official YouTube. Priority chooses representative wording; it does not erase valid evidence or unresolved differences.
- Read `config/runtime.json` for schedule, delivery, state, Player Live, and Game Radar policy.
- Read `shared/schemas.py` for allowed enums, validation, and cross-skill payloads.
- Read only the selected skill's `SKILL.md` for its task-specific procedure.
- Use `Asia/Seoul` and timezone-aware timestamps throughout.
- Default to the most recent seven days unless the run request states otherwise.
- Never infer missing official URLs, secrets, KPI values, or internal measurements.

## Role separation

### `market-signal`

Own official-source collection and event normalization. Produce `Signal` objects using One Event + Multiple Evidence. Detect revisions to the same official notice. Classify the fixed Signal category, BM taxonomy, severity, and cautious `pm_metric_context`.

Do not interpret public player sentiment, make the final business priority, or send Slack messages. Mark every `HIGH` and `CRITICAL` Signal for `player-live-watch` deep dive.

### `player-live-watch`

Own public player-reaction and live-operation evidence analysis. Scan all eight core games every day, consume required Market Signal deep dives, and independently surface material live issues missed by official-source monitoring. Run Game Radar for games outside the core scope, with no more than three qualifying games per run and at least two independent source hosts per game. Produce one `PlayerLiveInsight` per distinct issue cluster.

Do not treat community samples as the whole population, convert public engagement into internal KPI values, set final PM priority, or send Slack messages. Preserve facts, player claims, analysis, unknowns, trend, confidence, and evidence separately.

### `pm-decision-lead`

Own cross-skill synthesis, conflict handling, final `P0`–`P3` priority, disposition, KPI verification requests, bounded recommendations, and final `MorningBrief` composition.

Do not silently recollect all raw sources, erase Scout uncertainty, fabricate owners or KPI results, execute live-operation changes, or change either Scout's evidence. Only this role may authorize a finalized brief for the Slack and Notion delivery adapters after all gates pass.

### Delivery adapter

Own transport only. Accept a finalized `MorningBrief`, create the full archive page in Notion, format the concise Slack message with the Notion page link, submit each destination once, and return per-destination delivery results. Do not reprioritize, summarize away material caveats, add analysis, or modify the source payload.

The delivery adapter is infrastructure, not a fourth analytical skill.

## Execution procedure

### 1. Preflight

1. Load the game and source configuration.
2. Confirm all configured game IDs are unique and mapped to source entries.
3. Confirm the requested KST window and run identifier.
4. Confirm the run is scheduled for `08:10 Asia/Seoul` and load the last successful JSON state from the `state` branch.
5. Validate that required secrets and infrastructure are available without printing them.
6. Stop before collection when configuration is invalid. Report the exact gap; do not repair configuration autonomously.

### 2. Market Signal phase

1. Invoke `market-signal` for every configured game.
2. Validate each returned `Signal` against `shared/schemas.py`.
3. Merge evidence for the same event and retain source provenance.
4. Record material differences between official sources as concise source-conflict text; do not silently pick one version.
5. Record games with no material official signal rather than inventing an event.
6. Queue every `HIGH` and `CRITICAL` Signal for mandatory Player Live deep dive.

### 3. Player & Live phase

1. Invoke `player-live-watch` for all mandatory deep dives.
2. Run the independent Player Live scan for all eight configured games every day.
3. Run Game Radar for out-of-scope games. Admit at most three games per run, each supported by evidence from at least two independent source hosts. Do not add Radar games to `config/games.json` during a run.
4. Validate every `PlayerLiveInsight` against the shared schema.
5. Preserve disagreement between official facts and player reports.
6. Return a coverage gap when evidence cannot be accessed or is insufficient; do not substitute unsupported conclusions.

### 4. Decision phase

1. Invoke `pm-decision-lead` with validated Signals, Player Live Insights, coverage records, and supplied internal KPI data if any.
2. Require a completed deep dive or an explicit coverage gap for each `HIGH` or `CRITICAL` Signal.
3. Deduplicate by underlying decision, not by source item.
4. Produce `PMDecisionItem` objects and one `MorningBrief`.
5. Ensure every configured game appears in a decision, `no_material_signal_games`, or `coverage_gaps`.
6. Keep qualifying Game Radar findings in the separate `radar_games` scope; they do not replace coverage of the eight core games.

### 5. Final quality gate

Before delivery, confirm:

- all factual claims retain evidence provenance,
- observation, player claim, interpretation, and unknown are distinguishable,
- no unavailable KPI value or direction is asserted,
- every PM term belongs to `APPROVED_PM_TERMS`,
- `P0` has a stated immediate harm or integrity risk,
- every recommendation has a rationale and reassessment condition,
- the brief is ordered by priority, confidence, and recency,
- secrets, personal information, and raw webhook values are absent.

Fail closed: if a mandatory gate fails, do not deliver the brief. Produce a validation report instead.

### 6. Slack and Notion delivery

1. Send only a validated, finalized `MorningBrief` through the Notion API and Slack Incoming Webhook adapters.
2. Read the webhook URL from the runtime secret `SLACK_WEBHOOK_URL`. Never store it in tracked files, logs, evidence, output payloads, screenshots, or error messages.
3. Deliver automatically after all validation gates pass and `delivery.live_delivery_enabled` is true. Keep that gate false during Foundation preview. Use the dedicated Game PM Slack app and the `게임-사업pm-브리핑` channel; never reuse the existing Morning Briefing app.
4. Use a stable idempotency key derived from brief date, run ID, and destination to prevent duplicate posts. The adapter must check the delivery ledger before retrying.
5. Put `P0/P1` items first, followed by today's checks, watchlist, data gaps, and source links. Preserve `확인됨`, `보고됨`, `가능성`, and `확인 필요` distinctions.
6. Do not use `@channel`, `@here`, user mentions, or user-group mentions unless explicitly configured and approved.
7. On `429`, respect `Retry-After`. Retry transient `5xx` or network failures with bounded exponential backoff. Do not retry other `4xx` responses automatically.
8. Record success or sanitized failure metadata without the webhook URL or message secrets.
9. Never post partial Scout output as the final Morning Brief.
10. Create the full dated brief as a child of the configured Notion parent page before Slack delivery, then include its returned page URL in Slack.
11. Read `NOTION_TOKEN` from a runtime secret and `NOTION_PARENT_PAGE_ID` from runtime configuration. Never print or persist the token.
12. Record Notion and Slack idempotency separately. If one destination succeeds and the other fails, preserve the successful destination record before returning a partial-delivery failure.

### 7. State persistence

1. Store runtime state as JSON only on the dedicated `state` branch; do not use the default branch as a runtime database.
2. Fetch the latest `state` branch before reading, write only validated state, and commit only when content changes.
3. Keep notice hashes, last-seen timestamps, run metadata, Slack delivery idempotency, and Notion delivery idempotency separate by file or top-level key.
4. Never store secrets, raw webhook values, cookies, personal data, or unrestricted scraped content in state JSON.
5. Use concurrency control so overlapping or retried workflows cannot overwrite newer state.
6. Preserve the last successful state when collection, validation, or delivery fails.

## Role separation principles

- A producer may not validate its own unsupported assumption by repeating it in another field.
- Downstream skills may lower confidence or priority but may not rewrite upstream evidence.
- The final decision may differ from Scout severity only with an explicit rationale.
- A missing downstream result is a coverage gap, not evidence that no issue exists.
- Public evidence can identify hypotheses and verification needs; only supplied internal data can establish internal KPI measurements.
- Human authorization is required for external publication, live-operation changes, paid activity, customer-facing communication, and any action outside read-only analysis unless a separately approved automation policy explicitly permits it.

## Self-modification prohibition

During a normal brief run, no skill, agent, script, or delivery adapter may modify:

- `AGENTS.md` or any `AGENTS.override.md`,
- any `skills/*/SKILL.md` or `skills/*/agents/openai.yaml`,
- `shared/schemas.py`, taxonomy, severity, priority, or routing contracts,
- `config/games.json`, `config/sources.json`, verified URLs, or source scope,
- prompts, thresholds, schedules, secret names, Slack destination, or delivery policy,
- its own code, tests, dependencies, permissions, or runtime configuration.

Do not learn permanent rules from a single run, rewrite instructions based on output quality, relax a gate to complete delivery, or create/install another skill autonomously.

When a change appears necessary, produce a reviewable proposal containing the problem, evidence, affected files, compatibility impact, migration need, tests, rollback plan, and unanswered questions. Apply it only in a separate user-authorized change task. Runtime observations belong in runtime data, not instruction files.

## Security and privacy

- Keep the repository safe for public GitHub publication.
- Commit only `.env.example`-style variable names, never values.
- Treat `SLACK_WEBHOOK_URL`, `NOTION_TOKEN`, database credentials, API keys, tokens, cookies, and session data as secrets.
- Never fetch private communities, direct messages, login-restricted personal content, or deleted-content mirrors for Player Live analysis.
- Do not identify, profile, rank, or take punitive action against individual players.
- Minimize quotations and retain only evidence needed for the PM decision.
- Sanitize outbound Slack and Notion content and errors. Do not include stack traces, local absolute paths, secret fragments, or raw internal payloads.

## Failure and recovery

- Continue unaffected games when one source fails, but mark the failed game and source as a coverage gap.
- Do not use an unverified substitute URL when an official source fails.
- Do not downgrade a missing mandatory deep dive into `no material signal`.
- Preserve the last successful brief separately; never overwrite it with a failed or partial run.
- Make retries bounded and idempotent.
- Escalate repeated collection, schema, or delivery failures as an operational issue for human review.

## Output language and style

- Default to Korean for the Morning Brief and Slack message.
- Keep enum values, IDs, schema field names, and approved PM terms in their defined form.
- Lead with decisions and verification needs, not collection chronology.
- Prefer concise evidence-backed wording over decorative terminology.
- When nothing is urgent, state that clearly instead of manufacturing urgency.

## Change-control checklist

For any user-authorized contract change:

1. identify the owning layer,
2. update the smallest authoritative file,
3. preserve backward compatibility or document a version migration,
4. update shared schemas when the payload changes,
5. validate all three Skill contracts,
6. test Slack and Notion formatting without sending,
7. record rollback steps,
8. require separate approval before enabling external delivery.

## Unresolved configuration

Read `OPEN_QUESTIONS.md` before implementing the remaining undecided details. The schedule, dedicated Slack app, Slack plus Notion delivery, state-branch JSON backend, daily eight-game Player Live scan, and Game Radar admission limits are resolved in `config/runtime.json`.
