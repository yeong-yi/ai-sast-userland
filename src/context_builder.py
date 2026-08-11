#!/usr/bin/env python3
"""Build bounded, regex-based code context bundles for scanner candidates."""

from __future__ import annotations

import argparse
import bisect
import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scanner import SOURCE_EXTENSIONS, mask_comments_and_literals


CONTROL_WORDS = {
    "if", "for", "while", "switch", "catch", "sizeof", "return", "defined",
    "alignof", "decltype", "static_assert", "typeof",
}
MAX_CANDIDATE_FUNCTION_LINES = 140
MAX_BUNDLE_CODE_LINES = 220
MAX_CALLERS_WITH_CODE = 2
MAX_CALLEES_WITH_CODE = 3
RELATED_SNIPPET_LINES = 24
MAX_RELATIONS_PER_DIRECTION = 30


@dataclass
class SourceFile:
    path: Path
    relative_path: str
    text: str
    masked: str
    lines: list[str]
    line_starts: list[int]

    def line_number(self, offset: int) -> int:
        return bisect.bisect_right(self.line_starts, offset)


@dataclass
class CallSite:
    name: str
    line: int
    offset: int


@dataclass
class FunctionInfo:
    identifier: str
    name: str
    file: str
    start_line: int
    body_start_line: int
    end_line: int
    start_offset: int
    body_start_offset: int
    end_offset: int
    calls: list[CallSite] = field(default_factory=list)

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build bounded code-context bundles from scanner candidates."
    )
    parser.add_argument("--target", default="target/userland")
    parser.add_argument("--candidates", default="reports/candidates.json")
    parser.add_argument("--output", default="reports/context_bundles.json")
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=0,
        help="process only this many candidates; 0 means all",
    )
    return parser.parse_args()


def load_source(path: Path, project_root: Path) -> SourceFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    masked = mask_comments_and_literals(text)
    starts = [0]
    starts.extend(match.end() for match in re.finditer("\n", text))
    return SourceFile(
        path=path,
        relative_path=path.relative_to(project_root).as_posix(),
        text=text,
        masked=masked,
        lines=text.splitlines(),
        line_starts=starts,
    )


def previous_non_space(text: str, start: int) -> int:
    index = start
    while index >= 0 and text[index].isspace():
        index -= 1
    return index


def matching_open_paren(text: str, close_index: int) -> int | None:
    depth = 0
    for index in range(close_index, -1, -1):
        if text[index] == ")":
            depth += 1
        elif text[index] == "(":
            depth -= 1
            if depth == 0:
                return index
    return None


def brace_pairs(masked: str) -> dict[int, int]:
    stack: list[int] = []
    pairs: dict[int, int] = {}
    for index, char in enumerate(masked):
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            pairs[stack.pop()] = index
    return pairs


def function_at_brace(source: SourceFile, brace_index: int, close_index: int) -> FunctionInfo | None:
    close_paren = previous_non_space(source.masked, brace_index - 1)
    if close_paren < 0 or source.masked[close_paren] != ")":
        return None
    open_paren = matching_open_paren(source.masked, close_paren)
    if open_paren is None:
        return None

    name_end = previous_non_space(source.masked, open_paren - 1) + 1
    name_match = re.search(r"(?:~?[A-Za-z_]\w*)\s*$", source.masked[:name_end])
    if not name_match:
        return None
    name = name_match.group(0).strip().lstrip("~")
    if name in CONTROL_WORDS:
        return None

    delimiter = max(
        source.masked.rfind(";", 0, name_match.start()),
        source.masked.rfind("{", 0, name_match.start()),
        source.masked.rfind("}", 0, name_match.start()),
    )
    signature_start = delimiter + 1
    # A function may begin immediately after #if/#ifdef. The directive is not
    # part of its signature, so start after the final directive in this span.
    prefix_span = source.masked[signature_start:name_match.start()]
    directives = list(re.finditer(r"(?m)^[ \t]*#[^\n]*(?:\n|$)", prefix_span))
    if directives:
        signature_start += directives[-1].end()
    while signature_start < name_match.start() and source.masked[signature_start].isspace():
        signature_start += 1
    signature_prefix = source.masked[signature_start:name_match.start()]
    if "=" in signature_prefix or not signature_prefix.strip():
        return None

    start_line = source.line_number(signature_start)
    body_start_line = source.line_number(brace_index)
    end_line = source.line_number(close_index)
    identifier = f"{source.relative_path}:{start_line}:{name}"
    return FunctionInfo(
        identifier=identifier,
        name=name,
        file=source.relative_path,
        start_line=start_line,
        body_start_line=body_start_line,
        end_line=end_line,
        start_offset=signature_start,
        body_start_offset=brace_index,
        end_offset=close_index,
    )


