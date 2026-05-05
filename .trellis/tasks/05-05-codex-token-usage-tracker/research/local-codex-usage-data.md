# Research: local Codex usage data

- Query: Research local Codex storage/logging surfaces for token usage on this machine, focusing on `~/.codex/logs_2.sqlite`, `~/.codex/state_5.sqlite`, `~/.codex/history.jsonl`, and plugin/cache directories. Do not read `~/.codex/auth.json`; use schema inspection and aggregate/sample metadata only.
- Scope: internal
- Date: 2026-05-05

## Findings

### Files found

- `~/.codex/state_5.sqlite` - primary local state database for threads, thread metadata, rollout paths, and aggregate `tokens_used`.
- `~/.codex/state_5.sqlite-wal` / `~/.codex/state_5.sqlite-shm` - SQLite WAL sidecars; readers should account for live updates.
- `~/.codex/logs_2.sqlite` - structured local log database; schema has log metadata and free-form `feedback_log_body`.
- `~/.codex/logs_2.sqlite-wal` / `~/.codex/logs_2.sqlite-shm` - SQLite WAL sidecars; log rows are actively changing during Codex use.
- `~/.codex/history.jsonl` - prompt history JSONL with only `session_id`, `ts`, and `text` top-level keys in the inspected sample.
- `~/.codex/sessions/**/*.jsonl` - session rollout JSONL files referenced by `state_5.sqlite.threads.rollout_path`; this is the cleanest observed source for split token usage.
- `~/.codex/plugins/cache/` - installed plugin bundles, skills, docs, scripts, and assets; no persisted usage records observed.
- `~/.codex/cache/codex_apps_tools/*.json` - app-tool cache JSON with top-level `schema_version` and `tools`; no token usage keys observed.
- `~/.codex/sqlite/codex-dev.db` - local automation/inbox database; inspected schema has no rows and no token usage fields.

### Schema and aggregate observations

