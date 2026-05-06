# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

This project ships local CLI-style tooling inside plugins. Tooling must be usable from a fresh checkout without hidden user-specific setup, and failures must explain the missing prerequisite before the core reporter runs.

---

## Forbidden Patterns

- Do not document plugin entry points as direct interpreter invocations when the tool is intended to be distributed. A direct command such as `python3 plugins/<plugin>/scripts/tool.py` makes missing-runtime failures opaque and bypasses compatibility checks.

---

## Required Patterns

### Scenario: Plugin CLI Runtime Launcher

#### 1. Scope / Trigger
- Trigger: adding or changing a distributed plugin CLI entry point, especially one implemented in Python or another local interpreter runtime.
- Applies to commands exposed through plugin README files, skill instructions, and user-facing `$` workflows.

#### 2. Signatures
- POSIX launcher: `plugins/<plugin>/bin/<command> [reporter-args...]`
- Reporter diagnostics: `<command> doctor [--codex-home <path>] [--json]`
- Reporter summary: `<command> [current-session|today|7-days|month|all] [--group none|project|directory]`

#### 3. Contracts
- Environment:
  - `PYTHON` is optional and, when set, is the first runtime candidate.
  - The launcher must fall back to `python3`, then `python` when earlier candidates are missing or unusable.
  - A usable Python runtime must satisfy the reporter's minimum version and include the standard-library modules it needs, such as `sqlite3`.
- Output:
  - Runtime failures go to stderr with an actionable install or configuration hint.
  - `doctor --json` preserves machine-readable exact diagnostics.
  - Human summary output may round display costs, but JSON cost fields must retain exact fixed precision.
- Safety:
  - Diagnostics may inspect runtime version, `sqlite3` availability, Codex home existence, state database schema/counts, and session file names.
  - Diagnostics must not read auth files, history files, raw transcript bodies, prompts, responses, or event bodies.

#### 4. Validation & Error Matrix
- `PYTHON` points to a missing executable -> print a warning and continue to fallback candidates.
- Candidate runtime is Python below the minimum version -> print unsupported-version detail and continue.
- Candidate runtime lacks `sqlite3` -> print missing-module detail and continue.
- No candidate works -> exit non-zero with a final message listing the candidate order and how to set `PYTHON`.
- `doctor` finds missing Codex data sources -> exit non-zero after printing which data source is missing.

#### 5. Good/Base/Bad Cases
- Good: README and skill examples call `plugins/codex-token-usage/bin/codex-token-usage`.
- Base: developer-only verification may still call `python3 -m unittest` or `python3 -m mypy`.
- Bad: user-facing docs tell users to run `python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py` directly.

#### 6. Tests Required
- Unit test `doctor --json` with a temporary Codex home and assert no secret file contents are printed.
- Unit test missing Codex data sources and assert a non-zero doctor status plus actionable messages.
- Launcher test with `PYTHON` set to a valid interpreter and assert the command reaches the reporter.
- Launcher regression test with `PYTHON` set to a missing path and assert fallback still reaches `python3` or `python`.
- Shell syntax check for every POSIX launcher.

#### 7. Wrong vs Correct

##### Wrong
```bash
python3 plugins/codex-token-usage/scripts/codex_usage_reporter.py today
```

##### Correct
```bash
plugins/codex-token-usage/bin/codex-token-usage today
plugins/codex-token-usage/bin/codex-token-usage doctor
```

---

## Testing Requirements

- Public plugin commands need focused tests for parser behavior, output shape, runtime diagnostics, and launcher fallback. A shell launcher must have at least `sh -n` coverage plus one execution test when the host platform supports it.

---

## Code Review Checklist

<!-- What reviewers should check -->

(To be filled by the team)
