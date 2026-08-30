# Open questions for the automation phase

The decisions already approved by the user are recorded in `config/runtime.json`. Only the remaining implementation choices below require confirmation.

## Resolved operating decisions

- Run with GitHub Actions every day, including weekends and holidays, at `08:10 Asia/Seoul`.
- Deliver automatically after validation to `게임-사업pm-브리핑` through a dedicated Game PM Slack app.
- Store runtime state as JSON on the dedicated `state` branch.
- Scan all eight configured games through Player Live every day.
- Allow Player Live sources from 인벤, 디시인사이드, 네이버 공식카페, YouTube, 치지직, and 아카라이브.
- Game Radar may include at most three external games per run and requires at least two independent source hosts per game.

## Slack delivery

1. Should the system send one compact message, a message plus thread details, or one message per game?
2. What is the maximum acceptable message length before details move to a thread or attachment?
3. Should `P0` or delivery failures trigger a separate alert channel?
4. Are any mentions allowed? If so, which exact user or user group and for which priority?
5. Where will `SLACK_WEBHOOK_URL` be managed and who may rotate it?
6. How long should the delivery ledger and sanitized failure logs be retained?
7. Should a corrected brief use a follow-up message, a replacement post, or manual review?

## Schedule and run policy

8. What time defines the daily collection cutoff in KST?
9. Should the seven-day window remain the main view while highlighting changes since the last successful run?
10. Should a missed run backfill automatically or wait for manual instruction?
11. How many retries and what maximum total run time are acceptable before declaring failure?

## Player & Live source scope

12. What are the verified per-game URLs for each approved public platform?
13. What recurrence threshold, in addition to Game Radar's two-host rule, makes a core-game reaction material?
14. Are public app-store reviews or public rankings in scope?
15. Are screenshots admissible when the original post cannot be accessed?

## Internal data and state retention

16. Will internal KPI data be available in V1? If so, through which read-only source and with what definitions?
17. What retention period applies to state JSON, normalized evidence, hashes, briefs, and sanitized logs?
18. Should historical comparisons use calendar-day, weekday, update-cycle, or cohort baselines?
19. Which role approves schema migrations and source-list changes?

## PM decision policy

20. Who is the human escalation owner for `P0` and `P1` items?
21. Are there game-specific priority overrides or business calendars that affect competitive timing?
22. What evidence or KPI condition closes an issue as `RESOLVED`?
23. Should positive opportunities be ranked with risks or shown in a separate brief section?
24. What confidence is required before recommending an external player communication?
