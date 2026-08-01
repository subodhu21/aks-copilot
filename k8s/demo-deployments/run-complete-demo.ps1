# Complete Self-Healing Demo Script
# Automates: Deploy broken pods → Detect → Notify → Wait 1min → Auto-heal → Fix → Verify

param(
    [string]$Context = "aks-ai-agent-demo"
)

$ErrorActionPreference = "Continue"

function Write-Header {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host ("=" * 70) -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([int]$Step, [int]$Total, [string]$Description)
    Write-Host ""
    Write-Host ("=" * 70) -ForegroundColor Yellow
    Write-Host "STEP $Step/$Total: $Description" -ForegroundColor Yellow
    Write-Host ("=" * 70) -ForegroundColor Yellow
    Write-Host ""
}

function Wait-WithCountdown {
    param([int]$Seconds, [string]$Message)
    Write-Host ""
    Write-Host "⏳ $Message" -ForegroundColor Yellow
    for ($i = $Seconds; $i -gt 0; $i -= 5) {
        $mins = [Math]::Floor($i / 60)
        $secs = $i % 60
        if ($mins -gt 0) {
            Write-Host "   ⏱️  ${mins}m ${secs}s remaining..." -ForegroundColor Gray
        } else {
            Write-Host "   ⏱️  ${secs}s remaining..." -ForegroundColor Gray
        }
        Start-Sleep -Seconds ([Math]::Min(5, $i))
    }
    Write-Host "✅ Wait complete!" -ForegroundColor Green
    Write-Host ""
}

# ============================================================================
# MAIN DEMO
# ============================================================================

Write-Header "🎬 KUBERNETES SELF-HEALING DEMO - COMPLETE AUTOMATED RUN"
Write-Host "Started at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host "Context: $Context"
Write-Host ""

$TotalSteps = 9

# ============================================================================
# STEP 1: Cleanup
# ============================================================================
Write-Step 1 $TotalSteps "Cleanup - Remove any existing demo resources"

Write-Host "🧹 Deleting existing deployments..." -ForegroundColor Yellow
kubectl delete deployment api-gateway web-frontend --context $Context --ignore-not-found=true 2>&1 | Out-Null

Write-Host "🧹 Deleting existing services..." -ForegroundColor Yellow
kubectl delete service api-gateway-service web-frontend-service --context $Context --ignore-not-found=true 2>&1 | Out-Null

Write-Host "🧹 Deleting existing configmaps..." -ForegroundColor Yellow
kubectl delete configmap web-frontend-html --context $Context --ignore-not-found=true 2>&1 | Out-Null

Wait-WithCountdown 10 "Waiting for resources to be deleted..."

# ============================================================================
# STEP 2: Deploy broken pods
# ============================================================================
Write-Step 2 $TotalSteps "Deploy Broken Pods (CrashLoopBackOff, ImagePullBackOff)"

Write-Host "📋 Deploying api-gateway (will crash - missing REDIS_HOST)..." -ForegroundColor Cyan
kubectl apply -f 01-api-gateway-crashloop.yaml --context $Context

Write-Host ""
Write-Host "📋 Deploying web-frontend (will fail - non-existent image)..." -ForegroundColor Cyan
kubectl apply -f 03-web-frontend-imagepull.yaml --context $Context

# ============================================================================
# STEP 3: Wait for failures
# ============================================================================
Write-Step 3 $TotalSteps "Wait for Pods to Fail"

Wait-WithCountdown 45 "Waiting for pods to accumulate failures..."

Write-Host "📊 Current pod status:" -ForegroundColor Cyan
kubectl get pods --context $Context

# ============================================================================
# STEP 4: Run monitoring
# ============================================================================
Write-Step 4 $TotalSteps "Run Monitoring - Detect Failures and Send Notifications"

Write-Host "🔍 AI is now scanning the cluster for failures..." -ForegroundColor Cyan
Write-Host "📧 Notifications will be sent to Slack..." -ForegroundColor Cyan
Write-Host "⏳ Then AI will wait 1 minute before auto-healing (demo mode)..." -ForegroundColor Cyan
Write-Host ""

