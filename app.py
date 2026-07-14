import html
import uuid

from dotenv import load_dotenv

# ai_tutor가 import 시점에 os.environ에서 Upstage 설정을 읽으므로, 그 전에 .env를 로드한다.
# 로컬 개발 전용이며 .env는 .gitignore에 등록되어 커밋되지 않는다. 클러스터 배포 시에는
# .env 파일 대신 Kubernetes Secret을 환경변수로 주입한다(YAML에 값 커밋 금지).
load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import executor
import rag
from ai_tutor import get_ai_hint
from lab_loader import Lab, Step, load_labs

app = FastAPI(title="DR 실습 튜터")

LABS: dict[str, Lab] = load_labs()

# 강의자료 RAG는 이 두 랩에만 연결한다(실제로 자료가 있는 주제).
LAB_RAG_TOPIC: dict[str, str] = {
    "lab-k8s-basics": "kubernetes",
    "lab-terraform-basics": "terraform",
}

# session_id(쿠키) -> { lab_id: {"current_step": int, "attempts": {step_id: int}, "done": bool} }
# 이 앱은 DR 복구 시 재생성되는 데모용 단일 Pod라서 별도 DB 없이 프로세스 메모리로 충분하다.
SESSIONS: dict[str, dict] = {}


def get_session(request: Request) -> tuple[str, dict]:
    sid = request.cookies.get("session_id")
    if not sid or sid not in SESSIONS:
        sid = str(uuid.uuid4())
        SESSIONS[sid] = {}
    return sid, SESSIONS[sid]


def get_lab_progress(session: dict, lab_id: str) -> dict:
    return session.setdefault(lab_id, {"current_step": 1, "attempts": {}, "done": False})


def with_session_cookie(response: HTMLResponse, sid: str) -> HTMLResponse:
    response.set_cookie("session_id", sid, httponly=True, samesite="lax")
    return response


