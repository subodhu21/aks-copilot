# Self-Healing Demo Setup Script
# Deploys realistic microservices with intentional failures

param(
    [string]$Context = "aks-ai-agent-demo",
    [string]$Namespace = "default"
)

Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Self-Healing Demo - Setup" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

# Step 1: Clean up old demo resources
Write-Host "Step 1: Cleaning up old demo resources..." -ForegroundColor Yellow
kubectl delete deployment api-gateway data-processor web-frontend user-service payment-service `
    -n $Namespace --context $Context --ignore-not-found=true 2>&1 | Out-Null

# Also clean up old standalone pods
kubectl delete pod demo-crashloop demo-imagepull demo-healthy `
    -n $Namespace --context $Context --ignore-not-found=true 2>&1 | Out-Null

Write-Host "✓ Cleanup complete" -ForegroundColor Green
Write-Host ""

# Step 2: Deploy all demo services
Write-Host "Step 2: Deploying demo microservices..." -ForegroundColor Yellow
Write-Host ""

$deployments = @(
    @{ Name = "API Gateway"; File = "01-api-gateway-crashloop.yaml"; Type = "CrashLoopBackOff" },
    @{ Name = "Data Processor"; File = "02-data-processor-oom.yaml"; Type = "OOMKilled" },
    @{ Name = "Web Frontend"; File = "03-web-frontend-imagepull.yaml"; Type = "ImagePullBackOff" },
    @{ Name = "User Service"; File = "04-user-service-healthy.yaml"; Type = "Healthy" },
    @{ Name = "Payment Service"; File = "05-payment-service-flaky.yaml"; Type = "High Restarts" }
)

foreach ($deployment in $deployments) {
    Write-Host "  Deploying $($deployment.Name) ($($deployment.Type))..." -ForegroundColor White
    kubectl apply -f $deployment.File --context $Context -n $Namespace 2>&1 | Out-Null
    Write-Host "  ✓ $($deployment.Name) deployed" -ForegroundColor Green
}

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Deployment Status" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

# Step 3: Wait for pods to be created
Write-Host "Waiting for pods to be created..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Step 4: Show current status
kubectl get deployments -n $Namespace --context $Context -l demo
Write-Host ""
kubectl get pods -n $Namespace --context $Context --selector='demo in (crashloop,oomkilled,imagepull,healthy,high-restarts)'

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Expected Failures (Demo Scenarios)" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

Write-Host "1. " -NoNewline -ForegroundColor White
Write-Host "api-gateway" -NoNewline -ForegroundColor Yellow
Write-Host "        → CrashLoopBackOff (missing REDIS_HOST env var)" -ForegroundColor White

Write-Host "2. " -NoNewline -ForegroundColor White
Write-Host "data-processor" -NoNewline -ForegroundColor Yellow
Write-Host "     → OOMKilled (insufficient memory limit)" -ForegroundColor White

Write-Host "3. " -NoNewline -ForegroundColor White
Write-Host "web-frontend" -NoNewline -ForegroundColor Yellow
Write-Host "       → ImagePullBackOff (non-existent image)" -ForegroundColor White

Write-Host "4. " -NoNewline -ForegroundColor White
Write-Host "user-service" -NoNewline -ForegroundColor Green
Write-Host "       → Healthy (control group)" -ForegroundColor White

Write-Host "5. " -NoNewline -ForegroundColor White
Write-Host "payment-service" -NoNewline -ForegroundColor Yellow
Write-Host "    → Flaky (will accumulate restarts)" -ForegroundColor White

Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Next Steps" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host ""

Write-Host "1. Wait 60 seconds for failures to accumulate:" -ForegroundColor White
Write-Host "   Start-Sleep -Seconds 60" -ForegroundColor Cyan
Write-Host ""

Write-Host "2. Check pod status:" -ForegroundColor White
Write-Host "   kubectl get pods -n $Namespace --context $Context" -ForegroundColor Cyan
Write-Host ""

Write-Host "3. Run self-healing test:" -ForegroundColor White
Write-Host "   cd C:\aks-ai-agent" -ForegroundColor Cyan
Write-Host "   C:\Python311\python.exe -u test_step1_monitoring.py" -ForegroundColor Cyan
Write-Host ""

Write-Host "4. Watch self-healing in action:" -ForegroundColor White
Write-Host "   kubectl get pods -n $Namespace --context $Context --watch" -ForegroundColor Cyan
Write-Host ""

Write-Host ("=" * 70) -ForegroundColor Cyan
Write-Host "Demo Ready!" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Cyan
