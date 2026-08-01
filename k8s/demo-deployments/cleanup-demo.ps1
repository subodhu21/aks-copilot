# Self-Healing Demo Cleanup Script
# Removes all demo deployments and services

param(
    [string]$Context = "aks-ai-agent-demo",
    [string]$Namespace = "default"
)

Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Self-Healing Demo - Cleanup" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

Write-Host "Removing demo deployments..." -ForegroundColor Yellow

$deployments = @(
    "api-gateway",
    "data-processor",
    "web-frontend",
    "user-service",
    "payment-service"
)

foreach ($deployment in $deployments) {
    Write-Host "  Deleting $deployment..." -ForegroundColor White
    kubectl delete deployment $deployment -n $Namespace --context $Context --ignore-not-found=true 2>&1 | Out-Null
    Write-Host "  ✓ $deployment removed" -ForegroundColor Green
}

Write-Host ""
Write-Host "Removing services..." -ForegroundColor Yellow

$services = @(
    "api-gateway-service",
    "data-processor-service",
    "web-frontend-service",
    "user-service",
    "payment-service"
)

foreach ($service in $services) {
    kubectl delete service $service -n $Namespace --context $Context --ignore-not-found=true 2>&1 | Out-Null
}

Write-Host "✓ Services removed" -ForegroundColor Green
Write-Host ""

# Also remove old standalone pods
Write-Host "Removing old standalone demo pods..." -ForegroundColor Yellow
kubectl delete pod demo-crashloop demo-imagepull demo-healthy `
    -n $Namespace --context $Context --ignore-not-found=true 2>&1 | Out-Null
Write-Host "✓ Old pods removed" -ForegroundColor Green
Write-Host ""

Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Cleanup Complete!" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

# Show remaining resources
Write-Host "Remaining resources:" -ForegroundColor Yellow
kubectl get all -n $Namespace --context $Context
Write-Host ""
