#!/usr/bin/env python3
"""Validate submission artifacts and always write Markdown/HTML reports."""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate final SAST submission artifacts.")
    parser.add_argument("--reports", default="reports")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    root = Path.cwd().resolve()
    reports = (root / args.reports).resolve()
    target = (root / "target" / "userland").resolve()
    checks: list[dict[str, Any]] = []

    def check(
        check_id: str,
        name: str,
        action: Callable[[], str],
        related_files: list[str],
    ) -> None:
        try:
            details = action()
            status = "통과"
        except Exception as exc:
            details = str(exc)
            status = "실패"
        checks.append({
            "id": check_id,
            "name": name,
            "status": status,
            "details": details,
            "related_files": related_files,
        })

    data: dict[str, Any] = {}

    def load_required_data() -> str:
        data["candidates"] = load_json(reports / "candidates.json")
        data["contexts"] = load_json(reports / "context_bundles.json")
        data["analysis"] = load_json(reports / "analysis_results.json")
        data["triage"] = load_json(reports / "triage_selection.json")
        data["batch"] = load_json(reports / "batch_results.json")
        data["prompts"] = load_json(root / "config" / "agent_prompts.json")
        data["reviews"] = load_json(root / "config" / "security_reviews.json")
        return "필수 JSON 7개를 UTF-8로 읽었습니다."

    check("V01", "필수 JSON 파일과 문법", load_required_data, [
        "reports/candidates.json", "reports/context_bundles.json",
        "reports/analysis_results.json", "reports/triage_selection.json",
        "reports/batch_results.json", "config/agent_prompts.json", "config/security_reviews.json",
    ])

    def candidate_context_counts() -> str:
        candidate_report = data["candidates"]
        context_report = data["contexts"]
        candidate_count = len(candidate_report["candidates"])
        bundle_count = len(context_report["bundles"])
        if candidate_report["summary"]["total_candidates"] != candidate_count:
            raise ValueError("candidates.json summary와 실제 후보 배열 길이가 다릅니다.")
        if candidate_count != bundle_count:
            raise ValueError(f"후보 {candidate_count}개와 문맥 묶음 {bundle_count}개가 다릅니다.")
        if context_report["summary"]["input_candidates"] != candidate_count:
            raise ValueError("context_bundles.json의 input_candidates가 후보 수와 다릅니다.")
        return f"후보와 문맥 묶음이 각각 {candidate_count}개로 일치합니다."

    check("V02", "후보 수와 문맥 묶음 수 일치", candidate_context_counts, [
        "reports/candidates.json", "reports/context_bundles.json",
    ])

    def analysis_candidate_ids() -> str:
        candidates = data["candidates"]["candidates"]
        bundles = {item["candidate_id"]: item for item in data["contexts"]["bundles"]}
        expected_ids = {f"CAND-{index:04d}" for index in range(1, len(candidates) + 1)}
        if set(bundles) != expected_ids:
            raise ValueError("문맥 묶음 ID가 candidates.json 순번과 연속적으로 대응하지 않습니다.")
        referenced: list[str] = []
        for result in data["analysis"]["results"]:
            for candidate_id in result["source_candidate_ids"]:
                if candidate_id not in bundles:
                    raise ValueError(f"분석 결과가 존재하지 않는 후보를 참조합니다: {candidate_id}")
                index = int(candidate_id.split("-")[1]) - 1
                original = candidates[index]
                bundled = bundles[candidate_id]["candidate"]
                for left, right in (("file", "file"), ("line", "line"), ("function", "risky_function")):
                    if original[left] != bundled[right]:
                        raise ValueError(f"{candidate_id}의 {left}가 후보와 문맥에서 다릅니다.")
                referenced.append(candidate_id)
        if len(referenced) != len(set(referenced)):
            raise ValueError("동일 원본 후보 ID가 여러 분석 건에 중복 보고됐습니다.")
        return f"분석에 사용한 {len(referenced)}개 원본 후보 ID가 모두 실제 후보와 일치하고 중복되지 않습니다."

    check("V03", "분석 후보 ID 존재와 중복 제거", analysis_candidate_ids, [
        "reports/candidates.json", "reports/context_bundles.json", "reports/analysis_results.json",
    ])

    def verify_citations() -> str:
        verified = 0
        for result in data["analysis"]["results"]:
            for evidence in result["evidence"]:
                path = (root / evidence["file"]).resolve()
                if target not in path.parents:
                    raise ValueError(f"인용 경로가 target/userland 밖입니다: {evidence['file']}")
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                line_number = evidence["line"]
                if not 1 <= line_number <= len(lines):
                    raise ValueError(f"줄 번호 범위 오류: {evidence['file']}:{line_number}")
                actual = lines[line_number - 1]
                if evidence["contains"] not in actual:
                    raise ValueError(f"인용 코드 불일치: {evidence['file']}:{line_number}")
                if evidence.get("source_line") != actual:
                    raise ValueError(f"저장된 source_line 불일치: {evidence['file']}:{line_number}")
                verified += 1
        expected = data["analysis"]["summary"]["verified_citations"]
        if verified != expected:
            raise ValueError(f"실제 검증 인용 {verified}개와 집계 {expected}개가 다릅니다.")
        return f"인용 {verified}개의 경로·줄 번호·코드가 UserLand 원본과 일치합니다."

    check("V04", "인용 경로·줄 번호·코드 원문 대조", verify_citations, [
        "reports/analysis_results.json", "target/userland",
    ])

    def verdict_counts() -> str:
        analysis = data["analysis"]
        actual = Counter(item["final_assessment"]["verdict"] for item in analysis["results"])
        expected = Counter(analysis["summary"]["verdict_counts"])
        if actual != expected:
            raise ValueError(f"analysis_results 집계 불일치: 실제 {dict(actual)}, 요약 {dict(expected)}")
        markdown = (reports / "security_report.md").read_text(encoding="utf-8")
        html_report = (reports / "security_report.html").read_text(encoding="utf-8")
        for verdict, count in actual.items():
            md_summary = f"- {verdict}: {count}건"
            if md_summary not in markdown:
                raise ValueError(f"Markdown 요약에 판정 집계가 없습니다: {md_summary}")
            if verdict not in html_report or str(count) not in html_report:
                raise ValueError(f"HTML 보고서에서 판정 또는 집계를 찾지 못했습니다: {verdict}")
        return "판정 집계가 JSON·Markdown·HTML에서 일치합니다: " + ", ".join(f"{k} {v}건" for k, v in actual.items())

    check("V05", "최종 판정 집계 일치", verdict_counts, [
        "reports/analysis_results.json", "reports/security_report.md", "reports/security_report.html",
    ])

    def report_files() -> str:
        required = [
            "security_report.md", "security_report.html",
            "rejected_candidates.md", "rejected_candidates.html",
            "needs_more_context.md", "needs_more_context.html",
            "agent_run_log.md", "agent_run_log.html",
        ]
        missing = [name for name in required if not (reports / name).is_file() or (reports / name).stat().st_size == 0]
        if missing:
            raise ValueError("누락되거나 빈 보고서: " + ", ".join(missing))
        return f"필수 Markdown/HTML 보고서 {len(required)}개가 모두 존재하며 비어 있지 않습니다."

    check("V06", "Markdown과 HTML 보고서 생성", report_files, ["reports"])

    def agent_log_content() -> str:
        log_md = (reports / "agent_run_log.md").read_text(encoding="utf-8")
        log_html = (reports / "agent_run_log.html").read_text(encoding="utf-8")
        agents = data["prompts"]["agents"]
        required_labels = ["역할:", "실행 시간:", "입력:", "프롬프트/지시문:", "결과 요약:", "생성 파일:", "실패 또는 정보 부족:"]
        for agent in agents:
            if agent["name"] not in log_md or agent["name"] not in log_html:
                raise ValueError(f"에이전트 로그 누락: {agent['name']}")
            if agent["prompt_template"] not in log_md:
                raise ValueError(f"프롬프트 템플릿 로그 누락: {agent['name']}")
        for label in required_labels:
            if label not in log_md:
                raise ValueError(f"실행 로그 필드 누락: {label}")
        return f"여섯 역할과 프롬프트 템플릿, 시간·입력·결과·실패 필드가 두 로그에 기록됐습니다."

    check("V07", "에이전트 실행 로그 완전성", agent_log_content, [
        "config/agent_prompts.json", "reports/agent_run_log.md", "reports/agent_run_log.html",
    ])

    def provenance() -> str:
        reviews = data["reviews"]
        analysis = data["analysis"]
        if reviews.get("review_origin") != "human_provided_review" or reviews.get("automated_ai_analysis") is not False:
            raise ValueError("security_reviews.json의 사람 검토 출처가 명확하지 않습니다.")
        if analysis.get("review_origin") != "human_provided_review" or analysis.get("automated_ai_analysis") is not False:
            raise ValueError("analysis_results.json의 사람 검토 출처가 명확하지 않습니다.")
        return "검토 데이터와 분석 결과가 human_provided_review이며 자동 AI 분석이 아님을 명시합니다."

    check("V08", "사람 검토 출처와 AI API 미사용 표기", provenance, [
        "config/security_reviews.json", "reports/analysis_results.json",
    ])

    def report_quality() -> str:
        markdown = (reports / "security_report.md").read_text(encoding="utf-8")
        html_report = (reports / "security_report.html").read_text(encoding="utf-8")
        for required in ["## 용어 설명", "## 최우선 검토 후보", "취약점 확정"]:
            if required not in markdown:
                raise ValueError(f"Markdown 품질 안내 누락: {required}")
        if "용어 설명" not in html_report or "최우선 검토 후보" not in html_report:
            raise ValueError("HTML에 용어 설명 또는 최우선 후보 요약이 없습니다.")
        forbidden = ["공격에 성공했다", "권한 상승이 확인됐다", "확정 취약점이다"]
        combined = markdown + "\n" + html_report
        found = [phrase for phrase in forbidden if phrase in combined]
        if found:
            raise ValueError("근거 없이 확정적으로 표현한 문장 발견: " + ", ".join(found))
        return "판정 구분, 용어 설명, 최우선 후보 요약과 비확정 안내가 있으며 과장 표현은 발견되지 않았습니다."

    check("V09", "보고서 표현과 비전공자 설명", report_quality, [
        "reports/security_report.md", "reports/security_report.html",
    ])

    def target_clean() -> str:
        command = ["git", "-c", f"safe.directory={target.as_posix()}", "-C", str(target), "status", "--short"]
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        if completed.returncode != 0:
            raise ValueError("UserLand Git 상태 확인 실패: " + completed.stderr.strip())
        if completed.stdout.strip():
            raise ValueError("target/userland 원본 변경 발견:\n" + completed.stdout.strip())
        return "target/userland Git 작업 트리에 변경이 없습니다."

    check("V10", "UserLand 원본 무변경", target_clean, ["target/userland"])

    def batch_consistency() -> str:
        batch = data["batch"]
        candidates = data["candidates"]["candidates"]
        if batch.get("batch_count") < 3 or len(batch.get("batches", [])) < 3:
            raise ValueError("실제 실행된 배치가 3개보다 적습니다.")
        batch_candidates = sum(item["candidate_count"] for item in batch["batches"])
        batch_files = sum(item["file_count"] for item in batch["batches"])
        if batch_candidates != len(candidates):
            raise ValueError(f"배치 후보 합 {batch_candidates}와 전체 후보 {len(candidates)}가 다릅니다.")
        if batch_files != data["candidates"]["summary"]["scanned_files"]:
            raise ValueError("배치 파일 합과 전체 검사 파일 수가 다릅니다.")
        relation = batch["whole_scan_relation"]
        if not relation.get("counts_match") or not relation.get("candidate_identity_match"):
            raise ValueError("배치와 전체 스캔의 후보 정체성이 일치하지 않습니다.")
        if any(item["error_count"] for item in batch["batches"]):
            raise ValueError("하나 이상의 배치에 파일 읽기 오류가 있습니다.")
        return f"{len(batch['batches'])}개 배치의 파일 {batch_files}개와 후보 {batch_candidates}개가 전체 분석과 일치하며 오류가 없습니다."

    check("V11", "3개 배치 실행과 전체 분석 일치", batch_consistency, [
        "reports/batch_results.json", "reports/candidates.json",
    ])

    def assignment_deliverables() -> str:
        required = [
            "architecture.md", "architecture.html", "token_strategy.md", "token_strategy.html",
            "prompt_history.md", "prompt_history.html", "differentiation_report.md",
            "differentiation_report.html", "presentation_outline.md",
        ]
        missing = [name for name in required if not (reports / name).is_file() or (reports / name).stat().st_size == 0]
        if missing:
            raise ValueError("필수 과제 문서 누락 또는 빈 파일: " + ", ".join(missing))
        architecture = (reports / "architecture.md").read_text(encoding="utf-8")
        if "```mermaid" not in architecture:
            raise ValueError("architecture.md에 Mermaid 구성도가 없습니다.")
        outline = (reports / "presentation_outline.md").read_text(encoding="utf-8")
        slide_count = len(re.findall(r"^## \d+장\.", outline, flags=re.MULTILINE))
        if not 7 <= slide_count <= 9:
            raise ValueError(f"발표 구성은 7~9장이어야 하지만 {slide_count}장입니다.")
        return f"필수 문서 {len(required)}개, Mermaid 구성도와 {slide_count}장 발표 개요가 준비됐습니다."

    check("V12", "과제 필수 문서와 발표 구성", assignment_deliverables, [
        "reports/architecture.md", "reports/token_strategy.md", "reports/prompt_history.md",
        "reports/differentiation_report.md", "reports/presentation_outline.md",
    ])

    passed = sum(item["status"] == "통과" for item in checks)
    failed = len(checks) - passed
    generated_at = datetime.now(timezone.utc).isoformat()
    elapsed = round(time.perf_counter() - started, 3)
    overall = "통과" if failed == 0 else "실패"

    md = [
        "# 제출 전 자동 검증 보고서", "",
        f"- 전체 결과: **{overall}**", f"- 통과: {passed}개", f"- 실패: {failed}개",
        f"- 실행 시간: {elapsed}초", f"- 생성 시각(UTC): `{generated_at}`", "",
        "> 실패 항목도 숨기지 않고 아래 표와 상세 내용에 기록합니다.", "",
        "| ID | 검증 항목 | 결과 | 관련 파일 |", "|---|---|---|---|",
    ]
    for item in checks:
        md.append(f"| {item['id']} | {item['name']} | **{item['status']}** | {', '.join(item['related_files'])} |")
    for item in checks:
        md.extend(["", f"## {item['id']} — {item['name']}", "", f"- 결과: **{item['status']}**", f"- 설명: {item['details']}", f"- 관련 파일: {', '.join(f'`{p}`' for p in item['related_files'])}"])
    (reports / "validation_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    rows = "".join(
        f"<tr><td>{html.escape(item['id'])}</td><td>{html.escape(item['name'])}</td>"
        f"<td><span class='status {'pass' if item['status']=='통과' else 'fail'}'>{item['status']}</span></td>"
        f"<td>{html.escape(item['details'])}</td><td><code>{html.escape(', '.join(item['related_files']))}</code></td></tr>"
        for item in checks
    )
    html_text = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>제출 전 자동 검증 보고서</title>
