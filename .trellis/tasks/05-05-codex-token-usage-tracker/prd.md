# brainstorm: Codex token usage tracker

## Goal

Explore a practical way to track Codex token usage, including input tokens, output tokens, cached input tokens, and related cost/usage breakdowns, either as a Codex plugin or another local tooling approach.

## What I already know

* The user wants a way to measure Codex token consumption.
* The desired dimensions include input, output, cache, and similar usage categories.
* The implementation form is open: a Codex plugin is one possibility, but another approach is acceptable if it gives better data or lower maintenance cost.
* The project repository currently has only `AGENTS.md`; this task is likely about creating new local tooling rather than modifying an existing app.
* Local Codex configuration exists under `~/.codex/`, including plugin/cache directories and SQLite databases that may contain usage or session logs.
* Official Codex plugins bundle skills, app integrations, MCP servers, and hooks, but no documented plugin/hook surface exposes Codex's internal per-request model `usage` object.
* The local machine has usable token breakdowns under `~/.codex/sessions/**/*.jsonl` at `payload.info.total_token_usage`, including input, cached input, output, reasoning output, and total tokens.
* `~/.codex/state_5.sqlite.threads` is useful as a session index and total-only cross-check through `rollout_path` and `tokens_used`.
* Official Codex plugin documentation does not currently expose a documented API for third-party `/model`-style arrow-key pickers or native in-place tab switching.
* OpenAI API pricing can support an API-equivalent cost estimate, but local Codex session usage is not a billing record and must be labeled as an estimate.

## Assumptions (temporary)

* The first useful deliverable is a local usage reporter rather than a cloud billing replacement.
* Exact per-request usage is preferred over approximate transcript tokenization.
* The tool should avoid reading or exposing sensitive auth data.

## Open Questions

* None currently.

## Requirements (evolving)

* Track token usage for Codex sessions where the data is locally available.
* Break usage down into at least input, output, cached input, and totals when the source data supports it.
* Prefer a maintainable implementation that can survive Codex CLI changes.
* Read only whitelisted metadata paths and avoid printing raw prompt/response/log text by default.
* Deliver the MVP as a Codex plugin wrapper, not only a standalone script.
* Bundle the local read-only reporter implementation inside the plugin so the user can invoke usage summaries from Codex.
* The plugin should provide a simple default summary and support explicit report scopes through arguments or documented usage.
* Provide a Codex-facing `$` command or equivalent invocation that prints a usage panel inside the Codex CLI conversation, similar in spirit to Codex's built-in status output.
* The panel should default to today's usage.
* The panel should expose logical tab views for switching between usage dimensions inside CLI output; it must not default to opening a browser or writing an HTML page.
* First-version tabs should be `Current Session`, `Today`, `7 Days`, `Month`, and `All`.
* The `Current Session` tab should report the current Codex session when it can be detected; if the active session cannot be mapped safely, the CLI panel should say that current-session detection is unavailable rather than guessing from raw transcript content.
* `Today`, `7 Days`, `Month`, and `All` must support project/directory grouping.
* The reporter should show API-equivalent estimated cost when the session model maps to an official OpenAI API pricing entry.
* The cost estimate should compute uncached input, cached input, and output costs separately. `reasoning_output_tokens` is a displayed output breakdown, not an extra charged bucket.
* Unknown/unmapped model costs should be reported as unavailable with a warning instead of guessed from nearby model names.
* Native arrow-key or in-place tab switching should only be claimed if a documented Codex plugin UI surface supports it; otherwise, tab switching means selecting logical tabs through `$codex-token-usage <tab>` / `$codex-token-usage <tab> --group project|directory`.

## Acceptance Criteria (evolving)

* [x] A recommended MVP approach is selected with clear trade-offs.
* [x] The data source for token usage is identified and documented.
* [x] The MVP can produce a human-readable summary of usage.
* [x] Sensitive data such as auth tokens is not read or printed.
* [x] Session totals are computed without double-counting repeated usage metadata events.
* [x] A Codex plugin manifest exists and exposes a usable workflow entry for token usage reporting.
* [x] The default CLI panel view shows today's input, cached input, output, reasoning output, and total tokens.
* [x] Logical tab switching exposes alternate summary dimensions through CLI output.
* [ ] The CLI panel includes `Current Session`, `Today`, `7 Days`, `Month`, and `All` tab labels.
* [ ] `Today`, `7 Days`, `Month`, and `All` support grouping by project/directory.
* [ ] The CLI output includes API-equivalent estimated cost when pricing is known.
* [ ] Unknown/unmapped models are surfaced as cost-unavailable warnings.
* [ ] Documentation clearly states that native keyboard tab switching is not currently supported by documented local plugin APIs.

## Definition of Done (team quality bar)

* Tests added/updated where appropriate.
* Lint / typecheck / CI green if a code implementation is added.
* Docs/notes updated if behavior changes.
* Rollout/rollback considered if risky.

## Out of Scope (explicit)

* Replacing OpenAI billing dashboards.
* Uploading local Codex logs to a third-party service.
* Editing Codex internals unless no supported or stable alternative exists.

