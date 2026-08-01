# Self-Healing Setup Script
# Run this to configure and test self-healing for the first time

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AKS AI Agent - Self-Healing Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "Error: .env file not found!" -ForegroundColor Red
    Write-Host "Please create .env from .env.example first." -ForegroundColor Yellow
    exit 1
}

Write-Host "Step 1: Installing python-dateutil dependency..." -ForegroundColor Green
C:\Python311\python.exe -m pip install python-dateutil>=2.8.0 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org

Write-Host ""
Write-Host "Step 2: Configuring self-healing settings..." -ForegroundColor Green

# Check if self-healing settings already exist in .env
$envContent = Get-Content ".env" -Raw
if ($envContent -notmatch "SELF_HEALING_ENABLED") {
    Write-Host "Adding self-healing configuration to .env..." -ForegroundColor Yellow
    
    $selfHealingConfig = @"

# ========== Self-Healing Actions ==========
# Enable automated self-healing for pod failures
SELF_HEALING_ENABLED=yes

# Self-healing mode: "auto" (execute immediately), "ask" (require approval), "disabled"
SELF_HEALING_MODE=auto

# Dry run mode - log actions without executing (RECOMMENDED for first test)
SELF_HEALING_DRY_RUN=yes

# Maximum self-healing actions per hour (rate limit)
SELF_HEALING_MAX_ACTIONS_PER_HOUR=10

# Action-specific thresholds
RESTART_MIN_CRASH_COUNT=5
RESTART_MIN_INTERVAL_SECONDS=300
SCALE_UP_MIN_OOM_COUNT=2
SCALE_UP_MAX_REPLICAS=10
IMAGEPULL_RETRY_MAX_AGE_SECONDS=1800
"@
    
    Add-Content -Path ".env" -Value $selfHealingConfig
    Write-Host "✓ Self-healing configuration added to .env" -ForegroundColor Green
} else {
    Write-Host "✓ Self-healing configuration already exists in .env" -ForegroundColor Green
}

Write-Host ""
Write-Host "Step 3: Testing self-healing with DRY RUN..." -ForegroundColor Green
Write-Host "(No actual changes will be made)" -ForegroundColor Yellow
Write-Host ""

# Run test
C:\Python311\python.exe -u test_step1_monitoring.py

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "1. Review the test output above to see what actions would be taken" -ForegroundColor White
Write-Host "2. If satisfied, disable dry run mode in .env:" -ForegroundColor White
Write-Host "   SELF_HEALING_DRY_RUN=no" -ForegroundColor Cyan
Write-Host "3. Run the test again to execute actions for real" -ForegroundColor White
Write-Host "4. Read SELF-HEALING-GUIDE.md for full documentation" -ForegroundColor White
Write-Host ""
Write-Host "Configuration file: .env" -ForegroundColor Gray
Write-Host "Documentation: SELF-HEALING-GUIDE.md" -ForegroundColor Gray
Write-Host ""