<style>body{{margin:0;background:#f5f7fb;color:#172033;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}}main{{max-width:1180px;margin:auto;padding:32px 20px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:20px 0}}.card{{background:white;border:1px solid #dbe2ea;border-radius:12px;padding:18px}}.metric{{font-size:28px;font-weight:800}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:11px;border-bottom:1px solid #dbe2ea;text-align:left;vertical-align:top}}th{{background:#eef2f7}}.status{{padding:3px 9px;border-radius:99px;font-weight:700}}.pass{{background:#dcfae6;color:#067647}}.fail{{background:#fee4e2;color:#b42318}}code{{overflow-wrap:anywhere}}</style></head>
<body><main><h1>제출 전 자동 검증 보고서</h1><p>실패 항목도 숨기지 않고 기록합니다.</p><section class="cards"><div class="card"><div class="metric">{overall}</div><div>전체 결과</div></div><div class="card"><div class="metric">{passed}</div><div>통과</div></div><div class="card"><div class="metric">{failed}</div><div>실패</div></div></section><table><thead><tr><th>ID</th><th>검증 항목</th><th>결과</th><th>설명</th><th>관련 파일</th></tr></thead><tbody>{rows}</tbody></table><p>실행 시간 {elapsed}초 · UTC {html.escape(generated_at)}</p></main></body></html>"""
    (reports / "validation_report.html").write_text(html_text, encoding="utf-8")

    print(f"Validation status: {overall}")
    print(f"Passed: {passed}/{len(checks)}")
    print(f"Failed: {failed}/{len(checks)}")
    print("Reports: reports/validation_report.md, reports/validation_report.html")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
