FROM python:3.12-slim

WORKDIR /app

# k8s/terraform 랩의 "실제 실행 기반 검증"에 필요한 바이너리.
# kubectl은 dl.k8s.io의 공식 stable 배포본을 그대로 받는다(버전 채널을 하드코딩하지 않아
# 항상 현재 stable을 받고, 클러스터와의 마이너 버전 스큐도 보통 문제되지 않는다).
# terraform은 hashicorp/local 프로바이더만 쓰므로 특정 안정 버전(1.9.8)으로 고정한다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && KUBECTL_VERSION=$(curl -fsSL https://dl.k8s.io/release/stable.txt) \
    && curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && curl -fsSL -o /tmp/terraform.zip https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip \
    && unzip /tmp/terraform.zip -d /usr/local/bin \
    && rm /tmp/terraform.zip \
    && apt-get purge -y unzip \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ai_tutor.py lab_loader.py executor.py rag.py ./
COPY labs ./labs
# rag_index.json은 로컬에서 build_rag_index.py로 미리 만들어야 한다(강사님 강의자료는
# 저작권이 있어 저장소에 커밋하지 않는다 - .gitignore 처리됨). 없어도 앱은 정상 동작하고
# RAG 기능만 자동으로 비활성화된다(rag.is_available() == False).
COPY rag_index.json* ./

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
