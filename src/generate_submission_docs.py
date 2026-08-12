#!/usr/bin/env python3
"""Generate reproducible assignment documentation from current reports."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def markdown_to_html(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    in_code = False
    code_language = ""
    code_lines: list[str] = []
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_language = line[3:].strip()
                code_lines = []
            else:
                content = "\n".join(code_lines)
                css_class = "mermaid" if code_language == "mermaid" else "code"
                output.append(f"<pre class='{css_class}'>{html.escape(content)}</pre>")
                in_code = False
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\|[|:\- ]+\|$", lines[index + 1]):
            headers = [cell.strip() for cell in line.strip("|").split("|")]
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                rows.append([cell.strip().replace("\\|", "|") for cell in lines[index].strip("|").split("|")])
                index += 1
            output.append("<table><thead><tr>" + "".join(f"<th>{inline(cell)}</th>" for cell in headers) + "</tr></thead><tbody>")
            output.extend("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in rows)
            output.append("</tbody></table>")
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            output.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if line.startswith("- "):
            output.append("<ul>")
            while index < len(lines) and lines[index].startswith("- "):
                output.append(f"<li>{inline(lines[index][2:])}</li>")
                index += 1
            output.append("</ul>")
            continue
        if re.match(r"^\d+\. ", line):
            output.append("<ol>")
            while index < len(lines) and re.match(r"^\d+\. ", lines[index]):
                output.append(f"<li>{inline(re.sub(r'^\d+\. ', '', lines[index]))}</li>")
                index += 1
            output.append("</ol>")
            continue
        if line.startswith("> "):
            output.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line.strip():
            output.append(f"<p>{inline(line)}</p>")
        index += 1
    mermaid_script = "<script type='module'>import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';mermaid.initialize({startOnLoad:true,theme:'neutral'});</script>" if "```mermaid" in markdown else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{margin:0;background:#f5f7fb;color:#172033;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.65}}main{{max-width:1100px;margin:auto;padding:34px 22px 70px}}h1{{font-size:32px}}h2{{margin-top:36px;border-bottom:2px solid #dbe2ea;padding-bottom:8px}}h3{{margin-top:26px}}p,li{{max-width:92ch}}table{{width:100%;border-collapse:collapse;background:#fff;margin:18px 0;border:1px solid #dbe2ea}}th,td{{padding:11px;border-bottom:1px solid #dbe2ea;text-align:left;vertical-align:top}}th{{background:#eaf0f7}}code{{background:#eef2f7;padding:2px 5px;border-radius:4px}}pre.code,pre.mermaid{{background:#fff;border:1px solid #dbe2ea;border-radius:10px;padding:18px;overflow:auto}}blockquote{{margin:18px 0;padding:12px 16px;border-left:4px solid #667085;background:#fff;color:#475467}}</style>{mermaid_script}</head><body><main>{''.join(output)}</main></body></html>"""


def write_pair(reports: Path, stem: str, title: str, content: str) -> None:
    (reports / f"{stem}.md").write_text(content.rstrip() + "\n", encoding="utf-8")
    (reports / f"{stem}.html").write_text(markdown_to_html(content, title), encoding="utf-8")


