# Report presentation — 2026-09-04

User-approved presentation order is config/games.json array order. report_group
contains the user's editorial genre grouping, not a change to the genre taxonomy.
Compact Slack and Notion include all scoped games, including missing-evidence games.
Analytical priority values are unchanged; fixed display order supersedes priority
sorting for this compact presentation only. No new collection or paid calls.

Public references reviewed:
- https://www.notion.com/en-gb/customers/gs-group — GS collaboration/documentation case.
- https://www.notion.com/ko/customers/socar — progress visibility and feedback case.
- https://www.notion.com/templates/project-status-report-page — public status-report template.

These are design references, not proof of a specific game-business PM internal report
or a universal corporate standard. New structure: executive summary, four genre
sections, eight game summaries, expandable facts/reactions/interpretation/unknowns/
conflicts/provenance, then limitations. Do not fabricate analysis to fill an empty
section. Preserve all evidence links and material caveats. Slack remains concise.

Preview is editorial selection from saved September 4 afternoon evidence, not a
production API result or a delivered Notion page. Markdown preview approximates
Notion blocks; exact fonts and page width depend on Notion. No live send or upload.
Rollback: revert report_layout.py, formatter changes and game presentation metadata.
No payload or persistent state migration; legacy detailed report path unchanged.

## API-free source presentation policy

In compact-v1, official homepages and official communities are the core fact sources,
DCInside is a sampled player-reaction source, and YouTube is supplementary. Accept a
video only when its channel and exact publication timestamp are verified. Keep HTTP,
RSS and metadata failure details in diagnostic artifacts; do not repeat them in Slack
or per-game Notion content. Notion shows one consolidated collection-scope notice.
A game receives a separate evidence-gap card only when neither core official material
nor a public-community sample is available. This presentation rule does not erase or
alter internal collection diagnostics.