def render_layout(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Segoe UI", system-ui, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      margin: 0;
      padding: 2.5rem 1.5rem;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 2rem;
      margin-bottom: 1.25rem;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
    }}
    h1 {{ margin: 0 0 0.5rem; font-size: 1.5rem; color: #f8fafc; }}
    h2 {{ margin: 0 0 0.75rem; font-size: 1.2rem; color: #f8fafc; }}
    p.desc {{ color: #94a3b8; line-height: 1.6; }}
    pre.desc {{
      color: #cbd5e1;
      line-height: 1.6;
      white-space: pre-wrap;
      font-family: inherit;
      margin: 0 0 1rem;
    }}
    .badge {{
      display: inline-block;
      font-size: 0.75rem;
      padding: 0.2rem 0.6rem;
      border-radius: 999px;
      background: #334155;
      color: #93c5fd;
      margin-bottom: 0.75rem;
    }}
    a.lab-link {{
      display: block;
      text-decoration: none;
      color: inherit;
    }}
    a.lab-link:hover .card {{ border-color: #38bdf8; }}
    label {{ display: block; margin-bottom: 0.5rem; font-size: 0.9rem; color: #cbd5e1; }}
    textarea {{
      width: 100%;
      min-height: 110px;
      padding: 0.75rem 1rem;
      border: 1px solid #475569;
      border-radius: 8px;
      background: #0f172a;
      color: #f1f5f9;
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 0.95rem;
      resize: vertical;
    }}
    textarea:focus {{
      outline: none;
      border-color: #38bdf8;
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
    }}
    button {{
      margin-top: 1rem;
      padding: 0.7rem 1.4rem;
      border: none;
      border-radius: 8px;
      background: #2563eb;
      color: white;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
    }}
    button:hover {{ background: #1d4ed8; }}
    button.secondary {{ background: #334155; }}
    button.secondary:hover {{ background: #475569; }}
    .alert {{ margin-top: 1.25rem; padding: 1rem; border-radius: 8px; line-height: 1.6; white-space: pre-wrap; }}
    .alert.success {{ background: #14532d; border: 1px solid #22c55e; color: #bbf7d0; }}
    .alert.hint {{ background: #422006; border: 1px solid #f59e0b; color: #fde68a; }}
    .topnav {{ margin-bottom: 1.25rem; }}
    .topnav a {{ color: #93c5fd; text-decoration: none; font-size: 0.9rem; }}
    .progress {{ color: #64748b; font-size: 0.85rem; margin-bottom: 0.75rem; }}
    .ai-badge {{ font-size: 0.72rem; color: #64748b; margin-top: 0.4rem; }}
    .alert-source {{
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      opacity: 0.85;
      margin-bottom: 0.5rem;
    }}
    pre.transcript {{
      background: #020617;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 0.9rem 1rem;
      margin-top: 1rem;
      color: #a1a1aa;
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 0.82rem;
      white-space: pre-wrap;
      max-height: 320px;
      overflow-y: auto;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    {body}
  </div>
</body>
</html>"""


def render_lab_list() -> str:
    cards = ""
    for lab in LABS.values():
        cards += f"""
        <a class="lab-link" href="/lab/{html.escape(lab.id)}">
          <div class="card">
            <span class="badge">{html.escape(lab.difficulty or '')}</span>
            <h2>{html.escape(lab.title)}</h2>
            <p class="desc">{html.escape(lab.description)} · 총 {len(lab.steps)}단계</p>
          </div>
        </a>"""
    body = f"""
    <div class="card">
      <h1>DR 실습 튜터</h1>
      <p class="desc">장애 복구(DR) 상황에서 제공되는 실습 문제풀이 웹입니다. 랩을 선택해 실습을 시작하세요.</p>
      <p class="ai-badge">AI 튜터</p>
    </div>
    {cards}
    """
    return render_layout("DR 실습 튜터", body)


def render_step_page(
    lab: Lab,
    step: Step,
    progress: dict,
    message: str = "",
    message_type: str = "",
    ai_generated: bool = False,
    transcript: str = "",
    rag_applied: bool = False,
) -> str:
    step_index = lab.steps.index(step) + 1
    total = len(lab.steps)

    alert_html = ""
    if message:
        alert_class = "success" if message_type == "success" else "hint"
        source_note = ""
        if message_type == "hint":
            if ai_generated:
                label = "🤖 AI 튜터 응답" + (" (참고 자료 활용)" if rag_applied else "")
                source_note = f'<div class="alert-source">{label}</div>'
            else:
                source_note = '<div class="alert-source">📋 정적 힌트 (AI 튜터 미가용/미설정)</div>'
        alert_html = f'<div class="alert {alert_class}">{source_note}{html.escape(message)}</div>'

    transcript_html = ""
    if transcript:
        caption = "직전 단계 실행 결과" if message_type == "success" else "실행 결과"
        transcript_html = (
            f'<div class="progress">{html.escape(caption)}</div>'
            f'<pre class="transcript">{html.escape(transcript)}</pre>'
        )

    placeholder = (
        "main.tf 내용을 그대로 입력하세요" if step.input_type == "file" else "여기에 명령어를 입력하세요"
    )

    body = f"""
    <div class="topnav"><a href="/">&larr; 전체 랩 목록</a> &middot; <a href="/lab/{html.escape(lab.id)}/reset">이 랩 다시 풀기</a></div>
    <div class="card">
      <span class="badge">{html.escape(lab.title)}</span>
      <div class="progress">단계 {step_index} / {total}</div>
      <h1>{html.escape(step.title)}</h1>
      <pre class="desc">{html.escape(step.description.strip())}</pre>
      <form method="post" action="/lab/{html.escape(lab.id)}/check">
        <input type="hidden" name="step_id" value="{step.id}">
        <label for="answer">{'파일 내용 입력' if step.input_type == 'file' else '명령어 입력 (여러 줄 가능, 한 줄에 한 명령)'}</label>
        <textarea id="answer" name="answer" placeholder="{placeholder}" autocomplete="off" required></textarea>
        <button type="submit">제출</button>
      </form>
      {alert_html}
      {transcript_html}
    </div>
    """
    return render_layout(f"{lab.title} - {step.title}", body)


def render_lab_complete(lab: Lab, transcript: str = "") -> str:
    transcript_html = f'<pre class="transcript">{html.escape(transcript)}</pre>' if transcript else ""
    body = f"""
    <div class="topnav"><a href="/">&larr; 전체 랩 목록</a></div>
    <div class="card">
      <span class="badge">{html.escape(lab.title)}</span>
      <h1>🎉 모든 단계를 완료했습니다!</h1>
      <p class="desc">{html.escape(lab.title)} 실습을 모두 마쳤습니다.</p>
      {transcript_html}
      <form method="get" action="/lab/{html.escape(lab.id)}/reset">
        <button type="submit" class="secondary">이 랩 다시 풀기</button>
      </form>
    </div>
    """
    return render_layout(f"{lab.title} - 완료", body)


def render_not_found(message: str) -> str:
    body = f"""
    <div class="card">
      <h1>찾을 수 없습니다</h1>
      <p class="desc">{html.escape(message)}</p>
      <a href="/">&larr; 전체 랩 목록으로 이동</a>
    </div>
    """
    return render_layout("Not Found", body)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    sid, _ = get_session(request)
    return with_session_cookie(HTMLResponse(render_lab_list()), sid)


@app.get("/lab/{lab_id}", response_class=HTMLResponse)
async def show_lab(lab_id: str, request: Request) -> HTMLResponse:
    sid, session = get_session(request)
    lab = LABS.get(lab_id)
    if not lab:
        return with_session_cookie(HTMLResponse(render_not_found(f"'{lab_id}' 랩을 찾을 수 없습니다."), status_code=404), sid)

    progress = get_lab_progress(session, lab_id)
    if progress["done"]:
        return with_session_cookie(HTMLResponse(render_lab_complete(lab)), sid)

    step = lab.get_step(progress["current_step"])
    if not step:
        progress["done"] = True
        return with_session_cookie(HTMLResponse(render_lab_complete(lab)), sid)

    return with_session_cookie(HTMLResponse(render_step_page(lab, step, progress)), sid)


@app.get("/lab/{lab_id}/reset")
async def reset_lab(lab_id: str, request: Request) -> RedirectResponse:
    sid, session = get_session(request)
    session[lab_id] = {"current_step": 1, "attempts": {}, "done": False}
    lab = LABS.get(lab_id)
    if lab and lab.execution:
        await executor.reset_lab_workspace(sid, lab_id)
    response = RedirectResponse(url=f"/lab/{lab_id}", status_code=303)
    return with_session_cookie(response, sid)


@app.post("/lab/{lab_id}/check", response_class=HTMLResponse)
async def check_step(
    lab_id: str,
    request: Request,
    step_id: int = Form(...),
    answer: str = Form(...),
) -> HTMLResponse:
    sid, session = get_session(request)
    lab = LABS.get(lab_id)
    if not lab:
        return with_session_cookie(HTMLResponse(render_not_found(f"'{lab_id}' 랩을 찾을 수 없습니다."), status_code=404), sid)

    step = lab.get_step(step_id)
    if not step:
        return with_session_cookie(HTMLResponse(render_not_found("해당 단계를 찾을 수 없습니다."), status_code=404), sid)

    progress = get_lab_progress(session, lab_id)

    if lab.execution:
        passed, transcript = await _run_execution_step(sid, lab, step, answer)
    else:
        passed, transcript = step.check(answer), ""

    if passed:
        next_step_id = step_id + 1
        next_step = lab.get_step(next_step_id)
        if next_step:
            progress["current_step"] = next_step_id
            message = f"정답입니다! '{step.title}' 단계를 통과했습니다."
            page = render_step_page(lab, next_step, progress, message, "success", transcript=transcript)
        else:
            progress["done"] = True
            page = render_lab_complete(lab, transcript=transcript)
        return with_session_cookie(HTMLResponse(page), sid)

    attempts = progress["attempts"]
    attempts[step_id] = attempts.get(step_id, 0) + 1
    attempt_count = attempts[step_id]

    rag_chunks: list[rag.Chunk] = []
    topic = LAB_RAG_TOPIC.get(lab.id)
    if topic:
        rag_chunks = rag.retrieve(f"{step.title} {answer}", topic, top_k=2)
    rag_context_text = "\n---\n".join(f"({c.source} p.{c.page}) {c.text}" for c in rag_chunks)

    ai_hint = await get_ai_hint(
        lab.title, step.title, step.description, answer, attempt_count, rag_context=rag_context_text
    )
    if ai_hint:
        hint_text = ai_hint
        ai_generated = True
    else:
        hint_text = step.static_hint(attempt_count)
        ai_generated = False

    # 강의자료 발췌는 위에서 AI 힌트 생성에만 참고시키고, 화면에는 절대 그대로 노출하지 않는다
    # (화면을 녹화하는 시연영상 등을 통해 원문이 배포되는 것을 원천적으로 막기 위함).
    # 대신 "참고 자료가 활용됐다"는 사실만 표시한다.
    rag_applied = bool(rag_chunks) and ai_generated
    page = render_step_page(
        lab, step, progress, hint_text, "hint", ai_generated, transcript=transcript, rag_applied=rag_applied
    )
    return with_session_cookie(HTMLResponse(page), sid)


async def _run_execution_step(sid: str, lab: Lab, step: Step, answer: str) -> tuple[bool, str]:
    """k8s/terraform 처럼 execution=true 인 랩의 실제 실행+검증을 수행하고,
    (통과 여부, 화면에 보여줄 터미널 트랜스크립트) 를 반환한다."""
    cwd = executor.workdir_for(sid, lab.id)
    transcript_parts: list[str] = []
    submitted_something_real = False

    if step.input_type == "file":
        await executor.write_file(cwd, step.target_path, answer)
        transcript_parts.append(f"(파일 저장됨: {step.target_path})")
        submitted_something_real = True
    else:
        results = await executor.run_submission(answer, cwd, runtime=lab.runtime)
        if not results:
            transcript_parts.append("(입력한 명령이 없습니다.)")
        for r in results:
            status = "OK" if r.ok else "FAIL"
            transcript_parts.append(f"$ {r.line}\n[{status}] {r.output}")
        submitted_something_real = any(r.ok for r in results)

    if not submitted_something_real:
        # 안전장치: 실제로 성공한 명령이 하나도 없으면, 클러스터/파일시스템이 우연히 이미
        # 원하는 상태였다는 이유만으로 통과시키지 않는다(예: 노드가 항상 Ready인 상태에서
        # 관계없는/차단된 명령만 입력해도 검증이 통과해버리는 허점을 막는다).
        transcript_parts.append("--- 검증 건너뜀 ---\n실제로 성공한 명령이 없어 검증을 진행하지 않습니다.")
        return False, "\n\n".join(transcript_parts)

    passed, verify_details = await executor.run_verify(step, cwd, runtime=lab.runtime)
    if verify_details:
        transcript_parts.append("--- 검증 ---")
        transcript_parts.extend(verify_details)

    return passed, "\n\n".join(transcript_parts)
