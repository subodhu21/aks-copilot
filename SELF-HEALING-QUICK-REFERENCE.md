# Self-Healing Quick Reference Card

## 🚀 Quick Commands

### Run Full Test (Live Mode - ENABLED)
```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

### View Statistics & History
```powershell
C:\Python311\python.exe view_self_healing_stats.py
```

### Verify Setup
```powershell
C:\Python311\python.exe test_self_healing_setup.py
```

---

## ⚙️ Current Configuration

| Setting | Value | Status |
|---------|-------|--------|
| **Enabled** | ✅ YES | Active |
| **Mode** | Auto | Immediate execution |
| **Dry Run** | ❌ NO | **LIVE EXECUTION** |
| **Rate Limit** | 10/hour | 5 used, 5 remaining |

**⚠️ WARNING: Live execution is ENABLED. Actions will be executed for real!**

---

## 📊 Current Statistics

- **Total Actions:** 5
- **Executed:** 2 (in dry run)
- **Rejected:** 3 (safety)
- **Success Rate:** 100%
- **Rate Limit:** 5/10 (50%)

---

## 🔧 What Will Happen Next?

When you run the test:

### ✅ demo-crashloop (CrashLoopBackOff)
- **Action:** DELETE POD
- **Reason:** 272 restarts > threshold (5)
- **Result:** New pod will be created automatically
- **Status:** WILL EXECUTE

### ❌ demo-imagepull (ImagePullBackOff)
- **Action:** SKIPPED
- **Reason:** Pod too old (8 days > 30 min threshold)
- **Result:** No action taken
- **Status:** WILL SKIP (correctly)

---

## 🛡️ Safety Features Active

- ✅ Rate Limiting (10/hour)
- ✅ Cooldown (5 min between actions)
- ✅ Age Validation (reject old pods)
- ✅ Restart Threshold (min 5 restarts)
- ✅ StatefulSet Protection
- ✅ Action History Tracking

---

## 🎯 To Test ImagePull Retry

Create fresh pods (< 30 min old):

```powershell
# Delete old pods
kubectl delete -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo

# Create new ones
kubectl apply -f k8s/local/demo-broken-pods.yaml --context aks-ai-agent-demo

# Wait 1 minute
Start-Sleep -Seconds 60

# Test - ImagePull will now be approved!
C:\Python311\python.exe -u test_step1_monitoring.py
```

---

## 🔄 Switch Back to Dry Run

If you want to test without executing:

**Edit `.env` and change:**
```ini
SELF_HEALING_DRY_RUN=yes
```

---

## 📈 Configuration Tuning

### Production (Conservative)
```ini
SELF_HEALING_MODE=ask           # Manual approval
RESTART_MIN_CRASH_COUNT=10      # Higher threshold
SELF_HEALING_MAX_ACTIONS_PER_HOUR=5
RESTART_MIN_INTERVAL_SECONDS=600  # 10 min cooldown
```

### Dev/Staging (Aggressive)
```ini
SELF_HEALING_MODE=auto          # Automatic
RESTART_MIN_CRASH_COUNT=3       # Lower threshold
SELF_HEALING_MAX_ACTIONS_PER_HOUR=20
RESTART_MIN_INTERVAL_SECONDS=180  # 3 min cooldown
```

### Current (Balanced)
```ini
SELF_HEALING_MODE=auto
RESTART_MIN_CRASH_COUNT=5
SELF_HEALING_MAX_ACTIONS_PER_HOUR=10
RESTART_MIN_INTERVAL_SECONDS=300  # 5 min
```

---

## 📝 Files & Locations

| File | Purpose |
|------|---------|
| `self_healing.py` | Core module |
| `.env` | Configuration |
| `self_healing_state.json` | Action history & state |
| `test_step1_monitoring.py` | Main test |
| `view_self_healing_stats.py` | Statistics viewer |
| `SELF-HEALING-TEST-REPORT.md` | Detailed test report |

---

## 🆘 Troubleshooting

### Actions Not Running?
```powershell
# Check config
C:\Python311\python.exe test_self_healing_setup.py
```

### Rate Limit Hit?
Check: `self_healing_state.json` → `recent_hour_count`  
Wait 1 hour or increase limit in `.env`

### Action Failed?
Review: `self_healing_state.json` → `history` → look for `status: "failed"`

---

## 📚 Documentation

- **This Card:** `SELF-HEALING-QUICK-REFERENCE.md`
- **Full Report:** `SELF-HEALING-TEST-REPORT.md`
- **Complete Guide:** `SELF-HEALING-GUIDE.md`
- **Quick Start:** `SELF-HEALING-README.md`

---

**Status:** ✅ Ready to Use | **Mode:** 🔴 LIVE EXECUTION
