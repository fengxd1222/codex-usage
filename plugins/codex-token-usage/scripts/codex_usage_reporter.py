#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Iterator, Sequence
from urllib.parse import quote

if TYPE_CHECKING:
    import sqlite3
else:
    try:
        import sqlite3
    except ImportError:
        sqlite3 = None


USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)

DEFAULT_TAB = "today"

TAB_CHOICES = ("current-session", "today", "7-days", "month", "all")

TAB_LABELS = {
    "current-session": "Current Session",
    "today": "Today",
    "7-days": "7 Days",
    "month": "Month",
    "all": "All",
}

TAB_ALIASES = {
    "current": "current-session",
    "session": "current-session",
    "7d": "7-days",
    "seven-days": "7-days",
    "week": "7-days",
    "monthly": "month",
    "this-month": "month",
    "all-time": "all",
}

TAB_ARGUMENT_CHOICES = tuple(dict.fromkeys((*TAB_CHOICES, *TAB_ALIASES.keys())))

GROUP_CHOICES = ("none", "project", "directory")
GROUP_ALIASES = {
    "repo": "project",
    "repos": "project",
    "cwd": "directory",
    "dir": "directory",
    "path": "directory",
}
GROUP_ARGUMENT_CHOICES = tuple(dict.fromkeys((*GROUP_CHOICES, *GROUP_ALIASES.keys())))

CURRENT_SESSION_ID_ENV_VARS = (
    "CODEX_SESSION_ID",
    "CODEX_THREAD_ID",
    "OPENAI_CODEX_SESSION_ID",
)

CURRENT_SESSION_PATH_ENV_VARS = (
    "CODEX_ROLLOUT_PATH",
    "CODEX_TRANSCRIPT_PATH",
    "OPENAI_CODEX_TRANSCRIPT_PATH",
)

COMMAND_CHOICES = ("summary", "doctor", "html-panel", "panel")
OPTIONS_WITH_VALUES = (
    "--codex-home",
    "--group",
    "--session-id",
    "--session-rollout-path",
)
NO_CURRENT_SESSION_GUESSING_NOTE = (
    "not guessing from history, transcript text, raw logs, prompts, or responses."
)

USAGE_KEY_NEEDLE = '"total_token_usage"'
TIMESTAMP_KEY_NEEDLE = '"timestamp"'
PRICING_SNAPSHOT_DATE = "2026-05-05"
PRICING_NOTE = (
    "API-equivalent estimate from explicit OpenAI API per-1M token rates; "
    "reasoning output tokens are display-only, not an extra charged bucket; "
    f"pricing snapshot {PRICING_SNAPSHOT_DATE}."
)
MIN_PYTHON_VERSION = (3, 10)


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_output_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_mapping(cls, value: object) -> "TokenUsage":
        if not isinstance(value, dict):
            return cls()
        return cls(**{field: safe_int(value.get(field)) for field in USAGE_FIELDS})

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_output_tokens=self.reasoning_output_tokens + other.reasoning_output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    def is_zero(self) -> bool:
        return all(getattr(self, field) == 0 for field in USAGE_FIELDS)

    def comparison_value(self) -> int:
        if self.total_tokens > 0:
            return self.total_tokens
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.output_tokens
            + self.reasoning_output_tokens
        )

    def to_dict(self) -> dict[str, int]:
        return {field: getattr(self, field) for field in USAGE_FIELDS}


@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_per_1m: Decimal
    cached_input_per_1m: Decimal | None
    output_per_1m: Decimal
    source: str


@dataclass(frozen=True)
class CostEstimate:
    uncached_input_cost: Decimal
    cached_input_cost: Decimal
    output_cost: Decimal
    total_cost: Decimal
    currency: str = "USD"

    def to_dict(self) -> dict[str, str]:
        return {
            "currency": self.currency,
            "uncached_input_cost": format_money_decimal(self.uncached_input_cost),
            "cached_input_cost": format_money_decimal(self.cached_input_cost),
            "output_cost": format_money_decimal(self.output_cost),
            "total_cost": format_money_decimal(self.total_cost),
        }


@dataclass(frozen=True)
class CostResult:
    estimate: CostEstimate | None
    warnings: tuple[str, ...]


MODEL_PRICING: dict[str, ModelPricing] = {
    "gpt-5.5": ModelPricing(
        model="gpt-5.5",
        input_per_1m=Decimal("5.00"),
        cached_input_per_1m=Decimal("0.50"),
        output_per_1m=Decimal("30.00"),
        source="OpenAI API pricing, Standard short-context",
    ),
    "gpt-5.5-pro": ModelPricing(
        model="gpt-5.5-pro",
        input_per_1m=Decimal("30.00"),
        cached_input_per_1m=None,
        output_per_1m=Decimal("180.00"),
        source="OpenAI API pricing, Standard short-context",
    ),
    "gpt-5.4": ModelPricing(
        model="gpt-5.4",
        input_per_1m=Decimal("2.50"),
        cached_input_per_1m=Decimal("0.25"),
        output_per_1m=Decimal("15.00"),
        source="OpenAI API pricing, Standard short-context",
    ),
    "gpt-5.4-mini": ModelPricing(
        model="gpt-5.4-mini",
        input_per_1m=Decimal("0.75"),
        cached_input_per_1m=Decimal("0.075"),
        output_per_1m=Decimal("4.50"),
        source="OpenAI API pricing, Standard short-context",
    ),
    "gpt-5.4-nano": ModelPricing(
        model="gpt-5.4-nano",
        input_per_1m=Decimal("0.20"),
        cached_input_per_1m=Decimal("0.02"),
        output_per_1m=Decimal("1.25"),
        source="OpenAI API pricing, Standard short-context",
    ),
    "gpt-5.4-pro": ModelPricing(
        model="gpt-5.4-pro",
        input_per_1m=Decimal("30.00"),
        cached_input_per_1m=None,
        output_per_1m=Decimal("180.00"),
        source="OpenAI API pricing, Standard short-context",
    ),
    "gpt-5.3-codex": ModelPricing(
        model="gpt-5.3-codex",
        input_per_1m=Decimal("1.75"),
        cached_input_per_1m=Decimal("0.175"),
        output_per_1m=Decimal("14.00"),
        source="OpenAI API pricing, specialized Codex rate",
    ),
    "gpt-5.3-chat-latest": ModelPricing(
        model="gpt-5.3-chat-latest",
        input_per_1m=Decimal("1.75"),
        cached_input_per_1m=Decimal("0.175"),
        output_per_1m=Decimal("14.00"),
        source="OpenAI API pricing, specialized ChatGPT model rate",
    ),
}


