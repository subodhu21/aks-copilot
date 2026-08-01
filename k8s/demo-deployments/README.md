# Self-Healing Demo Deployments - Simplified

Easy-to-demonstrate Kubernetes deployments for self-healing showcase.

---

## 📁 Files (Simplified Demo)

| File | Purpose |
|------|---------|
| `01-api-gateway-crashloop.yaml` | CrashLoopBackOff demo ⭐ |
| `03-web-frontend-imagepull.yaml` | ImagePullBackOff demo ⭐ |
| `simple-demo.yaml` | **Master file (2 scenarios)** ⭐ |
| `setup-demo.ps1` | Automated setup script |
| `cleanup-demo.ps1` | Cleanup script |
| `SIMPLE-DEMO-GUIDE.md` | **Quick demo guide (3 min)** ⭐ |
| `README.md` | This file |

---

## 🚀 Quick Start (3 Minutes)

### Option 1: Use Existing Deployments (Already Running!)

```powershell
# They're already deployed! Just run the test:
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

### Option 2: Fresh Deployment

```powershell
# Clean up
kubectl delete deployment api-gateway web-frontend -n default --context aks-ai-agent-demo

# Deploy fresh
kubectl apply -f simple-demo.yaml --context aks-ai-agent-demo

# Wait for failures to accumulate
Start-Sleep -Seconds 90

# Run self-healing
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

---

## 📊 Current Demo Status

### ✅ Currently Deployed (Ready!)

**api-gateway** (2 pods)
- Status: Error/CrashLoopBackOff
- Restarts: 6+ (threshold: 5) ✓
- Self-healing: Will delete and restart
- Demo time: Ready now!

**web-frontend** (2 pods)
- Status: ImagePullBackOff
- Age: 6+ minutes (threshold: 30 min) ✓
- Self-healing: Will delete and retry
- Demo time: Ready now!

---

## 🎬 What Self-Healing Will Do

### Scenario 1: api-gateway ⭐⭐⭐⭐⭐
- **Detects:** 6 restarts > threshold (5)
- **Action:** Delete both pods
- **Result:** Kubernetes creates fresh pods
- **Verification:** New pod names, reset restart counts
- **Demo Value:** Shows automatic restart with backoff reset

### Scenario 2: web-frontend ⭐⭐⭐⭐⭐
- **Detects:** Pod age 6 min < threshold (30 min)
- **Action:** Delete both pods (retry transient issue)
- **Result:** Kubernetes attempts fresh pull
- **Verification:** New pods created
- **Demo Value:** Shows age-based smart retry logic

---

## 🎯 Expected Self-Healing Output

```
SELF-HEALING ACTIONS
====================
Enabled: True
Mode: auto
Dry Run: False

Actions Executed: 4
  ✓ RestartCrashLoopPod (api-gateway-xxx)
    Status: success
    New pod: api-gateway-abc123 is Running
  
  ✓ RestartCrashLoopPod (api-gateway-yyy)
    Status: success
    New pod: api-gateway-def456 is Running
  
  ✓ RetryImagePull (web-frontend-xxx)
    Status: success
    Pod deleted to retry image pull
  
  ✓ RetryImagePull (web-frontend-yyy)
    Status: success
    Pod deleted to retry image pull
```

---

## 📈 Key Demo Points

### Technical Capabilities
✅ Automatic pod restart  
✅ Smart retry logic (age-based)  
✅ Restart threshold detection  
✅ Verification of actions  
✅ New pods created automatically  

### Safety Features
✅ Age validation (6 min < 30 min = retry)  
✅ Restart threshold (6 > 5 = act)  
✅ Rate limiting active  
✅ Cooldowns enforced  
✅ State tracking operational  

---

## 🔄 Reset Demo

```powershell
.\cleanup-demo.ps1
kubectl apply -f simple-demo.yaml --context aks-ai-agent-demo
Start-Sleep -Seconds 90
```

---

## 📝 Quick Commands

### Check Status
```powershell
kubectl get pods -n default --context aks-ai-agent-demo
```

### Watch Live
```powershell
kubectl get pods -n default --context aks-ai-agent-demo --watch
```

### Run Self-Healing
```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

### View Statistics
```powershell
C:\Python311\python.exe view_self_healing_stats.py
```

---

## 💡 Tips

- **Minikube Dashboard:** Already open, refresh to see changes
- **Wait for Restarts:** api-gateway needs 5+ restarts (usually 1-2 min)
- **Fresh = Retry:** web-frontend will retry because it's < 30 min old
- **Pod Names:** Look for different hashes after self-healing

---

**Demo is ready! Run the test to see self-healing in action!** 🎉

**Read:** `SIMPLE-DEMO-GUIDE.md` for complete walkthrough

