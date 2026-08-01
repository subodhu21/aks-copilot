# 🎬 Run Complete Self-Healing Demo

## One-Command Demo

This single script runs the complete demo automatically:

1. ✅ **Cleanup** - Remove old resources
2. ❌ **Deploy** - Create broken pods (CrashLoopBackOff, ImagePullBackOff)
3. ⏳ **Wait** - Let pods accumulate failures (45 seconds)
4. 🔍 **Detect** - AI scans and finds failures
5. 📧 **Notify** - Send Slack notifications
6. ⏱️ **Delay** - Wait 1 minute (demo presentation window)
7. 🤖 **Heal** - AI auto-heals the pods
8. 🔧 **Fix** - Apply correct configurations
9. ✅ **Verify** - Confirm all pods are healthy

---

## Quick Start

### Option 1: Python Script (Recommended)

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe run-complete-demo.py
```

### Option 2: PowerShell Script

```powershell
cd C:\aks-ai-agent\k8s\demo-deployments
.\run-complete-demo.ps1
```

---

## What You'll See

### Phase 1: Deployment (0-45 seconds)
```
STEP 1/9: Cleanup - Remove any existing demo resources
  🧹 Deleting existing deployments...
  ✅ Cleanup complete

STEP 2/9: Deploy Broken Pods
  📋 Deploying api-gateway (will crash - missing REDIS_HOST)...
  📋 Deploying web-frontend (will fail - non-existent image)...
  ✅ Deployments created

STEP 3/9: Wait for Pods to Fail
  ⏳ Waiting for pods to accumulate failures...
  ⏱️  45s remaining...
  ⏱️  40s remaining...
  ...
  📊 Current pod status:
  NAME                          STATUS
  api-gateway-xxx               Error
  api-gateway-yyy               CrashLoopBackOff
  web-frontend-xxx              ImagePullBackOff
  web-frontend-yyy              ErrImagePull
```

### Phase 2: Detection & Notification (45-90 seconds)
```
STEP 4/9: Run Monitoring - Detect Failures and Send Notifications
  🔍 AI is now scanning the cluster for failures...
  📧 Notifications will be sent to Slack...
  ⏳ Then AI will wait 1 minute before auto-healing...

  [Self-Healing] Evaluating 4 failing pods...
  [Self-Healing] ⏳ Waiting 60 seconds before starting auto-healing...
  [Self-Healing] 💡 This delay allows you to show the failure notification in your demo
  [Self-Healing] ⏱️  Auto-healing starts in 60 seconds...
  [Self-Healing] ⏱️  Auto-healing starts in 50 seconds...
  [Self-Healing] ⏱️  Auto-healing starts in 40 seconds...
  ...
```

**👉 This is your presentation window!**
- Show Slack notification
- Explain failures in dashboard
- Talk about AI analysis
- Build anticipation

### Phase 3: Auto-Healing (90-120 seconds)
```
  [Self-Healing] 🤖 Starting auto-healing now!

  Executing action 1/4: RestartCrashLoopPod
    Pod: api-gateway-xxx
    Status: ✅ Success - New pod api-gateway-abc is Running

  Executing action 2/4: RestartCrashLoopPod
    Pod: api-gateway-yyy
    Status: ✅ Success - New pod api-gateway-def is Running

  Executing action 3/4: RetryImagePull
    Pod: web-frontend-xxx
    Status: ✅ Executed (pod deleted for retry)

  Executing action 4/4: RetryImagePull
    Pod: web-frontend-yyy
    Status: ✅ Executed (pod deleted for retry)

  [Self-Healing] 📧 Sending healing success notification to Slack...
  [Self-Healing] ✅ Healing notification sent!
```

**👉 Check Slack for the healing success notification!**

### Phase 4: Configuration Fix (120-180 seconds)
```
STEP 6/9: Apply Fixed Configurations
  🔧 Applying api-gateway fix (adding REDIS_HOST)...
  ✅ deployment.apps/api-gateway configured

  🔧 Applying web-frontend fix (using nginx image)...
  ✅ deployment.apps/web-frontend configured

STEP 7/9: Wait for Pods to Become Healthy
  ⏳ Waiting for api-gateway pods to be ready...
  pod/api-gateway-abc condition met
  pod/api-gateway-def condition met

  ⏳ Waiting for web-frontend pods to be ready...
  pod/web-frontend-ghi condition met
  pod/web-frontend-jkl condition met
```

### Phase 5: Success! (180 seconds)
```
STEP 8/9: Verify All Pods Are Healthy
  NAME                          READY   STATUS    RESTARTS   AGE
  api-gateway-abc               1/1     Running   0          45s
  api-gateway-def               1/1     Running   0          45s
  web-frontend-ghi              1/1     Running   0          30s
  web-frontend-jkl              1/1     Running   0          30s

======================================================================
✅ DEMO COMPLETE!
======================================================================

What happened:
  1. ❌ Deployed 4 broken pods (2 CrashLoopBackOff, 2 ImagePullBackOff)
  2. 🔍 AI detected the failures
  3. 📧 Notifications sent to Slack
  4. ⏳ Waited 1 minute (demo delay)
  5. 🤖 AI auto-healed the pods (restart/retry)
  6. 🔧 Applied configuration fixes
  7. ✅ All pods are now healthy!

View Results:
  Dashboard: http://127.0.0.1:63390
  All 4 pods should be green and Running
