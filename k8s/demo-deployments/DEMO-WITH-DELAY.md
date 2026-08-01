# 🎬 Self-Healing Demo with 1-Minute Delay

## Overview

This demo includes a **1-minute delay** between:
1. **Pod failure detection & notification** ❌
2. **Auto-healing execution** 🤖

This makes it perfect for presentations where you want to show:
- "Look, the AI detected a failure and sent a notification!"
- *[Wait 1 minute while explaining]*
- "Now watch as the AI automatically heals the pod!"

---

## Configuration

The delay is controlled by this setting in `.env`:

```bash
# Demo delay: Wait N seconds after notification before starting auto-healing
SELF_HEALING_DELAY_SECONDS=60
```

**Options:**
- `60` = 1 minute delay (demo mode) ✅ **Current setting**
- `0` = No delay (immediate healing for production)
- `120` = 2 minutes (longer demo)

---

## Demo Flow with 1-Minute Delay

### Step 1: Deploy Broken Pods
```powershell
cd C:\aks-ai-agent\k8s\demo-deployments
kubectl apply -f 01-api-gateway-crashloop.yaml --context aks-ai-agent-demo
kubectl apply -f 03-web-frontend-imagepull.yaml --context aks-ai-agent-demo
```

**Show in Dashboard:** http://127.0.0.1:63390
- 4 pods in red (2 CrashLoopBackOff, 2 ImagePullBackOff)

---

### Step 2: Run Monitoring (Shows Delay)
```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe test_step1_monitoring.py
```

**What You'll See:**

```
================================================
SELF-HEALING ACTIONS
================================================
Enabled: True
Mode: auto

[Self-Healing] Evaluating 4 failing pods...
[Self-Healing] ⏳ Waiting 60 seconds before starting auto-healing...
[Self-Healing] 💡 This delay allows you to show the failure notification in your demo
[Self-Healing] ⏱️  Auto-healing starts in 60 seconds...
[Self-Healing] ⏱️  Auto-healing starts in 50 seconds...
[Self-Healing] ⏱️  Auto-healing starts in 40 seconds...
[Self-Healing] ⏱️  Auto-healing starts in 30 seconds...
[Self-Healing] ⏱️  Auto-healing starts in 20 seconds...
[Self-Healing] ⏱️  Auto-healing starts in 10 seconds...
[Self-Healing] 🤖 Starting auto-healing now!

✅ RestartCrashLoopPod - api-gateway-xxx → Success
✅ RestartCrashLoopPod - api-gateway-yyy → Success
✅ RetryImagePull - web-frontend-xxx → Success
✅ RetryImagePull - web-frontend-yyy → Success
```

---

### Step 3: During the 1-Minute Wait

**This is your presentation window!** Use this time to:

#### Show the Failure Notification
- Open Slack/Teams channel
- Point out the notification that was just sent
- Read the error message aloud

#### Explain the Dashboard
- Show red pods in Minikube dashboard
- Click on a pod to show logs
- Explain the root cause (missing env var, bad image)

#### Explain What AI Will Do
- "In production, this would heal immediately"
- "For demo, we added a 1-minute delay"
- "Watch the countdown - AI is analyzing the failures"
- "It's planning the remediation actions"

#### Build Anticipation
- "The AI has decided to restart these pods"
- "It verified this is safe - passed all safety checks"
- "Now it's waiting for permission to execute"
- "Watch what happens when the timer hits zero..."

---

### Step 4: Auto-Healing Executes

After 60 seconds:

```
[Self-Healing] 🤖 Starting auto-healing now!

Executing action 1/4: RestartCrashLoopPod
  Pod: api-gateway-xxx
  ✅ Success: New pod api-gateway-abc is Running
  
Executing action 2/4: RestartCrashLoopPod
  Pod: api-gateway-yyy
  ✅ Success: New pod api-gateway-def is Running
  
Executing action 3/4: RetryImagePull
  Pod: web-frontend-xxx
  ⚠️ Executed (needs config fix)
  
Executing action 4/4: RetryImagePull
  Pod: web-frontend-yyy
  ⚠️ Executed (needs config fix)
```

**Point Out:**
- Actions executed automatically
- Safety checks passed
- Verification confirmed success
- All recorded in audit trail

---

### Step 5: Apply Fixes (Turn Pods Green)
```powershell
kubectl apply -f 01-api-gateway-fixed.yaml --context aks-ai-agent-demo
kubectl apply -f 03-web-frontend-fixed.yaml --context aks-ai-agent-demo

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app=api-gateway --context aks-ai-agent-demo --timeout=120s
kubectl wait --for=condition=ready pod -l app=web-frontend --context aks-ai-agent-demo --timeout=120s
```

