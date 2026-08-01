# Simple Self-Healing Demo (2 Scenarios)

**Time:** 3 minutes  
**Services:** 2 (api-gateway, web-frontend)  
**Status:** ✅ Ready

---

## 🎯 What You Have Now

### 2 Demo Deployments (Easy to Show)

1. **api-gateway** (CrashLoopBackOff)
   - Crashes immediately (missing env var)
   - Restarts quickly (easy to see high restart count)
   - Self-healing: Deletes pod → Fresh restart
   - **Demo Time:** 30 seconds to accumulate restarts

2. **web-frontend** (ImagePullBackOff)
   - Can't pull non-existent image
   - Fresh deployment (< 30 min) → Will retry
   - Self-healing: Deletes pod → Retries pull
   - **Demo Time:** Immediate (fresh pod)

---

## 🚀 Quick Demo Script (3 Minutes)

### Step 1: Show Current State (30 seconds)

**In Minikube Dashboard:**
- Navigate to **Deployments**
- See 2 deployments: api-gateway, web-frontend
- Both showing red (failing)

**In PowerShell:**
```powershell
kubectl get pods -n default --context aks-ai-agent-demo
```

**Expected:**
```
NAME                            READY   STATUS              RESTARTS   AGE
api-gateway-xxx                 0/1     Error/CrashLoop     3-5        1m
web-frontend-xxx                0/1     ImagePullBackOff    0          1m
```

### Step 2: Wait for api-gateway to Accumulate Restarts (30 seconds)

```powershell
# Watch restart count increase
kubectl get pods -l app=api-gateway --context aks-ai-agent-demo --watch
```

Wait until RESTARTS shows 5+ (takes about 1-2 minutes with backoff)

Press **Ctrl+C** to stop watching.

### Step 3: Run Self-Healing (1 minute)

```powershell
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```

**Expected Output:**
```
SELF-HEALING ACTIONS
Enabled: True
Dry Run: False

Actions Executed: 2
  ✓ RestartCrashLoopPod (api-gateway)
    Status: success
    New pod created
  
  ✓ RetryImagePull (web-frontend)
    Status: success
    Retried image pull
```

### Step 4: Show Results (1 minute)

**In Dashboard:**
- api-gateway: New pod with fresh name
- web-frontend: New pod (still fails - demo image doesn't exist)

**In PowerShell:**
```powershell
kubectl get pods -n default --context aks-ai-agent-demo
```

**See:**
- api-gateway: NEW pod names (different hash)
- api-gateway: RESTARTS reset to 0-1 (fresh start)
- web-frontend: NEW pod names
- Recent AGE (just created)

---

## 📊 What This Demonstrates

### api-gateway (CrashLoopBackOff)
✅ **Automatic pod restart**  
✅ **Restart count reset** (backoff cleared)  
✅ **New pod created** by deployment  
✅ **Verification works** (new pod detected)

### web-frontend (ImagePullBackOff)  
✅ **Age-based validation** (fresh pod = retry)  
✅ **Smart retry logic**  
✅ **Action executed**  
✅ **New pod attempted** (still fails - expected for demo)

---

## 🎬 Talking Points

### api-gateway
> "This service is crashing because it's missing a required environment variable. 
> After 5 restarts, self-healing intervenes.
> It deletes the pod to reset the exponential backoff.
> Kubernetes creates a fresh pod automatically.
> New pod gets a clean start with no backoff delay."

### web-frontend
> "This service can't pull its Docker image.
> Self-healing checks the pod age - it's fresh (< 30 minutes).
> That suggests a transient registry issue, not a config problem.
> So it retries by deleting the pod.
> If it was 8 days old, it would skip it - that's a real config issue."

---

## ⚡ Super Quick Demo (1 Minute)

If you're short on time:

```powershell
# 1. Show failures (10 sec)
kubectl get pods --context aks-ai-agent-demo

# 2. Run self-healing (30 sec)
C:\Python311\python.exe -u test_step1_monitoring.py

# 3. Show new pods (10 sec)
kubectl get pods --context aks-ai-agent-demo
```

Point out: "New pod names, fresh restart counts, automatic remediation."

---

## 🔄 Reset Demo

```powershell
# Delete old deployments
kubectl delete deployment api-gateway web-frontend -n default --context aks-ai-agent-demo

# Recreate fresh
kubectl apply -f simple-demo.yaml --context aks-ai-agent-demo

# Wait 60 seconds for failures
Start-Sleep -Seconds 60
```

---

## 📈 Success Indicators

**In Dashboard:**
- ✅ Red indicators on failing pods
- ✅ After self-healing: New pod names visible
- ✅ Events showing "Deleted" and "Created"

**In Console:**
- ✅ "Actions Executed: 2"
- ✅ "Status: success"
- ✅ New pod names in kubectl output
- ✅ Low restart counts on new pods

**In Slack:**
- ✅ Notifications sent with AI analysis
- ✅ Root cause explanations

---

## 🎯 Key Messages

1. **Autonomous** - No human clicked anything
2. **Safe** - Safety checks prevented bad actions
3. **Smart** - Age-based validation (fresh = retry, old = skip)
4. **Verified** - Confirmed new pods were created
5. **Fast** - Seconds, not minutes

---

## 💡 If Things Don't Work

### api-gateway not accumulating restarts?
Wait longer (exponential backoff takes time) or check logs:
```powershell
kubectl logs -l app=api-gateway --context aks-ai-agent-demo --previous
```

### Self-healing not executing?
Check configuration:
```powershell
C:\Python311\python.exe check_dry_run.py
```
Should show: `SELF_HEALING_DRY_RUN in module: False`

### Rate limit hit?
```powershell
C:\Python311\python.exe view_self_healing_stats.py
```
Check rate limit status. Wait 1 hour if at limit.

---

## 📝 Current State

```
✅ Deployments: 2 (api-gateway, web-frontend)
✅ Old demo pods: DELETED (cleaned up)
✅ Other deployments: DELETED (simplified)
✅ Minikube dashboard: RUNNING
✅ Self-healing: ENABLED (live mode)
```

---

**You now have the simplest, fastest demo possible!** 🎉

**Next command:**
```powershell
# Wait for failures to develop
Start-Sleep -Seconds 90

# Run self-healing
cd C:\aks-ai-agent
C:\Python311\python.exe -u test_step1_monitoring.py
```
