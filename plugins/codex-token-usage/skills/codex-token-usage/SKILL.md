---
name: codex-token-usage
description: Print a Codex CLI-internal token usage and estimated cost panel with Current Session, Today, 7 Days, Month, and All views.
---

# Codex Token Usage

Use this skill when the user invokes `$codex-token-usage`, asks for a Codex token usage panel, or asks for local Codex token usage summaries.

## Workflow

1. From the repository root, run the default CLI panel. This prints inside the Codex CLI conversation and defaults to `Today`:

   ```bash
   plugins/codex-token-usage/bin/codex-token-usage
   ```

2. If the user asks to check setup or troubleshoot missing data, run diagnostics. This does not read secrets:

   ```bash
   plugins/codex-token-usage/bin/codex-token-usage doctor
   ```

3. For explicit views, pass the logical tab name directly or use `summary --tab`:

   ```bash
   plugins/codex-token-usage/bin/codex-token-usage current-session
   plugins/codex-token-usage/bin/codex-token-usage today
   plugins/codex-token-usage/bin/codex-token-usage 7-days
   plugins/codex-token-usage/bin/codex-token-usage month
   plugins/codex-token-usage/bin/codex-token-usage all
   ```

4. For `Today`, `7 Days`, `Month`, and `All`, group by project or directory when requested:

   ```bash
   plugins/codex-token-usage/bin/codex-token-usage today --group project
   plugins/codex-token-usage/bin/codex-token-usage 7-days --group directory
   plugins/codex-token-usage/bin/codex-token-usage month --group project
   plugins/codex-token-usage/bin/codex-token-usage all --group directory
   ```

5. If Codex provides a safe current-session identity, pass it through to the reporter. Do not infer it from raw transcript content:

   ```bash
   plugins/codex-token-usage/bin/codex-token-usage current-session --session-id "$CODEX_SESSION_ID"
   ```

6. Optional only: if the user explicitly asks for an HTML file, generate it without making it the default `$codex-token-usage` behavior:

   ```bash
   plugins/codex-token-usage/bin/codex-token-usage html-panel
   ```

## Safety Rules

- Do not read `~/.codex/auth.json`.
- Do not read `~/.codex/history.jsonl`.
- Do not read raw Codex log bodies.
- Do not print raw prompt, response, transcript, or event bodies.
- Use the bundled reporter, which only extracts the whitelisted `payload.info.total_token_usage` fields from session JSONL lines and uses `state_5.sqlite.threads.rollout_path` as the session index.
- For `Current Session`, use only a safe exact match from a provided session id or rollout path. If no safe match is available, print the unavailable message.

## Cost Rules

- Show API-equivalent cost as an estimate, not as an actual bill.
- Use only explicit official-pricing model mappings from the bundled reporter.
- Compute uncached input, cached input, and output costs. Do not price `reasoning_output_tokens` as an extra bucket.
- If a model has no explicit official pricing mapping, print cost unavailable instead of guessing.

## Panel Surface

The panel is a status-like text report printed in the Codex CLI output. It must not open a browser or write an HTML page by default.
Current official Codex plugin docs do not expose `/model`-style native arrow-key tab switching for local plugins, so tabs are selected through logical view arguments or user intent.
