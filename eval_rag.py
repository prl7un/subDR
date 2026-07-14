"""RAG 검색 품질을 빠르게 점검하는 스크립트.

rag_index.json을 빌드(build_rag_index.py)한 뒤 언제든 재실행할 수 있는 반복적 평가
도구다. 손으로 만든 질의 몇 개로 "기대하는 강의자료 파일이 top-k 검색 결과에 실제로
들어오는지"를 확인해, 청킹/검색 설정을 바꿀 때마다 품질이 유지되는지 빠르게 회귀 테스트
할 수 있다.

실행: python eval_rag.py (subDR 안에서, rag_index.json 이 이미 존재해야 함)
"""
from __future__ import annotations

import rag

# (질의, topic, 기대 소스 파일명에 포함되어야 할 부분 문자열)
TEST_CASES = [
    ("Pod가 뭐야", "kubernetes", "Pod"),
    ("Deployment 무중단 배포 방법", "kubernetes", "Deployment"),
    ("클러스터 모니터링 어떻게 해", "kubernetes", "모니터링"),
    ("환경 설정 컨피그맵 시크릿", "kubernetes", "환경 설정"),
    ("휘발성 데이터 볼륨 극복", "kubernetes", "휘발성"),
    ("테라폼 HCL 문법 기본 리소스", "terraform", "HCL"),
    ("테라폼 상태 관리 명령어", "terraform", "상태 관리"),
    ("테라폼 변수와 출력값 다루기", "terraform", "변수와 출력"),
]


def main() -> None:
    index = rag.load_index()
    print(f"인덱스 청크 수: {len(index.chunks)}")
    if not index.chunks:
        print("인덱스가 비어 있습니다. build_rag_index.py 를 먼저 실행하세요.")
        return

    hits = 0
    for query, topic, expect_substr in TEST_CASES:
        results = index.retrieve(query, topic, top_k=3)
        sources = [r.source for r in results]
        hit = any(expect_substr in s for s in sources)
        hits += int(hit)
        mark = "OK" if hit else "MISS"
        print(f"[{mark}] '{query}' ({topic}) -> {sources}")

    print(f"\n적중률: {hits}/{len(TEST_CASES)}")


if __name__ == "__main__":
    main()