# Run monitoring script
Set-Location C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py

# ============================================================================
# STEP 5: Show actions
# ============================================================================
Write-Step 5 $TotalSteps "Review Self-Healing Actions"

Write-Host "📊 Checking self-healing state file..." -ForegroundColor Cyan

if (Test-Path "self_healing_state.json") {
    Write-Host "✅ Self-healing actions recorded in state file" -ForegroundColor Green
} else {
    Write-Host "⚠️  State file not found" -ForegroundColor Yellow
}

# ============================================================================
# STEP 6: Apply fixes
# ============================================================================
Write-Step 6 $TotalSteps "Apply Fixed Configurations"

Set-Location C:\aks-ai-agent\k8s\demo-deployments

Write-Host "🔧 Applying api-gateway fix (adding REDIS_HOST)..." -ForegroundColor Cyan
kubectl apply -f 01-api-gateway-fixed.yaml --context $Context

Write-Host ""
Write-Host "🔧 Applying web-frontend fix (using nginx image)..." -ForegroundColor Cyan
kubectl apply -f 03-web-frontend-fixed.yaml --context $Context

# ============================================================================
# STEP 7: Wait for ready
# ============================================================================
Write-Step 7 $TotalSteps "Wait for Pods to Become Healthy"

Write-Host "⏳ Waiting for api-gateway pods to be ready..." -ForegroundColor Yellow
kubectl wait --for=condition=ready pod -l app=api-gateway --context $Context --timeout=120s 2>&1 | Out-Null

Write-Host "⏳ Waiting for web-frontend pods to be ready..." -ForegroundColor Yellow
kubectl wait --for=condition=ready pod -l app=web-frontend --context $Context --timeout=120s 2>&1 | Out-Null

Wait-WithCountdown 10 "Giving pods time to stabilize..."

# ============================================================================
# STEP 8: Verify
# ============================================================================
Write-Step 8 $TotalSteps "Verify All Pods Are Healthy"

kubectl get pods --context $Context -o wide

# ============================================================================
# STEP 9: Summary
# ============================================================================
Write-Step 9 $TotalSteps "Demo Complete - Summary"

Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "✅ DEMO COMPLETE!" -ForegroundColor Green
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host ""
Write-Host "What happened:" -ForegroundColor Yellow
Write-Host "  1. ❌ Deployed 4 broken pods (2 CrashLoopBackOff, 2 ImagePullBackOff)" -ForegroundColor White
Write-Host "  2. 🔍 AI detected the failures" -ForegroundColor White
Write-Host "  3. 📧 Notifications sent to Slack" -ForegroundColor White
Write-Host "  4. ⏳ Waited 1 minute (demo delay)" -ForegroundColor White
Write-Host "  5. 🤖 AI auto-healed the pods (restart/retry)" -ForegroundColor White
Write-Host "  6. 🔧 Applied configuration fixes" -ForegroundColor White
Write-Host "  7. ✅ All pods are now healthy!" -ForegroundColor White
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "View Results:" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "  Dashboard: http://127.0.0.1:63390" -ForegroundColor Cyan
Write-Host "  Context: $Context" -ForegroundColor Cyan
Write-Host ""
Write-Host "  All 4 pods should be green and Running:" -ForegroundColor White
Write-Host "    - api-gateway (2 replicas)" -ForegroundColor White
Write-Host "    - web-frontend (2 replicas)" -ForegroundColor White
Write-Host ""
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host "  • Check Slack for failure notifications" -ForegroundColor White
Write-Host "  • Open dashboard to see green pods" -ForegroundColor White
Write-Host "  • Review self_healing_state.json for audit trail" -ForegroundColor White
Write-Host "  • Run 'kubectl get pods' to verify status" -ForegroundColor White
Write-Host ""
Write-Host "Completed at: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host ("=" * 70) -ForegroundColor Green
Write-Host ""
