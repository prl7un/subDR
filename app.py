from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="Linux Command Practice")

CORRECT_COMMAND = "mkdir target_dir"
SUCCESS_MESSAGE = "검증 성공! 'mkdir target_dir' 명령어를 정확히 입력하셨습니다."


def mock_ai_tutor_hint(user_input: str) -> str:
    """실제 AI API 연동 전 Mock 함수. 향후 여기서 외부 API를 호출하도록 교체할 수 있습니다."""
    _ = user_input  # API 요청 페이로드로 사용할 입력값 (Mock에서는 미사용)
    return (
        "AI튜터 힌트(API 모의 응답): "
        "디렉토리를 생성하는 리눅스 명령어는 make directory의 약자인 mkdir을 사용합니다. "
        "다시 시도해 보세요!"
    )


def render_page(message: str = "", message_type: str = "") -> str:
    alert_class = ""
    if message_type == "success":
        alert_class = "success"
    elif message_type == "hint":
        alert_class = "hint"

    alert_html = ""
    if message:
        alert_html = f'<div class="alert {alert_class}">{message}</div>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Linux 명령어 실습</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      font-family: "Segoe UI", system-ui, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      min-height: 100vh;
      margin: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }}
    .card {{
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 2rem;
      width: 100%;
      max-width: 520px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.35);
    }}
    h1 {{
      margin: 0 0 0.5rem;
      font-size: 1.35rem;
      color: #f8fafc;
    }}
    .assignment {{
      color: #94a3b8;
      margin-bottom: 1.5rem;
      line-height: 1.6;
    }}
    label {{
      display: block;
      margin-bottom: 0.5rem;
      font-size: 0.9rem;
      color: #cbd5e1;
    }}
    input[type="text"] {{
      width: 100%;
      padding: 0.75rem 1rem;
      border: 1px solid #475569;
      border-radius: 8px;
      background: #0f172a;
      color: #f1f5f9;
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 1rem;
    }}
    input[type="text"]:focus {{
      outline: none;
      border-color: #38bdf8;
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
    }}
    button {{
      margin-top: 1rem;
      width: 100%;
      padding: 0.75rem;
      border: none;
      border-radius: 8px;
      background: #2563eb;
      color: white;
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
    }}
    button:hover {{ background: #1d4ed8; }}
    .alert {{
      margin-top: 1.25rem;
      padding: 1rem;
      border-radius: 8px;
      line-height: 1.6;
    }}
    .alert.success {{
      background: #14532d;
      border: 1px solid #22c55e;
      color: #bbf7d0;
    }}
    .alert.hint {{
      background: #422006;
      border: 1px solid #f59e0b;
      color: #fde68a;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Linux 명령어 실습</h1>
    <p class="assignment">실습 과제: mkdir target_dir 명령어를 입력하세요</p>
    <form method="post" action="/check">
      <label for="command">명령어 입력</label>
      <input
        type="text"
        id="command"
        name="command"
        placeholder="mkdir target_dir"
        autocomplete="off"
        required
      />
      <button type="submit">제출</button>
    </form>
    {alert_html}
  </div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return render_page()


@app.post("/check", response_class=HTMLResponse)
async def check_command(command: str = Form(...)) -> str:
    if command.strip() == CORRECT_COMMAND:
        return render_page(SUCCESS_MESSAGE, "success")

    hint = mock_ai_tutor_hint(command)
    return render_page(hint, "hint")