@dataclass(frozen=True)
class ThreadRecord:
    thread_id: str
    rollout_path: Path
    created_at: datetime | None
    updated_at: datetime | None
    model_provider: str
    model: str
    reasoning_effort: str
    cwd: str
    tokens_used: int


@dataclass(frozen=True)
class ParsedUsage:
    usage: TokenUsage
    usage_at: datetime | None
    usage_events: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SessionUsage:
    thread: ThreadRecord
    source_path: Path
    usage: TokenUsage
    usage_at: datetime | None
    usage_events: int
    warnings: tuple[str, ...]

    def effective_time(self) -> datetime | None:
        return self.usage_at or self.thread.updated_at or self.thread.created_at

    def model_label(self) -> str:
        if self.thread.model:
            return self.thread.model
        if self.thread.model_provider:
            return self.thread.model_provider
        return "unknown"

    def repo_label(self) -> str:
        return self.project_label()

    def project_label(self) -> str:
        if not self.thread.cwd:
            return "unknown"
        name = Path(self.thread.cwd).name
        return name or self.thread.cwd

    def directory_label(self) -> str:
        if not self.thread.cwd:
            return "unknown"
        return str(Path(self.thread.cwd).expanduser())


@dataclass(frozen=True)
class UsageReport:
    codex_home: Path
    generated_at: datetime
    sessions: tuple[SessionUsage, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True)
class DoctorReport:
    codex_home: Path
    checks: tuple[DoctorCheck, ...]

    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok(),
            "codex_home": str(self.codex_home),
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class AggregateRow:
    label: str
    sessions: int
    usage: TokenUsage
    cost: CostResult


@dataclass(frozen=True)
class CurrentSessionContext:
    session_id: str | None = None
    rollout_path: Path | None = None


@dataclass(frozen=True)
class CurrentSessionResolution:
    session: SessionUsage | None
    message: str


def safe_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return 0
    else:
        return 0
    return parsed if parsed > 0 else 0


def canonical_tab(value: str) -> str:
    return TAB_ALIASES.get(value, value)


def canonical_group(value: str | None) -> str:
    if value is None:
        return "none"
    return GROUP_ALIASES.get(value, value)


def default_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_epoch_ms(value: object) -> datetime | None:
    millis = safe_int(value)
    if millis == 0:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)


def sqlite_readonly_uri(path: Path) -> str:
    return f"file:{quote(str(path.resolve()))}?mode=ro"


def load_thread_index(codex_home: Path) -> tuple[list[ThreadRecord], list[str]]:
    db_path = codex_home / "state_5.sqlite"
    warnings: list[str] = []
    if sqlite3 is None:
        return [], ["Python sqlite3 module is unavailable."]
    if not db_path.exists():
        return [], [f"Missing Codex state database: {db_path}"]

    try:
        connection = sqlite3.connect(sqlite_readonly_uri(db_path), uri=True)
    except sqlite3.Error as exc:
        return [], [f"Could not open Codex state database read-only: {exc}"]

    try:
        with connection:
            connection.row_factory = sqlite3.Row
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'threads'"
            ).fetchone()
            if table is None:
                return [], ["Codex state database has no threads table."]

            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(threads)").fetchall()
            }
            if "rollout_path" not in columns:
                return [], ["Codex threads table has no rollout_path column."]

            selected = [
                column_or_null(columns, "id", "thread_id"),
                column_or_null(columns, "rollout_path", "rollout_path"),
                column_or_null(columns, "created_at_ms", "created_at_ms"),
                column_or_null(columns, "updated_at_ms", "updated_at_ms"),
                column_or_null(columns, "model_provider", "model_provider"),
                column_or_null(columns, "model", "model"),
                column_or_null(columns, "reasoning_effort", "reasoning_effort"),
                column_or_null(columns, "cwd", "cwd"),
                column_or_null(columns, "tokens_used", "tokens_used"),
            ]
            query = (
                f"SELECT {', '.join(selected)} FROM threads "
                "WHERE rollout_path IS NOT NULL AND rollout_path != ''"
            )
            rows = connection.execute(query).fetchall()
    except sqlite3.Error as exc:
        return [], [f"Could not query Codex threads table: {exc}"]
    finally:
        connection.close()

    records: list[ThreadRecord] = []
    for row in rows:
        rollout_path = normalize_rollout_path(codex_home, str(row["rollout_path"] or ""))
        if rollout_path is None:
            warnings.append("Skipped a thread with an invalid rollout_path.")
            continue
        records.append(
            ThreadRecord(
                thread_id=str(row["thread_id"] or ""),
                rollout_path=rollout_path,
                created_at=parse_epoch_ms(row["created_at_ms"]),
                updated_at=parse_epoch_ms(row["updated_at_ms"]),
                model_provider=str(row["model_provider"] or ""),
                model=str(row["model"] or ""),
                reasoning_effort=str(row["reasoning_effort"] or ""),
                cwd=str(row["cwd"] or ""),
                tokens_used=safe_int(row["tokens_used"]),
            )
        )
    return records, warnings


def column_or_null(columns: set[str], column: str, alias: str) -> str:
    if column in columns:
        return f"{column} AS {alias}"
    return f"NULL AS {alias}"


