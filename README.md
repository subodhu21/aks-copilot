# AKS Operations Copilot - 4-Step Platform Journey

Local AI-powered AKS assistant that evolves across four maturity levels:

1. Local AI Kubernetes troubleshooter
2. AKS operational assistant
3. Autonomous remediation engine
4. Platform engineering AI assistant

# AKS Operations Copilot - 4-Step Platform Journey

Local AI-powered AKS assistant that evolves across four maturity levels:

1. **Local AI Kubernetes troubleshooter** — Analyze pod logs & issues
2. **AKS operational assistant** — Namespace-level health & priorities
3. **Autonomous remediation engine** — Safe remediation plans & execution
4. **Platform engineering AI assistant** — Strategic guidance & KPIs

## ✨ New: Self-Healing Actions

**Automated pod failure remediation is now available!**

The agent can now automatically detect and fix common Kubernetes pod failures:
- 🔄 **Auto-restart CrashLoopBackOff pods**
- 📈 **Auto-scale on OOMKilled**
- 🔁 **Retry ImagePullBackOff** (transient registry issues)

**Quick Start:**
```powershell
.\setup-self-healing.ps1
```

**Documentation:**
- Quick Start: [SELF-HEALING-README.md](SELF-HEALING-README.md)
- Full Guide: [SELF-HEALING-GUIDE.md](SELF-HEALING-GUIDE.md)

Self-healing includes safety features: rate limiting, cooldowns, validation checks, verification, rollback, and dry-run mode for testing.

---

## 🚀 Quick Start

