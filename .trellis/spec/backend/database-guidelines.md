# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

<!--
Document your project's database conventions here.

Questions to answer:
- What ORM/query library do you use?
- How are migrations managed?
- What are the naming conventions for tables/columns?
- How do you handle transactions?
-->

(To be filled by the team)

---

## Query Patterns

<!-- How should queries be written? Batch operations? -->

(To be filled by the team)

---

## Migrations

<!-- How to create and run migrations -->

(To be filled by the team)

---

## Naming Conventions

<!-- Table names, column names, index names -->

(To be filled by the team)

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

(To be filled by the team)

<spec-entry category="decision" keywords="codex-usage,state-5-sqlite,session-jsonl,privacy" date="2026-05-05" source="plugins/codex-token-usage/scripts/codex_usage_reporter.py">

### Local Codex Usage Reporter Data Contract

#### 1. Scope / Trigger

- Trigger: local infrastructure integration that reads Codex-managed storage for token usage reporting.
- Scope: repo-local Codex plugin reporters that summarize local Codex token usage.

#### 2. Signatures

- CLI default: `python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py` prints the status-like text panel with `Today` selected.
- CLI views: `python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py <current-session|today|7-days|month|all>`.
- CLI grouping: `python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py <today|7-days|month|all> --group <project|directory>`.
- CLI JSON: `python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py summary --tab <current-session|today|7-days|month|all> [--group <project|directory>] --json`.
- Optional HTML only: `python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py html-panel [--open] [--output <path>] [--print-fallback]`.
- Database index: read-only SQLite connection to `~/.codex/state_5.sqlite`, table `threads`, column `rollout_path`.

#### 3. Contracts

- Allowed SQLite columns: `id`, `rollout_path`, `created_at_ms`, `updated_at_ms`, `model_provider`, `model`, `reasoning_effort`, `cwd`, `tokens_used`.
- Allowed JSONL path: files under `~/.codex/sessions/**/*.jsonl` referenced by `threads.rollout_path`.
- Allowed JSONL usage object: `payload.info.total_token_usage`.
- Allowed usage fields: `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, `total_tokens`.
- Default repo labels must use `basename(cwd)` rather than full local paths.
- `Current Session` must map only from an exact supplied session id or rollout path. If unavailable, print an unavailable message and do not infer from raw transcript content.
- Cost is an API-equivalent estimate, not a bill. Use only explicit official-pricing mappings; unknown models must report cost unavailable.
- Cost formula: `max(input_tokens - cached_input_tokens, 0) * input_rate + cached_input_tokens * cached_input_rate + output_tokens * output_rate`.
- `reasoning_output_tokens` is display-only and must not be charged as a separate bucket.

#### 4. Validation & Error Matrix

- Missing `state_5.sqlite` -> return an empty report with a warning.
- Missing `threads` table or `rollout_path` column -> return an empty report with a warning.
- `rollout_path` outside `~/.codex/sessions` -> skip the path and do not print the full path.
- Missing or unreadable session JSONL -> keep the report running and add a warning.
- Repeated cumulative `total_token_usage` rows -> keep the highest/latest cumulative object, not the sum of all rows.

#### 5. Good/Base/Bad Cases

- Good: one session file has repeated cumulative usage events; the report shows the final cumulative total once.
- Base: no local Codex state exists; the report renders zero totals and a warning.
- Bad: a thread points at `~/.codex/auth.json`; the reporter skips it and does not open or print it.

#### 6. Tests Required

- Assert repeated cumulative usage is not double-counted.
- Assert rollout paths outside `~/.codex/sessions` are skipped.
- Assert raw prompt/response fields in a JSONL row are not included in text or optional HTML output.
- Assert the default CLI panel contains `Current Session`, `Today`, `7 Days`, `Month`, and `All`, with `Today` active by default.
- Assert `today`, `7-days`, `month`, and `all` support project/directory grouping.
- Assert cost estimates use cached-input and output rates, and unknown models report cost unavailable.
- Assert default invocation does not open a browser or write an HTML file.

#### 7. Wrong vs Correct

Wrong:

```text
Sum every payload.info.total_token_usage object in every JSONL row.
```

Correct:

```text
For each session file, keep the highest/latest cumulative payload.info.total_token_usage object and aggregate those per-session totals.
```

</spec-entry>
