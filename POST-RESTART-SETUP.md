# AI-Powered K8s Health Monitor — Setup Guide

Complete self-service guide. No dependencies on anyone — just follow the steps.

---

## Part A: One-Time Installation (only if tools are missing)

Open **PowerShell as Administrator** and run:

```powershell
# 1. Docker Desktop — download and install from https://www.docker.com/products/docker-desktop/
#    (Requires Windows restart after first install)

# 2. Python 3.11 — download from https://www.python.org/downloads/
#    Install to C:\Python311, check "Add to PATH"

# 3. Minikube
winget install Kubernetes.minikube

# 4. AWS CLI v2
winget install Amazon.AWSCLI

# 5. Git
winget install Git.Git
```

### One-Time: Configure AWS SSO Profile

Run this once to create the `my-sso` profile:

```powershell
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" configure sso
```

Enter these values when prompted:

| Prompt | Value |
|--------|-------|
| SSO session name | `my-sso` |
| SSO start URL | `https://identitycenter.amazonaws.com/ssoins-7223507b59100a4c` |
| SSO region | `us-east-1` |
| SSO registration scopes | `sso:account:access` |
| Account | `660759886267` |
| Role | `AdministratorAccess` |
| CLI default region | `us-east-2` |
| CLI default output | `json` |
| CLI profile name | `my-sso` |

### One-Time: Create Minikube Cluster

```powershell
minikube start -p aks-ai-agent-demo --driver=docker --cpus=2 --memory=1800mb
```

### One-Time: Deploy Demo Pods

```powershell
cd C:\aks-ai-agent
kubectl apply -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo
```

This creates 3 pods:
- `demo-crashloop` — intentionally crashes (CrashLoopBackOff)
- `demo-imagepull` — references a non-existent image (ImagePullBackOff)
- `demo-healthy` — runs normally (busybox, imagePullPolicy=Never)

### One-Time: Install Python Packages

```powershell
C:\Python311\python.exe -m pip install -r C:\aks-ai-agent\requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

### One-Time: Create `.env` File

Create `C:\aks-ai-agent\.env` with this content:

```ini
AI_PROVIDER=bedrock
AWS_REGION=us-east-2
AWS_SECRETS_REGION=us-east-1
AWS_PROFILE=my-sso
AWS_ACCESS_KEY_ID=@awssecret:ai-copilot:AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY=@awssecret:ai-copilot:AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN=@awssecret:ai-copilot:AWS_SESSION_TOKEN
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-6
BEDROCK_TEMPERATURE=0.2
BEDROCK_MAX_TOKENS=1024
K8S_CONTEXT=aks-ai-agent-demo
K8S_NAMESPACE=default
NOTIFICATION_PROVIDER=slack
NOTIFICATION_COOLDOWN_SECONDS=3
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### One-Time: Configure Git

```powershell
& "C:\Program Files\Git\cmd\git.exe" config --global user.name "Subodh Ukarde"
& "C:\Program Files\Git\cmd\git.exe" config --global user.email "t548771x@tdsynnex.com"
```

---

## Part B: After Every Restart (do these steps each time)

### Step 1 — Start Docker Desktop

Launch **Docker Desktop** from the Start menu. Wait for the whale icon in the system tray to show "Running" (takes ~30 seconds).

### Step 2 — Start Minikube

```powershell
minikube start -p aks-ai-agent-demo
```

Verify it's running:

```powershell
minikube status -p aks-ai-agent-demo
```

Expected output:
```
host: Running
kubelet: Running
apiserver: Running
kubeconfig: Configured
```

### Step 3 — Verify Demo Pods

```powershell
kubectl get pods -n default --context aks-ai-agent-demo
```

Expected output:
```
NAME             READY   STATUS             RESTARTS   AGE
demo-crashloop   0/1     CrashLoopBackOff   xxx        xxx
demo-healthy     1/1     Running            x          xxx
demo-imagepull   0/1     ImagePullBackOff   0          xxx
```

If pods are missing, re-create them:

```powershell
cd C:\aks-ai-agent
kubectl apply -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo
```

