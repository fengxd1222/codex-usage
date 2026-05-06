from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "codex-token-usage"
    / "scripts"
    / "codex_usage_reporter.py"
)
LAUNCHER_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "codex-token-usage"
    / "bin"
    / "codex-token-usage"
)
SPEC = importlib.util.spec_from_file_location("codex_usage_reporter", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Could not load reporter module from {SCRIPT_PATH}")
reporter = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reporter
SPEC.loader.exec_module(reporter)


class CodexUsageReporterTest(unittest.TestCase):
    def test_extracts_latest_cumulative_usage_without_double_counting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [
                    usage_event("2026-05-05T09:00:00Z", 10, 3, 4, 2, 14),
                    usage_event("2026-05-05T09:01:00Z", 10, 3, 4, 2, 14),
                    usage_event("2026-05-05T09:02:00Z", 18, 5, 7, 3, 25),
                ],
            )
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 25)])

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )
            text = reporter.render_text_report(report, "today")

            self.assertEqual(len(report.sessions), 1)
            self.assertEqual(report.sessions[0].usage.total_tokens, 25)
            self.assertEqual(report.sessions[0].usage.input_tokens, 18)
            self.assertIn("Total tokens: 25", text)
            self.assertNotIn("64", text)

    def test_only_counts_whitelisted_payload_info_total_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [
                    {
                        "timestamp": "2026-05-05T10:00:00Z",
                        "type": "event_msg",
                        "payload": {
                            "info": {
                                "not_usage": {
                                    "total_token_usage": {
                                        "input_tokens": 900,
                                        "cached_input_tokens": 900,
                                        "output_tokens": 900,
                                        "reasoning_output_tokens": 900,
                                        "total_tokens": 3600,
                                    }
                                },
                                "total_token_usage": {
                                    "input_tokens": 8,
                                    "cached_input_tokens": 2,
                                    "output_tokens": 3,
                                    "reasoning_output_tokens": 1,
                                    "total_tokens": 11,
                                },
                            }
                        },
                    }
                ],
            )
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 11)])

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(report.sessions[0].usage.total_tokens, 11)
            self.assertEqual(report.sessions[0].usage.input_tokens, 8)

    def test_skips_paths_outside_sessions_and_never_reports_raw_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            outside_path = home / "auth.json"
            outside_path.write_text("secret-token", encoding="utf-8")
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [
                    {
                        "timestamp": "2026-05-05T10:00:00Z",
                        "payload": {
                            "message": "raw prompt should not appear",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 4,
                                    "cached_input_tokens": 1,
                                    "output_tokens": 2,
                                    "reasoning_output_tokens": 1,
                                    "total_tokens": 6,
                                }
                            },
                        },
                    }
                ],
            )
            write_state_db(
                home,
                [
                    (outside_path, "gpt-5", "/work/secret-repo", 100),
                    (session_path, "gpt-5", "/work/visible-repo", 6),
                ],
            )

            original_open = Path.open

            def guarded_open(path: Path, *args: Any, **kwargs: Any) -> Any:
                if path == outside_path:
                    raise AssertionError("Reporter must not open auth.json.")
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "open", guarded_open):
                report = reporter.build_usage_report(
                    home,
                    now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
                )
            text = reporter.render_text_report(report, "all", "project")

            self.assertEqual(len(report.sessions), 1)
            self.assertIn("outside ~/.codex/sessions", "\n".join(report.warnings))
            self.assertIn("visible-repo", text)
            self.assertNotIn("secret-token", text)
            self.assertNotIn("raw prompt should not appear", text)
            self.assertNotIn(str(outside_path), text)

    def test_cli_panel_contains_required_tabs_and_defaults_to_today(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [usage_event("2026-05-05T10:00:00Z", 1, 0, 2, 0, 3)],
            )
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 3)])

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )
            panel = reporter.render_text_report(report)

            for label in ("Current Session", "Today", "7 Days", "Month", "All"):
                self.assertIn(label, panel)
            self.assertNotIn("By Model", panel)
            self.assertNotIn("By Repo", panel)
            self.assertIn("[Today]", panel)
            self.assertNotIn("<html", panel)

    def test_default_invocation_prints_cli_panel_without_html_or_browser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [usage_event("2026-05-05T10:00:00Z", 1, 0, 2, 0, 3)],
            )
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 3)])
            output = io.StringIO()

            with patch.object(reporter.webbrowser, "open") as browser_open:
                with redirect_stdout(output):
                    status = reporter.main(["--codex-home", str(home)])

            self.assertEqual(status, 0)
            self.assertIn("Codex Token Usage", output.getvalue())
            self.assertIn("[Today]", output.getvalue())
            self.assertFalse((home / "token-usage-panel" / "index.html").exists())
            browser_open.assert_not_called()

    def test_view_name_argument_selects_cli_tab_and_group(self) -> None:
        args = reporter.parse_args(("month",))

        self.assertEqual(args.command, "summary")
        self.assertEqual(args.tab, "month")
        self.assertEqual(args.group, "none")

        args = reporter.parse_args(("--codex-home", "/tmp/codex-home", "today", "--group", "project"))
        self.assertEqual(args.command, "summary")
        self.assertEqual(args.codex_home, Path("/tmp/codex-home"))
        self.assertEqual(args.tab, "today")
        self.assertEqual(args.group, "project")

    def test_doctor_reports_runtime_and_data_source_status_without_secret_reads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(session_path, [usage_event("2026-05-05T10:00:00Z", 1, 0, 2, 0, 3)])
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 3)])
            (home / "auth.json").write_text("secret-token", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                status = reporter.main(["doctor", "--codex-home", str(home), "--json"])

            self.assertEqual(status, 0)
            data = json.loads(output.getvalue())
            self.assertTrue(data["ok"])
            self.assertIn("python", {item["name"] for item in data["checks"]})
            self.assertIn("sqlite3", {item["name"] for item in data["checks"]})
            self.assertNotIn("secret-token", output.getvalue())

    def test_doctor_surfaces_missing_codex_data_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()

            with redirect_stdout(output):
                status = reporter.main(["doctor", "--codex-home", tmp])

            self.assertEqual(status, 1)
            self.assertIn("Status: needs attention", output.getvalue())
            self.assertIn("Missing Codex state database", output.getvalue())
            self.assertIn("Missing Codex sessions directory", output.getvalue())
            self.assertIn("does not read auth.json", output.getvalue())

    def test_launcher_executes_reporter_with_python_runtime_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(session_path, [usage_event("2026-05-05T10:00:00Z", 1, 0, 2, 0, 3)])
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 3)])

            completed = subprocess.run(
                [
                    str(LAUNCHER_PATH),
                    "doctor",
                    "--codex-home",
                    str(home),
                ],
                check=False,
                capture_output=True,
                env={**os.environ, "PYTHON": sys.executable},
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Codex Token Usage Doctor", completed.stdout)
            self.assertIn("sqlite3: ok", completed.stdout)

    def test_launcher_falls_back_when_python_env_is_unusable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(session_path, [usage_event("2026-05-05T10:00:00Z", 1, 0, 2, 0, 3)])
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 3)])

            completed = subprocess.run(
                [
                    str(LAUNCHER_PATH),
                    "doctor",
                    "--codex-home",
                    str(home),
                ],
                check=False,
                capture_output=True,
                env={**os.environ, "PYTHON": "/definitely/missing/python"},
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("$PYTHON runtime not found", completed.stderr)
            self.assertIn("Codex Token Usage Doctor", completed.stdout)

    def test_current_session_maps_only_by_explicit_safe_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [usage_event("2026-05-05T10:00:00Z", 1, 0, 2, 0, 3)],
            )
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 3)])

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )
            panel = reporter.render_text_report(
                report,
                "current-session",
                current_session_context=reporter.CurrentSessionContext(session_id="thread-1"),
            )

            self.assertIn("[Current Session]", panel)
            self.assertIn("Status: available (gpt-5)", panel)
            self.assertIn("Total tokens: 3", panel)

    def test_current_session_unavailable_does_not_guess_from_raw_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [
                    {
                        "timestamp": "2026-05-05T10:00:00Z",
                        "payload": {
                            "message": "raw prompt should not appear",
                            "info": {
                                "total_token_usage": {
                                    "input_tokens": 1,
                                    "cached_input_tokens": 0,
                                    "output_tokens": 2,
                                    "reasoning_output_tokens": 0,
                                    "total_tokens": 3,
                                }
                            },
                        },
                    }
                ],
            )
            write_state_db(home, [(session_path, "gpt-5", "/work/repo-one", 3)])

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )
            panel = reporter.render_text_report(report, "current-session")

            self.assertIn("Status: unavailable", panel)
            self.assertIn("not guessing from history, transcript text, raw logs, prompts, or responses", panel)
            self.assertNotIn("raw prompt should not appear", panel)

    def test_month_filters_current_month_and_grouping_by_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            current = home / "sessions" / "2026" / "05" / "05" / "current.jsonl"
            previous_month = home / "sessions" / "2026" / "04" / "30" / "old.jsonl"
            write_session(current, [usage_event("2026-05-05T10:00:00Z", 100, 40, 20, 5, 120)])
            write_session(previous_month, [usage_event("2026-04-30T10:00:00Z", 1000, 0, 100, 0, 1100)])
            write_state_db_with_times(
                home,
                [
                    (current, "gpt-5.4", "/work/repo-one", 120, 1777971600000),
                    (previous_month, "gpt-5.4", "/work/repo-two", 1100, 1777539600000),
                ],
            )

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )
            month = reporter.render_text_report(report, "month")
            grouped = reporter.render_text_report(report, "month", "project")

            self.assertIn("Sessions: 1", month)
            self.assertIn("Total tokens: 120", month)
            self.assertNotIn("repo-two", grouped)
            self.assertIn("repo-one", grouped)

    def test_cost_formula_uses_cached_input_and_output_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [usage_event("2026-05-05T10:00:00Z", 1_000_000, 400_000, 100_000, 90_000, 1_100_000)],
            )
            write_state_db(home, [(session_path, "gpt-5.4", "/work/repo-one", 1_100_000)])

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )
            text = reporter.render_text_report(report, "today")
            data = reporter.report_to_json(report, "today")

            self.assertIn("- Estimated cost: $3.10 USD", text)
            self.assertEqual(data["cost"]["estimate"]["total_cost"], "3.100000")

    def test_unknown_model_cost_is_unavailable_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            session_path = home / "sessions" / "2026" / "05" / "05" / "rollout.jsonl"
            write_session(
                session_path,
                [usage_event("2026-05-05T10:00:00Z", 10, 1, 2, 1, 12)],
            )
            write_state_db(home, [(session_path, "gpt-unknown", "/work/repo-one", 12)])

            report = reporter.build_usage_report(
                home,
                now=datetime(2026, 5, 5, 12, 0, tzinfo=timezone.utc),
            )
            text = reporter.render_text_report(report, "today")

            self.assertIn("- Estimated cost: unavailable", text)
            self.assertIn("no explicit official pricing mapping", text)