```

---

## Timeline

| Time | Phase | What Happens |
|------|-------|--------------|
| 0:00 | Cleanup | Remove old demo resources |
| 0:10 | Deploy | Create broken pods |
| 0:55 | Wait | Pods accumulate failures |
| 1:00 | Detect | AI scans and sends notifications |
| 1:10 | Delay Start | 60-second countdown begins |
| **1:10-2:10** | **Your Presentation Window** | **Show Slack, explain failures** |
| 2:10 | Heal | AI executes auto-healing |
| 2:20 | Fix | Apply correct configs |
| 2:50 | Verify | Confirm all pods healthy |
| 3:00 | Done | Demo complete! |

**Total Duration:** ~3 minutes

---

## Configuration

The demo uses settings from `.env`:

```bash
# Self-healing enabled
SELF_HEALING_ENABLED=yes
SELF_HEALING_MODE=auto
SELF_HEALING_DRY_RUN=no

# 1-minute delay for demo
SELF_HEALING_DELAY_SECONDS=60

# Disable recovery notifications (avoid premature alerts during healing)
SEND_RECOVERY_NOTIFICATIONS=no

# Kubernetes context
K8S_CONTEXT=aks-ai-agent-demo
```

**Note:** Recovery notifications are disabled to avoid confusing "Recovered!" alerts that would be sent when self-healing deletes pods, before the fixed configuration is even applied.

---

## Before Running

### Prerequisites
1. ✅ Minikube cluster running
2. ✅ Dashboard accessible (http://127.0.0.1:63390)
3. ✅ Python with dependencies installed
4. ✅ kubectl configured with `aks-ai-agent-demo` context
5. ✅ Slack webhook configured (optional)

### Verify Setup
```powershell
# Check cluster
minikube status -p aks-ai-agent-demo

# Check context
kubectl config current-context

# Test delay config
C:\Python311\python.exe test_delay.py
```

---

## During the Demo

### At 1:10 (Notification Sent)
**Show:**
- Slack channel with failure alert
- Dashboard with 4 red pods

**Say:**
- "The AI detected 4 failing pods"
- "Notifications were sent to our team"
- "Now the AI is analyzing whether it's safe to auto-heal"

### At 1:30 (Countdown Visible)
**Show:**
- Console countdown: "Auto-healing starts in 40 seconds..."
- Pod details in dashboard (logs, events)

**Say:**
- "The AI has validated safety checks"
- "Rate limits and cooldowns are being enforced"
- "Watch the countdown - healing is about to start"

### At 2:10 (Healing Executes)
**Show:**
- Console output showing actions
- Dashboard refreshing with new pod names

**Say:**
- "There it goes! AI is restarting the crash-loop pods"
- "It's retrying the image pull failures"
- "All actions are being logged for audit"

### At 2:50 (All Green)
**Show:**
- Dashboard with 4 green pods
- All Running status, low restart counts

**Say:**
- "Success! All pods are now healthy"
- "The entire process was automated"
- "From detection to resolution in under 2 minutes"

---

## After the Demo

### View Results
```powershell
# Check pods
kubectl get pods --context aks-ai-agent-demo

# View self-healing log
C:\Python311\python.exe view_self_healing_stats.py

# Check state file
Get-Content self_healing_state.json | ConvertFrom-Json
```

### Cleanup
```powershell
cd C:\aks-ai-agent\k8s\demo-deployments
.\cleanup-demo.ps1
```

---

## Troubleshooting

### Demo Fails to Start
**Check:**
```powershell
# Verify cluster is running
minikube status -p aks-ai-agent-demo

# Verify context
kubectl config get-contexts
```

### Pods Don't Turn Green
**Possible causes:**
- Image pull taking too long (wait longer)
- Minikube resources low (restart minikube)
- Configuration issue (check fixed YAML files)

**Solution:**
```powershell
# Check pod logs
kubectl logs <pod-name> --context aks-ai-agent-demo

# Reapply fixes manually
kubectl apply -f k8s/demo-deployments/01-api-gateway-fixed.yaml
kubectl apply -f k8s/demo-deployments/03-web-frontend-fixed.yaml
```

### No Notifications Sent
**Check:**
```powershell
# Verify Slack webhook in .env
grep SLACK_WEBHOOK_URL .env
```

### Delay Not Working
**Check:**
```powershell
# Verify delay setting
C:\Python311\python.exe test_delay.py
```

---

## Re-run the Demo

The script can be run multiple times:

```powershell
# Run again
C:\Python311\python.exe run-complete-demo.py
```

Each run:
- ✅ Cleans up previous resources
- ✅ Starts fresh with broken pods
- ✅ Goes through complete flow
- ✅ Ends with healthy pods

---

## Files

### Main Script
- `run-complete-demo.py` - Complete automated demo (Python)
- `k8s/demo-deployments/run-complete-demo.ps1` - PowerShell version

### Broken Configs (for demo)
- `k8s/demo-deployments/01-api-gateway-crashloop.yaml`
- `k8s/demo-deployments/03-web-frontend-imagepull.yaml`

### Fixed Configs (applied automatically)
- `k8s/demo-deployments/01-api-gateway-fixed.yaml`
- `k8s/demo-deployments/03-web-frontend-fixed.yaml`

### Documentation
- `RUN-DEMO.md` - This file
- `DEMO-READY-WITH-DELAY.md` - Configuration guide
- `k8s/demo-deployments/DEMO-WITH-DELAY.md` - Detailed demo guide

---

## Success Criteria

✅ **Demo is successful when:**
1. Script completes without errors
2. All 4 pods end up in Running state
3. Slack notification was sent
4. 1-minute delay was visible
5. Self-healing actions were logged
6. Dashboard shows all green pods

---

## Ready to Present!

**Just run:**
```powershell
C:\Python311\python.exe run-complete-demo.py
```

**Total time:** 3 minutes from start to finish

**Your presentation window:** 1 minute (while countdown is running)

**Dashboard:** http://127.0.0.1:63390

🎉 **Break a leg!**
