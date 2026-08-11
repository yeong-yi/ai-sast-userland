#!/usr/bin/env python3
"""Find calls to review-worthy C/C++ functions.

This is a candidate collector, not a vulnerability detector. It deliberately
uses only the Python standard library and never modifies the scanned source.
"""

from __future__ import annotations

import argparse
import bisect
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_EXTENSIONS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect C/C++ function-call candidates for manual review."
    )
    parser.add_argument("--target", default="target/userland", help="directory to scan")
    parser.add_argument("--rules", default="config/rules.json", help="JSON rule file")
    parser.add_argument(
        "--output", default="reports/candidates.json", help="JSON report path"
    )
    return parser.parse_args()


def load_rules(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("rules.json must contain a non-empty 'rules' list")

    required = {"function", "severity", "reason"}
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or not required.issubset(rule):
            raise ValueError(f"each rule must contain {sorted(required)}")
        if rule["function"] in seen:
            raise ValueError(f"duplicate rule: {rule['function']}")
        if rule["severity"] not in SEVERITY_ORDER:
            raise ValueError(f"unsupported severity: {rule['severity']}")
        seen.add(rule["function"])
    return rules


def mask_comments_and_literals(text: str) -> str:
    """Replace comments, strings, and character literals while preserving lines."""
    chars = list(text)
    state = "code"
    i = 0
    while i < len(chars):
        current = chars[i]
        following = chars[i + 1] if i + 1 < len(chars) else ""

        if state == "code":
            if current == "/" and following == "/":
                chars[i] = chars[i + 1] = " "
                state = "line_comment"
                i += 2
                continue
            if current == "/" and following == "*":
                chars[i] = chars[i + 1] = " "
                state = "block_comment"
                i += 2
                continue
            if current == '"':
                chars[i] = " "
                state = "string"
                i += 1
                continue
            if current == "'":
                chars[i] = " "
                state = "character"
                i += 1
                continue
        elif state == "line_comment":
            if current == "\n":
                state = "code"
            else:
                chars[i] = " "
        elif state == "block_comment":
            if current == "*" and following == "/":
                chars[i] = chars[i + 1] = " "
                state = "code"
                i += 2
                continue
            if current != "\n":
                chars[i] = " "
        elif state in {"string", "character"}:
            closing = '"' if state == "string" else "'"
            if current == "\\" and following:
                if current != "\n":
                    chars[i] = " "
                if following != "\n":
                    chars[i + 1] = " "
                i += 2
                continue
            if current == closing:
                chars[i] = " "
                state = "code"
            elif current != "\n":
                chars[i] = " "
        i += 1
    return "".join(chars)


def preprocessor_lines(masked_text: str) -> set[int]:
    """Return 1-based line numbers occupied by # directives and continuations."""
    excluded: set[int] = set()
    continuing = False
    for number, line in enumerate(masked_text.splitlines(), start=1):
        directive = continuing or line.lstrip().startswith("#")
        if directive:
            excluded.add(number)
        continuing = directive and line.rstrip().endswith("\\")
    return excluded


def scan_file(
    path: Path,
    project_root: Path,
    rules_by_name: dict[str, dict[str, str]],
    call_pattern: re.Pattern[str],
) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise OSError(f"could not read {path}: {exc}") from exc

    masked = mask_comments_and_literals(text)
    excluded_lines = preprocessor_lines(masked)
    line_starts = [0]
    line_starts.extend(match.end() for match in re.finditer("\n", masked))
    original_lines = text.splitlines()
    findings: list[dict[str, Any]] = []

    for match in call_pattern.finditer(masked):
        line_number = bisect.bisect_right(line_starts, match.start())
        if line_number in excluded_lines:
            continue
        function_name = match.group(1)
        rule = rules_by_name[function_name]
        code = original_lines[line_number - 1].strip() if original_lines else ""
        findings.append(
            {
                "status": "review_candidate",
                "file": path.relative_to(project_root).as_posix(),
                "line": line_number,
                "function": function_name,
                "code": code,
                "severity": rule["severity"],
                "reason": rule["reason"],
            }
        )
    return findings


def main() -> int:
    args = parse_args()
    project_root = Path.cwd().resolve()
    target = (project_root / args.target).resolve()
    rules_path = (project_root / args.rules).resolve()
    output_path = (project_root / args.output).resolve()

    if not target.is_dir():
        raise FileNotFoundError(f"target directory not found: {target}")
    if not rules_path.is_file():
        raise FileNotFoundError(f"rules file not found: {rules_path}")

    rules = load_rules(rules_path)
    rules_by_name = {rule["function"]: rule for rule in rules}
    names = "|".join(re.escape(name) for name in rules_by_name)
    call_pattern = re.compile(rf"\b({names})\s*\(")
    source_files = sorted(
        path for path in target.rglob("*") if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS
    )

    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in source_files:
        try:
            candidates.extend(scan_file(path, project_root, rules_by_name, call_pattern))
        except OSError as exc:
            errors.append({"file": path.relative_to(project_root).as_posix(), "error": str(exc)})

    candidates.sort(
        key=lambda item: (
            SEVERITY_ORDER[item["severity"]],
            item["file"],
            item["line"],
            item["function"],
        )
    )
    function_counts = Counter(item["function"] for item in candidates)
    severity_counts = Counter(item["severity"] for item in candidates)
    report = {
        "report_type": "review_candidates",
        "notice": "These matches are review candidates, not confirmed vulnerabilities.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": Path(args.target).as_posix(),
        "summary": {
            "scanned_files": len(source_files),
            "total_candidates": len(candidates),
            "counts_by_function": {
                rule["function"]: function_counts[rule["function"]] for rule in rules
            },
            "counts_by_severity": {
                severity: severity_counts[severity]
                for severity in ("critical", "high", "medium", "low")
                if severity_counts[severity]
            },
            "read_errors": len(errors),
        },
        "errors": errors,
        "candidates": candidates,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Scanned files: {len(source_files)}")
    print(f"Review candidates: {len(candidates)}")
    print(f"Read errors: {len(errors)}")
    print(f"Report: {output_path.relative_to(project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