**Show in Dashboard:**
- All 4 pods now green ✅
- Low/zero restart counts
- Running status

---

## Adjusting the Delay

### For Shorter Demo (30 seconds)
```bash
# In .env file
SELF_HEALING_DELAY_SECONDS=30
```

### For Longer Presentation (2 minutes)
```bash
# In .env file
SELF_HEALING_DELAY_SECONDS=120
```

### For Production (No Delay)
```bash
# In .env file
SELF_HEALING_DELAY_SECONDS=0
```

---

## Presentation Script

### Minute 0:00 - Deploy Broken Pods
**Say:** "Let me show you what happens when pods fail in production..."
**Do:** Deploy crashloop and imagepull deployments
**Show:** Dashboard with 4 red pods

### Minute 0:30 - Run Monitoring
**Say:** "Our AI monitoring system runs every minute, scanning for failures..."
**Do:** Run `test_step1_monitoring.py`
**Show:** Console output showing detection

### Minute 1:00 - Notification Sent
**Say:** "The AI detected 4 failed pods and sent notifications to our team..."
**Show:** Slack/Teams notification
**Highlight:** Error details, pod names, reasons

### Minute 1:30 - Countdown Begins
**Say:** "Now the AI is analyzing whether it's safe to auto-heal these failures..."
**Show:** Console countdown: "Auto-healing starts in 60 seconds..."
**Explain:** Safety checks, rate limiting, validation

### Minute 2:00 - Dashboard Walkthrough
**Say:** "Let me show you what's happening in the cluster..."
**Do:** Click through failing pods in dashboard
**Show:** Logs, events, restart counts

### Minute 2:30 - Healing Executes
**Say:** "And... there it goes! The AI is now executing the healing actions!"
**Show:** Console output showing actions
**Highlight:** Restart pods, verify success

### Minute 3:00 - Apply Fixes
**Say:** "For persistent config issues, we need to fix the root cause..."
**Do:** Apply fixed manifests
**Show:** Pods turning green in dashboard

### Minute 3:30 - Success!
**Say:** "All pods are now healthy! The AI detected, notified, and helped resolve the issues."
**Show:** Green pods, low restart counts, healthy status

---

## Key Talking Points

### During the 1-Minute Wait:

1. **Safety First**
   - "Notice the AI is checking safety before acting"
   - "Rate limits prevent runaway automation"
   - "Cooldowns ensure we don't overwhelm the cluster"

2. **Intelligent Analysis**
   - "It's analyzing pod logs for root cause"
   - "Determining if this is a transient issue"
   - "Checking if the pod is too old (config problem)"

3. **Controlled Remediation**
   - "For CrashLoopBackOff: restart the pod"
   - "For ImagePullBackOff: retry if recently created"
   - "For OOMKilled: scale up deployment (not shown today)"

4. **Enterprise Features**
   - "All actions logged to audit trail"
   - "Can run in dry-run mode for testing"
   - "Verification confirms healing succeeded"
   - "Rollback available if healing fails"

---

## Troubleshooting

### Delay Not Working?
Check `.env` file:
```bash
# Make sure this line exists and is set to 60
SELF_HEALING_DELAY_SECONDS=60
```

### Want to Skip Delay During Testing?
```bash
# Set to 0 for immediate healing
SELF_HEALING_DELAY_SECONDS=0
```

### Countdown Not Showing?
Make sure you're running with Python's unbuffered output:
```powershell
C:\Python311\python.exe -u test_step1_monitoring.py
```

---

## Success Metrics

- ✅ Pods detected: 4 (2 CrashLoopBackOff, 2 ImagePullBackOff)
- ✅ Notifications sent: 1 (within 10 seconds)
- ✅ Delay period: 60 seconds (demo-friendly)
- ✅ Actions executed: 4 (2 restarts, 2 retries)
- ✅ Time to green: ~90 seconds after applying fixes
- ✅ Final state: All pods healthy ✅

---

## Production vs Demo Mode

| Feature | Demo Mode | Production Mode |
|---------|-----------|----------------|
| Delay | 60 seconds | 0 seconds |
| Purpose | Show notification first | Immediate healing |
| Countdown | Visible in console | No countdown |
| Best for | Presentations | 24/7 operations |

**To switch to production mode:**
```bash
# In .env
SELF_HEALING_DELAY_SECONDS=0
```

---

## Next Steps

Ready to present! The 1-minute delay gives you perfect timing to:
1. Show the failure detection
2. Explain what's happening
3. Build anticipation
4. Watch the auto-healing execute
5. Demonstrate successful recovery

**Dashboard:** http://127.0.0.1:63390

🎉 **Demo ready with perfect timing!**
