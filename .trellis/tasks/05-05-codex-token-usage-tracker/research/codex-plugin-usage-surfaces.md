# Research: Codex plugin usage surfaces

- Query: Official OpenAI/Codex extension or plugin mechanisms and whether a Codex plugin can access per-request token usage.
- Scope: mixed
- Date: 2026-05-05

## Findings

### Summary

Official Codex plugin surfaces package workflows and integrations, but the documented plugin/hook inputs do not expose per-request token usage. A plugin can bundle skills, apps/connectors, MCP servers, and hooks; those surfaces can read external data, run local scripts, or subscribe to lifecycle metadata, but none is documented as receiving the underlying Codex model response `usage` object. The closest official Codex usage surface found is the Codex App Server JSON-RPC event `thread/tokenUsage/updated`, which is a client/app-server event stream rather than a plugin API.

Recommendation: Do not build the MVP as a Codex plugin for exact usage; prototype against the documented Codex App Server `thread/tokenUsage/updated` event or a supported local session-log/reporting surface, and keep a plugin only as an optional UI/workflow wrapper.

### Files found

- `.trellis/workflow.md` - Trellis requires research artifacts to be persisted under the task `research/` directory and not left only in chat.
- `.trellis/spec/backend/index.md` - Backend spec index exists but is still a placeholder template.
- `.trellis/spec/frontend/index.md` - Frontend spec index exists but is still a placeholder template.
- `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md` - Task goal is to track Codex token usage, preferably exact per-request usage, while avoiding sensitive auth data.
- `.codex/config.toml` - Project Codex config documents that hooks require a user-level feature flag.
- `.codex/hooks.json` - Current repo hooks only run Trellis `SessionStart` and `UserPromptSubmit` scripts.
- `/Users/fengxudong/.codex/skills/.system/plugin-creator/SKILL.md` - Local system skill describing Codex plugin scaffolding and marketplace conventions.
- `/Users/fengxudong/.codex/skills/.system/plugin-creator/references/plugin-json-spec.md` - Local plugin manifest and marketplace JSON sample spec.
- `/Users/fengxudong/.codex/skills/.system/skill-creator/references/openai_yaml.md` - Local `agents/openai.yaml` field reference for skill UI metadata and MCP dependencies.
- `/Users/fengxudong/.codex/plugins/cache/openai-bundled/browser-use/0.1.0-alpha1/skills/browser/SKILL.md` - Bundled Browser Use skill showing a plugin-provided script plus Node REPL runtime pattern.
- `/Users/fengxudong/.codex/plugins/cache/openai-bundled/browser-use/0.1.0-alpha1/skills/browser/agents/openai.yaml` - Bundled skill UI metadata example.
- `/Users/fengxudong/.codex/plugins/cache/openai-primary-runtime/documents/26.430.10722/README.md` - Primary-runtime file-type wrapper plugin example.

### Code patterns

- Plugin scaffolding expects a required `.codex-plugin/plugin.json` and may add optional `skills/`, `hooks/`, `scripts/`, `assets/`, `.mcp.json`, and `.app.json` components: `/Users/fengxudong/.codex/skills/.system/plugin-creator/SKILL.md:47`.
- Plugin marketplace entries use repo or home marketplace files, include `policy.installation`, `policy.authentication`, and `category`, and render in declared order: `/Users/fengxudong/.codex/skills/.system/plugin-creator/SKILL.md:68`.
- The plugin manifest sample can point to `skills`, `hooks`, `mcpServers`, and `apps`, but it does not define any token-usage permission or telemetry field: `/Users/fengxudong/.codex/skills/.system/plugin-creator/references/plugin-json-spec.md:17`.
- Manifest path conventions are relative plugin-root paths, normally beginning with `./`: `/Users/fengxudong/.codex/skills/.system/plugin-creator/references/plugin-json-spec.md:91`.
- `agents/openai.yaml` can declare UI metadata and `dependencies.tools`, but only `mcp` is supported for tool dependencies in the local reference: `/Users/fengxudong/.codex/skills/.system/skill-creator/references/openai_yaml.md:16`.
- Browser Use shows a plugin pattern where a skill imports a bundled helper script and uses the Node REPL MCP runtime to access a browser surface; this is an integration surface, not Codex model telemetry: `/Users/fengxudong/.codex/plugins/cache/openai-bundled/browser-use/0.1.0-alpha1/skills/browser/SKILL.md:18`.
- Browser Use `agents/openai.yaml` contains UI copy and a default prompt, with no usage/token telemetry declaration: `/Users/fengxudong/.codex/plugins/cache/openai-bundled/browser-use/0.1.0-alpha1/skills/browser/agents/openai.yaml:1`.
- Documents is a bundled primary-runtime wrapper plugin for document workflows, reinforcing the pattern that plugins package workflow-specific capabilities: `/Users/fengxudong/.codex/plugins/cache/openai-primary-runtime/documents/26.430.10722/README.md:1`.
- This repo currently enables only Trellis lifecycle hooks in `.codex/hooks.json`, and no `PostToolUse` or `Stop` hook is configured for usage capture: `.codex/hooks.json:1`.
- This repo's project config says `codex_hooks` must be enabled globally in `~/.codex/config.toml`; project-local config alone cannot enable hooks: `.codex/config.toml:7`.
- The PRD explicitly prefers exact usage and forbids exposing sensitive auth data: `.trellis/tasks/05-05-codex-token-usage-tracker/prd.md:17`.

### Comparable extension / data access patterns

