# Self-Healing Actions - User Guide

The AKS AI Agent now includes **automated self-healing capabilities** that can detect and remediate common Kubernetes pod failures without human intervention.

---

## 🎯 What is Self-Healing?

Self-healing automatically fixes common pod issues:

1. **Auto-Restart CrashLoopBackOff pods** - Deletes stuck pods to trigger fresh restart
2. **Auto-Scale on Resource Pressure** - Increases replicas when pods are OOMKilled
3. **Retry ImagePullBackOff** - Deletes pods to retry transient registry issues

Each action follows a **validate → execute → verify** pattern with safety checks and rollback capabilities.

---

## 🚀 Quick Start

### Step 1: Enable Self-Healing

Add to your `.env` file:

```ini
# Enable self-healing
SELF_HEALING_ENABLED=yes

# Mode: "auto" (execute immediately), "ask" (manual approval), "disabled"
SELF_HEALING_MODE=auto

# Dry run mode - test without executing (recommended for first test)
SELF_HEALING_DRY_RUN=yes
```

### Step 2: Test with Dry Run

Run the monitoring test to see what actions would be taken:

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

You'll see output like:

```
SELF-HEALING ACTIONS
==================================================
Enabled: True
Mode: auto
Dry Run: True
Summary: [DRY RUN] Would execute 3 actions, skip 0

Actions Executed: 3
  ✓ RestartCrashLoopPod
    Pod: demo-crashloop-abc123
    Status: dry_run
    Message: [DRY RUN] Would execute: Delete pod demo-crashloop-abc123...
```

### Step 3: Enable Live Execution

Once satisfied with dry run, disable dry run mode:

```ini
SELF_HEALING_DRY_RUN=no
```

Now actions will execute automatically!

---

## ⚙️ Configuration Options

### Core Settings

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `SELF_HEALING_ENABLED` | yes/no | no | Master enable/disable switch |
| `SELF_HEALING_MODE` | auto/ask/disabled | ask | Execution mode (see below) |
| `SELF_HEALING_DRY_RUN` | yes/no | no | Test mode - logs actions without executing |
| `SELF_HEALING_MAX_ACTIONS_PER_HOUR` | number | 10 | Rate limit to prevent runaway automation |

### Execution Modes

- **`auto`**: Actions execute immediately when conditions are met (fully automated)
- **`ask`**: Actions require manual approval via dashboard (coming soon)
- **`disabled`**: Self-healing is disabled (same as `SELF_HEALING_ENABLED=no`)

### Action-Specific Thresholds

#### Auto-Restart CrashLoopBackOff

| Variable | Default | Description |
|----------|---------|-------------|
| `RESTART_MIN_CRASH_COUNT` | 5 | Minimum restart count before auto-restarting |
| `RESTART_MIN_INTERVAL_SECONDS` | 300 | Cooldown between restart attempts (5 minutes) |

**Safety Checks:**
- ✓ Restart count exceeds threshold
- ✓ Last restart was more than interval ago
- ✓ Not a StatefulSet (requires manual handling)
- ✓ Not recently restarted by self-healing

#### Auto-Scale on OOMKilled

| Variable | Default | Description |
|----------|---------|-------------|
| `SCALE_UP_MIN_OOM_COUNT` | 2 | Minimum OOMKilled pods before scaling |
| `SCALE_UP_MAX_REPLICAS` | 10 | Maximum replicas (cost protection) |

**Safety Checks:**
- ✓ At least N pods are OOMKilled
- ✓ Current replicas below max threshold
- ✓ Scale target is valid (original + 2, capped at max)

**Rollback:** If verification fails, automatically scales back to original replica count.

#### Retry ImagePullBackOff

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGEPULL_RETRY_MAX_AGE_SECONDS` | 1800 | Max pod age for retry (30 minutes) |

**Safety Checks:**
- ✓ Pod is relatively new (not an old misconfiguration)
- ✓ Not recently retried by self-healing
- ✓ Cooldown period has passed

**Rationale:** Old pods in ImagePullBackOff likely have a real config issue (bad tag, missing auth), not a transient registry issue.

---

## 📊 Monitoring Self-Healing Activity

### View Action History

```python
from self_healing import get_self_healing_history, get_self_healing_stats

# Get last 50 actions
history = get_self_healing_history(limit=50)
for action in history:
    print(f"{action['timestamp']}: {action['action_type']} - {action['status']}")

