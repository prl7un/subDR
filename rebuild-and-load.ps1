# app.py/labs 등을 수정한 뒤, 새 이미지를 빌드해서 kind(dr-cluster) 노드에 다시 적재하는 스크립트.
# subDR 이 실제 컨테이너 레지스트리에 푸시되지 않으므로, 로컬 코드 변경을 실제로 반영하려면
# 매번 이 스크립트(또는 아래 두 명령)를 실행해야 한다. 그 뒤 ArgoCD/kubectl 로 재배포하면
# 새 이미지가 반영된다(imagePullPolicy: IfNotPresent 라 태그가 같아도 로드된 이미지가 갱신됨).
param(
    [string]$ImageTag = "test",
    [string]$ClusterName = "dr-cluster"
)

$ErrorActionPreference = "Stop"

Write-Host "1/2 도커 이미지 빌드 중 (subdr-app:$ImageTag) ..."
docker build -t "subdr-app:$ImageTag" .

Write-Host "2/2 kind 클러스터($ClusterName)에 이미지 적재 중 ..."
kind load docker-image "subdr-app:$ImageTag" --name $ClusterName

Write-Host "완료. dr_active 가 이미 true 라면 Pod를 재시작해야 새 이미지가 반영됩니다:"
Write-Host "  kubectl -n default rollout restart deployment/dr-recovery-app"