- `logs_2.sqlite` has tables `_sqlx_migrations` and `logs`; `logs` columns are `id`, `ts`, `ts_nanos`, `level`, `target`, `feedback_log_body`, `module_path`, `file`, `line`, `thread_id`, `process_uuid`, and `estimated_bytes`. No schema-level token columns exist.
- `logs_2.sqlite.logs` had 50,121 rows at inspection time. Keyword counts in `feedback_log_body` show token data appears in log text, including `input_tokens` 90 matches, `output_tokens` 1,512 matches, `cached_tokens` 25 matches, `cache_creation_input_tokens` 10 matches, `cache_read_input_tokens` 10 matches, `total_tokens` 80 matches, and `usage` 2,771 matches.
- Token-related log matches cluster under targets such as `codex_core::stream_events_utils`, `codex_otel.log_only`, `codex_client::transport`, and `codex_api::sse::responses`. Sampled matching log bodies were non-JSON text, so using this database for exact usage would require brittle text parsing and carries higher privacy risk.
- `state_5.sqlite` includes `threads.tokens_used` and `thread_goals.tokens_used` / `thread_goals.token_budget`.
- `state_5.sqlite.threads` had 78 rows; 73 had nonzero `tokens_used`; aggregate `sum(tokens_used)` was 400,024,332 at inspection time.
- `state_5.sqlite.threads` also has `rollout_path`, `created_at_ms`, `updated_at_ms`, `source`, `model_provider`, `model`, `reasoning_effort`, `cwd`, `title`, and first-message fields. Use only non-sensitive columns for reporting unless the user explicitly asks for transcript-level context.
- `state_5.sqlite.thread_goals` had 1 row with `tokens_used` 95,987 and nullable `token_budget`.
- `history.jsonl` had 208 valid JSONL rows with top-level keys `session_id`, `ts`, and `text`; no token-ish key paths were found. It is useful for mapping prompts to session IDs only if sensitive text handling is acceptable; it is not a usage source.
- `~/.codex/sessions/**/*.jsonl` had 78 files and 33,874 valid rows. Event top-level keys were `timestamp`, `type`, and `payload`; event types included `response_item`, `event_msg`, `turn_context`, `session_meta`, and `compacted`.
- Session rollout JSONL contains repeated nested usage fields under `payload.info.total_token_usage` and `payload.info.last_token_usage`: `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, and `total_tokens`.
- In the inspected session files, 73 files had usage events. Summing the last observed `total_token_usage` per file yielded `input_tokens` 398,736,775, `cached_input_tokens` 361,245,184, `output_tokens` 1,915,017, `reasoning_output_tokens` 799,323, and `total_tokens` 400,651,792. The close match to `state_5.sqlite.threads.tokens_used` suggests `threads.tokens_used` is a convenient total-only summary while rollout JSONL is the split source.
- Plugin/cache inspection found 125 files under `~/.codex/plugins/cache/` and 2 files under `~/.codex/cache/`. Text keyword hits for generic `token` / `usage` exist in plugin docs/scripts, but no `input_tokens`, `output_tokens`, `cached_tokens`, or `total_tokens` usage fields were observed in those caches.

### Do input/output/cached token fields exist?

- `input_tokens`: yes, observed in `~/.codex/sessions/**/*.jsonl` under `payload.info.total_token_usage.input_tokens` and `payload.info.last_token_usage.input_tokens`; also appears in `logs_2.sqlite.logs.feedback_log_body` text.
- `output_tokens`: yes, observed in session rollout JSONL under `payload.info.total_token_usage.output_tokens` and `payload.info.last_token_usage.output_tokens`; also appears in log text.
- `cached token fields`: yes, session rollout JSONL uses `cached_input_tokens`; log text also contains `cached_tokens`, `cached_input_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens`.
- `total_tokens`: yes, observed in session rollout JSONL and log text.
- `state_5.sqlite`: has aggregate `tokens_used`, but no input/output/cached split columns.
- `history.jsonl`: no token fields found.
- `plugins/cache`: no persisted token usage fields found.

### Likely query strategy

Use `state_5.sqlite.threads` as the session index and metadata source, then parse the referenced rollout JSONL files for usage splits:

1. Open `~/.codex/state_5.sqlite` read-only and query `threads.id`, `threads.rollout_path`, `threads.created_at_ms`, `threads.updated_at_ms`, `threads.source`, `threads.model_provider`, `threads.model`, `threads.reasoning_effort`, and `threads.tokens_used`.
2. For each `rollout_path`, stream the JSONL file and inspect only usage metadata paths under `payload.info.total_token_usage` and `payload.info.last_token_usage`.
3. For per-session totals, take the last or maximum `payload.info.total_token_usage.total_tokens` observed in a file. In this sample, last and max matched, which is consistent with cumulative counters.
4. For per-turn detail, do not sum every `last_token_usage` occurrence blindly because usage metadata is repeated across many events. Instead, deduplicate by changes in cumulative `total_token_usage` or by a stable response/turn boundary if one is available in the event stream.
5. Use `state_5.sqlite.threads.tokens_used` as a fast total-only fallback and as a cross-check against parsed rollout totals.
6. Treat `logs_2.sqlite` as a diagnostic fallback only. It contains token strings but only inside free-form log bodies, which are harder to parse safely and may contain sensitive surrounding text.
7. Do not use `history.jsonl` or plugin/cache directories as usage sources.

### Code patterns

- The project currently has no application code beyond `AGENTS.md`; the task PRD explicitly notes this repository is likely for new local tooling rather than modifying an existing app: `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md:12`.
- The PRD requires tracking input, output, cache, and total dimensions when source data supports it: `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md:27`.
- The PRD requires avoiding sensitive auth data exposure: `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md:36`.
- Trellis requires persisted research artifacts under task directories: `.trellis/workflow.md:9` and `.trellis/workflow.md:42`.

### External references

- Local Codex version metadata from `~/.codex/version.json`: `latest_version` was `0.128.0`, `last_checked_at` was `2026-05-05T01:17:44.101629Z`.
- No web or third-party documentation was needed for this local storage inspection.

### Related specs

- `.trellis/spec/backend/index.md` - inspected; currently a guideline index placeholder, including database and logging guideline slots.
- `.trellis/spec/frontend/index.md` - inspected; currently a guideline index placeholder.

### Risks

- Privacy: `history.jsonl`, session rollout JSONL, and log bodies can contain prompts, responses, file paths, command output, and other sensitive content. A usage reporter should parse only whitelisted metadata paths and should never print raw events by default.
- Schema stability: `state_5.sqlite` and rollout JSONL are local Codex internals, not a documented public API. Version changes may rename fields or alter event repetition.
- Duplication: `payload.info.total_token_usage` and `last_token_usage` appear on many events. Naive summing across rows will overcount.
- Live writes: SQLite WAL files and active JSONL session files can change while being read. Prefer read-only SQLite connections, tolerate incomplete trailing JSONL lines, and consider snapshot/copy behavior for long reports.
- Semantics: `cached_input_tokens` is a split of input tokens in observed session metadata. Cost calculation needs model-specific pricing and cache pricing rules, which were not researched here.
- Log parsing: `logs_2.sqlite.feedback_log_body` contains token strings but sampled matching bodies were non-JSON; parsing them is fragile and may require reading sensitive context around the numbers.
- Coverage: 5 `state_5.sqlite.threads` rows had zero `tokens_used`; these may be empty, failed, or not-yet-backfilled sessions.

### One-line recommendation

Build the MVP as a local read-only reporter that indexes sessions from `state_5.sqlite.threads.rollout_path` and extracts whitelisted `payload.info.total_token_usage` fields from `~/.codex/sessions/**/*.jsonl`; use `threads.tokens_used` only as a total-only cross-check and avoid `history.jsonl`, raw log bodies, and plugin/cache directories for primary accounting.

## Caveats / Not Found

- `~/.codex/auth.json` was not read.
- Raw prompt, response, history text, first user messages, titles, cwd values, and auth-like values were intentionally not printed into this research.
- No `input_tokens`, `output_tokens`, or `cached_input_tokens` columns were found in `logs_2.sqlite` or `state_5.sqlite` schemas.
- No token usage fields were found in `history.jsonl`.
- No persisted token usage records were found in `~/.codex/plugins/cache/` or `~/.codex/cache/codex_apps_tools/`.
- `~/.codex/log/codex-tui.log` was identified as a large logging surface but not inspected beyond file metadata because raw logs are more likely to include sensitive content.