# Get statistics
stats = get_self_healing_stats()
print(f"Total actions: {stats['total_actions']}")
print(f"Success rate: {stats['success_rate']}")
print(f"Rate limit: {stats['rate_limit']}")
```

### State Files

Self-healing tracks state in two files:

1. **`self_healing_state.json`** - Action history and rate limiting
2. **`notification_state.json`** - Notification deduplication (existing)

Override paths with:
```ini
SELF_HEALING_STATE_FILE=/var/data/aks_self_healing_state.json
```

---

## 🛡️ Safety Features

### 1. Rate Limiting
- Maximum actions per hour (default: 10)
- Prevents runaway automation if something goes wrong
- Tracked per-namespace

### 2. Cooldown Periods
- Each action has a cooldown (e.g., 5 minutes between restarts)
- Prevents repeated actions on same resource

### 3. Validation Checks
- Every action validates safety before execution
- Checks resource type, age, recent history
- Rejects unsafe actions (e.g., StatefulSets, old pods)

### 4. Verification
- After execution, verifies action succeeded
- Checks pod state, replica count, etc.
- Triggers rollback if verification fails

### 5. Rollback Capability
- Scale operations can auto-rollback
- Restores original state if verification fails

### 6. Dry Run Mode
- Test self-healing without executing
- See exactly what would happen
- Safe for production testing

---

## 🔍 Troubleshooting

### Actions Not Executing

**Check 1: Is self-healing enabled?**
```ini
SELF_HEALING_ENABLED=yes
SELF_HEALING_MODE=auto  # not "disabled"
SELF_HEALING_DRY_RUN=no  # not "yes"
```

**Check 2: Rate limit reached?**
```python
from self_healing import get_self_healing_stats
stats = get_self_healing_stats()
print(stats['rate_limit'])  # e.g., "10/10" means limit reached
```

Wait 1 hour or increase `SELF_HEALING_MAX_ACTIONS_PER_HOUR`.

**Check 3: Cooldown period active?**
Actions have cooldowns (default: 5 minutes). Check logs for "recently restarted" messages.

**Check 4: Safety checks failing?**
Review test output for rejection reasons:
```
Actions Skipped: 1
  - RestartCrashLoopPod
    Pod: demo-crashloop-abc123
    Reason: Safety check failed: Restart count (3) below threshold (5)
```

### Action Failed or Error

**Check execution logs:**
```
Actions Executed: 1
  ⚠ RestartCrashLoopPod
    Pod: demo-crashloop-abc123
    Status: failed
    Message: Execution failed: Failed to delete pod
```

**Common causes:**
1. **RBAC permissions** - Service account needs pod delete/scale permissions
2. **Network issues** - kubectl cannot reach K8s API
3. **Resource conflicts** - Another process modified the resource

**Check verification logs:**
```
Status: verification_failed
Message: Action executed but verification failed: New pod not in Running/Pending state
```

Verification failures trigger automatic rollback (for scale operations).

### Testing Self-Healing

**1. Dry Run Mode (Safest)**
```ini
SELF_HEALING_ENABLED=yes
SELF_HEALING_MODE=auto
SELF_HEALING_DRY_RUN=yes
```

Run test and review output. No actual changes.

**2. Dev Environment + Lower Thresholds**
```ini
# More aggressive for testing
RESTART_MIN_CRASH_COUNT=2
RESTART_MIN_INTERVAL_SECONDS=60
SCALE_UP_MIN_OOM_COUNT=1
```

**3. Manual Action Execution**
```python
from self_healing import RestartCrashLoopPod

action = RestartCrashLoopPod(
    pod_name="demo-crashloop-abc123",
    namespace="default",
    k8s_context="aks-ai-agent-demo",
    reason="CrashLoopBackOff",
    pod_info={"restart_count": 10}
)