## Technical Notes

* Repo root inspected: `/Users/fengxudong/Desktop/projects/codex-usage`.
* Local Codex directory inspected at a high level: `~/.codex`.
* OpenAI product guidance should come from official OpenAI docs where available.
* Official docs: Codex plugins are for reusable workflows with skills/apps/MCP servers; plugin build docs recommend a local skill for one repo or personal workflow before publishing a plugin.
* Official docs: Codex App Server lists `thread/tokenUsage/updated`, but the public docs do not fully specify payload shape or whether it is per-turn versus aggregate.
* Official API docs: Responses expose a `usage` object for direct API calls; the organization Usage API provides aggregate fields such as input, output, and cached input tokens. These APIs do not automatically reveal Codex's internal requests to a plugin.

## Research References

* [`research/local-codex-usage-data.md`](research/local-codex-usage-data.md) — local session JSONL is the cleanest observed source for split usage; SQLite is useful as index/cross-check.
* [`research/codex-plugin-usage-surfaces.md`](research/codex-plugin-usage-surfaces.md) — plugin/hook surfaces do not document per-request usage; App Server usage events are the closest official Codex-adjacent surface.
* [`research/openai-pricing-cost-model.md`](research/openai-pricing-cost-model.md) — official pricing-derived cost formula, model mapping rules, and estimate caveats.
* [`research/codex-interactive-ui-capabilities.md`](research/codex-interactive-ui-capabilities.md) — current plugin surfaces do not document `/model`-style native keyboard tab UI for local plugins.

## Research Notes

### Feasible approaches here

**Approach A: Local read-only reporter** (Recommended)

* How it works: query `~/.codex/state_5.sqlite.threads` for thread metadata and `rollout_path`, then stream each referenced session JSONL file and extract only `payload.info.total_token_usage`.
* Pros: works with the data already present on this machine; gives input/output/cached/reasoning/total breakdowns; can be implemented as a small CLI first.
* Cons: relies on local Codex internal file formats; must tolerate schema changes and live-written files.

**Approach B: Codex App Server usage listener**

* How it works: build a small client around the Codex App Server JSON-RPC stream and subscribe to `thread/tokenUsage/updated`.
* Pros: closest official Codex-adjacent usage event; potentially live dashboard-friendly.
* Cons: payload and granularity still need validation; more moving parts than a local reporter; may not cover historical usage.

**Approach C: Plugin wrapper around the reporter**

* How it works: package a local skill/plugin that invokes the reporter and formats summaries inside Codex.
* Pros: convenient UX once the reporter is solid; shareable across repos or machines.
* Cons: not a better data source by itself; a plugin still needs the local reporter or App Server listener underneath.

## Decision (ADR-lite)

**Context**: The user wants an end-to-end Codex plugin or equivalent for tracking token usage, and prefers avoiding a staged CLI-first implementation.

**Decision**: Build the MVP as a Codex plugin wrapper that bundles a local read-only usage reporter. The plugin provides the Codex-facing workflow entry; the reporter parses local Codex session metadata and avoids raw transcript/log output.

**Consequences**: This gives the desired user experience in one deliverable. The data layer still depends on local Codex internal files, so the parser must be isolated, defensive, and documented. App Server live tracking remains a future enhancement rather than the MVP source of truth.

**UI Decision**: Prefer a `$` command or equivalent plugin invocation that prints a status-like tabbed usage panel directly in Codex CLI output. The default tab is `Today`; the first-version top-level tabs are `Current Session`, `Today`, `7 Days`, `Month`, and `All`. Project/directory grouping is selected by arguments rather than separate top-level tabs.

**UI Consequences**: The MVP should not open a local HTML page or browser window. Tabs are logical CLI views, selected by command arguments or user intent, rather than browser UI tabs. A future native plugin panel can be added only if Codex exposes a documented in-CLI interactive surface.

**Cost Decision**: Show cost as an API-equivalent estimate, not as the user's actual bill. Use only explicit official-pricing model mappings. Compute uncached input, cached input, and output costs separately; do not charge `reasoning_output_tokens` as an extra bucket.

## Expansion Sweep

### Future evolution

* Add model/day/project filters, cost estimates, trend charts, and budget alerts after the data layer is reliable.
* Keep the parser isolated so future Codex format changes only touch one module.
* Optionally add a live App Server listener later if `thread/tokenUsage/updated` proves stable enough.

### Related scenarios

* Support both historical reports (`today`, `last 7 days`, by model) and eventually live session monitoring.
* Keep API billing reconciliation separate from local Codex session accounting.
* Keep the default output text-first so it works inside Codex CLI without an external browser.
* If Codex later documents plugin-authored interactive CLI views, add true keyboard tab switching as a separate enhancement.

### Failure and edge cases

* Avoid double-counting repeated `total_token_usage` metadata across multiple JSONL events.
* Tolerate missing `rollout_path`, incomplete trailing JSONL rows, active WAL writes, and absent local Codex data.
* Never read `~/.codex/auth.json` and never print raw event bodies unless an explicit debug flag is added.