def normalize_rollout_path(codex_home: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = codex_home / path
    return path.resolve(strict=False)


def path_is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def allowed_session_path(codex_home: Path, path: Path) -> bool:
    sessions_root = (codex_home / "sessions").resolve(strict=False)
    resolved = path.resolve(strict=False)
    return resolved.suffix == ".jsonl" and path_is_relative_to(resolved, sessions_root)


def extract_usage_from_session_file(path: Path) -> ParsedUsage:
    best_usage = TokenUsage()
    best_time: datetime | None = None
    usage_events = 0
    warnings: list[str] = []
    path_label = session_file_label(path)

    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if USAGE_KEY_NEEDLE not in line:
                    continue
                timestamp = extract_line_timestamp(line)
                found_object = False
                for object_text in iter_whitelisted_usage_objects(line):
                    found_object = True
                    try:
                        usage = TokenUsage.from_mapping(json.loads(object_text))
                    except json.JSONDecodeError:
                        warnings.append(
                            f"Skipped malformed usage metadata in {path_label}:{line_number}."
                        )
                        continue
                    if usage.is_zero():
                        continue
                    usage_events += 1
                    if usage_is_better(usage, timestamp, best_usage, best_time):
                        best_usage = usage
                        best_time = timestamp
                if not found_object:
                    warnings.append(
                        "Skipped usage-like metadata outside the whitelisted "
                        f"payload.info.total_token_usage path in {path_label}:{line_number}."
                    )
    except FileNotFoundError:
        warnings.append(f"Missing session file: {path_label}")
    except OSError as exc:
        warnings.append(f"Could not read session file {path_label}: {exc}")

    return ParsedUsage(
        usage=best_usage,
        usage_at=best_time,
        usage_events=usage_events,
        warnings=tuple(warnings),
    )


def session_file_label(path: Path) -> str:
    return path.name or "(unnamed session file)"


def extract_line_timestamp(line: str) -> datetime | None:
    if TIMESTAMP_KEY_NEEDLE not in line:
        return None
    root_start = line.find("{")
    if root_start == -1:
        return None
    root_end = find_json_object_end(line, root_start)
    if root_end is None:
        return None
    for value_start, value_end in iter_direct_string_values_for_key(
        line, "timestamp", root_start, root_end
    ):
        return parse_timestamp(json_unescape_string(line[value_start:value_end]))
    return None


def iter_whitelisted_usage_objects(line: str) -> Iterator[str]:
    root_start = line.find("{")
    if root_start == -1:
        return
    root_end = find_json_object_end(line, root_start)
    if root_end is None:
        return
    for payload_start, payload_end in iter_direct_object_values_for_key(
        line, "payload", root_start, root_end
    ):
        for info_start, info_end in iter_direct_object_values_for_key(
            line, "info", payload_start, payload_end
        ):
            for usage_start, usage_end in iter_direct_object_values_for_key(
                line, "total_token_usage", info_start, info_end
            ):
                yield line[usage_start:usage_end]


def iter_direct_object_values_for_key(
    text: str,
    key: str,
    start: int,
    end: int,
) -> Iterator[tuple[int, int]]:
    for value_start, value_end in iter_direct_values_for_key(text, key, start, end):
        if text[value_start:value_start + 1] == "{":
            yield value_start, value_end


def iter_direct_string_values_for_key(
    text: str,
    key: str,
    start: int,
    end: int,
) -> Iterator[tuple[int, int]]:
    for value_start, value_end in iter_direct_values_for_key(text, key, start, end):
        if text[value_start:value_start + 1] == '"':
            yield value_start, value_end


def iter_direct_values_for_key(
    text: str,
    key: str,
    start: int,
    end: int,
) -> Iterator[tuple[int, int]]:
    key_literal = json.dumps(key)
    depth = 0
    index = start
    while index < end:
        char = text[index]
        if char == '"':
            string_end = find_json_string_end(text, index, end)
            if string_end is None:
                return
            if depth == 1 and text[index:string_end] == key_literal:
                colon = next_non_whitespace(text, string_end, end)
                if colon is not None and text[colon:colon + 1] == ":":
                    value_start = next_non_whitespace(text, colon + 1, end)
                    if value_start is not None:
                        value_end = find_json_value_end(text, value_start, end)
                        if value_end is not None:
                            yield value_start, value_end
            index = string_end
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth <= 0 and index > start:
                return
        index += 1


def find_json_value_end(text: str, start: int, end: int) -> int | None:
    if start >= end:
        return None
    if text[start] == "{":
        object_end = find_json_object_end(text, start)
        if object_end is None or object_end > end:
            return None
        return object_end
    if text[start] == '"':
        return find_json_string_end(text, start, end)
    index = start
    while index < end and text[index] not in ",}":
        index += 1
    return index


def find_json_string_end(text: str, start: int, end: int) -> int | None:
    escaped = False
    for index in range(start + 1, end):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return index + 1
    return None


def next_non_whitespace(text: str, start: int, end: int) -> int | None:
    for index in range(start, end):
        if not text[index].isspace():
            return index
    return None


def json_unescape_string(value: str) -> str | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, str) else None


def find_json_object_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def usage_is_better(
    candidate: TokenUsage,
    candidate_time: datetime | None,
    current: TokenUsage,
    current_time: datetime | None,
) -> bool:
    candidate_value = candidate.comparison_value()
    current_value = current.comparison_value()
    if candidate_value != current_value:
        return candidate_value > current_value
    if candidate_time is None:
        return False
    if current_time is None:
        return True
    return candidate_time > current_time


def build_usage_report(
    codex_home: Path | None = None,
    now: datetime | None = None,
) -> UsageReport:
    home = (codex_home or default_codex_home()).expanduser().resolve(strict=False)
    generated_at = now or datetime.now().astimezone()
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)

    threads, warnings = load_thread_index(home)
    sessions: list[SessionUsage] = []
    seen_paths: set[Path] = set()
    for thread in threads:
        if not allowed_session_path(home, thread.rollout_path):
            path_name = thread.rollout_path.name or "(unnamed)"
            warnings.append(f"Skipped rollout path outside ~/.codex/sessions: {path_name}")
            continue
        if thread.rollout_path in seen_paths:
            warnings.append(f"Skipped duplicate rollout path: {thread.rollout_path.name}")
            continue
        seen_paths.add(thread.rollout_path)

        parsed = extract_usage_from_session_file(thread.rollout_path)
        usage = parsed.usage
        parsed_warnings = list(parsed.warnings)
        if usage.is_zero() and thread.tokens_used > 0:
            usage = TokenUsage(total_tokens=thread.tokens_used)
            parsed_warnings.append(
                f"Used total-only SQLite fallback for {thread.rollout_path.name}."
            )
        sessions.append(
            SessionUsage(
                thread=thread,
                source_path=thread.rollout_path,
                usage=usage,
                usage_at=parsed.usage_at,
                usage_events=parsed.usage_events,
                warnings=tuple(parsed_warnings),
            )
        )

    all_warnings = list(warnings)
    for session in sessions:
        all_warnings.extend(session.warnings)

    return UsageReport(
        codex_home=home,
        generated_at=generated_at,
        sessions=tuple(sessions),
        warnings=tuple(all_warnings),
    )


