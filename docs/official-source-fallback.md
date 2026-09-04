# Official source resilience — 2026-09-04

## Scope and evidence

User-authorized collector-only change. Local Mabinogi notice HTML exposes ten
notice candidates, while the saved GitHub collection had no notice links in its
12,344-character response. Cause is not established. The verified YouTube channel
is reachable and its configured ID is correct, but its RSS returns HTTP 404.

## Implementation

- Manual `Official source diagnostic (no AI or delivery)` workflow: one notice
  request, 20-second timeout, zero retries, read-only permissions, no secrets,
  no state checkout or paid analysis. Logs only approved titles, numeric counts
  and response/redirect flags. Arbitrary titles and redirect URLs are not logged.
- RSS failure or invalid XML activates public-channel HTML fallback. A valid but
  empty feed does not trigger additional work. Preserve the original RSS gap.
- Read configured channel, discover its actual videos tab, verify channel identity
  on both pages, then inspect at most three unique video detail pages. No pagination,
  proxies, external dependencies, transcripts or API keys. Existing HTTP retry
  policy still applies to each request (five logical fallback requests maximum).
- Verify each video's channel and ID, accessible playability and explicit
  timezone-aware publication date within seven days. Reject date-only, relative,
  missing, future and old dates. Exclude live content. Developer-channel game
  filters still apply. Preserve official title/description only, not inferred video
  contents. The fallback does not cover Shorts/live or promise exhaustive coverage.
- Zero verified videos is acceptable and remains an explicit bounded-coverage gap.
- Local live check returned zero verified recent fallback videos; this is not proof
  that the channel has no recent uploads. Local notice diagnostics returned HTTP200,
  ten thread markers, no redirect and no tested access-warning markers.

## Compatibility, validation and rollout

Existing CollectedNotice, state hashes and delivery contracts are unchanged.
No migration, game scope change, quantity minimum or AI budget increase. Game Radar
remains deferred; its future limit is three extra games with two independent hosts.
Unit tests cover identity/date rejection, bounds, deduplication, filtering, RSS
failure integration, valid-empty RSS and sanitized diagnostics. Existing preview
and delivery tests remain offline. No Slack/Notion send is authorized by this change.

After publishing these files to GitHub, run the manual diagnostic workflow once
and compare its flags with the local result. Do not run `daily` or `signal-test`
to diagnose HTTP responses. Cloud response diagnosis remains pending until then.

Rollback: remove fallback import and invocation from youtube_collector.py and
restore its original `continue` after recording feed failure; remove the standalone
diagnostic workflow/module if undesired. No state migration or credential changes.
