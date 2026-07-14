"""labs/*.yaml 을 파싱해 앱에서 쓰기 좋은 자료구조로 올려주는 모듈.

두 가지 채점 방식을 지원한다.
- 텍스트 매칭(answer_contains): linux/docker 랩. 실제 실행 없이 입력 문자열에 정답
  키워드가 다 들어있는지만 본다 (구 mock 방식의 확장).
- 실행 기반 검증(execution + verify): k8s/terraform 랩. 사용자가 입력한 명령을 실제로
  실행시키고(executor.py), 그 뒤 verify에 정의된 "우리가 직접 관리하는" 검증 명령/파일
  체크를 실행해 실제 상태가 바뀌었는지 확인한다. verify 항목은 사용자 입력이 아니라
  랩 작성자가 정의한 신뢰 입력이라 answer_contains보다 훨씬 안전하고 정확하다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

LABS_DIR = Path(__file__).parent / "labs"


@dataclass
class VerifyCheck:
    type: str = "command"  # command | file_exists | file_absent | dir_exists | file_contains | file_not_contains
    cmd: str = ""
    path: str = ""
    expect: str = ""


@dataclass
class Step:
    id: int
    title: str
    description: str
    answer_contains: list[str] = field(default_factory=list)
    hint_levels: list[str] = field(default_factory=list)
    input_type: str = "command"  # command | file (파일로 저장 후 검증)
    target_path: str = ""
    verify: list[VerifyCheck] = field(default_factory=list)
    # 이 단계를 재시도할 때 이전 시도가 남긴 리소스와 충돌(AlreadyExists 등)하지 않도록,
    # 학생 명령을 실행하기 전에 먼저 실행하는 신뢰된(랩 작성자 정의) 정리 명령들.
    pre_cleanup: list[str] = field(default_factory=list)

    def check(self, submitted_text: str) -> bool:
        """(텍스트 매칭 랩 전용) 제출한 텍스트에 정답 키워드가 모두 포함되어 있으면 통과."""
        normalized = " ".join(submitted_text.split()).lower()
        return all(" ".join(kw.split()).lower() in normalized for kw in self.answer_contains)

    def static_hint(self, level: int) -> str:
        if not self.hint_levels:
            return "아직 이 단계에는 등록된 힌트가 없습니다. 문제 설명을 다시 읽어보세요."
        idx = max(0, min(level - 1, len(self.hint_levels) - 1))
        return self.hint_levels[idx]


@dataclass
class Lab:
    id: str
    title: str
    description: str
    difficulty: str
    execution: bool = False  # True면 실제 실행 기반 검증(executor.py) 사용
    runtime: str = "kubectl_terraform"  # kubectl_terraform | shell
    steps: list[Step] = field(default_factory=list)

    def get_step(self, step_id: int) -> Step | None:
        return next((s for s in self.steps if s.id == step_id), None)


def _parse_verify(items: list[dict]) -> list[VerifyCheck]:
    return [
        VerifyCheck(
            type=v.get("type", "command"),
            cmd=v.get("cmd", ""),
            path=v.get("path", ""),
            expect=v.get("expect", ""),
        )
        for v in items
    ]


def _parse_lab(data: dict) -> Lab:
    steps = [
        Step(
            id=s["id"],
            title=s["title"],
            description=s["description"],
            answer_contains=s.get("answer_contains", []),
            hint_levels=s.get("hint_levels", []),
            input_type=s.get("input_type", "command"),
            target_path=s.get("target_path", ""),
            verify=_parse_verify(s.get("verify", [])),
            pre_cleanup=s.get("pre_cleanup", []),
        )
        for s in sorted(data.get("steps", []), key=lambda s: s["id"])
    ]
    return Lab(
        id=data["id"],
        title=data["title"],
        description=data.get("description", ""),
        difficulty=data.get("difficulty", ""),
        execution=data.get("execution", False),
        runtime=data.get("runtime", "kubectl_terraform"),
        steps=steps,
    )


def load_labs() -> dict[str, Lab]:
    """labs/*.yaml 을 모두 읽어 lab id -> Lab 매핑으로 반환한다."""
    labs: dict[str, Lab] = {}
    for path in sorted(LABS_DIR.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        lab = _parse_lab(data)
        labs[lab.id] = lab
    return labs