def filter_sessions_for_tab(report: UsageReport, tab: str) -> tuple[SessionUsage, ...]:
    tab = canonical_tab(tab)
    if tab == "all":
        return report.sessions
    today = report.generated_at.astimezone().date()
    if tab == "today":
        start = today
        end = today
    elif tab == "7-days":
        start = today - timedelta(days=6)
        end = today
    elif tab == "month":
        start = today.replace(day=1)
        end = today
    else:
        return report.sessions
    filtered: list[SessionUsage] = []
    for session in report.sessions:
        effective = session.effective_time()
        if effective is None:
            continue
        session_date = effective.astimezone().date()
        if start <= session_date <= end:
            filtered.append(session)
    return tuple(filtered)


def aggregate_usage(sessions: Iterable[SessionUsage]) -> TokenUsage:
    total = TokenUsage()
    for session in sessions:
        total = total.add(session.usage)
    return total


def sessions_cost(sessions: Iterable[SessionUsage]) -> CostResult:
    total = CostEstimate(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
    warnings: list[str] = []
    any_cost = False
    for session in sessions:
        result = cost_for_session(session)
        warnings.extend(result.warnings)
        if result.estimate is None:
            continue
        any_cost = True
        total = CostEstimate(
            uncached_input_cost=total.uncached_input_cost + result.estimate.uncached_input_cost,
            cached_input_cost=total.cached_input_cost + result.estimate.cached_input_cost,
            output_cost=total.output_cost + result.estimate.output_cost,
            total_cost=total.total_cost + result.estimate.total_cost,
        )
    return CostResult(estimate=total if any_cost else None, warnings=tuple(warnings))


def cost_for_session(session: SessionUsage) -> CostResult:
    model = session.model_label().strip().lower()
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return CostResult(
            estimate=None,
            warnings=(
                f"Cost unavailable for model '{session.model_label()}': no explicit official pricing mapping.",
            ),
        )
    usage = session.usage
    cached_tokens = min(usage.cached_input_tokens, usage.input_tokens)
    if cached_tokens > 0 and pricing.cached_input_per_1m is None:
        return CostResult(
            estimate=None,
            warnings=(
                f"Cost unavailable for model '{pricing.model}': official cached-input rate is not listed.",
            ),
        )
    cached_rate = pricing.cached_input_per_1m or pricing.input_per_1m
    uncached_input_tokens = max(usage.input_tokens - cached_tokens, 0)
    uncached_input_cost = token_cost(uncached_input_tokens, pricing.input_per_1m)
    cached_input_cost = token_cost(cached_tokens, cached_rate)
    output_cost = token_cost(usage.output_tokens, pricing.output_per_1m)
    total = uncached_input_cost + cached_input_cost + output_cost
    return CostResult(
        estimate=CostEstimate(
            uncached_input_cost=uncached_input_cost,
            cached_input_cost=cached_input_cost,
            output_cost=output_cost,
            total_cost=total,
        ),
        warnings=(),
    )


def token_cost(tokens: int, rate_per_1m: Decimal) -> Decimal:
    return (Decimal(tokens) * rate_per_1m) / Decimal("1000000")


def aggregate_by(
    sessions: Iterable[SessionUsage],
    labeler: Callable[[SessionUsage], str],
) -> tuple[AggregateRow, ...]:
    totals: dict[str, TokenUsage] = {}
    counts: dict[str, int] = {}
    grouped_sessions: dict[str, list[SessionUsage]] = {}
    for session in sessions:
        label = str(labeler(session) or "unknown")
        totals[label] = totals.get(label, TokenUsage()).add(session.usage)
        counts[label] = counts.get(label, 0) + 1
        grouped_sessions.setdefault(label, []).append(session)
    rows = [
        AggregateRow(
            label=label,
            sessions=counts[label],
            usage=usage,
            cost=sessions_cost(grouped_sessions[label]),
        )
        for label, usage in totals.items()
    ]
    rows.sort(key=lambda row: (-row.usage.total_tokens, row.label.lower()))
    return tuple(rows)


def group_labeler(group: str) -> Callable[[SessionUsage], str]:
    group = canonical_group(group)
    if group == "project":
        return lambda item: item.project_label()
    if group == "directory":
        return lambda item: item.directory_label()
    raise ValueError(f"Unknown group: {group}")


def render_tab_bar(active_tab: str) -> str:
    active_tab = canonical_tab(active_tab)
    labels = [
        f"[{label}]" if tab == active_tab else label
        for tab, label in TAB_LABELS.items()
    ]
    return "Tabs: " + " | ".join(labels)


def resolve_current_session(
    report: UsageReport,
    context: CurrentSessionContext | None,
) -> CurrentSessionResolution:
    context = context or CurrentSessionContext()
    id_match = find_session_by_thread_id(report.sessions, context.session_id)
    path_match: SessionUsage | None = None

    if context.rollout_path is not None:
        rollout_path = normalize_rollout_path(report.codex_home, str(context.rollout_path))
        if rollout_path is None:
            return CurrentSessionResolution(
                None,
                f"Current session is unavailable: provided rollout path is invalid; {NO_CURRENT_SESSION_GUESSING_NOTE}",
            )
        if not allowed_session_path(report.codex_home, rollout_path):
            return CurrentSessionResolution(
                None,
                "Current session is unavailable: provided rollout path is outside ~/.codex/sessions; "
                f"{NO_CURRENT_SESSION_GUESSING_NOTE}",
            )
        path_match = find_session_by_rollout_path(report.sessions, rollout_path)

    if id_match is not None and path_match is not None and id_match.source_path != path_match.source_path:
        return CurrentSessionResolution(
            None,
            "Current session is unavailable: provided session id and rollout path map to different threads; "
            f"{NO_CURRENT_SESSION_GUESSING_NOTE}",
        )
    if id_match is not None:
        return CurrentSessionResolution(id_match, "Current session mapped by exact thread id.")
    if path_match is not None:
        return CurrentSessionResolution(path_match, "Current session mapped by exact rollout path.")
    if context.session_id or context.rollout_path is not None:
        return CurrentSessionResolution(
            None,
            "Current session is unavailable: provided session identity did not match state_5.sqlite threads; "
            f"{NO_CURRENT_SESSION_GUESSING_NOTE}",
        )
    return CurrentSessionResolution(
        None,
        "Current session is unavailable: no supported Codex session id or rollout path was provided; "
        f"{NO_CURRENT_SESSION_GUESSING_NOTE}",
    )


def find_session_by_thread_id(
    sessions: Sequence[SessionUsage],
    thread_id: str | None,
) -> SessionUsage | None:
    if not thread_id:
        return None
    for session in sessions:
        if session.thread.thread_id == thread_id:
            return session
    return None


def find_session_by_rollout_path(
    sessions: Sequence[SessionUsage],
    rollout_path: Path,
) -> SessionUsage | None:
    resolved = rollout_path.resolve(strict=False)
    for session in sessions:
        if session.source_path.resolve(strict=False) == resolved:
            return session
    return None


def format_int(value: int) -> str:
    return f"{value:,}"


def render_text_report(
    report: UsageReport,
    tab: str = DEFAULT_TAB,
    group: str = "none",
    current_session_context: CurrentSessionContext | None = None,
) -> str:
    tab = canonical_tab(tab)
    group = canonical_group(group)
    if tab not in TAB_CHOICES:
        raise ValueError(f"Unknown tab: {tab}")
    if group not in GROUP_CHOICES:
        raise ValueError(f"Unknown group: {group}")
    if tab == "current-session" and group != "none":
        raise ValueError("Current Session does not support grouping.")

    lines = [
        "Codex Token Usage",
        f"Generated: {report.generated_at.isoformat(timespec='seconds')}",
        render_tab_bar(tab),
        "",
        f"Active view: {TAB_LABELS[tab]}",
    ]

    if tab == "current-session":
        lines.extend(render_current_session_block(report, current_session_context))
    else:
        sessions = filter_sessions_for_tab(report, tab)
        if group == "none":
            total = aggregate_usage(sessions)
            cost = sessions_cost(sessions)
            lines.extend(render_usage_block(len(sessions), total, cost))
        else:
            lines.append(f"Grouped by: {group}")
            lines.extend(render_aggregate_table(aggregate_by(sessions, group_labeler(group))))

    lines.extend(
        [
            "",
            f"Cost: {PRICING_NOTE}",
            "Source: ~/.codex/state_5.sqlite threads.rollout_path + whitelisted payload.info.total_token_usage metadata.",
            "Privacy: auth.json, history.jsonl, raw log bodies, prompts, responses, and event bodies are not read or printed.",
        ]
    )
    cost_warnings = cost_warnings_for_text_report(report, tab, group, current_session_context)
    warnings = (*report.warnings, *cost_warnings)
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in warnings[:8]:
            lines.append(f"- {warning}")
        if len(warnings) > 8:
            lines.append(f"- {len(warnings) - 8} more warning(s).")
    return "\n".join(lines)


def render_current_session_block(
    report: UsageReport,
    context: CurrentSessionContext | None,
) -> list[str]:
    resolution = resolve_current_session(report, context)
    if resolution.session is None:
        return [
            "Status: unavailable",
            resolution.message,
        ]
    return [
        f"Status: available ({resolution.session.model_label()})",
        *render_usage_block(1, resolution.session.usage, cost_for_session(resolution.session)),
    ]


def render_usage_block(
    session_count: int,
    usage: TokenUsage,
    cost: CostResult | None = None,
) -> list[str]:
    plural = "session" if session_count == 1 else "sessions"
    lines = [
        f"Status: {format_int(session_count)} {plural} in view",
        f"Sessions: {format_int(session_count)}",
        "",
        "Exact totals:",
        f"- Input tokens: {format_int(usage.input_tokens)}",
        f"- Cached input tokens: {format_int(usage.cached_input_tokens)}",
        f"- Output tokens: {format_int(usage.output_tokens)}",
        f"- Reasoning output tokens: {format_int(usage.reasoning_output_tokens)}",
        f"- Total tokens: {format_int(usage.total_tokens)}",
        "",
        "Derived:",
        f"- Cache rate: {format_percent(cache_rate(usage))}",
        f"- Average tokens/session: {format_average_tokens(usage.total_tokens, session_count)}",
    ]
    lines.extend(render_cost_block(cost))
    return lines


def render_cost_block(cost: CostResult | None) -> list[str]:
    if cost is None:
        return ["- Estimated cost: unavailable"]
    if cost.estimate is None:
        return ["- Estimated cost: unavailable"]
    estimate = cost.estimate
    return [
        f"- Estimated cost: {format_money(estimate.total_cost)} {estimate.currency}",
        (
            "- Cost breakdown: "
            f"uncached input {format_money(estimate.uncached_input_cost)}, "
            f"cached input {format_money(estimate.cached_input_cost)}, "
            f"output {format_money(estimate.output_cost)}"
        ),
    ]


def render_aggregate_table(rows: Sequence[AggregateRow]) -> list[str]:
    headers = [
        "Name",
        "Sessions",
        "Input",
        "Cached",
        "Output",
        "Reasoning",
        "Total",
        "Cost",
    ]
    values = [
        [
            row.label,
            format_int(row.sessions),
            format_int(row.usage.input_tokens),
            format_int(row.usage.cached_input_tokens),
            format_int(row.usage.output_tokens),
            format_int(row.usage.reasoning_output_tokens),
            format_int(row.usage.total_tokens),
            format_cost_cell(row.cost),
        ]
        for row in rows
    ]
    if not values:
        values = [["(none)", "0", "0", "0", "0", "0", "0", "unavailable"]]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in values))
        for index in range(len(headers))
    ]
    table = [
        "  ".join(headers[index].ljust(widths[index]) for index in range(len(headers))),
        "  ".join("-" * widths[index] for index in range(len(headers))),
    ]
    for row in values:
        table.append(
            "  ".join(
                row[index].rjust(widths[index]) if index > 0 else row[index].ljust(widths[index])
                for index in range(len(headers))
            )
        )
    return table


