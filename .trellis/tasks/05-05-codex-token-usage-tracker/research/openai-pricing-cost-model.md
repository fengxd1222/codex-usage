# Research: OpenAI pricing cost model for Codex token usage

- Query: Official OpenAI API pricing and usage fields needed to compute equivalent costs for local Codex usage.
- Scope: mixed
- Date: 2026-05-05

## Findings

### Files found

- `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md` - Task requirements and prior decisions for the Codex token usage reporter.
- `plugins/codex-token-usage/scripts/codex_usage_reporter.py` - Current local reporter implementation and usage field model.
- `tests/test_codex_usage_reporter.py` - Tests covering local usage parsing, privacy constraints, and CLI panels.
- `.trellis/spec/backend/index.md` - Backend spec index; content is mostly placeholder, but relevant as the implementation is a Python CLI-style backend utility.
- `.trellis/tasks/05-05-codex-token-usage-tracker/research/local-codex-usage-data.md` - Existing research on local Codex usage data source.
- `.trellis/tasks/05-05-codex-token-usage-tracker/research/codex-plugin-usage-surfaces.md` - Existing research on plugin and Codex-adjacent usage surfaces.

### Existing code patterns

- The reporter models local Codex usage with `input_tokens`, `cached_input_tokens`, `output_tokens`, `reasoning_output_tokens`, and `total_tokens`; these names are already close to OpenAI Responses usage fields, except local `cached_input_tokens` corresponds to API `usage.input_tokens_details.cached_tokens` rather than a top-level response field. See `plugins/codex-token-usage/scripts/codex_usage_reporter.py:18`.
- The local source of truth is intentionally `payload.info.total_token_usage` inside Codex session JSONL files, not direct OpenAI API responses or organization billing APIs. See `plugins/codex-token-usage/scripts/codex_usage_reporter.py:341`.
- The reporter takes the best cumulative usage snapshot from repeated session metadata events to avoid double-counting cumulative totals. See `plugins/codex-token-usage/scripts/codex_usage_reporter.py:366`.
- The reporter only reads rollout paths under `~/.codex/sessions/**/*.jsonl`, which keeps any cost feature from reading secrets such as `~/.codex/auth.json`. See `plugins/codex-token-usage/scripts/codex_usage_reporter.py:335`.
- Tests already assert that repeated `total_token_usage` events are not summed, raw prompt text is not printed, and `auth.json` is not opened. See `tests/test_codex_usage_reporter.py:33`, `tests/test_codex_usage_reporter.py:102`.
- The PRD explicitly says billing dashboards are out of scope and API billing reconciliation should stay separate from local Codex accounting. See `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md:62` and `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md:127`.

### Official pricing model

OpenAI's current API pricing page gives prices per 1M tokens and splits model charges into input, cached input, and output. For Standard short-context flagship/API models relevant to Codex-like usage:

| Model ID / product label | Input / 1M | Cached input / 1M | Output / 1M | Notes |
|---|---:|---:|---:|---|
| `gpt-5.5` | $5.00 | $0.50 | $30.00 | Standard short context. Long context is $10.00 / $1.00 / $45.00. |
| `gpt-5.5-pro` | $30.00 | n/a | $180.00 | Standard short context; no cached input rate listed. |
| `gpt-5.4` | $2.50 | $0.25 | $15.00 | Standard short context. Long context is $5.00 / $0.50 / $22.50. |
| `gpt-5.4-mini` | $0.75 | $0.075 | $4.50 | Standard short context. |
| `gpt-5.4-nano` | $0.20 | $0.02 | $1.25 | Standard short context. |
| `gpt-5.4-pro` | $30.00 | n/a | $180.00 | Standard short context. |
| `gpt-5.3-codex` | $1.75 | $0.175 | $14.00 | Specialized Codex pricing. Priority is $3.50 / $0.35 / $28.00. |
| `gpt-5.3-chat-latest` | $1.75 | $0.175 | $14.00 | Specialized ChatGPT model pricing. |

Sources:

- OpenAI API pricing overview: https://openai.com/api/pricing/ (lines 33-60 list `gpt-5.5`, `gpt-5.4`, and `gpt-5.4-mini` Standard rates).
- Detailed OpenAI API pricing: https://developers.openai.com/api/docs/pricing (lines 630-648 list Standard short/long context rates; lines 797-818 list specialized `gpt-5.3-codex` and `gpt-5.3-chat-latest`; lines 678-684 list Priority rates).
- Codex pricing docs: https://developers.openai.com/codex/pricing (lines 631-640 and 668-677 say API key Codex usage pays for tokens based on API pricing; lines 835-839 list ChatGPT credit rates per 1M input/cached/output tokens).
- Codex rate card Help Center: https://help.openai.com/en/articles/20001106-codex-rate-card (lines 34-44 list token-based Codex credits per 1M input/cached/output tokens and lines 47-56 describe fast mode and code review).

### Cost formula for API-equivalent estimates

For a single session or aggregate where all rows use the same model and service tier:

```text
uncached_input_tokens = max(input_tokens - cached_input_tokens, 0)
api_equivalent_cost =
  (uncached_input_tokens / 1_000_000) * input_rate_per_1m
  + (cached_input_tokens / 1_000_000) * cached_input_rate_per_1m
  + (output_tokens / 1_000_000) * output_rate_per_1m
```

Reasoning tokens should not be priced as a fourth category. Official Responses objects put reasoning counts under `output_tokens_details.reasoning_tokens`, and `max_output_tokens` includes both visible output and reasoning tokens. The local reporter's `reasoning_output_tokens` should therefore be a displayed breakdown of output usage, not an additional charged token bucket. API-equivalent pricing should use total `output_tokens` as the charged output quantity.

If the local Codex session data contains both `output_tokens` and `reasoning_output_tokens`, do not add them together unless local observation proves `output_tokens` excludes reasoning. Current code treats both as separate fields because the local JSONL format is internal. A cost feature should preserve the invariant that cost is computed from one charged output total per source row.

### Usage field mapping

| Local reporter field | OpenAI Responses API field | Organization Usage API field | Cost treatment |
|---|---|---|---|
| `input_tokens` | `usage.input_tokens` | `input_tokens` | Total text input tokens, including cached tokens. |
| `cached_input_tokens` | `usage.input_tokens_details.cached_tokens` | `input_cached_tokens` | Charged at cached input rate when model lists a cached input price. |
| `output_tokens` | `usage.output_tokens` | `output_tokens` | Charged at output rate. Includes reasoning for Responses pricing purposes. |
| `reasoning_output_tokens` | `usage.output_tokens_details.reasoning_tokens` | Not clearly exposed in aggregate completions usage fields found in docs. | Display only; do not add as a separate cost bucket. |
| `total_tokens` | `usage.total_tokens` | Not the cost field; aggregate API exposes input and output buckets. | Useful for reporting, not direct pricing. |

Sources:

- Responses API response object example: https://platform.openai.com/docs/api-reference/responses/object (lines 2032-2037 define `usage`; lines 2147-2157 show `input_tokens`, `input_tokens_details.cached_tokens`, `output_tokens`, `output_tokens_details.reasoning_tokens`, and `total_tokens`).
- Responses API `max_output_tokens`: https://platform.openai.com/docs/api-reference/responses/object (lines 257-264 and 1866-1870 state this bound includes visible output and reasoning tokens).
- Organization Usage API: https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage (lines 831-866 list usage and costs endpoints; lines 884-910 describe input, output, and cached input fields; lines 1108-1123 describe cost amount/currency/value).

### Prompt caching semantics

- Prompt caching is automatic for recent OpenAI models and is intended to reduce both latency and input token cost.
- Cache hits require exact prompt-prefix matches, so the static part of a prompt should come first and variable user/repo data should come later.
- Caching becomes available for prompts with 1024 or more tokens. Shorter requests still expose a cached token field, but it is zero.
- Cached tokens are still part of the input token count. For cost estimates, subtract cached tokens from input tokens before applying the uncached input rate, then apply the cached input rate to cached tokens.
- Cached input does not change output generation or output pricing.
- Cached tokens still count against TPM/rate limits, so cost savings do not imply rate-limit savings.

