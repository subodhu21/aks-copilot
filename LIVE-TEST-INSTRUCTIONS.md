# Live Self-Healing Test - Final Instructions

## 📋 Current Status

### ✅ Configuration Verified
The `.env` file is correctly set:
```ini
SELF_HEALING_DRY_RUN=no  # LIVE MODE
```

### ⚠️ Last Test Results
The previous test ran with the OLD configuration (dry run still enabled).

**Results from last run:**
- 3 failing pods detected
- 3 Slack notifications sent ✓
- 1 action skipped (ImagePull - pod too old) ✓
- 0 actions executed (was still in dry run)

---

## 🚀 Run LIVE Test Now

**Open a FRESH PowerShell window** (this ensures Python loads the new .env):

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

### What Will Happen (LIVE MODE):

#### 1. demo-crashloop (Error/CrashLoopBackOff)
**Status:** Will check restart count
- If restart count > 5: ✅ **POD WILL BE DELETED**
- New pod will be created automatically
- Expected: `Action succeeded: New pod created`

#### 2. demo-imagepull (ImagePullBackOff)
**Status:** ❌ **WILL BE SKIPPED**
- Reason: Pod is ~8 days old
- Safety check: Correctly rejects old pods
- Expected: `Safety check failed: Pod is too old`

#### 3. demo-healthy (HighRestartCount: 3)
**Status:** ❌ **WILL BE SKIPPED**
- Reason: Restart count (3) < threshold (5)
- Safety check: Below minimum threshold
- Expected: No action taken

---

## 🔍 How to Verify It's Running in LIVE Mode

Look for this in the output:

### Dry Run Mode (OLD):
```
Dry Run: True
Summary: [DRY RUN] Would execute 0 actions
Message: [DRY RUN] Would execute: Delete pod...
```

### Live Mode (NEW):
```
Dry Run: False
Summary: Executed 1 self-healing action
Status: success
Message: Action succeeded: New pod demo-crashloop-xyz789 is Running
```

---

## 🎯 Alternative: Force Verification

Run this to check the current setting:

```powershell
C:\Python311\python.exe check_dry_run.py
```

Expected output:
```
SELF_HEALING_DRY_RUN from .env: no
Evaluated as boolean: False
SELF_HEALING_DRY_RUN in module: False
```

If it shows `True`, there's a caching issue - restart PowerShell.

---

## 📊 After Running: Check Results

### 1. View Kubernetes Pods
```powershell
kubectl get pods -n default --context aks-ai-agent-demo
```

If self-healing executed, you'll see:
- **NEW** pod name for demo-crashloop (different hash suffix)
- Recent creation time (Age column)

Example:
```
NAME                    READY   STATUS             RESTARTS   AGE
demo-crashloop-abc123   0/1     CrashLoopBackOff   2          30s   ← NEW!
demo-imagepull          0/1     ImagePullBackOff   0          8d    ← OLD (unchanged)
demo-healthy            1/1     Running            3          8d
```

### 2. Check Self-Healing History
```powershell
C:\Python311\python.exe view_self_healing_stats.py
```

Look for:
- New action with `dry_run: False`
- Status: `success` or `verification_failed`
- Execution and verification details

### 3. Read State File
```powershell
Get-Content self_healing_state.json
```

Latest action should show:
```json
{
  "dry_run": false,
  "status": "success",
  "execution": {
    "success": true,
    "message": "Pod deleted successfully"
  },
  "verification": {
    "verified": true,
    "message": "New pod demo-crashloop-xyz789 is Running"
  }
}
```

---

## 🧪 Alternative Test: Create Fresh Pods

To test ImagePull retry in LIVE mode, create fresh pods:

```powershell
# Delete old pods (8 days old)
kubectl delete -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo

# Create new ones (will be < 5 minutes old)
kubectl apply -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo

# Wait for them to fail
Start-Sleep -Seconds 60

# Check status
kubectl get pods -n default --context aks-ai-agent-demo

# Run test - ImagePull retry will now be APPROVED!
C:\Python311\python.exe -u test_step1_monitoring.py
```

**Expected with fresh pods:**
- ✅ demo-crashloop: WILL BE DELETED
- ✅ demo-imagepull: WILL BE DELETED (now < 30 min old!)
- ❌ demo-healthy: SKIPPED (restart count too low)

---

## ⚠️ Safety Reminder

### What Can Go Wrong?
- If CrashLoopBackOff pod is critical, it will be restarted
- If there's a deployment issue, the new pod will also crash
- Rate limit (10/hour) will prevent runaway actions

### What CANNOT Go Wrong?
- ✅ Old pods won't be retried (age check)
- ✅ Low restart counts won't trigger action
- ✅ Rate limit prevents too many actions
- ✅ Cooldown prevents rapid retries
- ✅ StatefulSets are skipped

---

## 🔙 Revert to Dry Run

If you want to switch back to dry run mode:

**Edit `.env`:**
```ini
SELF_HEALING_DRY_RUN=yes
```

Then run the test again.

---

## 📝 Expected Output Format

```
Testing Step 1: Monitor and Notify Failures
==================================================

==================================================
Namespace: DEFAULT
==================================================

[Self-Healing] Evaluating 3 failing pods...
[Self-Healing] Executed 1 self-healing action, skipped 2

Status: success
Summary: Detected 3 failing pod(s), sent 3 notification(s)

Failing pods detected: 3
  - demo-crashloop: CrashLoopBackOff
  - demo-healthy: HighRestartCount (3)
  - demo-imagepull: ImagePullBackOff

Notifications sent/attempted: 3
  - Status: sent
    Message: Notification sent successfully to Slack

==================================================
SELF-HEALING ACTIONS
==================================================
Enabled: True
Mode: auto
Dry Run: False                    ← LOOK FOR THIS!
Summary: Executed 1 self-healing action, skipped 2

Actions Executed: 1
  ✓ RestartCrashLoopPod
    Pod: demo-crashloop
    Status: success                ← LOOK FOR THIS!
    Message: Action succeeded: New pod demo-crashloop-xyz789 is Running

    Safety Check Details:
      Safe: True
      Reason: All safety checks passed
    
    Execution Details:
      Success: True
      Message: Pod deleted successfully
    
    Verification Details:
      Verified: True
      Message: New pod demo-crashloop-xyz789 is Running

Actions Skipped: 2
  - RetryImagePull
    Pod: demo-imagepull
    Reason: Safety check failed: Pod is too old (11478 minutes)
  
  - RestartCrashLoopPod
    Pod: demo-healthy
    Reason: Restart count (3) below threshold (5)

==================================================
All namespaces scanned.
```

---

## ✅ Success Criteria

After running in a fresh PowerShell window, you should see:

1. ✅ `Dry Run: False` in output
2. ✅ At least 1 action with `Status: success`
3. ✅ New pod name in Kubernetes (different hash)
4. ✅ Action recorded in `self_healing_state.json` with `dry_run: false`

---

## 🎉 You're Ready!

**Open a NEW PowerShell window and run:**

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

**Watch self-healing execute for real!** 🚀

---

**Note:** If the PowerShell output is truncated/garbled, check these files:
- `self_healing_state.json` (action history)
- `kubectl get pods` (pod changes)
- `view_self_healing_stats.py` (statistics)
