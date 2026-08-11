#!/usr/bin/env python3
"""Validate reviewed security evidence and generate human-readable reports.

No AI API is used. Human-reviewed claims live in config/security_reviews.json;
this program verifies every cited source line and packages the results.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALID_VERDICTS = {"취약 가능성 높음", "취약 가능성 낮음", "정보 부족"}
VALID_VERIFICATION = {"확인됨", "반박됨", "추가 정보 필요"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate verified security review reports.")
    parser.add_argument("--contexts", default="reports/context_bundles.json")
    parser.add_argument("--reviews", default="config/security_reviews.json")
    parser.add_argument("--output-dir", default="reports")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def source_lines(project_root: Path, relative_path: str, cache: dict[str, list[str]]) -> list[str]:
    if relative_path not in cache:
        path = (project_root / relative_path).resolve()
        target_root = (project_root / "target" / "userland").resolve()
        if target_root not in path.parents:
            raise ValueError(f"evidence path is outside target/userland: {relative_path}")
        cache[relative_path] = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return cache[relative_path]


def validate_evidence(
    case: dict[str, Any], project_root: Path, cache: dict[str, list[str]]
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in case["evidence"]:
        evidence_id = item["id"]
        if evidence_id in indexed:
            raise ValueError(f"{case['analysis_id']}: duplicate evidence id {evidence_id}")
        lines = source_lines(project_root, item["file"], cache)
        line_number = item["line"]
        if line_number < 1 or line_number > len(lines):
            raise ValueError(f"{case['analysis_id']}: invalid line {item['file']}:{line_number}")
        actual = lines[line_number - 1]
        if item["contains"] not in actual:
            raise ValueError(
                f"{case['analysis_id']}: citation mismatch at {item['file']}:{line_number}; "
                f"expected {item['contains']!r}, got {actual!r}"
            )
        enriched = dict(item)
        enriched["source_line"] = actual
        enriched["citation_verified"] = True
        indexed[evidence_id] = enriched
    return indexed


def validate_references(case: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> None:
    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == "evidence_ids":
                    if not nested:
                        raise ValueError(f"{case['analysis_id']}: empty evidence_ids")
                    unknown = set(nested) - set(evidence)
                    if unknown:
                        raise ValueError(f"{case['analysis_id']}: unknown evidence ids {sorted(unknown)}")
                else:
                    walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(case["initial_analysis"])
    walk(case["independent_verification"])
    walk(case["final_assessment"])


def collect_additional_context(
    case: dict[str, Any], project_root: Path, cache: dict[str, list[str]]
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    total_lines = 0
    for request in case.get("additional_context", []):
        lines = source_lines(project_root, request["file"], cache)
        start = request["start_line"]
        end = request["end_line"]
        if start < 1 or end < start or end > len(lines):
            raise ValueError(f"{case['analysis_id']}: invalid context range {request}")
        total_lines += end - start + 1
        if total_lines > 120:
            raise ValueError(f"{case['analysis_id']}: additional context exceeds 120 lines")
        collected.append(
            {
                **request,
                "context_origin": "additional_context_after_initial_review",
                "code": "\n".join(lines[start - 1:end]),
            }
        )
    return collected


def citations(ids: list[str], evidence: dict[str, dict[str, Any]]) -> str:
    return ", ".join(f"`{evidence[item]['file']}:{evidence[item]['line']}`" for item in ids)


def render_claims(items: list[dict[str, Any]], evidence: dict[str, dict[str, Any]]) -> list[str]:
    rendered: list[str] = []
    for item in items:
        text = item.get("claim") or item.get("finding") or item.get("condition") or item.get("step")
        rendered.append(f"- {text} ({citations(item['evidence_ids'], evidence)})")
    return rendered


def render_security_report(results: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    verdict_rank = {"취약 가능성 높음": 0, "정보 부족": 1, "취약 가능성 낮음": 2}
    priority = min(
        results,
        key=lambda item: (
            verdict_rank[item["final_assessment"]["verdict"]],
            -item["final_assessment"]["confidence"],
        ),
    )
    priority_final = priority["final_assessment"]
    lines = [
        "# UserLand 보안 후보 검증 보고서",
        "",
        "> 위험 함수 호출만으로 취약점을 확정하지 않았습니다. 모든 인용은 생성 시 실제 원본 줄과 대조했습니다.",
        "",
        "## 요약",
        "",
        f"- 분석 건수: {summary['analyzed_cases']}건",
        f"- 원본 후보 수: {summary['source_candidates']}개",
        f"- 중복 묶음: {summary['deduplicated_candidates']}개 후보가 동일 원인으로 통합됨",
        f"- 취약 가능성 높음: {summary['verdict_counts'].get('취약 가능성 높음', 0)}건",
        f"- 취약 가능성 낮음: {summary['verdict_counts'].get('취약 가능성 낮음', 0)}건",
        f"- 정보 부족: {summary['verdict_counts'].get('정보 부족', 0)}건",
        "",
        "## 최우선 검토 후보",
        "",
        f"- 분석 ID: **{priority['analysis_id']}**",
        f"- 제목: {priority['title']}",
        f"- 판정: **{priority_final['verdict']}** (신뢰도 {priority_final['confidence']}/100)",
        f"- 우선 이유: {priority_final['core_basis'][0]['claim']}",
        f"- 주의: 코드 근거로 정한 검토 우선순위이며 실제 공격 성공이나 취약점 확정을 뜻하지 않습니다.",
        "",
        "## 용어 설명",
        "",
        "- **SAST**: 프로그램을 실행하지 않고 소스 코드를 읽어 보안 문제 후보를 찾는 검사입니다.",
        "- **검토 후보**: 위험해 보이므로 추가 확인이 필요한 코드이며, 확정 취약점은 아닙니다.",
        "- **취약 가능성 높음**: 입력 경로와 위험 동작의 연결 근거가 강하지만 동적 재현은 별도입니다.",
        "- **취약 가능성 낮음**: 크기 검사나 안전한 할당처럼 반대 근거가 확인된 후보입니다.",
        "- **정보 부족**: 현재 코드 묶음만으로 높음 또는 낮음을 책임 있게 결정할 수 없습니다.",
        "- **신뢰도**: 최종 판정을 뒷받침하는 인용과 검증의 충분함을 0~100으로 표현한 값입니다.",
        "- **오탐**: 검사기가 위험하다고 표시했지만 추가 검토에서 안전한 사용으로 확인된 경우입니다.",
        "",
        "## 전체 판정",
        "",
        "| 분석 ID | 원본 후보 | 위험 함수 | 최종 판정 | 신뢰도 | 검증 |",
        "|---|---|---|---|---:|---|",
    ]
    for result in results:
        source_ids = ", ".join(result["source_candidate_ids"])
        functions = ", ".join(result["risky_functions"])
        final = result["final_assessment"]
        lines.append(
            f"| {result['analysis_id']} | {source_ids} | `{functions}` | "
            f"{final['verdict']} | {final['confidence']} | {result['independent_verification']['overall_status']} |"
        )

    for result in results:
        evidence = {item["id"]: item for item in result["evidence"]}
        initial = result["initial_analysis"]
        final = result["final_assessment"]
        lines.extend([
            "",
            f"## {result['analysis_id']} — {result['title']}",
            "",
            f"- 원본 후보: {', '.join(result['source_candidate_ids'])}",
            f"- 최초 판정: {initial['verdict']}",
            f"- 독립 검증: {result['independent_verification']['overall_status']}",
            f"- 최종 판정: **{final['verdict']}** (신뢰도 {final['confidence']}/100)",
            f"- 예상 유형: {final['vulnerability_type']}",
            "",
            "### 핵심 근거",
            "",
            *render_claims(final["core_basis"], evidence),
            "",
            "### 공격에 필요한 조건",
            "",
            *render_claims(final["attack_conditions"], evidence),
            "",
            "### 반대 근거와 안전장치",
            "",
            *render_claims(final["counterevidence"], evidence),
            "",
            "### 추가 확인 사항",
            "",
        ])
        needs = final["needs_more_information"]
        lines.extend(f"- {item}" for item in needs or ["없음"])
    return "\n".join(lines) + "\n"


def render_filtered_report(
    title: str, intro: str, results: list[dict[str, Any]], verdict: str
) -> str:
    selected = [item for item in results if item["final_assessment"]["verdict"] == verdict]
    lines = [f"# {title}", "", intro, "", f"총 {len(selected)}건", ""]
    for item in selected:
        final = item["final_assessment"]
        lines.extend([
            f"## {item['analysis_id']} — {item['title']}",
            "",
            f"- 원본 후보: {', '.join(item['source_candidate_ids'])}",
            f"- 신뢰도: {final['confidence']}/100",
            f"- 독립 검증: {item['independent_verification']['overall_status']}",
        ])
        if verdict == "취약 가능성 낮음":
            lines.append(f"- 제외 이유: {final['disposition_reason']}")
        else:
            lines.append("- 필요한 정보:")
            lines.extend(f"  - {need}" for need in final["needs_more_information"])
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    project_root = Path.cwd().resolve()
    context_report = load_json((project_root / args.contexts).resolve())
    review_data = load_json((project_root / args.reviews).resolve())
    if review_data.get("review_origin") != "human_provided_review":
        raise ValueError("security reviews must explicitly declare human_provided_review")
    if review_data.get("automated_ai_analysis") is not False:
        raise ValueError("security reviews must not be represented as automated AI analysis")
    output_dir = (project_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    bundles = {item["candidate_id"]: item for item in context_report["bundles"]}
    cases = review_data["cases"]
    if len(cases) != 10:
        raise ValueError(f"expected exactly 10 review cases, got {len(cases)}")

    analysis_ids: set[str] = set()
    source_ids: list[str] = []
    results: list[dict[str, Any]] = []
    source_cache: dict[str, list[str]] = {}
    for case in cases:
        if case["analysis_id"] in analysis_ids:
            raise ValueError(f"duplicate analysis id: {case['analysis_id']}")
        analysis_ids.add(case["analysis_id"])
        unknown = set(case["source_candidate_ids"]) - set(bundles)
        if unknown:
            raise ValueError(f"{case['analysis_id']}: unknown source candidates {sorted(unknown)}")
        overlap = set(case["source_candidate_ids"]) & set(source_ids)
        if overlap:
            raise ValueError(f"source candidates included twice: {sorted(overlap)}")
        source_ids.extend(case["source_candidate_ids"])
        for candidate_id in case["source_candidate_ids"]:
            if bundles[candidate_id]["candidate"]["severity"] not in {"critical", "high"}:
                raise ValueError(f"{candidate_id} is not a high-priority candidate")

        if case["initial_analysis"]["verdict"] not in VALID_VERDICTS:
            raise ValueError(f"{case['analysis_id']}: invalid initial verdict")
        if case["final_assessment"]["verdict"] not in VALID_VERDICTS:
            raise ValueError(f"{case['analysis_id']}: invalid final verdict")
        if case["independent_verification"]["overall_status"] not in VALID_VERIFICATION:
            raise ValueError(f"{case['analysis_id']}: invalid verification status")
        confidence = case["final_assessment"]["confidence"]
        if not isinstance(confidence, int) or not 0 <= confidence <= 100:
            raise ValueError(f"{case['analysis_id']}: confidence must be 0..100")

        evidence = validate_evidence(case, project_root, source_cache)
        validate_references(case, evidence)
        additional = collect_additional_context(case, project_root, source_cache)
        source_bundles = [bundles[item] for item in case["source_candidate_ids"]]
        result = {
            "analysis_id": case["analysis_id"],
            "title": case["title"],
            "review_origin": "human_provided_review",
            "automated_ai_analysis": False,
            "source_candidate_ids": case["source_candidate_ids"],
            "deduplication_reason": case.get("deduplication_reason"),
            "risky_functions": sorted({item["candidate"]["risky_function"] for item in source_bundles}),
            "initial_context": source_bundles,
            "additional_context": additional,
            "evidence": list(evidence.values()),
            "initial_analysis": case["initial_analysis"],
            "independent_verification": {
                **case["independent_verification"],
                "citation_check": "확인됨",
                "verified_citations": len(evidence),
            },
            "final_assessment": case["final_assessment"],
        }
        results.append(result)

    verdict_counts = Counter(item["final_assessment"]["verdict"] for item in results)
    elapsed = round(time.perf_counter() - started, 3)
    summary = {
        "analyzed_cases": len(results),
        "source_candidates": len(source_ids),
        "deduplicated_candidates": len(source_ids) - len(results),
        "verdict_counts": dict(verdict_counts),
        "verified_citations": sum(len(item["evidence"]) for item in results),
        "execution_seconds": elapsed,
    }
    output = {
        "report_type": "evidence_verified_security_analysis",
        "notice": "No AI API or exploit execution was used; conclusions are bounded by cited source evidence.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_mode": "manual_review_plus_deterministic_citation_verification",
        "review_origin": "human_provided_review",
        "automated_ai_analysis": False,
        "summary": summary,
        "results": results,
    }
    (output_dir / "analysis_results.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "security_report.md").write_text(
        render_security_report(results, summary), encoding="utf-8"
    )
    (output_dir / "rejected_candidates.md").write_text(
        render_filtered_report(
            "반박되거나 가능성이 낮은 후보",
            "안전장치가 원문으로 확인되어 현재 우선순위에서 제외한 후보입니다.",
            results,
            "취약 가능성 낮음",
        ),
        encoding="utf-8",
    )
    (output_dir / "needs_more_context.md").write_text(
        render_filtered_report(
            "추가 문맥이 필요한 후보",
            "현재 증거만으로 높음 또는 낮음을 책임 있게 확정할 수 없는 후보입니다.",
            results,
            "정보 부족",
        ),
        encoding="utf-8",
    )
    print(f"Analyzed cases: {len(results)}")
    print(f"Source candidates: {len(source_ids)}")
    print(f"Verified citations: {summary['verified_citations']}")
    print(f"Verdicts: {dict(verdict_counts)}")
    print(f"Execution seconds: {elapsed:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