def format_money_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.000001'))}"


def format_money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01'))}"


def format_percent(value: Decimal | None) -> str:
    if value is None:
        return "unavailable"
    return f"{value.quantize(Decimal('0.01'))}%"


def format_average_tokens(total_tokens: int, session_count: int) -> str:
    if session_count <= 0:
        return "unavailable"
    average = Decimal(total_tokens) / Decimal(session_count)
    return f"{average.quantize(Decimal('0.01'))}"


def cache_rate(usage: TokenUsage) -> Decimal | None:
    if usage.input_tokens <= 0:
        return None
    cached_tokens = min(usage.cached_input_tokens, usage.input_tokens)
    return (Decimal(cached_tokens) * Decimal("100")) / Decimal(usage.input_tokens)


def format_cost_cell(cost: CostResult) -> str:
    if cost.estimate is None:
        return "unavailable"
    return format_money(cost.estimate.total_cost)


def cost_result_to_json(cost: CostResult) -> dict[str, object]:
    return {
        "available": cost.estimate is not None,
        "estimate": cost.estimate.to_dict() if cost.estimate is not None else None,
        "warnings": list(cost.warnings),
    }


def cost_warnings_for_text_report(
    report: UsageReport,
    tab: str,
    group: str,
    current_session_context: CurrentSessionContext | None,
) -> tuple[str, ...]:
    tab = canonical_tab(tab)
    group = canonical_group(group)
    if tab == "current-session":
        resolution = resolve_current_session(report, current_session_context)
        if resolution.session is None:
            return ()
        return cost_for_session(resolution.session).warnings
    sessions = filter_sessions_for_tab(report, tab)
    if group == "none":
        return sessions_cost(sessions).warnings
    warnings: list[str] = []
    for row in aggregate_by(sessions, group_labeler(group)):
        warnings.extend(row.cost.warnings)
    return tuple(warnings)