def write_state_db(home: Path, rows: list[tuple[Path, str, str, int]]) -> None:
    write_state_db_with_times(
        home,
        [
            (path, model, cwd, tokens_used, 1777971600000)
            for path, model, cwd, tokens_used in rows
        ],
    )


def write_state_db_with_times(
    home: Path,
    rows: list[tuple[Path, str, str, int, int]],
) -> None:
    connection = sqlite3.connect(home / "state_5.sqlite")
    try:
        with connection:
            connection.execute(
                """
                CREATE TABLE threads (
                    id TEXT,
                    rollout_path TEXT,
                    created_at_ms INTEGER,
                    updated_at_ms INTEGER,
                    model_provider TEXT,
                    model TEXT,
                    reasoning_effort TEXT,
                    cwd TEXT,
                    tokens_used INTEGER
                )
                """
            )
            for index, (path, model, cwd, tokens_used, updated_at_ms) in enumerate(rows, start=1):
                connection.execute(
                    """
                    INSERT INTO threads (
                        id,
                        rollout_path,
                        created_at_ms,
                        updated_at_ms,
                        model_provider,
                        model,
                        reasoning_effort,
                        cwd,
                        tokens_used
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"thread-{index}",
                        str(path),
                        updated_at_ms,
                        updated_at_ms,
                        "openai",
                        model,
                        "medium",
                        cwd,
                        tokens_used,
                    ),
                )
    finally:
        connection.close()


def write_session(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def usage_event(
    timestamp: str,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    reasoning_output_tokens: int,
    total_tokens: int,
) -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "info": {
                "total_token_usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_input_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning_output_tokens,
                    "total_tokens": total_tokens,
                }
            }
        },
    }


if __name__ == "__main__":
    unittest.main()