def extract_functions(source: SourceFile) -> list[FunctionInfo]:
    functions: list[FunctionInfo] = []
    for open_brace, close_brace in brace_pairs(source.masked).items():
        function = function_at_brace(source, open_brace, close_brace)
        if function is not None:
            functions.append(function)

    call_pattern = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
    for function in functions:
        body = source.masked[function.body_start_offset + 1:function.end_offset]
        for match in call_pattern.finditer(body):
            name = match.group(1)
            if name in CONTROL_WORDS:
                continue
            absolute_offset = function.body_start_offset + 1 + match.start(1)
            function.calls.append(
                CallSite(name=name, line=source.line_number(absolute_offset), offset=absolute_offset)
            )
    return functions


def find_matching_close_paren(text: str, open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def split_arguments(original: str, masked: str) -> list[str]:
    arguments: list[str] = []
    start = 0
    parens = brackets = braces = 0
    for index, char in enumerate(masked):
        if char == "(":
            parens += 1
        elif char == ")":
            parens -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
        elif char == "," and parens == brackets == braces == 0:
            arguments.append(original[start:index].strip())
            start = index + 1
    final = original[start:].strip()
    if final or arguments:
        arguments.append(final)
    return arguments


def extract_candidate_call(source: SourceFile, function_name: str, line: int) -> dict[str, Any] | None:
    pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(")
    for match in pattern.finditer(source.masked):
        if source.line_number(match.start()) != line:
            continue
        open_paren = source.masked.find("(", match.start(), match.end())
        close_paren = find_matching_close_paren(source.masked, open_paren)
        if close_paren is None:
            return None
        original_arguments = source.text[open_paren + 1:close_paren]
        masked_arguments = source.masked[open_paren + 1:close_paren]
        return {
            "expression": source.text[match.start():close_paren + 1],
            "arguments": split_arguments(original_arguments, masked_arguments),
            "start_line": source.line_number(match.start()),
            "end_line": source.line_number(close_paren),
        }
    return None


def code_segment(source: SourceFile, start_line: int, end_line: int, purpose: str) -> dict[str, Any]:
    start_line = max(1, start_line)
    end_line = min(len(source.lines), end_line)
    return {
        "purpose": purpose,
        "file": source.relative_path,
        "start_line": start_line,
        "end_line": end_line,
        "code": "\n".join(source.lines[start_line - 1:end_line]),
    }


def centered_range(start: int, end: int, focus: int, limit: int) -> tuple[int, int, list[dict[str, int]]]:
    total = end - start + 1
    if total <= limit:
        return start, end, []
    before = limit // 2
    selected_start = max(start, focus - before)
    selected_end = selected_start + limit - 1
    if selected_end > end:
        selected_end = end
        selected_start = end - limit + 1
    omitted: list[dict[str, int]] = []
    if selected_start > start:
        omitted.append({"start_line": start, "end_line": selected_start - 1})
    if selected_end < end:
        omitted.append({"start_line": selected_end + 1, "end_line": end})
    return selected_start, selected_end, omitted


def relation_record(function: FunctionInfo, call_line: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "function": function.name,
        "definition": {
            "file": function.file,
            "start_line": function.start_line,
            "end_line": function.end_line,
        },
    }
    if call_line is not None:
        result["call_line"] = call_line
    return result


def unique_relations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def build_bundle(
    candidate_id: str,
    candidate: dict[str, Any],
    sources: dict[str, SourceFile],
    functions_by_file: dict[str, list[FunctionInfo]],
    functions_by_name: dict[str, list[FunctionInfo]],
    reverse_calls: dict[str, list[tuple[FunctionInfo, CallSite]]],
) -> dict[str, Any]:
    missing: list[str] = []
    exclusions: list[dict[str, Any]] = []
    code_segments: list[dict[str, Any]] = []
    source = sources.get(candidate["file"])
    if source is None:
        missing.append("candidate source file could not be loaded")
        return {
            "candidate_id": candidate_id,
            "candidate": candidate,
            "missing_information": missing,
            "excluded_content": exclusions,
            "code_segments": code_segments,
        }

    containing = [
        function for function in functions_by_file.get(candidate["file"], [])
        if function.start_line <= candidate["line"] <= function.end_line
    ]
    owner = min(containing, key=lambda item: item.line_count) if containing else None
    call = extract_candidate_call(source, candidate["function"], candidate["line"])
    if call is None:
        missing.append("could not parse the risky call arguments")

    context_start = max(1, candidate["line"] - 8)
    context_end = min(len(source.lines), candidate["line"] + 8)
    code_segments.append(code_segment(source, context_start, context_end, "candidate_nearby_context"))
    used_lines = context_end - context_start + 1

    owner_record: dict[str, Any] | None = None
    callers: list[dict[str, Any]] = []
    callees: list[dict[str, Any]] = []

    if owner is None:
        missing.append("containing function definition was not found by the regex parser")
    else:
        owner_record = relation_record(owner)
        selected_start, selected_end, omitted = centered_range(
            owner.start_line, owner.end_line, candidate["line"], MAX_CANDIDATE_FUNCTION_LINES
        )
        # Avoid duplicating the nearby segment when the entire function is very small.
        code_segments = [segment for segment in code_segments if not (
            segment["file"] == owner.file
            and selected_start <= segment["start_line"]
            and segment["end_line"] <= selected_end
        )]
        used_lines = sum(s["end_line"] - s["start_line"] + 1 for s in code_segments)
        code_segments.append(
            code_segment(source, selected_start, selected_end, "candidate_containing_function")
        )
        used_lines += selected_end - selected_start + 1
        if omitted:
            exclusions.append({
                "reason": "candidate function exceeded the per-function line limit",
                "file": owner.file,
                "function": owner.name,
                "omitted_ranges": omitted,
            })

        caller_pairs = reverse_calls.get(owner.name, [])
        caller_pairs = sorted(
            caller_pairs,
            key=lambda pair: (pair[0].file != owner.file, abs(pair[1].line - candidate["line"]), pair[0].file),
        )
        for caller, site in caller_pairs:
            callers.append(relation_record(caller, site.line))
        callers = unique_relations(callers)

        called_sites: dict[str, CallSite] = {}
        for site in owner.calls:
            if site.name == candidate["function"]:
                continue
            called_sites.setdefault(site.name, site)
        for called_name, site in called_sites.items():
            definitions = functions_by_name.get(called_name, [])
            if definitions:
                ordered = sorted(definitions, key=lambda item: (item.file != owner.file, item.file, item.start_line))
                for definition in ordered:
                    record = relation_record(definition, site.line)
                    record["resolution"] = "definition_found"
                    callees.append(record)
            else:
                callees.append({
                    "function": called_name,
                    "call_line": site.line,
                    "resolution": "external_macro_or_definition_not_found",
                })
        callees = unique_relations(callees)

        if len(callers) > MAX_RELATIONS_PER_DIRECTION:
            exclusions.append({
                "reason": "caller relationship list exceeded the limit",
                "omitted_relationships": len(callers) - MAX_RELATIONS_PER_DIRECTION,
            })
            callers = callers[:MAX_RELATIONS_PER_DIRECTION]
        if len(callees) > MAX_RELATIONS_PER_DIRECTION:
            exclusions.append({
                "reason": "callee relationship list exceeded the limit",
                "omitted_relationships": len(callees) - MAX_RELATIONS_PER_DIRECTION,
            })
            callees = callees[:MAX_RELATIONS_PER_DIRECTION]

        caller_code_count = 0
        caller_relations_covered = 0
        for relation in callers:
            existing = next(
                (
                    segment for segment in code_segments
                    if segment["purpose"] == "caller_near_call_site"
                    and segment["file"] == relation["definition"]["file"]
                    and segment["start_line"] <= relation["call_line"] <= segment["end_line"]
                ),
                None,
            )
            if existing is not None:
                caller_relations_covered += 1
                continue
            if caller_code_count >= MAX_CALLERS_WITH_CODE:
                break
            relation_source = sources[relation["definition"]["file"]]
            remaining = MAX_BUNDLE_CODE_LINES - used_lines
            if remaining <= 0:
                break
            span = min(RELATED_SNIPPET_LINES, remaining)
            half = span // 2
            start = max(relation["definition"]["start_line"], relation["call_line"] - half)
            end = min(relation["definition"]["end_line"], start + span - 1)
            start = max(relation["definition"]["start_line"], end - span + 1)
            code_segments.append(code_segment(relation_source, start, end, "caller_near_call_site"))
            used_lines += end - start + 1
            caller_code_count += 1
            caller_relations_covered += 1

        callee_code_count = 0
        for relation in callees:
            if callee_code_count >= MAX_CALLEES_WITH_CODE or "definition" not in relation:
                continue
            relation_source = sources[relation["definition"]["file"]]
            remaining = MAX_BUNDLE_CODE_LINES - used_lines
            if remaining <= 0:
                break
            span = min(RELATED_SNIPPET_LINES, remaining)
            start = relation["definition"]["start_line"]
            end = min(relation["definition"]["end_line"], start + span - 1)
            code_segments.append(code_segment(relation_source, start, end, "callee_function_start"))
            used_lines += end - start + 1
            callee_code_count += 1

        if len(callers) > caller_relations_covered:
            exclusions.append({
                "reason": "bundle size favors the closest caller code",
                "caller_relationships_without_code": len(callers) - caller_relations_covered,
            })
        resolved_callee_count = sum(1 for item in callees if "definition" in item)
        if resolved_callee_count > callee_code_count:
            exclusions.append({
                "reason": "bundle size favors the closest callee code",
                "callee_definitions_without_code": resolved_callee_count - callee_code_count,
            })

    if not callers:
        missing.append("no caller function was found; it may be an entry point, callback, or regex miss")
    unresolved = [item["function"] for item in callees if "definition" not in item]
    if unresolved:
        missing.append(
            "definitions were not found for some calls: " + ", ".join(unresolved[:10])
        )

    actual_code_lines = sum(item["end_line"] - item["start_line"] + 1 for item in code_segments)
    return {
        "candidate_id": candidate_id,
        "analysis_status": "context_collected_not_vulnerability_confirmed",
        "candidate": {
            "file": candidate["file"],
            "line": candidate["line"],
            "risky_function": candidate["function"],
            "severity": candidate["severity"],
            "reason": candidate["reason"],
            "original_line": candidate["code"],
            "parsed_call": call,
        },
        "containing_function": owner_record,
        "call_relationships": {
            "callers": callers,
            "callees": callees,
            "confidence": "regex_approximation_requires_review",
        },
        "code_segments": code_segments,
        "bundle_size": {
            "included_code_lines": actual_code_lines,
            "maximum_code_lines": MAX_BUNDLE_CODE_LINES,
        },
        "excluded_content": exclusions,
        "missing_information": missing,
        "ai_handoff": {
            "instruction": (
                "Treat this as an unconfirmed review candidate. Use only the supplied code, "
                "cite exact file and line numbers, trace input to the risky call, identify "
                "missing evidence, and do not claim a vulnerability without a supported path."
            ),
            "questions": [
                "Can attacker-controlled input reach any risky-call argument?",
                "Do buffer allocation and bounds checks cover the terminating byte?",
                "Which assumptions cannot be verified from this bounded bundle?",
            ],
        },
    }


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    project_root = Path.cwd().resolve()
    target = (project_root / args.target).resolve()
    candidate_path = (project_root / args.candidates).resolve()
    output_path = (project_root / args.output).resolve()
    if not target.is_dir():
        raise FileNotFoundError(f"target directory not found: {target}")
    if not candidate_path.is_file():
        raise FileNotFoundError(f"candidate report not found: {candidate_path}")

    candidate_report = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidates = candidate_report.get("candidates", [])
    if args.max_candidates > 0:
        candidates = candidates[:args.max_candidates]

    source_paths = sorted(
        path for path in target.rglob("*")
        if path.is_file() and path.suffix.lower() in SOURCE_EXTENSIONS
    )
    sources: dict[str, SourceFile] = {}
    functions_by_file: dict[str, list[FunctionInfo]] = defaultdict(list)
    functions_by_name: dict[str, list[FunctionInfo]] = defaultdict(list)
    parse_errors: list[dict[str, str]] = []
    for path in source_paths:
        try:
            source = load_source(path, project_root)
            sources[source.relative_path] = source
            for function in extract_functions(source):
                functions_by_file[function.file].append(function)
                functions_by_name[function.name].append(function)
        except OSError as exc:
            parse_errors.append({"file": path.relative_to(project_root).as_posix(), "error": str(exc)})

    reverse_calls: dict[str, list[tuple[FunctionInfo, CallSite]]] = defaultdict(list)
    for file_functions in functions_by_file.values():
        for function in file_functions:
            for call in function.calls:
                reverse_calls[call.name].append((function, call))

    bundles = [
        build_bundle(
            f"CAND-{index:04d}", candidate, sources, functions_by_file,
            functions_by_name, reverse_calls,
        )
        for index, candidate in enumerate(candidates, start=1)
    ]
    elapsed = time.perf_counter() - started
    missing_owner_count = sum(1 for bundle in bundles if not bundle.get("containing_function"))
    report = {
        "report_type": "bounded_context_bundles",
        "notice": "Regex-based context for review; not confirmed vulnerabilities or a complete call graph.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_report": Path(args.candidates).as_posix(),
        "target": Path(args.target).as_posix(),
        "limits": {
            "candidate_function_code_lines": MAX_CANDIDATE_FUNCTION_LINES,
            "bundle_code_lines": MAX_BUNDLE_CODE_LINES,
            "callers_with_code": MAX_CALLERS_WITH_CODE,
            "callees_with_code": MAX_CALLEES_WITH_CODE,
            "relationships_per_direction": MAX_RELATIONS_PER_DIRECTION,
        },
        "summary": {
            "scanned_files": len(source_paths),
            "indexed_functions": sum(len(items) for items in functions_by_file.values()),
            "input_candidates": len(candidates),
            "created_bundles": len(bundles),
            "bundles_without_containing_function": missing_owner_count,
            "source_read_errors": len(parse_errors),
            "execution_seconds": round(elapsed, 3),
        },
        "parse_errors": parse_errors,
        "bundles": bundles,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Indexed files: {len(source_paths)}")
    print(f"Indexed functions: {report['summary']['indexed_functions']}")
    print(f"Context bundles: {len(bundles)}")
    print(f"Bundles without containing function: {missing_owner_count}")
    print(f"Execution seconds: {elapsed:.3f}")
    print(f"Report: {output_path.relative_to(project_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
