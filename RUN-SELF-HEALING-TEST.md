# Running Self-Healing Test - Manual Instructions

Since the PowerShell terminal has communication issues, here are the manual steps to test self-healing.

---

## ✅ Step 1: Verify Configuration

The self-healing configuration has been added to your `.env` file. Verify it's there:

Open `.env` and check for this section at the bottom:

```ini
# ========== Self-Healing Actions ==========
SELF_HEALING_ENABLED=yes
SELF_HEALING_MODE=auto
SELF_HEALING_DRY_RUN=yes
SELF_HEALING_MAX_ACTIONS_PER_HOUR=10
RESTART_MIN_CRASH_COUNT=5
RESTART_MIN_INTERVAL_SECONDS=300
SCALE_UP_MIN_OOM_COUNT=2
SCALE_UP_MAX_REPLICAS=10
IMAGEPULL_RETRY_MAX_AGE_SECONDS=1800
```

**✓ Configuration is already added!**

---

## ✅ Step 2: Install Dependencies

Open a **new PowerShell window** and run:

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -m pip install python-dateutil>=2.8.0 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

This installs the required `python-dateutil` package.

---

## ✅ Step 3: Verify Setup

Run the setup verification test:

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe test_self_healing_setup.py
```

**Expected Output:**
```
============================================================
Self-Healing Setup Verification
============================================================

✓ .env file found
✓ Self-healing configuration found in .env

Configuration:
  SELF_HEALING_ENABLED: yes
  SELF_HEALING_MODE: auto
  SELF_HEALING_DRY_RUN: yes

✓ self_healing module imported successfully
✓ python-dateutil module found
✓ All self-healing functions available
✓ Self-healing state system working

============================================================
✓ All checks passed! Self-healing is ready to use.
============================================================

⚠️  DRY RUN MODE is enabled (safe for testing)
   Actions will be logged but not executed.
```

---

## ✅ Step 4: Make Sure Post-Restart Setup is Complete

Before testing self-healing, ensure your environment is ready:

### 4a. Docker Desktop Running
- Check the system tray for the Docker whale icon
- Status should be "Running"

### 4b. Minikube Running
```powershell
minikube start -p aks-ai-agent-demo
minikube status -p aks-ai-agent-demo
```

Expected output:
```
host: Running
kubelet: Running
apiserver: Running
```

### 4c. Demo Pods Deployed
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

If pods are missing, create them:
```powershell
kubectl apply -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo
```

### 4d. AWS SSO Login
```powershell
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" sso login --profile my-sso
```

This opens a browser - click **Allow**.

Verify:
```powershell
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" sts get-caller-identity --profile my-sso
```

---

## ✅ Step 5: Run Self-Healing Test (Dry Run)

Now run the full monitoring test with self-healing:

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

### What to Look For

You should see output like:

```
Testing Step 1: Monitor and Notify Failures
==================================================

==================================================
Namespace: DEFAULT
==================================================

[Self-Healing] Evaluating 2 failing pods...
[Self-Healing] [DRY RUN] Would execute 2 actions, skip 0

Status: success
Summary: Detected 2 failing pod(s), sent 2 notification(s)

Failing pods detected: 2
  - demo-crashloop: CrashLoopBackOff
  - demo-imagepull: ImagePullBackOff

Notifications sent/attempted: 2
  - Status: success
    Message: Slack notification sent

==================================================
SELF-HEALING ACTIONS
==================================================
Enabled: True
Mode: auto
Dry Run: True
Summary: [DRY RUN] Would execute 2 actions, skip 0

Actions Executed: 2
  ✓ RestartCrashLoopPod
    Pod: demo-crashloop
    Status: dry_run
    Message: [DRY RUN] Would execute: Delete pod demo-crashloop to trigger fresh restart (restart count: 10)
  
  ✓ RetryImagePull
    Pod: demo-imagepull
    Status: dry_run
    Message: [DRY RUN] Would execute: Delete pod demo-imagepull to retry image pull (ImagePullBackOff)

