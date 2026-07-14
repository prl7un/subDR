"""강의자료 PDF(부모 폴더 sub_dr, git 저장소 밖)에서 텍스트만 추출해 rag_index.json 을
만드는 1회성 빌드 스크립트.

보안/저작권 원칙:
- 이미지는 절대 다루지 않는다(텍스트만 추출) — 강사님이 우려하신 "이미지 저작권" 문제를
  원천적으로 피한다.
- 여기서 만든 인덱스(rag_index.json)와 원본 PDF는 .gitignore 처리되어 커밋되지 않는다.
- 전부 로컬 파일 -> 로컬 파일 처리이며, 어디로도 전송되지 않는다.

실행 예 (PowerShell, sub_dr 절대경로를 /data 로 마운트):
  docker run --rm -v "C:\\Users\\i\\Desktop\\sub_dr:/data" -v "${PWD}:/app" -w /app \
      subdr-app:test python build_rag_index.py
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import fitz  # PyMuPDF

SOURCE_DIR = Path("/data")
OUTPUT_PATH = Path(__file__).parent / "rag_index.json"

# 파일명으로 확정 분류 (사용자가 확인해준 실제 커리큘럼 구성 기준).
TERRAFORM_FILES = {
    "01_IaC와 테라폼 소개.pdf",
    "02_HCL 문법과 기본 리소스 생성.pdf",
    "03_변수와 출력 값 다루기 .pdf",
    "04_상태 관리와 기본 명령어.pdf",
}

MIN_CHUNK_LEN = 40  # 제목만 있는 짧은 페이지는 다음 페이지와 합쳐서 청크를 만든다.


_TERRAFORM_FILES_NFC = {unicodedata.normalize("NFC", f) for f in TERRAFORM_FILES}


def topic_for(filename: str) -> str:
    # 파일 전송 과정(맥/디코/구글드라이브 등)에서 한글 유니코드 정규화 형태(NFC/NFD)가
    # 달라질 수 있어, 비교 전에 항상 NFC로 통일한다.
    normalized = unicodedata.normalize("NFC", filename)
    return "terraform" if normalized in _TERRAFORM_FILES_NFC else "kubernetes"


def extract_chunks(pdf_path: Path, topic: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    chunks: list[dict] = []
    buffer = ""
    buffer_start_page = 1
    last_page_idx = len(doc) - 1
    for page_num in range(len(doc)):
        text = doc[page_num].get_text().strip()
        text = " ".join(text.split())
        if not text:
            continue
        buffer = f"{buffer} {text}".strip() if buffer else text
        if len(buffer) < MIN_CHUNK_LEN and page_num != last_page_idx:
            continue
        chunks.append(
            {
                "topic": topic,
                "source": unicodedata.normalize("NFC", pdf_path.name),
                "page": buffer_start_page,
                "text": buffer,
            }
        )
        buffer = ""
        buffer_start_page = page_num + 2
    doc.close()
    return chunks


def main() -> None:
    pdf_files = sorted(SOURCE_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"'{SOURCE_DIR}' 에서 PDF를 찾지 못했습니다. 마운트 경로를 확인하세요.")
        return

    all_chunks: list[dict] = []
    for pdf_path in pdf_files:
        topic = topic_for(pdf_path.name)
        chunks = extract_chunks(pdf_path, topic)
        all_chunks.extend(chunks)
        print(f"{pdf_path.name} ({topic}) -> {len(chunks)}개 청크")

    OUTPUT_PATH.write_text(
        json.dumps({"chunks": all_chunks}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\n총 {len(all_chunks)}개 청크 저장 완료 -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
