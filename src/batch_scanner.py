#!/usr/bin/env python3
"""Run the existing scanner logic in stable, path-ordered code-size batches."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scanner import SEVERITY_ORDER, SOURCE_EXTENSIONS, load_rules, scan_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan UserLand in stable balanced batches.")
    parser.add_argument("--target", default="target/userland")
    parser.add_argument("--rules", default="config/rules.json")
    parser.add_argument("--full-results", default="reports/candidates.json")
    parser.add_argument("--output", default="reports/batch_results.json")
    parser.add_argument("--batch-count", type=int, default=3)
    return parser.parse_args()


def physical_line_count(path: Path) -> int:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for _ in handle)


def stable_balanced_batches(
    weighted_files: list[tuple[Path, int]], batch_count: int
) -> list[list[tuple[Path, int]]]:
    if batch_count < 1:
        raise ValueError("batch_count must be at least 1")
    if len(weighted_files) < batch_count:
        raise ValueError("batch_count cannot exceed the number of source files")

    batches: list[list[tuple[Path, int]]] = []
    cursor = 0
    remaining_lines = sum(weight for _, weight in weighted_files)
    for batch_index in range(batch_count):
        remaining_batches = batch_count - batch_index
        if remaining_batches == 1:
            batches.append(weighted_files[cursor:])
            break
        target_lines = remaining_lines / remaining_batches
        current: list[tuple[Path, int]] = []
        current_lines = 0
        files_left_after = len(weighted_files) - cursor
        while cursor < len(weighted_files) and files_left_after > remaining_batches - 1:
            path, weight = weighted_files[cursor]
            if current and current_lines + weight > target_lines:
                without_gap = abs(target_lines - current_lines)
                with_gap = abs(target_lines - (current_lines + weight))
                if without_gap <= with_gap:
                    break
            current.append((path, weight))
            current_lines += weight
            cursor += 1
            files_left_after = len(weighted_files) - cursor
            if current_lines >= target_lines:
                break
        batches.append(current)
        remaining_lines -= current_lines
    return batches


def candidate_key(candidate: dict[str, Any]) -> tuple[str, int, str]:
    return candidate["file"], candidate["line"], candidate["function"]


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    root = Path.cwd().resolve()
    target = (root / args.target).resolve()
    rules_path = (root / args.rules).resolve()
    full_results_path = (root / args.full_results).resolve()
    output_path = (root / args.output).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"target directory not found: {target}")
    if not full_results_path.is_file():
        raise FileNotFoundError("run scanner.py before batch_scanner.py")

    rules = load_rules(rules_path)
    rules_by_name = {rule["function"]: rule for rule in rules}
    names = "|".join(re.escape(name) for name in rules_by_name)
    call_pattern = re.compile(rf"\b({names})\s*\(")
    source_files = sorted(
        path for path in target.rglob("*")
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS
    )
    weighted_files = [(path, physical_line_count(path)) for path in source_files]
    batches = stable_balanced_batches(weighted_files, args.batch_count)

    batch_results: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    all_errors: list[dict[str, str]] = []
    for index, batch in enumerate(batches, start=1):
        batch_started = time.perf_counter()
        candidates: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        top_paths: Counter[str] = Counter()
        for path, _ in batch:
            relative_to_target = path.relative_to(target)
            top_paths[relative_to_target.parts[0]] += 1
            try:
                candidates.extend(scan_file(path, root, rules_by_name, call_pattern))
            except OSError as exc:
                errors.append({"file": path.relative_to(root).as_posix(), "error": str(exc)})
        candidates.sort(key=lambda item: (
            SEVERITY_ORDER[item["severity"]], item["file"], item["line"], item["function"]
        ))
        first_path = batch[0][0].relative_to(target).as_posix()
        last_path = batch[-1][0].relative_to(target).as_posix()
        result = {
            "batch_id": f"BATCH-{index:03d}",
            "selection": {
                "strategy": "path_sorted_contiguous_range_balanced_by_physical_code_lines",
                "first_relative_path": first_path,
                "last_relative_path": last_path,
                "top_level_path_counts": dict(sorted(top_paths.items())),
            },
            "file_count": len(batch),
            "estimated_code_lines": sum(weight for _, weight in batch),
            "candidate_count": len(candidates),
            "counts_by_function": dict(sorted(Counter(item["function"] for item in candidates).items())),
            "counts_by_severity": dict(sorted(Counter(item["severity"] for item in candidates).items())),
            "execution_seconds": round(time.perf_counter() - batch_started, 3),
            "error_count": len(errors),
            "errors": errors,
            "candidates": candidates,
        }
        batch_results.append(result)
        all_candidates.extend(candidates)
        all_errors.extend(errors)

    full_report = json.loads(full_results_path.read_text(encoding="utf-8"))
    full_keys = Counter(candidate_key(item) for item in full_report["candidates"])
    batch_keys = Counter(candidate_key(item) for item in all_candidates)
    missing_from_batches = list((full_keys - batch_keys).elements())
    extra_in_batches = list((batch_keys - full_keys).elements())
    relation = {
        "full_scan_candidate_count": len(full_report["candidates"]),
        "batch_candidate_count": len(all_candidates),
        "counts_match": len(full_report["candidates"]) == len(all_candidates),
        "candidate_identity_match": not missing_from_batches and not extra_in_batches,
        "missing_from_batches": [list(item) for item in missing_from_batches[:20]],
        "extra_in_batches": [list(item) for item in extra_in_batches[:20]],
        "explanation": (
            "각 C/C++ 파일을 정확히 한 배치에만 배정하고 scanner.py와 같은 탐지 함수를 사용하므로, "
            "세 배치 후보의 합은 전체 스캔 후보와 같아야 합니다."
        ),
    }
    report = {
        "report_type": "stable_batch_scan_results",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": Path(args.target).as_posix(),
        "batch_count": len(batch_results),
        "partition_policy": {
            "file_order": "normalized_relative_path_ascending",
            "balance_weight": "physical_code_lines",
            "stability": "same repository contents and batch_count produce the same path ranges",
            "token_rationale": "limits the amount of code considered in one analysis unit before candidate prioritization",
        },
        "summary": {
            "source_files": len(source_files),
            "estimated_code_lines": sum(weight for _, weight in weighted_files),
            "batch_candidates": len(all_candidates),
            "errors": len(all_errors),
            "execution_seconds": round(time.perf_counter() - started, 3),
        },
        "whole_scan_relation": relation,
        "batches": batch_results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Batches: {len(batch_results)}")
    for batch in batch_results:
        print(
            f"{batch['batch_id']}: files={batch['file_count']} lines={batch['estimated_code_lines']} "
            f"candidates={batch['candidate_count']} errors={batch['error_count']} "
            f"seconds={batch['execution_seconds']:.3f}"
        )
    print(f"Batch candidates: {len(all_candidates)}")
    print(f"Full scan candidates: {len(full_report['candidates'])}")
    print(f"Identity match: {relation['candidate_identity_match']}")
    print(f"Report: {output_path.relative_to(root)}")
    return 0 if relation["counts_match"] and relation["candidate_identity_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