def report_to_json(
    report: UsageReport,
    tab: str,
    group: str = "none",
    current_session_context: CurrentSessionContext | None = None,
) -> dict[str, object]:
    tab = canonical_tab(tab)
    group = canonical_group(group)
    if tab == "current-session":
        resolution = resolve_current_session(report, current_session_context)
        cost = (
            cost_for_session(resolution.session)
            if resolution.session is not None
            else CostResult(None, ())
        )
        return {
            "tab": tab,
            "group": "none",
            "generated_at": report.generated_at.isoformat(),
            "available": resolution.session is not None,
            "message": resolution.message,
            "sessions": 1 if resolution.session is not None else 0,
            "usage": (
                resolution.session.usage.to_dict()
                if resolution.session is not None
                else TokenUsage().to_dict()
            ),
            "cost": cost_result_to_json(cost),
            "pricing_note": PRICING_NOTE,
            "warnings": [*report.warnings, *cost.warnings],
        }
    sessions = filter_sessions_for_tab(report, tab)
    if group != "none":
        rows = aggregate_by(sessions, group_labeler(group))
        cost_warnings = [
            warning
            for row in rows
            for warning in row.cost.warnings
        ]
        return {
            "tab": tab,
            "group": group,
            "generated_at": report.generated_at.isoformat(),
            "rows": [
                {
                    "name": row.label,
                    "sessions": row.sessions,
                    "usage": row.usage.to_dict(),
                    "cost": cost_result_to_json(row.cost),
                }
                for row in rows
            ],
            "pricing_note": PRICING_NOTE,
            "warnings": [*report.warnings, *cost_warnings],
        }
    cost = sessions_cost(sessions)
    return {
        "tab": tab,
        "group": group,
        "generated_at": report.generated_at.isoformat(),
        "sessions": len(sessions),
        "usage": aggregate_usage(sessions).to_dict(),
        "cost": cost_result_to_json(cost),
        "pricing_note": PRICING_NOTE,
        "warnings": [*report.warnings, *cost.warnings],
    }