| Pattern | Official / local evidence | What it can access | Token usage fit |
| --- | --- | --- | --- |
| Plugin with bundled skills | Official Plugins and Agent Skills docs; local `plugin-creator` and installed plugin examples | Reusable instructions, references, optional scripts, UI metadata | Poor for exact usage. Skills guide model behavior but are not a runtime telemetry API. |
| Plugin-bundled apps or MCP servers | Official Plugins and Build Plugins docs; local plugin manifest references `apps` and `mcpServers` | External services, tool calls, shared information, and plugin-owned helper services | Useful for data collection outside Codex. Can capture usage only for API calls the plugin/MCP server itself makes, not Codex's own hidden model calls. |
| Hooks | Official Hooks docs; repo `.codex/hooks.json` | Lifecycle JSON on stdin, including `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `model`, and turn-scoped `turn_id`; can add context or block/continue some events | Medium for approximate logging, poor for exact usage. Documented hook fields do not include token usage. Transcript parsing may be possible but is not a documented exact per-request usage surface. |
| Codex App Server / SDK client | Official Codex App Server docs | JSON-RPC thread/turn lifecycle, item events, and `thread/tokenUsage/updated` notifications | Best official Codex-adjacent fit. It exposes usage updates for active threads, but it is an app-server client surface, not a plugin surface, and the docs found do not fully specify payload shape or whether updates are per-turn versus thread aggregate. |

### External references

- Official OpenAI Codex Plugins docs: `https://developers.openai.com/codex/plugins` - plugins bundle skills, app integrations, and MCP servers; plugin permissions still follow approval settings and external service policies.
- Official OpenAI Build Plugins docs: `https://developers.openai.com/codex/plugins/build` - `$plugin-creator`, `.codex-plugin/plugin.json`, marketplace files, manifest fields, path rules, bundled MCP servers, and lifecycle config.
- Official OpenAI Agent Skills docs: `https://developers.openai.com/codex/skills` - skills package instructions/resources/scripts, use progressive disclosure, support `agents/openai.yaml`, and can declare MCP tool dependencies.
- Official OpenAI Hooks docs: `https://developers.openai.com/codex/hooks` - hooks run deterministic scripts during Codex lifecycle, require `[features] codex_hooks = true`, receive common JSON fields, and list current matcher/event limitations.
- Official OpenAI Codex App Server docs: `https://developers.openai.com/codex/app-server` - JSON-RPC event stream includes `turn/*`, `item/*`, and `thread/tokenUsage/updated` usage updates for the active thread.
- Official OpenAI Responses API reference: `https://platform.openai.com/docs/api-reference/responses/object` - API responses have a `usage` object with input tokens, cached input token details, output tokens, reasoning token details, and total tokens when you control the API call.
- Official OpenAI Usage API reference: `https://platform.openai.com/docs/api-reference/usage` - aggregate usage objects include fields such as input tokens, cached input tokens, output tokens, request counts, model, project, and API key grouping.
- Local plugin versions observed in installed cache paths: Browser Use `0.1.0-alpha1`; Documents/Presentations/Spreadsheets primary runtime `26.430.10722`.

### Common conventions

- Use a stable kebab-case plugin name; the plugin folder and manifest `name` should match.
- Keep `.codex-plugin/plugin.json` as the required manifest; keep `skills/`, `assets/`, `.mcp.json`, `.app.json`, and lifecycle config at the plugin root.
- Keep manifest paths relative to the plugin root and start them with `./`.
- Use `$REPO_ROOT/.agents/plugins/marketplace.json` for repo-scoped plugin catalogs and `~/.agents/plugins/marketplace.json` for personal catalogs.
- Include `policy.installation`, `policy.authentication`, and `category` in marketplace entries.
- Put reusable workflow instructions in `skills/<skill-name>/SKILL.md` with `name` and `description` front matter.
- Use `agents/openai.yaml` for skill display metadata, default prompt, implicit invocation policy, and MCP tool dependencies.
- Restart Codex after local plugin or marketplace changes so installed/cache state is refreshed.
- Treat apps, MCP servers, and hooks as separate data-access mechanisms inside the plugin package; do not assume they can read Codex internal model calls.

### Constraints for this repo

- This task is in `.trellis/tasks/05-05-codex-token-usage-tracker/` with status `planning`; research belongs under that task's `research/` directory.
- No repo-local `plugins/` directory or `.agents/plugins/marketplace.json` exists yet; a plugin MVP would require adding both.
- The repo already uses `.agents/skills/` for Trellis skills, so a local skill is lower-friction than a full plugin for early experimentation.
- `.codex/hooks.json` is currently dedicated to Trellis `SessionStart` and `UserPromptSubmit`; adding usage hooks would need careful coexistence and probably `PostToolUse` or `Stop` hook design.
- Hooks require a user-level feature flag in `~/.codex/config.toml`; this research did not read user-level config, `auth.json`, or secrets.
- Specs under `.trellis/spec/backend/` and `.trellis/spec/frontend/` are placeholders, so there are no project-specific implementation conventions beyond Trellis workflow and the PRD's security requirement.
- The PRD says exact per-request usage is preferred and sensitive auth data must not be read or printed; any approach based on parsing transcripts or local logs must redact and avoid auth/session secrets by design.

## Caveats / Not Found

- Not found: any official Codex plugin manifest, skill metadata, MCP dependency, or hook stdin field that grants per-request token usage for Codex's underlying model call.
- Not found: a documented hook event specifically fired after each model response with a `usage` object.
- Found but not sufficient: Codex App Server documents `thread/tokenUsage/updated`, but the docs excerpt found only says it provides usage updates for the active thread; it does not fully specify payload shape or per-request granularity.
- Official OpenAI API responses expose exact `usage` for API calls you make directly, but that does not imply a Codex plugin can observe usage for Codex's own internal model requests.
- This research intentionally did not read `~/.codex/auth.json`, secrets, API keys, or non-plugin local databases.
