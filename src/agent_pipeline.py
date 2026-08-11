#!/usr/bin/env python3
"""Run the local role-based SAST workflow without connecting an external LLM."""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all local SAST agent roles.")
    parser.add_argument("--prompts", default="config/agent_prompts.json")
    parser.add_argument("--reviews", default="config/security_reviews.json")
    parser.add_argument("--reports", default="reports")
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def short_output(text: str, limit: int = 1200) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "\n... (truncated in run log)"


def command_stage(
    project_root: Path,
    agent: dict[str, Any],
    command: list[str],
    output_files: list[str],
) -> dict[str, Any]:
    started_at = utc_now()
    started = time.perf_counter()
    child_env = os.environ.copy()
    child_env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        cwd=project_root,
        env=child_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    duration = round(time.perf_counter() - started, 3)
    stage = {
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "role": agent["role"],
        "started_at": started_at,
        "execution_seconds": duration,
        "input_files": agent["input_files"],
        "prompt_template": agent["prompt_template"],
        "expected_response_schema": agent["expected_response_schema"],
        "execution_mode": "deterministic_local_program_no_llm_api",
        "command": subprocess.list2cmdline(command),
        "exit_code": completed.returncode,
        "stdout": short_output(completed.stdout),
        "stderr": short_output(completed.stderr),
        "generated_files": output_files if completed.returncode == 0 else [],
        "status": "success" if completed.returncode == 0 else "failed",
        "failures_or_missing_information": [] if completed.returncode == 0 else [short_output(completed.stderr) or "command failed"],
    }
    return stage


def local_stage(
    agent: dict[str, Any],
    action: Callable[[], tuple[str, list[str], list[str]]],
    execution_mode: str,
) -> dict[str, Any]:
    started_at = utc_now()
    started = time.perf_counter()
    try:
        summary, outputs, missing = action()
        status = "success"
        error = ""
    except Exception as exc:  # log the stage before stopping the pipeline
        summary, outputs, missing = "", [], [str(exc)]
        status = "failed"
        error = str(exc)
    return {
        "agent_id": agent["id"],
        "agent_name": agent["name"],
        "role": agent["role"],
        "started_at": started_at,
        "execution_seconds": round(time.perf_counter() - started, 3),
        "input_files": agent["input_files"],
        "prompt_template": agent["prompt_template"],
        "expected_response_schema": agent["expected_response_schema"],
        "execution_mode": execution_mode,
        "command": None,
        "exit_code": 0 if status == "success" else 1,
        "stdout": summary,
        "stderr": error,
        "generated_files": outputs,
        "status": status,
        "failures_or_missing_information": missing,
    }


