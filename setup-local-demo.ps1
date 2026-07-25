<#
.SYNOPSIS
    Spins up a local minikube cluster and runs the AKS AI Agent against it,
    end to end, for demo purposes - no real AKS cluster required.

.DESCRIPTION
    1. Verifies docker / minikube / kubectl are installed
    2. Starts (or reuses) a minikube cluster
    3. Builds the agent's Docker image and loads it into minikube
    4. Applies namespace / RBAC / local PVC / local Secret manifests
    5. Deploys two intentionally-broken demo pods (CrashLoopBackOff, ImagePullBackOff)
    6. Runs the agent as a one-off Job and tails its logs

.PARAMETER Teardown
    Delete the local demo cluster entirely.

.PARAMETER Reset
    Remove just the demo Job + broken pods (keeps the cluster running) so you
    can re-apply cleanly.

.PARAMETER SkipBuild
    Skip the docker build/load step (reuse the image already loaded into minikube).

.PARAMETER AzureEndpoint
.PARAMETER AzureApiKey
.PARAMETER AzureModelDeployment
    Optional real Azure OpenAI values. If omitted, the agent automatically
    falls back to deterministic (non-AI) analysis - the demo still works.

.PARAMETER TeamsWebhookUrl
    Optional MS Teams incoming webhook URL. If omitted, notifications are
    skipped gracefully (logged, not sent).

.PARAMETER SlackWebhookUrl
    Optional Slack incoming webhook URL (sent alongside MS Teams). If omitted,
    Slack notifications are skipped gracefully (logged, not sent).

.EXAMPLE
    ./setup-local-demo.ps1

.EXAMPLE
    ./setup-local-demo.ps1 -AzureEndpoint "https://my-resource.services.ai.azure.com/openai/v1" -AzureApiKey "xxxx"

.EXAMPLE
    ./setup-local-demo.ps1 -Reset       # re-run the demo on an already-running cluster
.EXAMPLE
    ./setup-local-demo.ps1 -Teardown    # delete the local cluster
#>

[CmdletBinding()]
param(
    [switch]$Teardown,
    [switch]$Reset,
    [switch]$SkipBuild,
    [string]$AzureEndpoint = "",
    [string]$AzureApiKey = "",
    [string]$AzureModelDeployment = "gpt-4o-mini",
    [string]$TeamsWebhookUrl = "",
    [string]$SlackWebhookUrl = "",
    [string]$AiProvider = "",
    [string]$AwsRegion = "",
    [string]$BedrockModelId = "",
    [string]$BedrockTemperature = "",
    [string]$BedrockMaxTokens = "",
    [string]$AwsAccessKeyId = "",
    [string]$AwsSecretAccessKey = "",
    [string]$AwsSessionToken = "",
    [string]$NotificationProvider = "",
    [string]$ClusterName = "aks-ai-agent-demo",
    [string]$ImageName = "aks-ai-agent:local",
    [int]$MemoryMb = 1800,
    [int]$Cpus = 2
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Refresh PATH from the registry in case a tool (e.g. minikube) was installed
# by winget/an installer after this PowerShell session started.
$machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machinePath;$userPath"

# ---------------------------------------------------------------------------
# Load optional .env for real credentials (never passed on the command line,
# never printed) — CLI params above still take precedence if explicitly set.
# ---------------------------------------------------------------------------
function Import-DotEnv {
    param([string]$Path)
    $vars = @{}
    if (Test-Path $Path) {
        Get-Content $Path | ForEach-Object {
            $line = $_.Trim()
            if ($line -and -not $line.StartsWith('#')) {
                $idx = $line.IndexOf('=')
                if ($idx -gt 0) {
                    $key = $line.Substring(0, $idx).Trim()
                    $val = $line.Substring($idx + 1).Trim()
                    # Strip a single matching pair of surrounding quotes, if present
                    if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
                        if ($val.Length -ge 2) { $val = $val.Substring(1, $val.Length - 2) }
                    }
                    if ($val -and -not $vars.ContainsKey($key)) { $vars[$key] = $val }
                }
            }
        }
    }
    return $vars
}
$dotenv = Import-DotEnv (Join-Path $PSScriptRoot ".env")
function Get-EnvOrParam {
    param([string]$ParamValue, [string]$Key, [string]$Default = "")
    if ($ParamValue) { return $ParamValue }
    if ($dotenv.ContainsKey($Key)) { return $dotenv[$Key] }
    return $Default
}
$AzureEndpoint        = Get-EnvOrParam $AzureEndpoint 'AZURE_INFERENCE_ENDPOINT'
$AzureApiKey          = Get-EnvOrParam $AzureApiKey 'AZURE_API_KEY'
$AzureModelDeployment = Get-EnvOrParam $AzureModelDeployment 'AZURE_MODEL_DEPLOYMENT' 'gpt-4o-mini'
$TeamsWebhookUrl      = Get-EnvOrParam $TeamsWebhookUrl 'MS_TEAMS_WEBHOOK_URL'
$SlackWebhookUrl      = Get-EnvOrParam $SlackWebhookUrl 'SLACK_WEBHOOK_URL'
$AiProvider           = Get-EnvOrParam $AiProvider 'AI_PROVIDER' 'azure'
$AwsRegion            = Get-EnvOrParam $AwsRegion 'AWS_REGION' 'us-east-2'
$BedrockModelId       = Get-EnvOrParam $BedrockModelId 'BEDROCK_MODEL_ID' 'openai.gpt-oss-120b-1:0'
$BedrockTemperature   = Get-EnvOrParam $BedrockTemperature 'BEDROCK_TEMPERATURE' '0.2'
$BedrockMaxTokens     = Get-EnvOrParam $BedrockMaxTokens 'BEDROCK_MAX_TOKENS' '1024'
$AwsAccessKeyId       = Get-EnvOrParam $AwsAccessKeyId 'AWS_ACCESS_KEY_ID'
$AwsSecretAccessKey   = Get-EnvOrParam $AwsSecretAccessKey 'AWS_SECRET_ACCESS_KEY'
$AwsSessionToken      = Get-EnvOrParam $AwsSessionToken 'AWS_SESSION_TOKEN'
$NotificationProvider = Get-EnvOrParam $NotificationProvider 'NOTIFICATION_PROVIDER' 'both'
# Skip the Teams webhook if it's a Key Vault reference placeholder (unresolved locally)
if ($TeamsWebhookUrl -like '@keyvault:*') { $TeamsWebhookUrl = "" }

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: '$Name' was not found on PATH." -ForegroundColor Red
        Write-Host "  $InstallHint" -ForegroundColor Yellow
        exit 1
    }
}

# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------
if ($Teardown) {
    Write-Step "Deleting minikube cluster '$ClusterName'"
    Assert-Command minikube "Install with: winget install Kubernetes.minikube"
    minikube delete -p $ClusterName
    exit 0
}

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
Write-Step "Checking prerequisites"
Assert-Command docker   "Install Docker Desktop: https://www.docker.com/products/docker-desktop/"
Assert-Command minikube "Install with: winget install Kubernetes.minikube"
Assert-Command kubectl  "Install with: winget install Kubernetes.kubectl"

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker does not appear to be running. Start Docker Desktop and retry." -ForegroundColor Red
    exit 1
}
Write-Host "docker, minikube, kubectl all found." -ForegroundColor Green

# ---------------------------------------------------------------------------
# Reset (demo resources only)
# ---------------------------------------------------------------------------
if ($Reset) {
    Write-Step "Resetting demo resources on existing cluster '$ClusterName'"
    kubectl config use-context $ClusterName
    kubectl delete job aks-ai-agent-demo -n platform-ops --ignore-not-found
    kubectl delete -f k8s/local/demo-broken-pods.yaml --ignore-not-found
    kubectl apply -f k8s/local/demo-broken-pods.yaml
}
else {
    # -----------------------------------------------------------------------
    # 1. Start (or reuse) the minikube cluster
    # -----------------------------------------------------------------------
    Write-Step "Starting minikube cluster '$ClusterName'"
    $running = $false
    try {
        $statusJson = minikube status -p $ClusterName -o json 2>$null | ConvertFrom-Json
        $running = ($statusJson.Host -eq "Running")
    } catch { $running = $false }

    if ($running) {
        Write-Host "Cluster '$ClusterName' is already running - reusing it." -ForegroundColor Green
    }
    else {
        minikube start -p $ClusterName --driver=docker --cpus=$Cpus --memory=${MemoryMb}mb
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: minikube start failed." -ForegroundColor Red
            Write-Host "  If the error mentions insufficient memory, either re-run with a lower value, e.g.:" -ForegroundColor Yellow
            Write-Host "    ./setup-local-demo.ps1 -MemoryMb 1400" -ForegroundColor Yellow
            Write-Host "  or increase Docker Desktop's memory limit: Docker Desktop > Settings > Resources > Memory." -ForegroundColor Yellow
            exit 1
        }
    }
    kubectl config use-context $ClusterName
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: could not switch kubectl context to '$ClusterName'." -ForegroundColor Red
        exit 1
    }

    # -----------------------------------------------------------------------
    # 2. Build + load the agent image
    # -----------------------------------------------------------------------
    if (-not $SkipBuild) {
        Write-Step "Building Docker image '$ImageName'"
        docker build -t $ImageName .
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Build failed, retrying once (transient registry/network errors are common)..." -ForegroundColor Yellow
            docker build -t $ImageName .
            if ($LASTEXITCODE -ne 0) {
                Write-Host "ERROR: docker build failed twice. See output above for details." -ForegroundColor Red
                exit 1
            }
        }

        Write-Step "Loading image into minikube"
        minikube image load $ImageName -p $ClusterName
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: failed to load image into minikube." -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host "Skipping build (using image already loaded)." -ForegroundColor Yellow
    }

    # -----------------------------------------------------------------------
    # 3. Namespace, RBAC, PVC, Secret
    # -----------------------------------------------------------------------
    Write-Step "Applying namespace + RBAC"
    kubectl apply -f k8s/namespace.yaml
    kubectl apply -f k8s/rbac.yaml

    Write-Step "Applying local PVC (storageClassName: standard)"
    kubectl apply -f k8s/local/pvc.yaml

    Write-Step "Applying local Secret"
    $secretYaml = Get-Content k8s/local/secret.yaml -Raw
    $secretYaml = $secretYaml.Replace('__AI_PROVIDER__', $AiProvider)
    $secretYaml = $secretYaml.Replace('__AZURE_ENDPOINT__', $AzureEndpoint)
    $secretYaml = $secretYaml.Replace('__AZURE_MODEL__', $AzureModelDeployment)
    $secretYaml = $secretYaml.Replace('__AZURE_API_KEY__', $AzureApiKey)
    $secretYaml = $secretYaml.Replace('__AWS_REGION__', $AwsRegion)
    $secretYaml = $secretYaml.Replace('__BEDROCK_MODEL_ID__', $BedrockModelId)
    $secretYaml = $secretYaml.Replace('__BEDROCK_TEMPERATURE__', $BedrockTemperature)
    $secretYaml = $secretYaml.Replace('__BEDROCK_MAX_TOKENS__', $BedrockMaxTokens)
    $secretYaml = $secretYaml.Replace('__AWS_ACCESS_KEY_ID__', $AwsAccessKeyId)
    $secretYaml = $secretYaml.Replace('__AWS_SECRET_ACCESS_KEY__', $AwsSecretAccessKey)
    $secretYaml = $secretYaml.Replace('__AWS_SESSION_TOKEN__', $AwsSessionToken)
    $secretYaml = $secretYaml.Replace('__NOTIFICATION_PROVIDER__', $NotificationProvider)
    $secretYaml = $secretYaml.Replace('__TEAMS_WEBHOOK__', $TeamsWebhookUrl)
    $secretYaml = $secretYaml.Replace('__SLACK_WEBHOOK__', $SlackWebhookUrl)
    $secretYaml | kubectl apply -f -

    # -----------------------------------------------------------------------
    # 4. Demo broken pods
    # -----------------------------------------------------------------------
    Write-Step "Deploying demo broken pods (CrashLoopBackOff, ImagePullBackOff)"
    kubectl apply -f k8s/local/demo-broken-pods.yaml
}

# ---------------------------------------------------------------------------
# 5. Run the agent as a one-off Job and tail its logs
# ---------------------------------------------------------------------------
Write-Step "Running the agent (one-off Job)"
kubectl delete job aks-ai-agent-demo -n platform-ops --ignore-not-found
$jobYaml = (Get-Content k8s/local/job.yaml -Raw).Replace('__IMAGE__', $ImageName)
$jobYaml | kubectl apply -f -

Write-Host "Waiting for pod to be scheduled..."
kubectl wait --for=condition=Ready pod -l job-name=aks-ai-agent-demo -n platform-ops --timeout=60s 2>$null

Write-Step "Agent output"
kubectl wait --for=condition=complete job/aks-ai-agent-demo -n platform-ops --timeout=120s 2>$null
kubectl logs job/aks-ai-agent-demo -n platform-ops --follow --tail=-1

Write-Step "Done"
Write-Host "Re-run the demo:        ./setup-local-demo.ps1 -Reset"
Write-Host "View broken pods:       kubectl get pods -n default"
Write-Host "Tail logs again:        kubectl logs job/aks-ai-agent-demo -n platform-ops"
Write-Host "Tear down the cluster:  ./setup-local-demo.ps1 -Teardown"
