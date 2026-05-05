# Research: Codex interactive UI capabilities for plugins

- Query: Can a third-party or local Codex plugin provide model-command-like arrow-key/tab interactions or tab switching inside Codex CLI or the Codex app?
- Scope: mixed
- Date: 2026-05-05

## Findings

### Bottom line

Current official Codex documentation supports plugins as bundles of skills, app/connector mappings, MCP servers, lifecycle hooks, and install-surface metadata. I found no documented plugin API for registering custom CLI slash commands, custom `/model`-style interactive pickers, arrow-key handlers, tabbed TUI panels, or custom in-Codex app views.

For the token usage plugin, the safest in-Codex surface is therefore:

- A skill invoked explicitly with `$codex-token-usage` or implicitly by description.
- Text output printed into the Codex conversation.
- Logical tabs selected by command arguments, for example `today`, `7-days`, `by-model`, rather than keyboard-driven in-place tab switching.
- Optional external output, such as an HTML file or a separate TUI process, only when explicitly requested.

### Files found

- `.trellis/workflow.md` - Trellis process requires research artifacts to persist under task `research/`; relevant as the artifact contract for this file.
- `.trellis/spec/backend/index.md` - Backend spec index exists but is still a template; no Codex plugin-specific implementation convention found.
- `.trellis/spec/frontend/index.md` - Frontend spec index exists but is still a template; no Codex plugin-specific UI convention found.
- `/Users/fengxudong/.codex/skills/.system/plugin-creator/references/plugin-json-spec.md` - Local plugin manifest reference listing supported fields.
- `plugins/codex-token-usage/.codex-plugin/plugin.json` - Current token usage plugin manifest.
- `plugins/codex-token-usage/skills/codex-token-usage/SKILL.md` - Current skill contract for text-panel invocation.
- `plugins/codex-token-usage/README.md` - Current user-facing plugin behavior and data-source description.
- `plugins/codex-token-usage/scripts/codex_usage_reporter.py` - Bundled reporter script; not fully inspected for UI capability because the research question is about Codex plugin surfaces rather than reporter internals.

### Official Codex docs

- Codex plugins overview: https://developers.openai.com/codex/plugins
  - Plugins are described as bundling skills, app integrations, and MCP servers into reusable Codex workflows.
  - The same page says plugins can contain skills, apps, and MCP servers, and notes that more capabilities are coming later.
  - The Codex CLI has an internal `/plugins` browser with marketplace tabs and install/enable controls. This is the plugin management UI, not a documented plugin-authored UI extension point.
  - Installed plugins are used by asking Codex directly or by typing `@` to invoke a plugin or one of its bundled skills.

- Build plugins: https://developers.openai.com/codex/plugins/build
  - A plugin is rooted by `.codex-plugin/plugin.json`.
  - The minimal manual plugin example packages a skill with `"skills": "./skills/"`.
  - Plugin structure includes `skills/`, optional `.app.json`, optional `.mcp.json`, optional lifecycle config, and assets.
  - The manifest points to bundled components and install-surface metadata. I found no `commands`, `views`, `panels`, `tabs`, `keybindings`, or equivalent UI-extension field.

- Codex CLI slash commands: https://developers.openai.com/codex/cli/slash-commands
  - Slash commands are documented as built-in controls for the interactive CLI.
  - The listed built-ins include `/plugins`, `/model`, `/status`, `/permissions`, `/agent`, and similar controls.
  - This page documents how to use built-ins, but I found no section for third-party custom slash command registration or plugin-authored slash-command UI.

- Codex app commands: https://developers.openai.com/codex/app/commands
  - The app command page documents app keyboard shortcuts, available slash commands, and deeplinks.
  - It states skills can be invoked with `$`, and enabled skills appear in the slash command list.
  - The available app slash commands shown are built-in app controls such as `/feedback`, `/mcp`, `/plan-mode`, `/review`, and `/status`; no custom app command or custom UI registration API was found.

- Codex skills: https://developers.openai.com/codex/skills
  - Skills package instructions, resources, and optional scripts.
  - Skills are available across CLI, IDE extension, and Codex app.
  - Explicit invocation is via `/skills` or `$` mention in CLI/IDE, and implicit invocation is based on the skill description.
  - This supports using `$codex-token-usage` as the stable plugin surface, but not keyboard-native tab switching inside the Codex UI.

