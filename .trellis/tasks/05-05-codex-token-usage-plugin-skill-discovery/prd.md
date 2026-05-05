# Fix Codex token usage plugin skill discovery

## Goal

Diagnose why the implemented Codex token usage plugin does not show its `$codex-token-usage` skill after a Codex restart, then make the minimal manifest or marketplace change needed for Codex to discover the skill.

## Requirements

* Inspect the existing plugin marketplace entry, plugin manifest, skill metadata, and installed Codex plugin cache conventions.
* Compare local paths including `.agents/plugins/marketplace.json`, `plugins/codex-token-usage/.codex-plugin/plugin.json`, `plugins/codex-token-usage/skills/codex-token-usage/SKILL.md`, and `plugins/codex-token-usage/skills/codex-token-usage/agents/openai.yaml`.
* Do not read secrets such as `~/.codex/auth.json`.
* Preserve other people's uncommitted work and avoid destructive git operations.
* Make the minimal change needed for Codex to discover the skill after restart.
* Run manifest/JSON validation and available tests.

## Acceptance Criteria

* [x] The plugin discovery issue is explained with evidence from the repo and local Codex cache conventions.
* [x] The minimal fix is applied to the relevant marketplace or manifest file.
* [x] JSON manifests validate successfully.
* [x] Existing reporter tests pass.
* [x] Changed files and verification commands are listed.

## Definition of Done

* All edited files are directly related to plugin discovery or Trellis task bookkeeping.
* No secrets are read.
* Tests/checks run are reported, including any limitations.

## Technical Approach

Compare the repo-local marketplace and plugin manifest against the local `plugin-creator` schema reference and installed plugin cache examples. If the manifest and skill path are structurally valid, prefer changing marketplace installation policy over duplicating skill files or reshaping the plugin package.

## Decision (ADR-lite)

**Context**: The plugin package exists, but the skill is absent from the available skills after restart.

**Decision**: Treat repo marketplace installation policy and plugin cache conventions as the primary discovery surface to diagnose first.

**Consequences**: The fix should stay small and avoid changing the reporter or skill workflow unless the manifest/path comparison proves those files are malformed.

## Out of Scope

* Changing token usage parsing, aggregation, panel rendering, or privacy policy behavior.
* Reading `~/.codex/auth.json`, raw prompt logs, or unrelated Codex history files.
* Installing third-party packages.

## Technical Notes

* Existing adjacent task: `.trellis/tasks/05-05-codex-token-usage-tracker/`.
* Prior research: `.trellis/tasks/05-05-codex-token-usage-tracker/research/codex-plugin-usage-surfaces.md`.
* Local cache examples inspected under `~/.codex/plugins/cache/` only; no auth or secret files are needed for this diagnosis.
* Diagnosis: the plugin package shape matches installed cache examples (`.codex-plugin/plugin.json`, `skills/<name>/SKILL.md`, and `agents/openai.yaml`). The repo marketplace entry was marked `AVAILABLE`, which makes the plugin installable but does not make the skill visible by default after restart.
* Fix: set `.agents/plugins/marketplace.json` policy `installation` to `INSTALLED_BY_DEFAULT` for `codex-token-usage`.