def create_triage(project_root: Path, reports: Path, reviews: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    contexts = load_json(reports / "context_bundles.json")
    bundles = {item["candidate_id"]: item for item in contexts["bundles"]}
    selected_cases: list[dict[str, Any]] = []
    used: set[str] = set()
    for case in reviews["cases"]:
        source_ids = case["source_candidate_ids"]
        overlap = used.intersection(source_ids)
        if overlap:
            raise ValueError(f"triage duplicate source candidates: {sorted(overlap)}")
        used.update(source_ids)
        candidates = []
        for source_id in source_ids:
            bundle = bundles[source_id]
            candidate = bundle["candidate"]
            if candidate["severity"] not in {"critical", "high"}:
                raise ValueError(f"triage selected non-high candidate: {source_id}")
            candidates.append({
                "candidate_id": source_id,
                "file": candidate["file"],
                "line": candidate["line"],
                "risky_function": candidate["risky_function"],
                "severity": candidate["severity"],
            })
        selected_cases.append({
            "analysis_id": case["analysis_id"],
            "title": case["title"],
            "source_candidate_ids": source_ids,
            "deduplication_reason": case.get("deduplication_reason"),
            "candidates": candidates,
        })
    output = {
        "report_type": "triage_selection",
        "selection_origin": "human_provided_review",
        "automated_ai_selection": False,
        "generated_at": utc_now(),
        "summary": {
            "selected_analysis_cases": len(selected_cases),
            "source_candidates": len(used),
            "deduplicated_candidates": len(used) - len(selected_cases),
        },
        "selected_cases": selected_cases,
    }
    write_json(reports / "triage_selection.json", output)
    summary = (
        f"Selected {len(selected_cases)} analysis cases from {len(used)} high-severity source candidates; "
        f"merged {len(used) - len(selected_cases)} duplicate candidate."
    )
    return summary, ["reports/triage_selection.json"], []


def create_review_handoff(reports: Path, reviews: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    output = {
        "report_type": "security_review_handoff",
        "review_origin": "human_provided_review",
        "automated_ai_analysis": False,
        "external_llm_api_used": False,
        "generated_at": utc_now(),
        "notice": "These reviews were written by a human and are not LLM-generated responses.",
        "reviews": reviews["cases"],
    }
    write_json(reports / "security_review_responses.json", output)
    missing = [
        "No external LLM API was configured or called; human-provided reviews were used.",
        "Security meaning is human-reviewed; deterministic checks validate citations and structure only.",
    ]
    return (
        f"Recorded {len(reviews['cases'])} human-provided reviews with explicit provenance.",
        ["reports/security_review_responses.json"],
        missing,
    )


def badge_class(verdict: str) -> str:
    if verdict == "취약 가능성 높음":
        return "high"
    if verdict == "정보 부족":
        return "unknown"
    return "low"


def evidence_citations(items: list[dict[str, Any]], evidence: dict[str, dict[str, Any]]) -> str:
    citations: list[str] = []
    for item in items:
        for evidence_id in item.get("evidence_ids", []):
            ref = evidence[evidence_id]
            citation = f"{ref['file']}:{ref['line']}"
            if citation not in citations:
                citations.append(citation)
    return ", ".join(citations)


def html_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#f5f7fb;--card:#fff;--ink:#172033;--muted:#64748b;--line:#dbe2ea;--high:#b42318;--high-bg:#fee4e2;--low:#067647;--low-bg:#dcfae6;--unknown:#b54708;--unknown-bg:#fef0c7}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.55}}
main{{max-width:1180px;margin:0 auto;padding:32px 20px 60px}}h1{{margin:0 0 8px;font-size:30px}}h2{{margin-top:34px}}.notice{{color:var(--muted);margin-bottom:24px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}.card,.case{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}}.metric{{font-size:28px;font-weight:750}}.label{{color:var(--muted);font-size:13px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:12px;overflow:hidden}}th,td{{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{background:#eef2f7}}code{{font-size:12px;overflow-wrap:anywhere}}
.badge{{display:inline-block;padding:3px 9px;border-radius:99px;font-size:12px;font-weight:700}}.badge.high{{background:var(--high-bg);color:var(--high)}}.badge.low{{background:var(--low-bg);color:var(--low)}}.badge.unknown{{background:var(--unknown-bg);color:var(--unknown)}}
.case{{margin:14px 0}}.case h3{{margin-top:0}}ul{{padding-left:22px}}details{{margin-top:10px}}pre{{white-space:pre-wrap;background:#101828;color:#e6edf7;padding:14px;border-radius:8px;overflow:auto}}
</style></head><body><main>{body}</main></body></html>"""


def render_analysis_html(analysis: dict[str, Any], verdict_filter: str | None, title: str) -> str:
    results = analysis["results"]
    if verdict_filter:
        results = [item for item in results if item["final_assessment"]["verdict"] == verdict_filter]
    summary = analysis["summary"]
    all_results = analysis["results"]
    verdict_rank = {"취약 가능성 높음": 0, "정보 부족": 1, "취약 가능성 낮음": 2}
    priority = min(
        all_results,
        key=lambda item: (
            verdict_rank[item["final_assessment"]["verdict"]],
            -item["final_assessment"]["confidence"],
        ),
    )
    priority_final = priority["final_assessment"]
    body = [
        f"<h1>{html.escape(title)}</h1>",
        "<p class='notice'>검토 출처: <strong>human_provided_review</strong> · 외부 LLM API 미사용 · 취약점 확정 보고서가 아닌 근거 기반 검토 결과</p>",
        "<section class='cards'>",
        f"<div class='card'><div class='metric'>{len(results)}</div><div class='label'>이 보고서의 분석 건</div></div>",
        f"<div class='card'><div class='metric'>{summary['verified_citations']}</div><div class='label'>원본 대조 인용</div></div>",
        f"<div class='card'><div class='metric'>{summary['verdict_counts'].get('취약 가능성 높음', 0)}</div><div class='label'>취약 가능성 높음</div></div>",
        f"<div class='card'><div class='metric'>{summary['verdict_counts'].get('정보 부족', 0)}</div><div class='label'>정보 부족</div></div>",
        "</section>",
        "<section class='case'><h2>최우선 검토 후보</h2>",
        f"<p><strong>{html.escape(priority['analysis_id'])} — {html.escape(priority['title'])}</strong></p>",
        f"<p><span class='badge {badge_class(priority_final['verdict'])}'>{html.escape(priority_final['verdict'])}</span> · 신뢰도 {priority_final['confidence']}/100</p>",
        f"<p>{html.escape(priority_final['core_basis'][0]['claim'])}</p>",
        "<p class='notice'>코드 근거로 정한 검토 우선순위이며 실제 공격 성공이나 취약점 확정을 뜻하지 않습니다.</p></section>",
        "<section class='case'><h2>용어 설명</h2><ul>",
        "<li><strong>SAST</strong>: 프로그램을 실행하지 않고 소스 코드에서 보안 문제 후보를 찾는 검사</li>",
        "<li><strong>검토 후보</strong>: 추가 확인이 필요한 코드이며 확정 취약점은 아님</li>",
        "<li><strong>취약 가능성 높음</strong>: 입력 경로와 위험 동작의 연결 근거가 강하지만 동적 재현은 별도</li>",
        "<li><strong>취약 가능성 낮음</strong>: 크기 검사나 안전한 할당 같은 반대 근거가 확인됨</li>",
        "<li><strong>정보 부족</strong>: 현재 자료만으로 높음 또는 낮음을 결정할 수 없음</li>",
        "<li><strong>신뢰도</strong>: 판정을 뒷받침하는 근거와 검증의 충분함을 나타내는 점수</li>",
        "</ul></section>",
        "<table><thead><tr><th>ID</th><th>원본 후보</th><th>제목</th><th>판정</th><th>신뢰도</th><th>검증</th></tr></thead><tbody>",
    ]
    for result in results:
        final = result["final_assessment"]
        verdict = final["verdict"]
        body.append(
            "<tr>"
            f"<td>{html.escape(result['analysis_id'])}</td>"
            f"<td>{html.escape(', '.join(result['source_candidate_ids']))}</td>"
            f"<td>{html.escape(result['title'])}</td>"
            f"<td><span class='badge {badge_class(verdict)}'>{html.escape(verdict)}</span></td>"
            f"<td>{final['confidence']}/100</td>"
            f"<td>{html.escape(result['independent_verification']['overall_status'])}</td></tr>"
        )
    body.append("</tbody></table>")

    for result in results:
        final = result["final_assessment"]
        evidence = {item["id"]: item for item in result["evidence"]}
        body.extend([
            "<article class='case'>",
            f"<h3>{html.escape(result['analysis_id'])} — {html.escape(result['title'])}</h3>",
            f"<p><span class='badge {badge_class(final['verdict'])}'>{html.escape(final['verdict'])}</span> · 신뢰도 {final['confidence']}/100 · {html.escape(final['vulnerability_type'])}</p>",
            "<h4>핵심 근거</h4><ul>",
        ])
        for claim in final["core_basis"]:
            body.append(f"<li>{html.escape(claim['claim'])}<br><code>{html.escape(evidence_citations([claim], evidence))}</code></li>")
        body.append("</ul><h4>공격 조건</h4><ul>")
        for condition in final["attack_conditions"]:
            body.append(f"<li>{html.escape(condition['condition'])}<br><code>{html.escape(evidence_citations([condition], evidence))}</code></li>")
        body.append("</ul><h4>반대 근거·안전장치</h4><ul>")
        for claim in final["counterevidence"]:
            body.append(f"<li>{html.escape(claim['claim'])}<br><code>{html.escape(evidence_citations([claim], evidence))}</code></li>")
        body.append("</ul><h4>추가 확인</h4><ul>")
        needs = final["needs_more_information"] or ["없음"]
        body.extend(f"<li>{html.escape(item)}</li>" for item in needs)
        body.append("</ul></article>")
    return html_shell(title, "".join(body))


def create_html_reports(reports: Path) -> tuple[str, list[str], list[str]]:
    analysis = load_json(reports / "analysis_results.json")
    if analysis.get("review_origin") != "human_provided_review":
        raise ValueError("analysis results do not declare human_provided_review")
    files = {
        "security_report.html": (None, "UserLand 근거 검증 보안 보고서"),
        "rejected_candidates.html": ("취약 가능성 낮음", "반박되거나 가능성이 낮은 후보"),
        "needs_more_context.html": ("정보 부족", "추가 문맥이 필요한 후보"),
    }
    for filename, (verdict, title) in files.items():
        (reports / filename).write_text(render_analysis_html(analysis, verdict, title), encoding="utf-8")
    return (
        "Generated accessible HTML summaries with verdict colors, tables, evidence citations, and provenance.",
        [f"reports/{name}" for name in files] + ["reports/agent_run_log.md", "reports/agent_run_log.html"],
        [],
    )


def render_run_log_markdown(run: dict[str, Any]) -> str:
    lines = [
        "# 역할 기반 SAST 에이전트 실행 로그",
        "",
        f"- 실행 ID: `{run['run_id']}`",
        f"- 시작: `{run['started_at']}`",
        f"- 종료: `{run['finished_at']}`",
        f"- 총 실행 시간: {run['execution_seconds']}초",
        "- 외부 LLM API: 사용하지 않음",
        "- 보안 검토 출처: `human_provided_review`",
        "",
        "> 에이전트는 역할을 분리한 워크플로 단계입니다. 이번 실행에서 외부 AI 모델을 호출하지 않았습니다.",
    ]
    for index, stage in enumerate(run["stages"], start=1):
        lines.extend([
            "",
            f"## {index}. {stage['agent_name']}",
            "",
            f"- 역할: {stage['role']}",
            f"- 상태: **{stage['status']}**",
            f"- 실행 시간: {stage['execution_seconds']}초",
            f"- 입력: {', '.join(f'`{item}`' for item in stage['input_files'])}",
            f"- 실행 방식: `{stage['execution_mode']}`",
            f"- 명령: `{stage['command'] or '로컬 데이터 변환 단계'}`",
            f"- 프롬프트/지시문: {stage['prompt_template']}",
            f"- 결과 요약: {stage['stdout'] or '출력 없음'}",
            f"- 생성 파일: {', '.join(f'`{item}`' for item in stage['generated_files']) or '없음'}",
            "- 실패 또는 정보 부족:",
        ])
        lines.extend(f"  - {item}" for item in stage["failures_or_missing_information"] or ["없음"])
    return "\n".join(lines) + "\n"


def render_run_log_html(run: dict[str, Any]) -> str:
    body = [
        "<h1>역할 기반 SAST 에이전트 실행 로그</h1>",
        f"<p class='notice'>실행 ID {html.escape(run['run_id'])} · 총 {run['execution_seconds']}초 · 외부 LLM API 미사용 · human_provided_review</p>",
        "<table><thead><tr><th>순서</th><th>에이전트</th><th>역할</th><th>상태</th><th>시간</th><th>생성 파일</th></tr></thead><tbody>",
    ]
    for index, stage in enumerate(run["stages"], start=1):
        status_class = "low" if stage["status"] == "success" else "high"
        body.append(
            f"<tr><td>{index}</td><td>{html.escape(stage['agent_name'])}</td><td>{html.escape(stage['role'])}</td>"
            f"<td><span class='badge {status_class}'>{html.escape(stage['status'])}</span></td>"
            f"<td>{stage['execution_seconds']}초</td><td>{html.escape(', '.join(stage['generated_files']) or '없음')}</td></tr>"
        )
    body.append("</tbody></table>")
    for index, stage in enumerate(run["stages"], start=1):
        body.extend([
            "<article class='case'>",
            f"<h3>{index}. {html.escape(stage['agent_name'])}</h3>",
            f"<p><strong>입력:</strong> {html.escape(', '.join(stage['input_files']))}</p>",
            f"<p><strong>실행 방식:</strong> {html.escape(stage['execution_mode'])}</p>",
            f"<p><strong>프롬프트/지시문:</strong> {html.escape(stage['prompt_template'])}</p>",
            f"<p><strong>결과 요약:</strong></p><pre>{html.escape(stage['stdout'] or '출력 없음')}</pre>",
            "<p><strong>실패 또는 정보 부족:</strong></p><ul>",
        ])
        body.extend(f"<li>{html.escape(item)}</li>" for item in stage["failures_or_missing_information"] or ["없음"])
        body.append("</ul></article>")
    return html_shell("역할 기반 SAST 에이전트 실행 로그", "".join(body))


def write_run_logs(reports: Path, run: dict[str, Any]) -> None:
    (reports / "agent_run_log.md").write_text(render_run_log_markdown(run), encoding="utf-8")
    (reports / "agent_run_log.html").write_text(render_run_log_html(run), encoding="utf-8")


def main() -> int:
    args = parse_args()
    project_root = Path.cwd().resolve()
    reports = (project_root / args.reports).resolve()
    reports.mkdir(parents=True, exist_ok=True)
    prompt_config = load_json((project_root / args.prompts).resolve())
    reviews = load_json((project_root / args.reviews).resolve())
    if reviews.get("review_origin") != "human_provided_review":
        raise ValueError("review provenance must be human_provided_review")
    agents = {agent["id"]: agent for agent in prompt_config["agents"]}
    required_agents = {
        "scanner_agent", "context_agent", "triage_agent", "security_review_agent",
        "verification_agent", "report_agent",
    }
    if set(agents) != required_agents:
        raise ValueError("agent prompt configuration must define exactly six required roles")

    run_started = time.perf_counter()
    run = {
        "run_id": datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ"),
        "started_at": utc_now(),
        "external_llm_api_used": False,
        "review_origin": "human_provided_review",
        "stages": [],
    }

    stages = run["stages"]
    stages.append(command_stage(
        project_root, agents["scanner_agent"],
        [sys.executable, "-B", "src/scanner.py"],
        ["reports/candidates.json"],
    ))
    if stages[-1]["status"] == "success":
        stages.append(command_stage(
            project_root, agents["context_agent"],
            [sys.executable, "-B", "src/context_builder.py"],
            ["reports/context_bundles.json"],
        ))
    if stages[-1]["status"] == "success":
        stages.append(local_stage(
            agents["triage_agent"],
            lambda: create_triage(project_root, reports, reviews),
            "deterministic_selection_from_human_provided_review",
        ))
    if stages[-1]["status"] == "success":
        stages.append(local_stage(
            agents["security_review_agent"],
            lambda: create_review_handoff(reports, reviews),
            "human_provided_review_no_llm_api",
        ))
    if stages[-1]["status"] == "success":
        stages.append(command_stage(
            project_root, agents["verification_agent"],
            [sys.executable, "-B", "src/analyze_candidates.py"],
            [
                "reports/analysis_results.json", "reports/security_report.md",
                "reports/rejected_candidates.md", "reports/needs_more_context.md",
            ],
        ))
    if stages[-1]["status"] == "success":
        stages.append(local_stage(
            agents["report_agent"],
            lambda: create_html_reports(reports),
            "deterministic_html_rendering_no_llm_api",
        ))

    run["finished_at"] = utc_now()
    run["execution_seconds"] = round(time.perf_counter() - run_started, 3)
    run["status"] = "success" if len(stages) == 6 and all(s["status"] == "success" for s in stages) else "failed"
    write_run_logs(reports, run)
    print(f"Pipeline status: {run['status']}")
    print(f"Completed agent stages: {len(stages)}/6")
    print(f"Execution seconds: {run['execution_seconds']:.3f}")
    print("External LLM API used: no")
    print("Review origin: human_provided_review")
    return 0 if run["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
