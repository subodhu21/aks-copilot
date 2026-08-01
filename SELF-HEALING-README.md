# Self-Healing Feature - Quick Start

## 🎯 Overview

The AKS AI Agent now includes **automated self-healing** that can detect and fix common Kubernetes pod failures without human intervention.

### What Gets Auto-Fixed?

1. **CrashLoopBackOff pods** → Automatically restarted
2. **OOMKilled pods** → Deployment scaled up for more resources
3. **ImagePullBackOff** → Pod deleted to retry (transient registry issues)

---

## ⚡ 5-Minute Setup

### 1. Run Setup Script

```powershell
cd C:\aks-ai-agent
.\setup-self-healing.ps1
```

This will:
- Install required dependencies
- Add self-healing config to `.env`
- Run a dry-run test (no actual changes)

### 2. Review Dry Run Output

You'll see what actions **would** be taken:

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
    Message: [DRY RUN] Would execute: Delete pod...
```

### 3. Enable Live Execution

If happy with the dry run, edit `.env`:

```ini
# Change this:
SELF_HEALING_DRY_RUN=yes

# To this:
SELF_HEALING_DRY_RUN=no
```

### 4. Run for Real

```powershell
C:\Python311\python.exe -u test_step1_monitoring.py
```

Now self-healing will execute automatically! 🎉

---

## 📋 Configuration

Key settings in `.env`:

```ini
# Enable/disable
SELF_HEALING_ENABLED=yes

# Mode: auto (immediate), ask (manual approval), disabled
SELF_HEALING_MODE=auto

# Test mode (no actual changes)
SELF_HEALING_DRY_RUN=no

# Safety: max actions per hour
SELF_HEALING_MAX_ACTIONS_PER_HOUR=10
```

### Action Thresholds

```ini
# CrashLoopBackOff: restart after N crashes
RESTART_MIN_CRASH_COUNT=5

# OOMKilled: scale up when N pods affected
SCALE_UP_MIN_OOM_COUNT=2

# ImagePullBackOff: only retry pods < 30 minutes old
IMAGEPULL_RETRY_MAX_AGE_SECONDS=1800
```

---

## 🛡️ Safety Features

### Built-in Protections

- ✅ **Rate Limiting** - Max 10 actions/hour (configurable)
- ✅ **Cooldowns** - 5 minute wait between actions on same resource
- ✅ **Validation** - Safety checks before every action
- ✅ **Verification** - Confirms action succeeded
- ✅ **Rollback** - Auto-reverts scale operations if they fail
- ✅ **Dry Run Mode** - Test without making changes

### What Won't Be Auto-Fixed

- ❌ StatefulSets (need manual intervention)
- ❌ Old ImagePullBackOff pods (likely config issues)
- ❌ Pods that were recently auto-fixed (cooldown active)
- ❌ When rate limit is reached

---

## 📊 Monitoring

### View Self-Healing History

```python
from self_healing import get_self_healing_history, get_self_healing_stats

# Last 50 actions
history = get_self_healing_history(limit=50)

# Statistics
stats = get_self_healing_stats()
print(f"Success rate: {stats['success_rate']}")
print(f"Rate limit: {stats['rate_limit']}")
```

### State File

Actions are tracked in: `self_healing_state.json`

Contains:
- Action history
- Rate limit tracking
- Cooldown timers

---

## 🔍 Troubleshooting

### Actions Not Running?

**Check 1:** Is it enabled?
```ini
SELF_HEALING_ENABLED=yes
SELF_HEALING_MODE=auto  # not disabled
SELF_HEALING_DRY_RUN=no  # not yes
```

**Check 2:** Rate limit reached?
```python
from self_healing import get_self_healing_stats
print(get_self_healing_stats()['rate_limit'])
# "10/10" means limit reached - wait 1 hour
```

**Check 3:** Review test output for rejection reasons
```
Actions Skipped: 1
  Reason: Restart count (3) below threshold (5)
```

### Action Failed?

Check logs in test output:
```
Status: failed
Message: Failed to delete pod
```

Common causes:
- RBAC permissions missing
- Network issues with K8s API
- Resource already modified

---

## 📚 Documentation

- **Full Guide**: `SELF-HEALING-GUIDE.md` - Complete documentation with examples
- **Setup**: `setup-self-healing.ps1` - Automated setup script
- **Code**: `self_healing.py` - Implementation details

---

## 🎓 Best Practices

### 1. Start with Dry Run
Always test with `SELF_HEALING_DRY_RUN=yes` first

### 2. Conservative Thresholds
Start high (e.g., `RESTART_MIN_CRASH_COUNT=10`) and lower gradually

### 3. Environment-Specific Rates
- **Dev**: 20 actions/hour
- **Staging**: 10 actions/hour
- **Production**: 5 actions/hour

### 4. Monitor History
Regularly review action history to catch patterns

### 5. Use with Alerts
Self-healing supplements monitoring, doesn't replace it

---

## ⚙️ How It Works

```
Pod Failure Detected
       ↓
Safety Validation
  (restart count, age, cooldown)
       ↓
Execute Action
  (delete pod, scale deployment)
       ↓
Verify Success
  (check new pod state)
       ↓
Rollback if Failed
  (scale operations only)
```

---

## 🚀 Example Scenarios

### Scenario 1: CrashLoopBackOff

**Before Self-Healing:**
- Pod crashes 8 times
- Stuck in exponential backoff
- **Manual action needed:** Delete pod

**With Self-Healing:**
- Detected: 8 restarts > threshold (5) ✓
- Action: Pod deleted automatically
- Result: New pod starts fresh and runs successfully

### Scenario 2: OOMKilled

**Before Self-Healing:**
- Traffic spike causes 3 pods OOMKilled
- Remaining pods overloaded
- **Manual action needed:** Scale up deployment

**With Self-Healing:**
- Detected: 3 OOMKilled pods > threshold (2) ✓
- Action: Scaled from 5 to 7 replicas
- Result: More capacity, load distributed

### Scenario 3: ImagePullBackOff

**Before Self-Healing:**
- Transient registry timeout
- Pod stuck, can't pull image
- **Manual action needed:** Delete pod to retry

**With Self-Healing:**
- Detected: ImagePullBackOff, pod age 5 minutes ✓
- Action: Pod deleted to retry pull
- Result: Image pulls successfully on retry

---

## 🔗 Integration

Works seamlessly with existing features:

- **Notifications**: Slack/Teams alerts still sent
- **AI Analysis**: Root cause analysis still provided
- **PR Generation**: Helm values fixes still created
- **Dashboard**: Shows all activity

Self-healing is a **safety net**, not a replacement for proper fixes.

---

## 📞 Support

Questions? Check:
1. This README for quick start
2. `SELF-HEALING-GUIDE.md` for full docs
3. Test output for detailed error messages
4. `self_healing_state.json` for action history

---

## ✅ Summary

Self-healing provides:
- ✅ Automated fixes for common pod failures
- ✅ Safety-first design with validation
- ✅ Rate limiting and cooldowns
- ✅ Dry run mode for testing
- ✅ Action history and statistics
- ✅ Rollback capabilities

**Get started in 5 minutes with `.\setup-self-healing.ps1`**