### Prerequisites
- `kubectl` configured to access your AKS cluster
- Python 3.8+
- **AI Provider (choose one):**
  - **Azure AI (Recommended)**: Access to [Azure Foundry](https://ai.azure.com) with a project and model deployment
  - **Ollama (Local)**: [Ollama](https://ollama.ai) installed and running locally

### Installation

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Set up your AI provider

# Option A: Use Azure Foundry models (RECOMMENDED)
# Copy .env.example to .env and configure Azure credentials:
cp .env.example .env
# Then edit .env with:
# - AI_PROVIDER=azure
# - AZURE_INFERENCE_ENDPOINT=https://<your-project>.models.ai.azure.com
# - AZURE_MODEL_DEPLOYMENT=gpt-4  (or claude-opus-4, etc.)
# - AZURE_API_KEY=<your-api-key>
# See .env.example for more details

# Option B: Use Ollama for local inference
# 1. Start Ollama: ollama run qwen2.5:3b
# 2. Create .env with: AI_PROVIDER=ollama
```

### Configuring Azure Foundry

If using Azure AI models:

1. **Get Azure Foundry Endpoint & Key:**
   - Navigate to https://ai.azure.com (Microsoft Foundry console)
   - Create or select your project
   - Find your model deployments (e.g., gpt-4, claude-opus-4)
   - Copy the **Endpoint URL** and **API Key**

2. **Create `.env` file:**
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` with your Azure credentials:**
   ```env
   AI_PROVIDER=azure
   AZURE_INFERENCE_ENDPOINT=https://<your-project>.models.ai.azure.com
   AZURE_MODEL_DEPLOYMENT=gpt-4
   AZURE_API_KEY=<your-api-key>
   ```

   Or use Azure Identity (DefaultAzureCredential):
   ```env
   AI_PROVIDER=azure
   AZURE_INFERENCE_ENDPOINT=https://<your-project>.models.ai.azure.com
   AZURE_MODEL_DEPLOYMENT=gpt-4
   AZURE_INFERENCE_CREDENTIAL=environment
   # Uses Azure CLI/SDK auth (no API key needed)
   ```

### Running the MCP Server (Recommended for AI Assistants)

The **MCP server is the primary interface** for Continue, Claude, and other AI clients.

```powershell
# Windows PowerShell
./start-mcp.ps1

# Or direct Python
python mcp_server.py
```

**Integration with Continue** (VS Code):
- The server is pre-configured in `.continue/mcpServers/new-mcp-server.yaml`
- Continue will auto-discover the `aks-operations-copilot` MCP server
- Use tools like `troubleshoot_pod`, `remediation_plan`, etc. in your chat

📖 **See [MCP-USAGE.md](MCP-USAGE.md)** for full MCP tool documentation.

### Alternative: Running as REST API (Legacy)

If you prefer a web interface or REST API:

```bash
python main.py
# API available at http://localhost:8001
# Web UI at http://localhost:8001/ui
```

⚠️ Note: The REST API is secondary—MCP is recommended for AI integrations.

### Testing

Verify the server is working:

```powershell
python test-mcp.py
```

## 📡 API Endpoints

### Step 1: Local AI Kubernetes troubleshooter
```
GET /step1/troubleshoot?pod=<pod-name>&namespace=<namespace>
```

**Example:**
```bash
curl "http://localhost:8000/step1/troubleshoot?pod=my-app&namespace=default"
```

**Response:**
```json
{
  "pod": "my-app",
  "namespace": "default",
  "issue_detected": "CrashLoopBackOff",
  "analysis": "Root cause: The application is exiting due to missing environment variable...",
  "logs_tail": "Error: REDIS_HOST not set...",
  "description_snippet": "State: Waiting Reason: CrashLoopBackOff..."
}
```

Backward-compatible alias:
```
GET /analyze?pod=<pod-name>&namespace=<namespace>
```

### Step 2: AKS operational assistant
```
GET /step2/operations?namespace=<namespace>
```

**Example:**
```bash
curl "http://localhost:8000/step2/operations?namespace=default"
```

Returns namespace health snapshot, problematic pods, warning events, and AI-generated operational priorities.

### Step 3: Autonomous remediation engine
```
POST /step3/remediate
```

**Example (dry run):**
```bash
curl -X POST "http://localhost:8000/step3/remediate" \
    -H "Content-Type: application/json" \
    -d '{"pod":"my-app","namespace":"default","auto_apply":false}'
```

**Example (auto-apply safe commands):**
```bash
curl -X POST "http://localhost:8000/step3/remediate" \
    -H "Content-Type: application/json" \
    -d '{"pod":"my-app","namespace":"default","auto_apply":true}'
```

This endpoint produces a safe remediation plan and can execute allowlisted commands only.

### Step 4: Platform engineering AI assistant
```
POST /step4/platform-assistant
```

**Example:**
```bash
curl -X POST "http://localhost:8000/step4/platform-assistant" \
    -H "Content-Type: application/json" \
    -d '{"goal":"Standardize AKS onboarding and reduce MTTR","namespace":"default","constraints":"Small team, no paid APM"}'
```

Returns a platform pattern recommendation, capability model, roadmap, and KPI/SLO suggestions.

### Health Check
```
GET /health
```

### List Pods
```
GET /list-pods?namespace=default
```

## 🏗️ Architecture

```
Step 1: Pod Troubleshooter
    ↓
Step 2: Namespace Operations Assistant
    ↓
Step 3: Safe Remediation Planner/Executor
    ↓
Step 4: Platform Engineering Advisor
```

## 🧠 How It Works

1. **Step 1 - Pod Monitoring**: Fetches pod logs and description from AKS
2. **Issue Detection**: Detects common Kubernetes issues:
   - `CrashLoopBackOff` → App crashing, check logs & env vars
   - `OOMKilled` → Out of memory, increase resource limits
   - `ImagePullBackOff` → Image not found, check ACR/registry
   - `Pending` → Insufficient resources or node issues
   - `Liveness Probe Failure` → Health check failing
3. **Step 2 - Operations View**: Builds namespace health snapshot + warning-event summary
4. **Step 3 - Remediation Engine**: Produces safe command plans and optional allowlisted execution
5. **Step 4 - Platform Assistant**: Produces platform roadmap, SLOs, and golden-path recommendations

## 🎯 Confidence Scoring

Every pod-failure notification (Teams/Slack) includes a **diagnosis confidence
score (0-100, High/Medium/Low)** alongside the root cause and fix. This is a
deterministic, rule-based score — not a number the AI model self-reports (LLMs
are unreliable at that). It measures how much corroborating evidence backs the
classification, computed in `calculate_diagnosis_confidence()` (`src/tools.py`)
from four weighted factors:

| Factor | Points | What it measures |
|---|---|---|
| Reason specificity | 0-30 | Exact K8s reason (`CrashLoopBackOff`, `OOMKilled`) vs. a derived heuristic (`HighRestartCount`, `Pending`) |
| Log evidence strength | 0-25 | Logs matched a specific root-cause keyword vs. only a generic error/exception vs. no logs at all |
| Context grounding | 0-20 | Deployment is repo-managed (Helm values + peer-env comparison available) vs. a system pod with no repo context |
| Classification certainty | 0-25 | `_classify_issue()` landed on a specific category vs. an ambiguous/unknown bucket |

Each notification shows the full factor breakdown so you (or a demo audience)
can see exactly why a score landed where it did.

The same idea extends to **self-healing actions** (`src/self_healing.py`).
Every action's `run()` lifecycle now does: `validate_safety()` (binary — is
this allowed at all: StatefulSet check, rate limit, cooldown) → **`calculate_confidence()`**
(graduated — how strong is the evidence THIS action will actually help, e.g.
restart count margin above threshold, pod age relative to the transient-issue
window, whether we already tried this recently) → execute → verify → rollback.
Actions that pass safety but score below `SELF_HEALING_MIN_CONFIDENCE`
(default 40) are rejected before execution, with the factor breakdown recorded
in the action result.

## 📝 Example Use Cases

### Pod keeps crashing
```bash
curl "http://localhost:8000/analyze?pod=backend&namespace=production"
```

Returns:
```
Root cause: Application missing config file
Fix: kubectl set env deployment/backend CONFIG_FILE=/etc/config.yaml
```

### Pod stuck in pending
```bash
curl "http://localhost:8000/analyze?pod=gpu-worker&namespace=ml"
```

Returns:
```
Root cause: No GPU nodes available
Fix: Scale node pool or change nodeSelector
```

## ⚙️ Project Structure

```
aks-ai-agent/
├── src/                      # All application logic
│   ├── agent.py              # AI agent (Azure/Bedrock/Ollama) for troubleshooting, ops, remediation, platform strategy
│   ├── tools.py               # kubectl helpers, issue detection, namespace snapshot, safe command execution
│   ├── self_healing.py       # Validate -> execute -> verify -> rollback remediation actions
│   ├── prompt_loader.py      # Loads prompt templates from prompts/prompts.md
│   ├── repo_context.py       # Azure DevOps repo context for Helm-specific remediation
│   ├── helm_config.py        # Helm chart metadata for deployment-specific fixes
│   ├── keyvault_loader.py    # Resolves @keyvault: secret references
│   ├── aws_secrets_loader.py # Resolves @awssecret: secret references
│   ├── test_step1_monitoring.py   # Primary end-to-end test/entrypoint
│   ├── run-complete-demo.py       # Scripted demo: deploy broken pods -> notify -> heal
│   └── view_self_healing_stats.py # Self-healing history/stats viewer
├── prompts/
│   └── prompts.md            # AI prompt templates (edit wording here, no code changes needed)
├── manifests/                # All Kubernetes YAML manifests
│   ├── namespace.yaml, rbac.yaml, pvc.yaml, secret.yaml, cronjob.yaml
│   ├── local/                # Local minikube demo manifests (job, pvc, secret, broken pods)
│   └── demo-deployments/     # Scripted demo manifests (broken + fixed + healthy pod)
├── requirements.txt          # Python dependencies (kept at project root)
├── .env / .env.example       # Configuration (kept at project root)
└── Dockerfile
```

Run any script from the project root, e.g.:
```bash
python src/test_step1_monitoring.py
python src/run-complete-demo.py
```

## 🔧 Troubleshooting

### Azure AI Integration Issues

#### "Azure API error: Invalid authentication credentials"
- Verify `AZURE_API_KEY` is correctly set in `.env`
- Check that the key hasn't expired
- Confirm the endpoint URL matches your project in [ai.azure.com](https://ai.azure.com)

#### "Azure AI client not initialized"
- Ensure `AZURE_INFERENCE_ENDPOINT` is set in `.env`
- If using environment credentials (`AZURE_INFERENCE_CREDENTIAL=environment`), verify Azure CLI is installed and authenticated:
  ```bash
  az login
  az account show
  ```

#### "Connection timeout calling Azure AI"
- Check your network connectivity to Azure
- Increase `AZURE_CHAT_TIMEOUT_SECONDS` in `.env` if experiencing slow responses:
  ```env
  AZURE_CHAT_TIMEOUT_SECONDS=60
  ```

### Fallback to Ollama

If Azure integration isn't available, the system automatically falls back to Ollama. To use Ollama:

1. Install Ollama: https://ollama.ai
2. Run: `ollama run qwen2.5:3b`
3. Set in `.env`: `AI_PROVIDER=ollama`

### General Issues

#### "Pod not found" error
Check pod exists:
```bash
kubectl get pods -n <namespace>
```

#### Empty or delayed responses
- **Azure**: Increase timeout and token limits:
  ```env
  AZURE_CHAT_TIMEOUT_SECONDS=60
  AZURE_MAX_TOKENS=2048
  ```
- **Ollama**: Use the balanced profile for better quality:
  ```env
  OLLAMA_PROFILE=balanced
  OLLAMA_TIMEOUT_SECONDS=30
  ```

## 🚀 Next Steps (Advanced)

1. **Use Managed Identity for Azure** - Replace API key with Azure AD authentication in production
2. **Database** - Store analysis history and trends
3. **Webhooks** - Auto-analyze pod failures in real-time
4. **Multi-model** - Add Mistral, Qwen for comparison

## 📄 License

MIT