### Step 4 — AWS SSO Login (required every restart / every 8 hours)

```powershell
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" sso login --profile my-sso
```

This opens a browser. Click **Allow** to authorize.

Verify it worked:

```powershell
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" sts get-caller-identity --profile my-sso
```

Expected output (your ARN):
```json
{
    "UserId": "AROAZTWC3XG54WU4WTVLZ:subodhu@cybage.com",
    "Account": "660759886267",
    "Arn": "arn:aws:sts::660759886267:assumed-role/AWSReservedSSO_AdministratorAccess_.../subodhu@cybage.com"
}
```

### Step 5 — Verify Python Packages (quick check)

```powershell
C:\Python311\python.exe -c "import streamlit, boto3, requests, dotenv; print('All packages OK')"
```

If it fails, re-install:

```powershell
C:\Python311\python.exe -m pip install -r C:\aks-ai-agent\requirements.txt --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

---

## Part C: Running the Application

### Run the Monitoring Test (detects pods + sends Slack alerts)

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

Expected output:
```
Detected 2 failing pod(s), sent 2 notification(s)
  - demo-crashloop: CrashLoopBackOff
  - demo-imagepull: ImagePullBackOff
```

### Start the Streamlit Dashboard

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -m streamlit run dashboard.py --server.port 8501
```

Open in browser: **http://localhost:8501**

To stop: press `Ctrl+C` in the terminal.

### Open Minikube Dashboard (optional)

```powershell
minikube dashboard -p aks-ai-agent-demo
```

This opens the Kubernetes dashboard in your browser. Press `Ctrl+C` to stop.

---

## Part D: Git Operations

```powershell
cd C:\aks-ai-agent

# Check status
& "C:\Program Files\Git\cmd\git.exe" status

# Stage and commit
& "C:\Program Files\Git\cmd\git.exe" add -A
& "C:\Program Files\Git\cmd\git.exe" commit -m "your message here"

# Push to Azure DevOps
& "C:\Program Files\Git\cmd\git.exe" push origin feature/cyhackathon
```

Remote: `https://dev.azure.com/techdatacorp/Enterprise%20Distributed%20Development/_git/ai-agents`
Branch: `feature/cyhackathon`

---

## Part E: Troubleshooting

| Problem | Solution |
|---------|----------|
| `ExpiredTokenException` from Bedrock | AWS SSO session expired. Run Step 4 again |
| `The SSO session has expired` | Run Step 4 again |
| Minikube won't start | Make sure Docker Desktop is running first (Step 1) |
| `Unable to connect to the server` from kubectl | Minikube is stopped. Run Step 2 |
| Pods missing | Run `kubectl apply -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo` |
| `demo-healthy` in ImagePullBackOff | Delete and recreate: `kubectl delete pod demo-healthy --context aks-ai-agent-demo` then re-apply |
| `ModuleNotFoundError` in Python | Re-install packages (Step 5) |
| `pip install` SSL/certificate errors | Corporate proxy (Zscaler). Use `--trusted-host` flags as shown above |
| PowerShell won't run scripts | Use `powershell -ExecutionPolicy Bypass` to start your session |
| Slack notifications not arriving | Verify `SLACK_WEBHOOK_URL` in `.env` |
| Streamlit shows blank page | Check terminal for errors; ensure port 8501 is free |
| `aws.exe` not found | Use full path: `& "C:\Program Files\Amazon\AWSCLIV2\aws.exe"` |
| `git.exe` not found | Use full path: `& "C:\Program Files\Git\cmd\git.exe"` |

---

## Quick Reference: Tool Locations

| Tool | Full Path |
|------|-----------|
| Python | `C:\Python311\python.exe` |
| AWS CLI | `C:\Program Files\Amazon\AWSCLIV2\aws.exe` |
| Minikube | `C:\Program Files\Kubernetes\Minikube\minikube.exe` |
| kubectl | `C:\Program Files\Docker\Docker\resources\bin\kubectl.exe` |
| Git | `C:\Program Files\Git\cmd\git.exe` |
| Project | `C:\aks-ai-agent` |
