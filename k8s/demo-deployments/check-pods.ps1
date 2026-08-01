# Check pod status in Minikube demo cluster
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Checking Pod Status in aks-ai-agent-demo cluster" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

$context = "aks-ai-agent-demo"

# Get pod status
Write-Host "Current Pod Status:" -ForegroundColor Yellow
kubectl get pods --context $context -o wide

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Waiting for pods to be Ready..." -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor Cyan

# Wait for api-gateway
Write-Host "`nWaiting for api-gateway pods..." -ForegroundColor Green
kubectl wait --for=condition=ready pod -l app=api-gateway --context $context --timeout=120s

# Wait for web-frontend
Write-Host "`nWaiting for web-frontend pods..." -ForegroundColor Green
kubectl wait --for=condition=ready pod -l app=web-frontend --context $context --timeout=120s

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Final Pod Status:" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Cyan
kubectl get pods --context $context -o wide

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "✅ All pods should now be green in the Minikube dashboard!" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host ""
Write-Host "Dashboard URL: http://127.0.0.1:63390" -ForegroundColor Cyan
