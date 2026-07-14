"""Upstage Solar 채팅 API를 이용한 AI 튜터 힌트 생성 모듈.

보안 원칙(오늘 정리한 원칙 그대로 적용):
- API 키는 코드에 하드코딩하지 않고 환경변수(.env, 로컬 전용 / 배포 시 K8s Secret)로만 읽는다.
- API 호출이 실패(키 없음/타임아웃/네트워크 오류/비정상 응답)하면 예외를 삼키고 None을 반환해,
  호출부(app.py)가 항상 갖고 있는 정적 hint_levels 폴백으로 자연스럽게 넘어가게 한다.
"""
from __future__ import annotations

import os

import httpx

UPSTAGE_API_KEY = os.environ.get("UPSTAGE_API_KEY", "").strip()
UPSTAGE_MODEL = os.environ.get("UPSTAGE_MODEL", "solar-pro3").strip()
UPSTAGE_BASE_URL = os.environ.get(
    "UPSTAGE_BASE_URL", "https://api.upstage.ai/v1/solar/chat/completions"
).strip()
REQUEST_TIMEOUT_SECONDS = 8.0

_SYSTEM_PROMPT = (
    "너는 리눅스/도커/쿠버네티스/테라폼을 가르치는 친절한 한국어 AI 튜터다. "
    "학생이 실습 문제를 틀렸을 때 정답 명령어를 통째로 알려주지 말고, "
    "왜 틀렸을 가능성이 높은지와 어떤 개념/옵션을 다시 살펴봐야 하는지를 "
    "2~3문장의 짧고 구체적인 한국어 힌트로 알려줘. 과도하게 길게 설명하지 마. "
    "강의자료 발췌가 함께 주어지면 그 내용을 참고해서 힌트에 자연스럽게 녹여내되, "
    "발췌 문장을 그대로 길게 베끼지 말고 네 말로 짧게 요약/재구성해서 알려줘."
)


async def get_ai_hint(
    lab_title: str,
    step_title: str,
    step_description: str,
    user_answer: str,
    attempt_count: int,
    rag_context: str = "",
) -> str | None:
    """AI 힌트를 생성한다. 실패 시 None (호출부에서 정적 힌트로 폴백).

    rag_context: 로컬 RAG(rag.py)로 검색한 강의자료 발췌(있으면). 학생 개인 실습을 돕는
    목적으로만 프롬프트에 짧게 포함되며, 그대로 베끼지 말고 참고만 하도록 지시한다.
    """
    if not UPSTAGE_API_KEY:
        return None

    rag_block = ""
    if rag_context:
        rag_block = f"\n[참고용 강의자료 발췌 (그대로 베끼지 말고 참고만)]\n{rag_context[:1200]}\n"

    user_prompt = (
        f"[실습] {lab_title} - {step_title}\n"
        f"[문제 설명]\n{step_description}\n\n"
        f"[학생이 시도한 입력 (틀림, {attempt_count}번째 시도)]\n{user_answer.strip()[:500]}\n"
        f"{rag_block}\n"
        "이 학생에게 줄 힌트를 작성해줘."
    )

    payload = {
        "model": UPSTAGE_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.5,
        "max_tokens": 220,
    }
    headers = {
        "Authorization": f"Bearer {UPSTAGE_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(UPSTAGE_BASE_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip() or None
    except Exception:
        # 네트워크 오류, 타임아웃, 키 오류, 응답 형식 변경 등 어떤 이유든
        # AI 튜터 실패는 실습 진행을 막아서는 안 되므로 조용히 폴백시킨다.
        return None