Source: https://developers.openai.com/api/docs/guides/prompt-caching (lines 630-635 describe automatic cost/latency savings and prefix placement; lines 640-648 describe cache lookup/hit/miss; lines 693-723 show cached token reporting; lines 729-733 recommend monitoring cache counts; lines 740-751 cover output behavior and TPM).

### Model mapping recommendations

Use exact model IDs first. A pricing table in this project should map normalized lowercase model IDs to a rate-card entry only when the ID is explicitly present in official pricing docs. Recommended initial mapping:

- `gpt-5.5` -> API Standard short-context unless local metadata proves long context, Batch, Flex, Priority, regional processing, or ChatGPT credits.
- `gpt-5.5-pro` -> API Standard short-context, no cached-input rate.
- `gpt-5.4` -> API Standard short-context unless local metadata proves a different processing mode or context tier.
- `gpt-5.4-mini` -> API Standard short-context.
- `gpt-5.4-nano` -> API Standard short-context.
- `gpt-5.4-pro` -> API Standard short-context, no cached-input rate.
- `gpt-5.3-codex` -> specialized Codex API Standard rate.
- `gpt-5.3-chat-latest` -> specialized ChatGPT API Standard rate.

Treat these as unmapped unless a separate official rate source is found for the exact model and billing mode:

- `gpt-5`, `gpt-5-codex`, `gpt-5-codex-mini`, `gpt-5.1`, `gpt-5.1-codex`, `gpt-5.1-codex-max`, `gpt-5.1-codex-mini`, `gpt-5.2`, `gpt-5.2-codex`, `gpt-5.3-codex-spark`.

Reasoning: official Codex docs mention older/preview model labels in retention or legacy credit contexts, but the current API pricing page found during this research does not list current dollar rates for every one of those historical/local names. In particular, the Codex Help Center rate card lists `GPT-5.2` in credits, while the detailed API pricing page does not list an API dollar row for `gpt-5.2`.

### Implementation implications

- Add cost as an optional "API-equivalent estimate" column or view, not as the default headline metric.
- Include the pricing snapshot date in output, because OpenAI pricing changes.
- Label subscription usage as credits, not dollars, unless the reporter knows Codex is using an API key and can map the exact service tier.
- Add `unknown_model` / `unpriced_model` warnings instead of falling back to a nearby model. Do not map `gpt-5.3-codex-spark` to `gpt-5.3-codex`; official docs call Spark a research preview with non-final credit rates.
- If a cached-input rate is missing for a model, either price cached tokens at the normal input rate or mark cost unavailable; do not silently price cached tokens at zero.
- Support `service_tier` and context tier as future dimensions. Official pricing can vary by Standard, Batch, Flex, Priority, short context, long context, and regional processing uplift.
- Keep organization Usage API and Costs API as a separate reconciliation feature. They are aggregate/admin APIs and do not expose the local Codex session/repo breakdown this reporter currently provides.

### Related specs

- `.trellis/spec/backend/index.md` - Backend guideline index for Python utility work; individual backend guidelines are placeholders, so task-local tests and PRD constraints are the stronger guidance.
- `.trellis/spec/guides/code-reuse-thinking-guide.md` - Relevant if adding a model pricing table, because pricing constants must be centralized and searched before edits.

## Caveats / Not Found

- The OpenAI developer docs MCP tools were not available in this researcher environment. Because Trellis researcher scope forbids writing outside the task research directory, no MCP installation was attempted. Official OpenAI web docs were used instead.
- No official public document was found that proves local Codex `~/.codex/sessions/**/*.jsonl` `payload.info.total_token_usage` fields have the same billing semantics as direct Responses API `usage` fields. Cost must be labeled as an estimate.
- No official API-dollar rows were found for every historical/local Codex model name mentioned in Codex docs, including `gpt-5.1-codex-max`, `gpt-5.1-codex-mini`, `gpt-5.2-codex`, `gpt-5-codex`, or `gpt-5-codex-mini`.
- Current local Codex thread metadata may not record service tier, context length tier, regional processing, Batch/Flex/Priority, or fast mode. Without those, exact billing cannot be reconstructed from local session logs alone.
- The official Codex docs have two pricing surfaces: API-key usage is based on API pricing, while ChatGPT plans use credits and included limits. These should not be merged into one dollar figure.