def main() -> int:
    root = Path.cwd().resolve()
    reports = root / "reports"
    batch = load_json(reports / "batch_results.json")
    contexts = load_json(reports / "context_bundles.json")
    analysis = load_json(reports / "analysis_results.json")
    prompts = load_json(root / "config" / "agent_prompts.json")
    triage = load_json(reports / "triage_selection.json")

    batch_rows = [
        [
            item["batch_id"], item["selection"]["first_relative_path"], item["selection"]["last_relative_path"],
            item["file_count"], f"{item['estimated_code_lines']:,}", item["candidate_count"],
            item["execution_seconds"], item["error_count"],
        ]
        for item in batch["batches"]
    ]
    batch_table = table(
        ["Batch", "시작 경로", "끝 경로", "파일", "예상 코드 줄", "후보", "시간(초)", "오류"],
        batch_rows,
    )

    architecture = f"""# BugBori 역할 기반 Multi-agent SAST 아키텍처

> 외부 LLM API는 사용하지 않았습니다. 에이전트는 책임·입력·출력이 분리된 재현 가능한 워크플로 단계이며, 보안 의미 분석은 `human_provided_review`로 표시합니다.

## 전체 입력·출력 흐름

```mermaid
flowchart LR
    U["UserLand 654 files"] --> B["Batch Scanner<br/>3 stable batches"]
    U --> S[Scanner Agent]
    R[config/rules.json] --> S
    B --> BR[batch_results.json]
    S --> CAND["candidates.json<br/>583 review candidates"]
    CAND --> C[Context Agent]
    U --> C
    C --> CB["context_bundles.json<br/>583 bounded bundles"]
    CB --> T[Triage Agent]
    T --> TS["triage_selection.json<br/>11 candidates to 10 cases"]
    TS --> SR[Security Review Agent]
    P[agent_prompts.json] --> SR
    H[human_provided_review] --> SR
    SR --> V[Verification Agent]
    U --> V
    V --> AR["analysis_results.json<br/>62 verified citations"]
    AR --> RP[Report Agent]
    RP --> OUT[Markdown + HTML + run logs]
    OUT --> VAL[Submission Validator]
    VAL --> VR[validation_report.md/html]
```

## 에이전트 책임과 신뢰성 장치

{table(
    ["Agent", "핵심 책임", "신뢰성 확보", "실패 시 처리"],
    [
        ["Scanner", "위험 함수 호출 후보 탐지", "주석·문자열 마스킹, 모든 결과를 review_candidate로 표시", "읽기 오류를 파일별 기록"],
        ["Context", "함수·호출자·피호출자·인자 수집", "코드 줄 제한, 누락과 제외 범위 명시", "함수를 못 찾으면 missing_information 유지"],
        ["Triage", "중복 통합과 우선순위 선정", "원본 후보 ID 중복 금지, high 후보 확인", "비정상 ID·중복이면 파이프라인 실패"],
        ["Security Review", "입력 경로·크기·방어 로직 검토", "사람 검토 출처 명시, 정보 부족 허용", "근거가 없으면 확정하지 않음"],
        ["Verification", "파일·줄·인용과 과장 결론 검증", "62개 인용을 원본과 대조", "한 줄이라도 불일치하면 보고서 생성 실패"],
        ["Report", "전체·제외·정보 부족 보고서 생성", "JSON 판정을 변경하지 않고 표현", "누락 파일은 제출 검증에서 실패 표시"],
    ],
)}

## SAST 설계 시 주안점

- **탐지와 확정 분리**: 위험 함수 호출은 시작점이지 취약점 확정이 아닙니다.
- **근거 우선**: 모든 중요한 판단은 파일 경로와 줄 번호를 갖습니다.
- **반대 근거 보존**: 길이 검사와 안전한 할당을 발견하면 낮음 판정에 반영합니다.
- **정보 부족 허용**: 호출 경로나 문자열 규약을 확인할 수 없으면 추측 대신 정보 부족으로 남깁니다.
- **실패 가시성**: 읽기 오류, 누락 함수, 잘린 코드, 검증 실패를 숨기지 않습니다.

## 정규식 호출 관계 분석의 한계

- 함수 포인터, 콜백, 매크로로 만들어진 호출을 놓칠 수 있습니다.
- 같은 함수 이름이 여러 파일에 있으면 잘못 연결될 수 있습니다.
- C++ 템플릿·오버로드·조건부 컴파일을 완전하게 해석하지 못합니다.
- 따라서 호출 관계의 신뢰도는 `regex_approximation_requires_review`이며 최종 검증에서 원문을 다시 봅니다.
"""
    write_pair(reports, "architecture", "BugBori 역할 기반 Multi-agent SAST 아키텍처", architecture)

    limits = contexts["limits"]
    token_strategy = f"""# 토큰 절약 전략과 신뢰도 보존

## 도입 이유

UserLand는 C/C++ 파일 {batch['summary']['source_files']}개, 약 {batch['summary']['estimated_code_lines']:,}줄입니다. 전체 코드를 한 번에 AI 입력으로 보내면 컨텍스트 한계를 넘고 비용·시간이 커지며, 중요한 근거가 긴 코드에 묻힙니다. 이 도구는 **전체 탐색은 로컬에서**, **의미 분석은 우선 후보의 제한된 문맥에서** 수행합니다.

{table(
    ["전략", "현재 설정/동작", "토큰 절약 효과", "신뢰도를 크게 해치지 않는 이유"],
    [
        ["코드 분할", "경로 순서와 코드량으로 3개 안정 배치", "한 번에 다루는 저장소 범위 축소", "모든 파일을 정확히 한 배치에 배정하고 후보 합을 전체 스캔과 대조"],
        ["후보 우선순위화", "위험도 high 후보를 먼저 Triage", "안전 가능성이 높은 546개 medium 후보의 심층 입력 지연", "낮은 후보를 삭제하지 않고 candidates.json에 보존"],
        ["함수별 길이 제한", f"후보 함수 최대 {limits['candidate_function_code_lines']}줄", "거대 함수 전체 전송 방지", "후보 줄 중심으로 자르고 제외 범위를 기록"],
        ["묶음 전체 제한", f"후보당 최대 {limits['bundle_code_lines']}줄", "입력 크기 상한 보장", "가장 가까운 함수와 호출 지점을 먼저 포함"],
        ["호출자/피호출자 제한", f"코드 포함 호출자 {limits['callers_with_code']}개, 피호출자 {limits['callees_with_code']}개", "넓은 호출 그래프 폭발 방지", "관계 메타데이터는 유지하고 코드만 가까운 순서로 제한"],
        ["중복 제거", f"원본 11개 후보를 {triage['summary']['selected_analysis_cases']}개 분석 건으로 통합", "같은 원인 반복 분석 방지", "통합된 원본 ID와 이유를 triage_selection.json에 보존"],
        ["필요 시 추가 문맥", "초기 분석이 요구한 매크로·구조체만 최대 120줄", "무관한 코드 전송 방지", "부족한 항목을 먼저 명시하고 해당 범위만 원본에서 재수집"],
    ],
)}

## 실제 절약 흐름

1. 235,816줄 전체를 로컬 Scanner가 검사합니다.
2. 583개 위치만 후보로 저장합니다.
3. 후보당 최대 220줄의 의미 문맥을 만듭니다.
4. high 후보 11개를 Triage해 10건만 정밀 검토합니다.
5. 필요한 추가 문맥만 수집하고 62개 핵심 인용을 원본 대조합니다.

## 남는 위험

- 제한 밖 코드에 중요한 데이터 흐름이 있을 수 있습니다.
- 정규식 호출 그래프가 간접 호출을 놓칠 수 있습니다.
- 이를 숨기지 않고 `excluded_content`와 `missing_information`에 기록하며, 정보 부족 판정을 허용합니다.
"""
    write_pair(reports, "token_strategy", "토큰 절약 전략", token_strategy)

    actual_by_agent = {
        "scanner_agent": f"654개 파일에서 후보 {batch['whole_scan_relation']['full_scan_candidate_count']}개",
        "context_agent": f"문맥 묶음 {contexts['summary']['created_bundles']}개, 포함 함수 누락 {contexts['summary']['bundles_without_containing_function']}개",
        "triage_agent": f"원본 후보 {triage['summary']['source_candidates']}개를 분석 {triage['summary']['selected_analysis_cases']}건으로 통합",
        "security_review_agent": "10건의 사람 작성 검토를 human_provided_review로 기록; 외부 LLM 호출 없음",
        "verification_agent": f"원본 인용 {analysis['summary']['verified_citations']}개 검증",
        "report_agent": "전체·제외·정보 부족 보고서와 실행 로그를 Markdown/HTML로 생성",
    }
    prompt_rows = []
    for index, agent in enumerate(prompts["agents"], start=1):
        expected = ", ".join(agent["expected_response_schema"].get("required", []))
        prompt_rows.append([
            index, agent["name"], agent["role"], ", ".join(agent["input_files"]),
            agent["prompt_template"], expected, actual_by_agent[agent["id"]],
            "human_provided_review" if agent["id"] == "security_review_agent" else "deterministic_local_result",
        ])
    prompt_history = f"""# 프롬프트 이력과 실제 결과

> 이 문서의 프롬프트는 역할별 분석 지시문입니다. 이번 실행에서는 외부 LLM API를 호출하지 않았습니다. Security Review 결과는 사람이 작성했으며 `human_provided_review`입니다.

## 단계별 기록

{table(["단계", "Agent", "목적", "입력", "프롬프트/지시문", "기대 JSON 필드", "실제 결과", "결과 출처"], prompt_rows)}

## 프롬프트 개선의 핵심

### 초기 형태

```text
이 코드에서 취약점을 찾아줘.
```

문제점은 근거·반대 증거·정보 부족을 요구하지 않아 위험 함수만으로 과장할 수 있다는 점입니다.

### 개선 형태

```text
후보를 취약점이라고 단정하지 마라. 인자별 출처, 외부 입력 경로, 버퍼 크기,
문자열 종료, 길이 검사, 반대 근거를 파일·줄 번호와 함께 작성하라.
정보가 없으면 정보 부족으로 남겨라.
```

개선 결과, 10건 중 8건은 안전장치로 낮음, 1건은 정보 부족, 1건만 높음으로 분리됐습니다. 이것은 자동 AI 분석 결과가 아니라 사람 검토와 결정론적 인용 검증의 결과입니다.

## 응답 보존 위치

- 기대 JSON 스키마: `config/agent_prompts.json`
- 사람 작성 응답: `config/security_reviews.json`
- 역할 전달 기록: `reports/security_review_responses.json`
- 검증 후 결과: `reports/analysis_results.json`
- 실제 실행 기록: `reports/agent_run_log.md`, `reports/agent_run_log.html`
"""
    write_pair(reports, "prompt_history", "프롬프트 이력과 실제 결과", prompt_history)

    differentiation = f"""# 기존 방식과의 차별점

## 한눈에 비교

{table(
    ["항목", "단순 위험 함수 grep", "이 프로젝트"],
    [
        ["탐지", "문자열 일치", "주석·문자열을 가리고 실제 호출 후보 탐지"],
        ["대규모 처리", "저장소 전체를 한 결과로 출력", "경로·파일 수·코드량 기준 3개 안정 배치"],
        ["문맥", "해당 한 줄", "포함 함수, 인자, 호출자·피호출자, 앞뒤 코드"],
        ["중복", "같은 원인을 여러 건 보고", "Triage가 원본 ID를 보존하며 한 분석 건으로 통합"],
        ["판정", "위험 함수 발견을 문제로 간주", "입력 경로·크기·종료·방어 로직을 함께 검토"],
        ["검증", "결과 생성 후 원문 대조 없음", "62개 파일·줄·코드 인용을 실제 원본과 자동 대조"],
        ["불확실성", "누락되기 쉬움", "정보 부족을 별도 판정·보고서로 유지"],
        ["재현성", "실행 기록이 제한적", "프롬프트·JSON·Markdown·HTML·실행 시간·검증 보고서 보존"],
    ],
)}

## 차별화된 흐름

```text
후보 탐지 → 제한된 의미 문맥 → 중복 통합 → 근거 기반 검토
→ 원문 인용 검증 → 낮음/정보 부족 분리 → 재현 가능한 보고서
```

## 실제 가치

- 전체 후보 {batch['whole_scan_relation']['full_scan_candidate_count']}개를 버리지 않고 보존하면서 높은 우선순위만 깊게 봅니다.
- `strcpy`와 `sprintf`가 있어도 안전한 길이 계산을 확인하면 낮음으로 반박합니다.
- 가장 중요한 AN-010을 한눈에 보여주되 실제 공격 성공으로 과장하지 않습니다.
- 실패·누락·정보 부족을 로그와 별도 보고서에 남겨 다음 검토자가 이어갈 수 있습니다.

## 정직한 한계

- 정규식 기반이므로 함수 포인터, 콜백, C++ 복잡 문법의 호출 관계가 부정확할 수 있습니다.
- 사람 검토 10건만 정밀 분석했으며 나머지 후보는 자동 확정되지 않았습니다.
- 동적 빌드·Sanitizer·실제 재현을 수행하지 않았습니다.
- 외부 LLM API를 사용하지 않았으므로 현재 Multi-agent는 역할과 입출력이 분리된 로컬 워크플로입니다.
"""
    write_pair(reports, "differentiation_report", "기존 SAST 방식과의 차별점", differentiation)

    presentation = f"""# BugBori 발표 구성안 — 9장

## 1장. 문제와 목표

- UserLand 규모: C/C++ {batch['summary']['source_files']}개, 약 {batch['summary']['estimated_code_lines']:,}줄
- 문제: 전체 코드를 AI에 한 번에 넣을 수 없고 위험 함수 검색은 오탐이 많음
- 목표: 위험한 부분부터 근거로 검토하고 불확실성을 숨기지 않는 SAST
- 발표 한 문장: **BugBori는 많이 찾는 도구가 아니라, 왜 위험한지를 검증하는 도구**

## 2장. 전체 아키텍처

- Scanner → Context → Triage → Security Review → Verification → Report
- 각 Agent의 입력과 출력 파일을 화살표로 설명
- 외부 LLM 미사용, 사람 검토 출처 명시
- 시각 자료: `reports/architecture.html`

## 3장. 대규모 저장소 Batch 처리

- 경로 정렬 + 물리 코드 줄 수 균형으로 3개 안정 배치
- 동일 저장소와 batch 수이면 같은 경로 구간 생성
- 전체 스캔 후보와 배치 후보의 파일·줄·함수 일치 검증

{batch_table}

## 4장. Agent 역할 분담과 신뢰성

- Scanner: 넓게 찾기
- Context: 필요한 문맥만 모으기
- Triage: 중복 제거·우선순위
- Review: 공격 경로와 안전장치 모두 보기
- Verification: 인용 62개 원문 확인
- Report: 낮음과 정보 부족도 별도 공개

## 5장. 토큰 절약 설계

- 후보 함수 {limits['candidate_function_code_lines']}줄, 묶음 {limits['bundle_code_lines']}줄 제한
- 호출자 {limits['callers_with_code']}개, 피호출자 {limits['callees_with_code']}개 코드 우선 포함
- 583개 후보 중 high 11개를 10건으로 통합
- 필요한 매크로·구조체만 추가 수집
- 제외 범위와 부족 정보를 기록해 신뢰도 손실을 가시화

## 6장. 실제 3개 Batch 결과

- 배치 후보 합 {batch['summary']['batch_candidates']}개 = 전체 후보 {batch['whole_scan_relation']['full_scan_candidate_count']}개
- 오류 {batch['summary']['errors']}건
- 후보 분포가 다른 이유: 경로별 코드 성격과 위험 함수 사용량이 다름
- 핵심 메시지: 균등 후보 수가 아니라 균형 코드량과 누락 없는 파일 배정이 목표

## 7장. AN-010 분석 사례

- 명령행 값 → apply_override → foreach_override_target → 256바이트 배열 strcpy
- 판정: 취약 가능성 높음, 신뢰도 97
- 근거: `dtoverlay.c:1852`, `dtoverlay.c:1859` 및 두 CLI 전달 경로
- 주의: 코드상 우선 후보이며 실제 공격 성공·권한 상승은 확인하지 않음

## 8장. 차별점과 한계

- 차별점: 후보 → 문맥 → 중복 통합 → 근거 검증 → 정보 부족 → 재현 보고서
- 일반 grep과 비교 표 제시
- 한계: 정규식 호출 그래프, 10건 사람 검토, 동적 검증 부재
- 정직한 한계 공개가 오히려 신뢰성을 높인다는 메시지

## 9장. 결론과 향후 계획

- 성과: 654개 파일, 3개 배치, 583개 후보, 62개 인용 검증, 제출 검증 자동화
- 다음 1: AN-010 안전한 동적 재현과 Sanitizer 확인
- 다음 2: AN-007 libfdt 문자열 종료 규약 조사
- 다음 3: 승인된 환경에서만 역할별 LLM 응답을 JSON 스키마로 연결
- 마무리: **확정할 수 있는 것과 없는 것을 분리한 근거 중심 SAST**
"""
    (reports / "presentation_outline.md").write_text(presentation.rstrip() + "\n", encoding="utf-8")

    print("Generated documentation:")
    for name in [
        "architecture.md", "architecture.html", "token_strategy.md", "token_strategy.html",
        "prompt_history.md", "prompt_history.html", "differentiation_report.md",
        "differentiation_report.html", "presentation_outline.md",
    ]:
        print(f"- reports/{name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