==================================================
All namespaces scanned.
```

**Key Points:**
- ✓ Failing pods detected
- ✓ Notifications sent to Slack
- ✓ Self-healing evaluated the pods
- ✓ Actions logged but NOT executed (dry run mode)

---

## ✅ Step 6: Enable Live Execution (Optional)

If you're satisfied with the dry run, you can enable live execution.

### Edit `.env`

Change:
```ini
SELF_HEALING_DRY_RUN=yes
```

To:
```ini
SELF_HEALING_DRY_RUN=no
```

### Run Again

```powershell
C:\Python311\python.exe -u test_step1_monitoring.py
```

Now you'll see:

```
Actions Executed: 2
  ✓ RestartCrashLoopPod
    Pod: demo-crashloop-abc123
    Status: success
    Message: Action succeeded: New pod demo-crashloop-xyz789 is Running
```

The pods will actually be deleted and recreated!

### Verify the Changes

```powershell
kubectl get pods -n default --context aks-ai-agent-demo
```

You should see new pod names with recent creation times.

---

## 🔍 Troubleshooting

### If you see "ModuleNotFoundError: No module named 'dateutil'"

Install the dependency:
```powershell
C:\Python311\python.exe -m pip install python-dateutil>=2.8.0 --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
```

### If you see "Actions Skipped" instead of "Actions Executed"

Check the reason in the output:
```
Actions Skipped: 1
  - RestartCrashLoopPod
    Reason: Restart count (3) below threshold (5)
```

**Solution:** Lower the threshold in `.env`:
```ini
RESTART_MIN_CRASH_COUNT=2
```

Or wait for more restarts to accumulate.

### If pods aren't failing

The demo pods should be in CrashLoopBackOff and ImagePullBackOff states. If they're not:

```powershell
# Delete and recreate them
kubectl delete -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo
kubectl apply -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo

# Wait a minute for them to fail
Start-Sleep -Seconds 60

# Check status
kubectl get pods -n default --context aks-ai-agent-demo
```

### If AWS SSO expired

You'll see: `ExpiredTokenException`

**Solution:**
```powershell
& "C:\Program Files\Amazon\AWSCLIV2\aws.exe" sso login --profile my-sso
```

---

## 📊 View Self-Healing History

After running tests, you can view the action history:

```powershell
C:\Python311\python.exe -c "from self_healing import get_self_healing_history, get_self_healing_stats; import json; print(json.dumps(get_self_healing_stats(), indent=2))"
```

This shows:
- Total actions taken
- Success rate
- Actions by type
- Rate limit status

---

## 📝 Summary

**What We Built:**
- ✅ `self_healing.py` - Core module with 3 automated actions
- ✅ Configuration in `.env` (already added!)
- ✅ Integration with `agent.py` and `test_step1_monitoring.py`
- ✅ Safety features: rate limiting, cooldowns, validation, verification, rollback
- ✅ Dry run mode for safe testing

**Self-Healing Actions:**
1. **RestartCrashLoopPod** - Deletes stuck CrashLoopBackOff pods
2. **ScaleUpOnResourcePressure** - Scales deployments when OOMKilled
3. **RetryImagePull** - Retries transient ImagePullBackOff issues

**Current State:**
- Configuration: ✅ Added to `.env`
- Mode: Dry Run (safe for testing)
- Ready to test!

---

## 🚀 Next Steps

1. ✅ Run `test_self_healing_setup.py` to verify setup
2. ✅ Run `test_step1_monitoring.py` to see dry-run output
3. ✅ Review what actions would be taken
4. ✅ Enable live execution by setting `SELF_HEALING_DRY_RUN=no`
5. ✅ Run again to see actual self-healing in action
6. ✅ Read `SELF-HEALING-GUIDE.md` for full documentation

---

## 📚 Documentation

- **This Guide**: `RUN-SELF-HEALING-TEST.md`
- **Quick Start**: `SELF-HEALING-README.md`
- **Full Guide**: `SELF-HEALING-GUIDE.md`
- **Implementation**: `SELF-HEALING-SUMMARY.md`

**Enjoy your new self-healing capabilities!** 🎉
