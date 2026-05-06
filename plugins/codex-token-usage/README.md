# Codex Token Usage

Local Codex plugin wrapper for token usage reporting inside Codex CLI output.

## Invocation

Invoke the skill as `$codex-token-usage` or ask Codex to show the Codex token usage panel. The default bundled reporter command is:

```bash
plugins/codex-token-usage/bin/codex-token-usage
```

The default invocation prints a status-like text panel in the Codex CLI conversation. It defaults to the `Today` view and includes logical tab labels for `Current Session`, `Today`, `7 Days`, `Month`, and `All`.

The launcher is dependency-free and resolves `$PYTHON`, then `python3`, then `python`. It validates Python 3.10+ and `sqlite3` support before running the reporter.

Run diagnostics without reading secrets:

```bash
plugins/codex-token-usage/bin/codex-token-usage doctor
```

Explicit views can be selected without a browser UI:

```bash
plugins/codex-token-usage/bin/codex-token-usage current-session
plugins/codex-token-usage/bin/codex-token-usage today
plugins/codex-token-usage/bin/codex-token-usage 7-days
plugins/codex-token-usage/bin/codex-token-usage month
plugins/codex-token-usage/bin/codex-token-usage all
```

`Today`, `7 Days`, `Month`, and `All` support project/directory grouping:

```bash
plugins/codex-token-usage/bin/codex-token-usage today --group project
plugins/codex-token-usage/bin/codex-token-usage 7-days --group directory
plugins/codex-token-usage/bin/codex-token-usage month --group project
plugins/codex-token-usage/bin/codex-token-usage all --group directory
```

`Current Session` uses only a safe exact match from a provided Codex session id or rollout path, including supported environment variables when present. If the active session cannot be mapped safely, the reporter prints an unavailable message instead of guessing from history, transcript text, raw logs, prompts, or responses.

HTML output is optional only:

```bash
plugins/codex-token-usage/bin/codex-token-usage html-panel
```

## Data Sources

The reporter is read-only. It uses:

- `~/.codex/state_5.sqlite`, table `threads`, as the session index.
- `threads.rollout_path` to locate session JSONL files under `~/.codex/sessions/**/*.jsonl`.
- Only whitelisted usage fields from `payload.info.total_token_usage`:
  `input_tokens`, `cached_input_tokens`, `output_tokens`,
  `reasoning_output_tokens`, and `total_tokens`.

It does not read `~/.codex/auth.json`, `~/.codex/history.jsonl`, log bodies, raw prompts, raw responses, or transcript text fields. Repo reporting uses the basename of the whitelisted `threads.cwd` path so the default panel does not print full local paths.

## Cost Estimates

The reporter includes API-equivalent estimated costs when the session model has an explicit OpenAI API pricing mapping. Estimates are not actual bills.

The formula is:

```text
uncached_input = max(input_tokens - cached_input_tokens, 0)
cost = uncached_input * input_rate + cached_input_tokens * cached_input_rate + output_tokens * output_rate
```

`reasoning_output_tokens` is displayed as an output breakdown but is not charged as a separate bucket. Unknown or unmapped models show cost unavailable with a warning instead of using a guessed nearby rate.

## Notes

`payload.info.total_token_usage` is cumulative and can appear repeatedly in a session file. The reporter keeps the highest/latest cumulative usage object per session instead of summing every event.

Current official Codex plugin docs do not expose `/model`-style native arrow-key tab switching for local plugins. `$codex-token-usage` therefore supports logical tabs through command arguments or user intent inside Codex.
