#!/usr/bin/env python3
"""
DB-care 하네스 오케스트레이터 v2
Planner → Generator(Claude Code) → Evaluator 루프 자동 실행
"""

import anthropic
import subprocess
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# ─── 설정 ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent   # db-care/ 폴더
HARNESS_DIR  = Path(__file__).parent           # harness/ 폴더
CLAUDE_MD    = PROJECT_ROOT / "CLAUDE.md"

client = anthropic.Anthropic()   # ANTHROPIC_API_KEY 환경변수 필요
MODEL  = "claude-opus-4-6"

# ─── 유틸리티 ─────────────────────────────────────────────────────────────────

def read_file(path: Path) -> str:
    try:    return path.read_text(encoding="utf-8")
    except: return ""

def write_file(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  📝 저장: {path.relative_to(PROJECT_ROOT)}")

def log(msg: str, level: str = "INFO"):
    icons = {"INFO":"ℹ️","SUCCESS":"✅","ERROR":"❌","WARN":"⚠️","SPRINT":"🏃"}
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n{icons.get(level,'•')} [{ts}] {msg}")

def call_claude(system: str, user: str, max_tokens: int = 4000) -> str:
    resp = client.messages.create(
        model=MODEL, max_tokens=max_tokens,
        system=system,
        messages=[{"role":"user","content":user}]
    )
    return resp.content[0].text

def extract_json(text: str) -> dict:
    s = text.find("{"); e = text.rfind("}") + 1
    return json.loads(text[s:e])

# ─── Generator ───────────────────────────────────────────────────────────────

def build_generator_prompt(sprint_num: int) -> str:
    contract   = read_file(HARNESS_DIR / f"sprint_{sprint_num:02d}_contract.md")
    claude_md  = read_file(CLAUDE_MD)
    status     = read_file(HARNESS_DIR / "sprint_status.md")
    prev_result = ""
    if sprint_num > 1:
        prev_result = f"\n\n# 이전 스프린트 결과\n{read_file(HARNESS_DIR / f'sprint_{sprint_num-1:02d}_result.md')}"

    # 이전 평가에서 피드백이 있으면 포함
    feedbacks = sorted(HARNESS_DIR.glob(f"sprint_{sprint_num:02d}_feedback_*.md"))
    feedback_text = ""
    if feedbacks:
        latest = feedbacks[-1]
        feedback_text = f"\n\n# ⚠️ 이전 시도 평가 피드백 (반드시 반영)\n{read_file(latest)}"

    return f"""# DB-care Sprint {sprint_num} 구현 요청

## 필수 선행 작업 (순서대로 실행)
1. CLAUDE.md 전체 읽기 — 프로젝트 맥락, 디자인 시스템, API 스펙 파악
2. harness/sprint_status.md 읽기 — 현재 진행 상황 확인
3. harness/sprint_{sprint_num:02d}_contract.md 읽기 — 이번 스프린트 요구사항 파악

## 이번 스프린트 계약 내용
{contract}
{prev_result}
{feedback_text}

## 구현 지침
- 계약의 모든 구현 항목을 빠짐없이 구현하라
- CLAUDE.md의 디자인 시스템(색상, 컴포넌트 Props)을 정확히 따르라
- 각 파일은 실제로 작동하는 코드여야 한다 (빈 껍데기 금지)
- 구현 완료 후 서버/앱을 실제로 실행해서 동작을 직접 확인하라
- 완료 후 harness/sprint_{sprint_num:02d}_result.md 작성:
  - 생성/수정된 파일 목록
  - 구현된 기능 요약
  - 서버/앱 실행 결과
  - 알려진 이슈 (있다면)
- harness/sprint_status.md에서 Sprint {sprint_num} 상태를 "✅ 완료"로 업데이트

## ⚠️ 중요
계약의 검증 기준을 하나씩 확인하며 구현하라.
충족하지 못한 항목이 있으면 즉시 해결하고 넘어가라.
"""

def run_generator(sprint_num: int) -> str:
    log(f"Generator 실행 — Sprint {sprint_num}", "SPRINT")
    prompt = build_generator_prompt(sprint_num)

    print(f"\n{'─'*60}")
    print(f"[Claude Code 프롬프트 미리보기 — Sprint {sprint_num}]")
    print(prompt[:500] + "...\n")
    print(f"{'─'*60}")

    try:
        result = subprocess.run(
            ["claude", "--dangerously-skip-permissions", "-p", prompt],
            cwd=str(PROJECT_ROOT),
            capture_output=False,  # 실시간 출력
            text=True,
            timeout=3600
        )
        log(f"Generator 완료 (exit: {result.returncode})",
            "SUCCESS" if result.returncode == 0 else "WARN")
        return "DONE"
    except subprocess.TimeoutExpired:
        log("Generator 타임아웃 (1시간 초과)", "ERROR")
        return "TIMEOUT"
    except FileNotFoundError:
        log("'claude' 명령어 없음. npm install -g @anthropic-ai/claude-code 실행 필요.", "ERROR")
        return "NOT_FOUND"

# ─── Evaluator ───────────────────────────────────────────────────────────────

def run_evaluator(sprint_num: int) -> dict:
    log(f"Evaluator 실행 — Sprint {sprint_num}", "SPRINT")

    contract    = read_file(HARNESS_DIR / f"sprint_{sprint_num:02d}_contract.md")
    result_log  = read_file(HARNESS_DIR / f"sprint_{sprint_num:02d}_result.md")
    claude_md   = read_file(CLAUDE_MD)

    # 실제 파일 인벤토리
    backend_py  = [str(f.relative_to(PROJECT_ROOT)) for f in PROJECT_ROOT.glob("backend/**/*.py")]
    frontend_jsx = [str(f.relative_to(PROJECT_ROOT)) for f in PROJECT_ROOT.glob("frontend/src/**/*.jsx")]
    file_list = f"Backend py: {backend_py}\nFrontend jsx: {frontend_jsx}"

    system = f"""당신은 엄격한 QA 엔지니어입니다.
스프린트 계약의 검증 기준을 하나씩 확인하고 PASS/FAIL을 판정하세요.

원칙:
- 관대하지 마세요. 기준 미충족 = FAIL
- 실패 원인은 코드 레벨(파일명, 함수명, 줄번호)로 구체적으로 명시하세요
- 반드시 JSON만 응답하세요 (마크다운 코드펜스 없이)

CLAUDE.md:
{claude_md}
"""

    user = f"""Sprint {sprint_num} 평가를 수행하세요.

## 계약
{contract}

## 구현 결과 로그
{result_log if result_log else "result.md 없음 — 구현 미완료 가능성"}

## 파일 현황
{file_list}

## 응답 형식 (JSON만)
{{
  "sprint": {sprint_num},
  "overall": "PASS or FAIL",
  "score": 0~100,
  "criteria_results": [
    {{"id": 1, "criterion": "...", "result": "PASS or FAIL", "reason": "..."}}
  ],
  "critical_issues": ["즉시 수정 필요한 이슈 목록"],
  "feedback_for_generator": "구체적 수정 지시 (파일명, 코드 수준)",
  "approved": true or false
}}"""

    raw = call_claude(system, user, max_tokens=3000)

    try:
        eval_result = extract_json(raw)
    except Exception as e:
        log(f"평가 JSON 파싱 실패: {e}", "ERROR")
        eval_result = {
            "sprint": sprint_num, "overall": "FAIL", "score": 0,
            "criteria_results": [], "critical_issues": ["평가 파싱 실패"],
            "feedback_for_generator": "result.md를 다시 작성하고 재시도하세요.",
            "approved": False
        }

    eval_path = HARNESS_DIR / f"sprint_{sprint_num:02d}_eval.json"
    write_file(eval_path, json.dumps(eval_result, ensure_ascii=False, indent=2))

    log(f"평가: {eval_result['overall']} ({eval_result['score']}/100)",
        "SUCCESS" if eval_result["approved"] else "ERROR")

    # 세부 결과 출력
    for c in eval_result.get("criteria_results", []):
        icon = "✅" if c["result"] == "PASS" else "❌"
        print(f"  {icon} [{c['id']}] {c['criterion'][:50]} — {c['reason'][:80]}")

    return eval_result

# ─── 스프린트 루프 ────────────────────────────────────────────────────────────

def run_sprint(sprint_num: int, max_retries: int = 3) -> bool:
    contract_path = HARNESS_DIR / f"sprint_{sprint_num:02d}_contract.md"
    if not contract_path.exists():
        log(f"Sprint {sprint_num} 계약 파일 없음. 건너뜀.", "WARN")
        return False

    for attempt in range(1, max_retries + 1):
        log(f"Sprint {sprint_num} — 시도 {attempt}/{max_retries}", "SPRINT")

        gen_result = run_generator(sprint_num)
        if gen_result in ("TIMEOUT", "NOT_FOUND"):
            return False

        eval_result = run_evaluator(sprint_num)

        if eval_result["approved"]:
            log(f"Sprint {sprint_num} PASS ✅ — 다음으로 이동합니다.", "SUCCESS")
            return True

        # 피드백 저장
        fb_path = HARNESS_DIR / f"sprint_{sprint_num:02d}_feedback_{attempt}.md"
        issues = "\n".join(f"- {i}" for i in eval_result["critical_issues"])
        write_file(fb_path, f"# Sprint {sprint_num} 시도 {attempt} 피드백\n\n"
                            f"## 점수: {eval_result['score']}/100\n\n"
                            f"## 즉시 수정 필요\n{issues}\n\n"
                            f"## Generator 지시\n{eval_result['feedback_for_generator']}")

        if attempt < max_retries:
            log(f"Sprint {sprint_num} FAIL — 피드백 반영 후 재시도합니다.", "WARN")
        else:
            log(f"Sprint {sprint_num} 최대 재시도 초과. 수동 검토 필요.", "ERROR")
            return False

    return False

# ─── 메인 ────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("  DB-care 하네스 엔지니어링 v2")
    print("="*60)

    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end   = int(sys.argv[2]) if len(sys.argv) > 2 else 6

    log(f"Sprint {start}~{end} 실행")

    for num in range(start, end + 1):
        success = run_sprint(num)
        if not success:
            log(f"Sprint {num} 실패 — 하네스 중단.", "ERROR")
            print(f"\n수동 확인: harness/sprint_{num:02d}_eval.json")
            sys.exit(1)

    log("전체 스프린트 완료 🎉 프로토타입 빌드 성공!", "SUCCESS")

if __name__ == "__main__":
    main()