def render_html_panel(
    report: UsageReport,
    current_session_context: CurrentSessionContext | None = None,
) -> str:
    generated = html.escape(report.generated_at.isoformat(timespec="seconds"))
    tab_buttons = "\n".join(
        f'<button class="tab-button{" active" if tab == "today" else ""}" data-tab="{tab}" type="button">{label}</button>'
        for tab, label in TAB_LABELS.items()
    )
    sections = "\n".join(render_html_section(report, tab, current_session_context) for tab in TAB_CHOICES)
    warnings = render_html_warnings(report.warnings)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Codex Token Usage</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f8fa;
      --fg: #172026;
      --muted: #66737f;
      --line: #d6dde3;
      --panel: #ffffff;
      --accent: #0f766e;
      --accent-soft: #d9f6f0;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #101418;
        --fg: #edf2f7;
        --muted: #a7b2bd;
        --line: #2f3942;
        --panel: #171d22;
        --accent-soft: #123b37;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1120px, calc(100vw - 32px));
      margin: 28px auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 16px;
    }}
    h1 {{
      margin: 0;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    .generated {{
      color: var(--muted);
      white-space: nowrap;
    }}
    .tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 20px 0;
    }}
    .tab-button {{
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--fg);
      border-radius: 8px;
      padding: 8px 12px;
      cursor: pointer;
    }}
    .tab-button.active {{
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--fg);
    }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 86px;
    }}
    .metric .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .metric .value {{
      margin-top: 8px;
      font-size: 24px;
      font-weight: 650;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 10px 12px;
      text-align: right;
      white-space: nowrap;
    }}
    th:first-child, td:first-child {{ text-align: left; }}
    tr:last-child td {{ border-bottom: 0; }}
    .notes, .warnings {{
      margin-top: 18px;
      color: var(--muted);
    }}
    .warnings {{
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }}
    @media (max-width: 720px) {{
      header {{ display: block; }}
      .generated {{ margin-top: 8px; white-space: normal; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
  <noscript><style>.tab-panel {{ display: block; margin-bottom: 24px; }}</style></noscript>
</head>
<body>
  <main>
    <header>
      <h1>Codex Token Usage</h1>
      <div class="generated">Generated {generated}</div>
    </header>
    <nav class="tabs" aria-label="Usage views">
      {tab_buttons}
    </nav>
    {sections}
    <div class="notes">
      Source: ~/.codex/state_5.sqlite threads.rollout_path plus whitelisted payload.info.total_token_usage metadata.
      Privacy: auth.json, history.jsonl, raw log bodies, prompts, responses, and event bodies are not read or printed.
    </div>
    {warnings}
  </main>
  <script>
    const buttons = Array.from(document.querySelectorAll(".tab-button"));
    const panels = Array.from(document.querySelectorAll(".tab-panel"));
    buttons.forEach((button) => {{
      button.addEventListener("click", () => {{
        const tab = button.dataset.tab;
        buttons.forEach((item) => item.classList.toggle("active", item === button));
        panels.forEach((panel) => panel.classList.toggle("active", panel.dataset.tab === tab));
      }});
    }});
  </script>
</body>
</html>
"""


def render_html_section(
    report: UsageReport,
    tab: str,
    current_session_context: CurrentSessionContext | None = None,
) -> str:
    active = " active" if tab == "today" else ""
    label = html.escape(TAB_LABELS[tab])
    if tab == "current-session":
        body = render_html_current_session(report, current_session_context)
    else:
        sessions = filter_sessions_for_tab(report, tab)
        body = render_html_metrics(len(sessions), aggregate_usage(sessions))
    return f'<section class="tab-panel{active}" data-tab="{tab}"><h2>{label}</h2>{body}</section>'


def render_html_current_session(
    report: UsageReport,
    context: CurrentSessionContext | None,
) -> str:
    resolution = resolve_current_session(report, context)
    if resolution.session is None:
        return f'<p>{html.escape(resolution.message)}</p>'
    return render_html_metrics(1, resolution.session.usage)


def render_html_metrics(session_count: int, usage: TokenUsage) -> str:
    metrics = [
        ("Sessions", session_count),
        ("Input", usage.input_tokens),
        ("Cached Input", usage.cached_input_tokens),
        ("Output", usage.output_tokens),
        ("Reasoning Output", usage.reasoning_output_tokens),
        ("Total", usage.total_tokens),
    ]
    cards = "\n".join(
        f'<div class="metric"><div class="label">{html.escape(label)}</div><div class="value">{format_int(value)}</div></div>'
        for label, value in metrics
    )
    return f'<div class="metrics">{cards}</div>'


def render_html_table(rows: Sequence[AggregateRow]) -> str:
    if not rows:
        rows = (AggregateRow("(none)", 0, TokenUsage(), CostResult(None, ())),)
    body = "\n".join(
        "<tr>"
        f"<td>{html.escape(row.label)}</td>"
        f"<td>{format_int(row.sessions)}</td>"
        f"<td>{format_int(row.usage.input_tokens)}</td>"
        f"<td>{format_int(row.usage.cached_input_tokens)}</td>"
        f"<td>{format_int(row.usage.output_tokens)}</td>"
        f"<td>{format_int(row.usage.reasoning_output_tokens)}</td>"
        f"<td>{format_int(row.usage.total_tokens)}</td>"
        "</tr>"
        for row in rows
    )
    return (
        "<table>"
        "<thead><tr><th>Name</th><th>Sessions</th><th>Input</th><th>Cached</th>"
        "<th>Output</th><th>Reasoning</th><th>Total</th></tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
    )


def render_html_warnings(warnings: Sequence[str]) -> str:
    if not warnings:
        return ""
    items = "\n".join(f"<li>{html.escape(warning)}</li>" for warning in warnings[:8])
    if len(warnings) > 8:
        items += f"\n<li>{len(warnings) - 8} more warning(s).</li>"
    return f'<div class="warnings"><strong>Warnings</strong><ul>{items}</ul></div>'


def default_panel_path(codex_home: Path) -> Path:
    return codex_home / "token-usage-panel" / "index.html"


def write_panel(
    report: UsageReport,
    output_path: Path | None = None,
    current_session_context: CurrentSessionContext | None = None,
) -> Path:
    path = output_path or default_panel_path(report.codex_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html_panel(report, current_session_context), encoding="utf-8")
    return path


def build_doctor_report(codex_home: Path | None = None) -> DoctorReport:
    home = (codex_home or default_codex_home()).expanduser().resolve(strict=False)
    checks = [
        check_python_runtime(),
        check_sqlite3_runtime(),
        check_codex_home(home),
        *check_codex_data_sources(home),
    ]
    return DoctorReport(codex_home=home, checks=tuple(checks))


def check_python_runtime() -> DoctorCheck:
    version = ".".join(str(part) for part in sys.version_info[:3])
    required = ".".join(str(part) for part in MIN_PYTHON_VERSION)
    ok = sys.version_info >= MIN_PYTHON_VERSION
    detail = f"{sys.executable} reports Python {version}; required >= {required}."
    return DoctorCheck("python", ok, detail)


def check_sqlite3_runtime() -> DoctorCheck:
    if importlib.util.find_spec("sqlite3") is None or sqlite3 is None:
        return DoctorCheck(
            "sqlite3",
            False,
            "Python sqlite3 module is unavailable; install Python with SQLite support.",
        )
    return DoctorCheck("sqlite3", True, f"sqlite3 module is available; SQLite {sqlite3.sqlite_version}.")


def check_codex_home(codex_home: Path) -> DoctorCheck:
    if not codex_home.exists():
        return DoctorCheck("codex-home", False, f"Codex home does not exist: {codex_home}")
    if not codex_home.is_dir():
        return DoctorCheck("codex-home", False, f"Codex home is not a directory: {codex_home}")
    return DoctorCheck("codex-home", True, f"Codex home is available: {codex_home}")


def check_codex_data_sources(codex_home: Path) -> tuple[DoctorCheck, ...]:
    return (
        check_state_database(codex_home),
        check_sessions_directory(codex_home),
    )


def check_state_database(codex_home: Path) -> DoctorCheck:
    db_path = codex_home / "state_5.sqlite"
    if sqlite3 is None:
        return DoctorCheck("state-db", False, "Cannot inspect state_5.sqlite because sqlite3 is unavailable.")
    if not db_path.exists():
        return DoctorCheck("state-db", False, f"Missing Codex state database: {db_path}")
    try:
        connection = sqlite3.connect(sqlite_readonly_uri(db_path), uri=True)
    except sqlite3.Error as exc:
        return DoctorCheck("state-db", False, f"Could not open state_5.sqlite read-only: {exc}")
    try:
        with connection:
            connection.row_factory = sqlite3.Row
            table = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'threads'"
            ).fetchone()
            if table is None:
                return DoctorCheck("state-db", False, "state_5.sqlite has no threads table.")
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(threads)").fetchall()
            }
            if "rollout_path" not in columns:
                return DoctorCheck("state-db", False, "threads table has no rollout_path column.")
            total_threads = safe_int(
                connection.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
            )
            rollout_threads = safe_int(
                connection.execute(
                    "SELECT COUNT(*) FROM threads WHERE rollout_path IS NOT NULL AND rollout_path != ''"
                ).fetchone()[0]
            )
    except sqlite3.Error as exc:
        return DoctorCheck("state-db", False, f"Could not inspect threads metadata: {exc}")
    finally:
        connection.close()
    if rollout_threads == 0:
        return DoctorCheck(
            "state-db",
            False,
            f"threads table is readable but has no rollout_path entries ({total_threads} thread rows).",
        )
    return DoctorCheck(
        "state-db",
        True,
        f"threads table is readable with {rollout_threads} rollout_path entries ({total_threads} thread rows).",
    )


def check_sessions_directory(codex_home: Path) -> DoctorCheck:
    sessions_root = codex_home / "sessions"
    if not sessions_root.exists():
        return DoctorCheck("sessions-dir", False, f"Missing Codex sessions directory: {sessions_root}")
    if not sessions_root.is_dir():
        return DoctorCheck("sessions-dir", False, f"Codex sessions path is not a directory: {sessions_root}")
    jsonl_count = sum(1 for path in sessions_root.rglob("*.jsonl") if path.is_file())
    if jsonl_count == 0:
        return DoctorCheck("sessions-dir", False, f"No session JSONL files found under: {sessions_root}")
    return DoctorCheck("sessions-dir", True, f"Found {jsonl_count} session JSONL file(s) under: {sessions_root}")


def render_doctor_report(report: DoctorReport) -> str:
    lines = [
        "Codex Token Usage Doctor",
        f"Codex home: {report.codex_home}",
        f"Status: {'ok' if report.ok() else 'needs attention'}",
        "",
    ]
    for check in report.checks:
        marker = "ok" if check.ok else "fail"
        lines.append(f"- {check.name}: {marker} - {check.detail}")
    lines.extend(
        [
            "",
            "Safety: doctor inspects Python, sqlite3, state_5.sqlite schema/counts, and session file names only.",
            "It does not read auth.json, history.jsonl, raw log bodies, prompts, responses, or transcript bodies.",
        ]
    )
    return "\n".join(lines)


def add_codex_home_arg(
    parser: argparse.ArgumentParser,
    *,
    default: object = None,
) -> None:
    parser.add_argument("--codex-home", type=Path, default=default, help="Override Codex home directory.")


def add_current_session_args(
    parser: argparse.ArgumentParser,
    *,
    default: object = None,
) -> None:
    parser.add_argument(
        "--session-id",
        default=default,
        help="Map the Current Session tab by exact Codex thread/session id.",
    )
    parser.add_argument(
        "--session-rollout-path",
        type=Path,
        default=default,
        help="Map the Current Session tab by exact rollout JSONL path under ~/.codex/sessions.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local read-only Codex token usage reporter.")
    add_codex_home_arg(parser)
    add_current_session_args(parser)
    subparsers = parser.add_subparsers(dest="command")

    summary = subparsers.add_parser("summary", help="Print a status-like Codex CLI usage panel.")
    summary.add_argument("--tab", choices=TAB_ARGUMENT_CHOICES, default=DEFAULT_TAB)
    summary.add_argument("--group", choices=GROUP_ARGUMENT_CHOICES, default="none")
    summary.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    add_codex_home_arg(summary, default=argparse.SUPPRESS)
    add_current_session_args(summary, default=argparse.SUPPRESS)

    doctor = subparsers.add_parser("doctor", help="Check runtime and local Codex data-source availability.")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable diagnostics.")
    add_codex_home_arg(doctor, default=argparse.SUPPRESS)

    panel = subparsers.add_parser(
        "html-panel",
        aliases=["panel"],
        help="Explicitly generate the optional HTML usage panel.",
    )
    panel.add_argument("--output", type=Path, default=None, help="Panel output path.")
    panel.add_argument("--open", action="store_true", help="Open the generated panel in a browser.")
    panel.add_argument(
        "--print-fallback",
        action="store_true",
        help="Also print the Today textual fallback summary.",
    )
    add_codex_home_arg(panel, default=argparse.SUPPRESS)
    add_current_session_args(panel, default=argparse.SUPPRESS)
    return parser


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = build_parser()
    argv = normalize_argv(argv)
    args = parser.parse_args(argv)
    if not hasattr(args, "tab"):
        args.tab = DEFAULT_TAB
    else:
        args.tab = canonical_tab(args.tab)
    if not hasattr(args, "json"):
        args.json = False
    if not hasattr(args, "group"):
        args.group = "none"
    else:
        args.group = canonical_group(args.group)
    return args


def normalize_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if not argv:
        return ("summary", "--tab", DEFAULT_TAB)
    if any(token in COMMAND_CHOICES for token in argv):
        return tuple(argv)

    index = 0
    while index < len(argv):
        token = argv[index]
        if token in OPTIONS_WITH_VALUES:
            index += 2
            continue
        if token.startswith("--"):
            index += 1
            continue
        if token in TAB_ARGUMENT_CHOICES:
            return (*argv[:index], "summary", "--tab", token, *argv[index + 1:])
        break
    return tuple(argv)


def first_env_value(names: Sequence[str]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def current_session_context_from_args(args: argparse.Namespace) -> CurrentSessionContext:
    session_id = args.session_id or first_env_value(CURRENT_SESSION_ID_ENV_VARS)
    rollout_path = args.session_rollout_path
    if rollout_path is None:
        raw_path = first_env_value(CURRENT_SESSION_PATH_ENV_VARS)
        if raw_path:
            rollout_path = Path(raw_path)
    return CurrentSessionContext(session_id=session_id, rollout_path=rollout_path)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(tuple(argv if argv is not None else sys.argv[1:]))
    codex_home = (args.codex_home or default_codex_home()).expanduser()

    if args.command == "doctor":
        doctor_report = build_doctor_report(codex_home)
        if args.json:
            print(json.dumps(doctor_report.to_dict(), indent=2, sort_keys=True))
        else:
            print(render_doctor_report(doctor_report))
        return 0 if doctor_report.ok() else 1

    report = build_usage_report(codex_home=codex_home)
    current_session_context = current_session_context_from_args(args)

    if args.command in (None, "summary"):
        if args.json:
            print(
                json.dumps(
                    report_to_json(
                        report,
                        args.tab,
                        args.group,
                        current_session_context,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                render_text_report(
                    report,
                    args.tab,
                    args.group,
                    current_session_context,
                )
            )
        return 0

    output_path = write_panel(report, args.output, current_session_context)
    opened = False
    if args.open:
        opened = webbrowser.open(output_path.resolve().as_uri())
    print(f"Optional Codex token usage HTML panel: {output_path}")
    if args.print_fallback or (args.open and not opened):
        print()
        print(render_text_report(report, DEFAULT_TAB, "none", current_session_context))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