result = action.run()
print(result)
```

---

## 📈 Dashboard Integration (Coming Soon)

The Streamlit dashboard will show:
- ✅ Self-healing actions in last 24 hours
- ✅ Success/failure rates by action type
- ✅ Manual approval UI for `mode=ask`
- ✅ Action history with timestamps
- ✅ Rate limit and cooldown status

---

## 🎓 Best Practices

### 1. Start with Dry Run
Always test new configurations with `SELF_HEALING_DRY_RUN=yes` first.

### 2. Use Conservative Thresholds
Start with high thresholds (e.g., `RESTART_MIN_CRASH_COUNT=10`) and lower gradually.

### 3. Monitor Action History
Regularly review `get_self_healing_history()` to catch unexpected patterns.

### 4. Set Appropriate Rate Limits
- **Dev/Test**: 20-30 actions/hour
- **Staging**: 10-15 actions/hour
- **Production**: 5-10 actions/hour (be conservative)

### 5. Use `mode=ask` for Production
Manual approval adds a safety layer for critical environments.

### 6. Combine with Alerts
Self-healing doesn't replace monitoring - you still get Slack/Teams notifications.

### 7. Review StatefulSet Failures Manually
Self-healing skips StatefulSets by design (they require careful handling).

---

## 🚨 When NOT to Use Self-Healing

1. **StatefulSets** - Require ordered, careful handling (auto-skipped)
2. **Database pods** - Manual intervention recommended
3. **Initial deployments** - Let pods stabilize first
4. **Major incidents** - Disable self-healing during active debugging
5. **Cost-sensitive workloads** - Auto-scaling can increase costs

To temporarily disable:
```ini
SELF_HEALING_ENABLED=no
```

Or just for specific namespaces, don't include them in the scan.

---

## 📝 Example Scenarios

### Scenario 1: Transient CrashLoopBackOff

**Situation:** Microservice pod crashes 8 times due to temporary DB connection issue. DB recovers but pod stuck in backoff.

**Self-Healing Response:**
1. Detects `demo-service-abc123` with 8 restarts
2. Validates: restart count (8) > threshold (5) ✓
3. Validates: no recent restart ✓
4. Executes: `kubectl delete pod demo-service-abc123`
5. Verifies: New pod `demo-service-xyz789` is Running ✓
6. Result: **Success** - Service recovers automatically

### Scenario 2: Memory Spike Causes OOMKilled

**Situation:** Traffic spike causes 3 pods to be OOMKilled in a deployment.

**Self-Healing Response:**
1. Detects 3 OOMKilled pods in `api-gateway` deployment
2. Validates: OOM count (3) > threshold (2) ✓
3. Validates: current replicas (5) < max (10) ✓
4. Executes: `kubectl scale deployment api-gateway --replicas=7`
5. Verifies: Deployment scaled to 7 replicas ✓
6. Result: **Success** - More capacity to handle load

### Scenario 3: ImagePullBackOff (Transient Registry Issue)

**Situation:** Pod fails to pull image due to temporary registry timeout.

**Self-Healing Response:**
1. Detects `worker-pod-def456` in ImagePullBackOff
2. Validates: pod age (5 minutes) < max age (30 minutes) ✓
3. Executes: `kubectl delete pod worker-pod-def456`
4. Verifies: New pod successfully pulls image ✓
5. Result: **Success** - Image pulled on retry

### Scenario 4: Old ImagePullBackOff (Config Issue)

**Situation:** Pod has been in ImagePullBackOff for 2 hours (bad tag).

**Self-Healing Response:**
1. Detects `legacy-app-ghi789` in ImagePullBackOff
2. Validates: pod age (2 hours) > max age (30 minutes) ✗
3. Result: **Skipped** - Likely a real config issue, needs manual fix

---

## 🔗 Integration with Existing Features

Self-healing works seamlessly with existing features:

- **Notifications**: Still sent to Slack/Teams before self-healing attempts
- **AI Analysis**: Still provides root cause analysis in notifications
- **PR Generation**: Still creates auto-fix PRs for Helm values issues
- **Dashboard**: Shows both notifications and self-healing actions

Self-healing is a **complementary safety net**, not a replacement for proper fixes.

---

## 📚 API Reference

### Main Functions

```python
from self_healing import (
    evaluate_and_heal,
    get_self_healing_history,
    get_self_healing_stats
)

# Evaluate and heal failing pods
result = evaluate_and_heal(
    failing_pods=[...],
    namespace="default",
    k8s_context="my-cluster"
)

# Get action history
history = get_self_healing_history(limit=50)

# Get statistics
stats = get_self_healing_stats()
```

### Action Classes

```python
from self_healing import (
    RestartCrashLoopPod,
    ScaleUpOnResourcePressure,
    RetryImagePull
)

# Create and execute individual action
action = RestartCrashLoopPod(
    pod_name="my-pod",
    namespace="default",
    k8s_context="my-cluster",
    reason="CrashLoopBackOff",
    pod_info={"restart_count": 10}
)

result = action.run()
```

Each action class provides:
- `validate_safety()` - Check if action is safe
- `execute()` - Perform the action
- `verify()` - Confirm success
- `rollback()` - Undo if verification fails

---

## 📞 Support

For issues or questions:
1. Check this guide's Troubleshooting section
2. Review `self_healing_state.json` for action history
3. Enable debug logging: `DEBUG=True` in `.env`
4. Examine test output for detailed error messages

---

## 🎉 Summary

Self-healing provides:
- ✅ **Automated remediation** for common pod failures
- ✅ **Safety-first design** with validation and rollback
- ✅ **Rate limiting** to prevent runaway automation
- ✅ **Dry run mode** for risk-free testing
- ✅ **Action history** for audit and debugging
- ✅ **Flexible configuration** for different environments

**Remember:** Self-healing is a safety net, not a substitute for proper troubleshooting and fixes. Always review why issues occurred and implement permanent solutions.
