"""k8s/terraform/linux 랩의 "실제 실행 기반 검증" 엔진.

두 가지 실행 모드(runtime)를 지원한다.

1) kubectl_terraform (k8s/terraform 랩)
   - 허용 명령: kubectl / terraform 뿐(화이트리스트). 셸 메타문자 전부 차단.
   - subprocess는 shell=False로만 실행해 셸 자체를 거치지 않는다(가장 안전).
   - kubectl은 네임스페이스 미지정 시 lab-sandbox로 강제 주입, RBAC도 그 네임스페이스로만 한정.

2) shell (linux 랩)
   - mkdir/touch/find/cp/chmod/stat/grep/cat/tar/ln/ls/echo 같은 표준 명령만 화이트리스트.
   - brace 확장({a,b})/리다이렉션(>)/find -exec \; 처럼 정답 자체가 셸 문법을 쓰기 때문에
     실제 셸(/bin/sh -c)을 거쳐야 한다. 대신:
       - 명령 치환(`` ` ``, `$()`)·변수 확장(`$`)·파이프(`|`)·백그라운드(`&`)·입력 리다이렉션(`<`)은
         전부 차단해 화이트리스트 우회 경로를 최소화한다.
       - 세션별 스크래치 디렉터리를 HOME으로 지정해 `~/work/...` 같은 경로가 그 안에만
         쓰이도록 한다(다만 /etc/passwd 조회처럼 리눅스 랩이 의도적으로 다루는 절대경로
         '읽기'는 허용된다 — 이 컨테이너는 1회성 데모 Pod라 잔존 위험이 낮다는 점을 감안한
         의도적 트레이드오프).
       - `rm -rf /`, `sudo`, `mkfs`, `dd`, `shutdown` 등 명백히 위험한 패턴은 별도 차단.

각 명령은 타임아웃(기본 20초)이 있어 무한 대기로 요청을 붙잡지 못한다.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from lab_loader import Step

ALLOWED_COMMANDS = {"kubectl", "terraform"}
FORBIDDEN_CHARS = set(";&|`$<>\n")
SANDBOX_NAMESPACE = "lab-sandbox"

SHELL_ALLOWED_COMMANDS = {
    "mkdir", "touch", "find", "cp", "chmod", "stat", "grep",
    "cat", "tar", "ln", "ls", "echo",
}
FORBIDDEN_CHARS_SHELL = set("`$&<|\n")

DEFAULT_TIMEOUT_SECONDS = 20
WORKDIR_ROOT = Path("/tmp/lab-exec")


@dataclass
class LineResult:
    line: str
    ok: bool
    output: str


def workdir_for(session_id: str, lab_id: str) -> Path:
    path = WORKDIR_ROOT / session_id / lab_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# kubectl / terraform 모드
# ---------------------------------------------------------------------------

def _reject_reason(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if any(ch in FORBIDDEN_CHARS for ch in stripped):
        return "허용되지 않는 특수문자(; & | ` $ < >)가 포함되어 실행이 차단되었습니다."
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        return "명령을 해석할 수 없습니다(따옴표 짝 확인)."
    if not tokens or tokens[0] not in ALLOWED_COMMANDS:
        return f"'{tokens[0] if tokens else stripped}' 명령은 이 실습에서 허용되지 않습니다 (kubectl/terraform만 가능)."
    return None


def _prepare(line: str) -> str:
    """네임스페이스 강제 주입 / terraform apply 자동 승인 등 안전한 보정을 적용한다."""
    stripped = line.strip()
    tokens = shlex.split(stripped)
    if tokens[0] == "kubectl" and "-n" not in tokens and "--namespace" not in tokens:
        tokens += ["-n", SANDBOX_NAMESPACE]
    if tokens[0] == "terraform" and len(tokens) >= 2 and tokens[1] == "apply" and "-auto-approve" not in tokens:
        tokens.append("-auto-approve")
    return shlex.join(tokens)


async def _run_one(line: str, cwd: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> LineResult:
    reason = _reject_reason(line)
    if reason:
        return LineResult(line=line, ok=False, output=reason)

    safe_line = _prepare(line)
    try:
        proc = await asyncio.create_subprocess_exec(
            *shlex.split(safe_line),
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace").strip()
        return LineResult(line=safe_line, ok=(proc.returncode == 0), output=output or "(출력 없음)")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return LineResult(line=safe_line, ok=False, output=f"{timeout}초 안에 끝나지 않아 중단되었습니다.")
    except FileNotFoundError:
        return LineResult(line=safe_line, ok=False, output="실행 파일을 찾을 수 없습니다 (kubectl/terraform 미설치?).")
    except Exception as exc:  # noqa: BLE001 - 학생에게 원인을 그대로 보여주는 게 유용하다
        return LineResult(line=safe_line, ok=False, output=f"실행 오류: {exc}")


# ---------------------------------------------------------------------------
# shell(linux) 모드
# ---------------------------------------------------------------------------

_ESCAPED_SEMI_PLACEHOLDER = "\x00ESCAPED_SEMI\x00"


def _reject_reason_shell(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None

    if any(ch in FORBIDDEN_CHARS_SHELL for ch in stripped):
        return "허용되지 않는 특수문자(명령치환/변수확장 `` ` `` `$`, 파이프 `|`, 백그라운드 `&`, `<`)가 포함되어 차단되었습니다."

    # find -exec ... \; 의 이스케이프된 세미콜론은 명령 구분자가 아니므로 임시로 치환해두고
    # 나머지 ';'만 실제 구분자로 보고 각 구간의 선두 명령어를 화이트리스트로 검사한다.
    masked = stripped.replace("\\;", _ESCAPED_SEMI_PLACEHOLDER)
    for segment in masked.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        try:
            tokens = shlex.split(segment.replace(_ESCAPED_SEMI_PLACEHOLDER, "\\;"))
        except ValueError:
            return "명령을 해석할 수 없습니다(따옴표 짝 확인)."
        if not tokens:
            continue
        if tokens[0] not in SHELL_ALLOWED_COMMANDS:
            allowed = ", ".join(sorted(SHELL_ALLOWED_COMMANDS))
            return f"'{tokens[0]}' 명령은 이 실습에서 허용되지 않습니다 (허용: {allowed})."
        # find -exec <명령> ... \; 는 화이트리스트에 없는 임의 명령을 실행시키는 우회 경로가
        # 될 수 있어, -exec 뒤에 오는 실행 명령도 반드시 화이트리스트 안에 있어야 한다.
        if tokens[0] == "find" and "-exec" in tokens:
            exec_idx = tokens.index("-exec")
            exec_cmd = tokens[exec_idx + 1] if exec_idx + 1 < len(tokens) else ""
            if exec_cmd not in SHELL_ALLOWED_COMMANDS:
                return f"find -exec 으로 실행하려는 '{exec_cmd}' 명령은 허용되지 않습니다."
    return None


async def _run_one_shell(line: str, cwd: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> LineResult:
    reason = _reject_reason_shell(line)
    if reason:
        return LineResult(line=line, ok=False, output=reason)

    env = os.environ.copy()
    env["HOME"] = str(cwd)
    try:
        # 정답들이 brace 확장({a,b,c}) 등 bash 전용 문법을 쓰므로, POSIX /bin/sh(=dash)가
        # 아니라 /bin/bash -c 로 명시 실행한다.
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", "-c", line.strip(),
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace").strip()
        return LineResult(line=line, ok=(proc.returncode == 0), output=output or "(출력 없음)")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        return LineResult(line=line, ok=False, output=f"{timeout}초 안에 끝나지 않아 중단되었습니다.")
    except Exception as exc:  # noqa: BLE001
        return LineResult(line=line, ok=False, output=f"실행 오류: {exc}")


async def _run_line(line: str, cwd: Path, runtime: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> LineResult:
    if runtime == "shell":
        return await _run_one_shell(line, cwd, timeout)
    return await _run_one(line, cwd, timeout)


async def run_submission(submitted_text: str, cwd: Path, runtime: str = "kubectl_terraform") -> list[LineResult]:
    """학생이 textarea에 입력한 여러 줄을 순서대로 실행하고 각 줄의 결과를 반환한다."""
    lines = [l for l in submitted_text.splitlines() if l.strip()]
    results: list[LineResult] = []
    for line in lines:
        results.append(await _run_line(line, cwd, runtime))
    return results


async def run_pre_cleanup(commands: list[str], cwd: Path, runtime: str = "kubectl_terraform") -> None:
    """단계 재시도 전에 랩 작성자가 정의한 정리 명령을 실행한다(사용자 입력 아님, 신뢰됨).
    이전 시도가 남긴 동일 이름 리소스와의 AlreadyExists 충돌을 막기 위한 것이라,
    실패(예: 원래 없어서 지울 게 없음)해도 학생 진행을 막지 않고 조용히 무시한다."""
    for cmd in commands:
        try:
            await _run_line(cmd, cwd, runtime, timeout=DEFAULT_TIMEOUT_SECONDS)
        except Exception:
            pass


async def write_file(cwd: Path, target_path: str, content: str) -> None:
    dest = (cwd / target_path).resolve()
    if not str(dest).startswith(str(cwd.resolve())):
        raise ValueError("워크스페이스 밖에는 파일을 쓸 수 없습니다.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


async def reset_lab_workspace(session_id: str, lab_id: str) -> None:
    """'다시 풀기' 시 스크래치 디렉터리를 지우고, k8s 랩이면 이전에 만든 실습 리소스도 정리한다.
    삭제 대상은 랩 작성자가 정의한 고정 리소스 이름뿐이라 사용자 입력이 관여하지 않는다."""
    workdir = WORKDIR_ROOT / session_id / lab_id
    shutil.rmtree(workdir, ignore_errors=True)

    if lab_id == "lab-k8s-basics":
        cleanup_cmd = (
            "kubectl delete pod nginx deployment web service web "
            f"-n {SANDBOX_NAMESPACE} --ignore-not-found --wait=false"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *shlex.split(cleanup_cmd),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=DEFAULT_TIMEOUT_SECONDS)
        except Exception:
            pass  # 정리 실패해도 다음 시도에서 이름 충돌만 발생할 뿐, 앱 진행은 막지 않는다.


COMMAND_CHECK_MAX_RETRIES = 5
COMMAND_CHECK_RETRY_DELAY_SECONDS = 2


async def run_verify(step: Step, cwd: Path, runtime: str = "kubectl_terraform") -> tuple[bool, list[str]]:
    """랩 작성자가 정의한 신뢰 검증 명령/파일 체크를 실행해 실제 상태를 확인한다.

    command 타입은 이미지 pull/스케줄링처럼 즉시 반영되지 않는 상태 변화가 있을 수 있어,
    바로 실패시키지 않고 짧게 재시도한다. 학생이 방금 실행한 명령이 맞다면 잠시 뒤 통과하고,
    정말 틀렸다면 그대로 재시도 실패 결과를 보여준다.
    """
    details: list[str] = []
    all_ok = True
    for check in step.verify:
        if check.type == "file_exists":
            path = cwd / check.path
            ok = path.exists()
            details.append(f"[파일 확인] {check.path} -> {'존재함' if ok else '없음'}")
        elif check.type == "dir_exists":
            path = cwd / check.path
            ok = path.is_dir()
            details.append(f"[디렉터리 확인] {check.path} -> {'존재함' if ok else '없음'}")
        elif check.type == "file_absent":
            path = cwd / check.path
            ok = not path.exists()
            details.append(f"[파일 없음 확인] {check.path} -> {'없음(통과)' if ok else '존재함(실패)'}")
        elif check.type == "file_contains":
            path = cwd / check.path
            ok = path.exists() and check.expect in path.read_text(encoding="utf-8", errors="replace")
            details.append(f"[파일 내용 확인] {check.path} 에 '{check.expect}' 포함 -> {ok}")
        elif check.type == "file_not_contains":
            path = cwd / check.path
            ok = (not path.exists()) or check.expect not in path.read_text(encoding="utf-8", errors="replace")
            details.append(f"[파일 내용 미포함 확인] {check.path} 에 '{check.expect}' 미포함 -> {ok}")
        else:  # command
            result = None
            for attempt in range(COMMAND_CHECK_MAX_RETRIES):
                result = await _run_line(check.cmd, cwd, runtime, timeout=DEFAULT_TIMEOUT_SECONDS)
                if result.ok and check.expect in result.output:
                    break
                if attempt < COMMAND_CHECK_MAX_RETRIES - 1:
                    await asyncio.sleep(COMMAND_CHECK_RETRY_DELAY_SECONDS)
            ok = bool(result and result.ok and check.expect in result.output)
            details.append(f"[검증] {check.cmd}\n  -> {result.output}\n  (기대값 '{check.expect}' 포함 여부: {ok})")
        all_ok = all_ok and ok
    return all_ok, details