- Codex hooks: https://developers.openai.com/codex/hooks
  - Hooks run deterministic scripts during lifecycle events and can be bundled by installed plugins.
  - Hooks can inject scripts into the agent loop, run validations, logging, prompt customization, and similar automation.
  - Hooks are lifecycle automation, not an interactive UI rendering API.

- Codex app-server: https://developers.openai.com/codex/app-server
  - App-server is a JSON-RPC protocol for embedding Codex into another product or rich client.
  - This could support a separate custom client that renders its own token usage UI, but it is not a plugin surface inside the stock Codex CLI/app.

### Code patterns

- Local plugin manifest only declares a skill and install-surface metadata:
  - `plugins/codex-token-usage/.codex-plugin/plugin.json:18` sets `"skills": "./skills/"`.
  - `plugins/codex-token-usage/.codex-plugin/plugin.json:19` starts the `interface` block.
  - `plugins/codex-token-usage/.codex-plugin/plugin.json:32` lists starter prompts.
  - No local `commands`, `tabs`, `views`, `panels`, `keybindings`, `apps`, `mcpServers`, or `hooks` field is present.

- Local plugin skill already models tabs as explicit views:
  - `plugins/codex-token-usage/skills/codex-token-usage/SKILL.md:12` says the default CLI panel prints inside the conversation and defaults to `Today`.
  - `plugins/codex-token-usage/skills/codex-token-usage/SKILL.md:18` says explicit views are passed by logical tab name.
  - `plugins/codex-token-usage/skills/codex-token-usage/SKILL.md:50` states the panel surface is a status-like text report printed in Codex CLI output.

- Local README documents the same non-interactive behavior:
  - `plugins/codex-token-usage/README.md:13` says the default invocation prints a status-like text panel with logical tab labels.
  - `plugins/codex-token-usage/README.md:15` says explicit views can be selected without a browser UI.
  - `plugins/codex-token-usage/README.md:28` makes HTML output optional only.

- Local plugin schema reference mirrors official docs:
  - `/Users/fengxudong/.codex/skills/.system/plugin-creator/references/plugin-json-spec.md:17` through `:20` list component pointers for `skills`, `hooks`, `mcpServers`, and `apps`.
  - `/Users/fengxudong/.codex/skills/.system/plugin-creator/references/plugin-json-spec.md:63` through `:67` define those top-level fields.
  - `/Users/fengxudong/.codex/skills/.system/plugin-creator/references/plugin-json-spec.md:69` through `:89` define `interface` as presentation metadata, not as runtime UI code.

### Practical design implication for `codex-token-usage`

Do not try to implement a `$codex-token-usage` flow that depends on arrow-key navigation, in-place tab state, or `/model`-style picker behavior inside Codex. The plugin should present a static text report and accept explicit view selectors.

Recommended command surface:

```bash
python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py today
python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py current-session
python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py 7-days
python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py by-model
python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py by-repo
python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py all
```

If richer interaction is required, use one of these non-plugin paths:

- External terminal TUI launched by the reporter, with its own lifecycle and clear opt-in behavior.
- Optional HTML report opened outside Codex.
- Separate product integration using `codex app-server`, if the goal is a custom rich client rather than a stock Codex plugin.

## Related specs

- `.trellis/workflow.md` - Research persistence rule and Phase 1.2 artifact conventions.
- `.trellis/spec/backend/index.md` - Template backend index; no relevant filled guideline found.
- `.trellis/spec/frontend/index.md` - Template frontend index; no relevant filled guideline found.

## Caveats / Not Found

- I found no official documentation for third-party/local plugins registering custom CLI slash commands.
- I found no official documentation for plugin-authored Codex CLI panels, keyboard event handlers, in-place tab switching, or interactive picker widgets.
- I found no official documentation for plugin-authored Codex app views beyond install-surface metadata, app/connector mappings, MCP, hooks, and skills.
- The absence above is based on the official docs and local schema/reference files available on 2026-05-05. Codex plugin capabilities are explicitly evolving, so this should be rechecked before investing in a custom interactive UI.
- I did not read sensitive Codex files such as `~/.codex/auth.json`, `~/.codex/history.jsonl`, or raw transcript/log bodies.
