"""
AKS Operations Copilot - AI Agent Module

Supports three AI providers:
1. Azure OpenAI (Recommended) - Uses Azure Foundry OpenAI-compatible endpoint
2. AWS Bedrock - Uses OpenAI's open-weight gpt-oss models via Bedrock's Converse API
3. Ollama (Legacy) - Uses local LLM inference

Automatically falls back to deterministic analysis if AI inference fails.
"""

# Load environment variables from .env file FIRST
from dotenv import load_dotenv
load_dotenv()

import json
import os
from typing import Optional, Dict, Any

from tools import detect_issue

# ========== Configuration ==========
AI_PROVIDER = os.getenv("AI_PROVIDER", "azure").lower().strip()

# Azure OpenAI Configuration
AZURE_INFERENCE_ENDPOINT = os.getenv("AZURE_INFERENCE_ENDPOINT", "").strip()
AZURE_MODEL_DEPLOYMENT = os.getenv("AZURE_MODEL_DEPLOYMENT", "gpt-5.5").strip()
AZURE_API_KEY = os.getenv("AZURE_API_KEY", "").strip()
AZURE_CHAT_TIMEOUT_SECONDS = float(os.getenv("AZURE_CHAT_TIMEOUT_SECONDS", "30"))
AZURE_TEMPERATURE = float(os.getenv("AZURE_TEMPERATURE", "0.2"))
AZURE_MAX_TOKENS = int(os.getenv("AZURE_MAX_TOKENS", "1024"))

# AWS Bedrock Configuration
# Credentials use the standard boto3 chain: AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
# env vars, ~/.aws/credentials, SSO profile, or an IAM role.
# Set AWS_PROFILE=<sso-profile-name> to use SSO credentials with auto-refresh.
AWS_REGION = os.getenv("AWS_REGION", "us-east-2").strip()
AWS_PROFILE = os.getenv("AWS_PROFILE", "").strip() or None
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "openai.gpt-oss-120b-1:0").strip()
BEDROCK_TEMPERATURE = float(os.getenv("BEDROCK_TEMPERATURE", "0.2"))
BEDROCK_MAX_TOKENS = int(os.getenv("BEDROCK_MAX_TOKENS", "1024"))

# Ollama Configuration (Legacy)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_PROFILE = os.getenv("OLLAMA_PROFILE", "fast").strip().lower()

# Determine which AI client to use
_ai_client = None
_bedrock_client = None
_use_ollama = False
_use_bedrock = False

if AI_PROVIDER == "ollama":
    _use_ollama = True
    _ai_provider_info = f"Ollama (local: {OLLAMA_MODEL})"
elif AI_PROVIDER == "bedrock":
    try:
        import boto3

        def _create_bedrock_client():
            """Create a Bedrock client using SSO profile (auto-refreshing) or default creds."""
            session = boto3.Session(
                profile_name=AWS_PROFILE,
                region_name=AWS_REGION,
            )
            return session.client("bedrock-runtime")

        _bedrock_client = _create_bedrock_client()
        _use_bedrock = True
        _profile_info = f", profile={AWS_PROFILE}" if AWS_PROFILE else ""
        _ai_provider_info = f"AWS Bedrock ({BEDROCK_MODEL_ID}, region={AWS_REGION}{_profile_info})"
    except Exception as e:
        print(f"[agent] Warning: Failed to initialize AWS Bedrock client: {e}")
        print(f"[agent] Falling back to Ollama")
        _use_ollama = True
        _ai_provider_info = "Ollama (local)"
else:
    try:
        from openai import OpenAI

        if not AZURE_INFERENCE_ENDPOINT:
            raise ValueError("AZURE_INFERENCE_ENDPOINT not set. Falling back to Ollama.")

        if AZURE_API_KEY and not AZURE_API_KEY.startswith("@keyvault"):
            # API key auth
            _ai_client = OpenAI(
                api_key=AZURE_API_KEY,
                base_url=AZURE_INFERENCE_ENDPOINT,
            )
            _auth_method = "api-key"
        else:
            # Azure AD auth — auto-refreshing token via httpx interceptor
            import httpx
            from azure.identity import DefaultAzureCredential

            class _AzureAdAuth(httpx.Auth):
                def __init__(self):
                    self._credential = DefaultAzureCredential()

                def auth_flow(self, request):
                    token = self._credential.get_token(
                        "https://cognitiveservices.azure.com/.default"
                    ).token
                    request.headers["Authorization"] = f"Bearer {token}"
                    yield request

            _ai_client = OpenAI(
                api_key="azure-ad",  # placeholder, overridden by auth handler
                base_url=AZURE_INFERENCE_ENDPOINT,
                http_client=httpx.Client(auth=_AzureAdAuth()),
            )
            _auth_method = "DefaultAzureCredential"

        _use_ollama = False
        _ai_provider_info = f"Azure OpenAI ({AZURE_MODEL_DEPLOYMENT}, auth={_auth_method})"
    except Exception as e:
        print(f"[agent] Warning: Failed to initialize Azure OpenAI client: {e}")
        print(f"[agent] Falling back to Ollama")
        _use_ollama = True
        _ai_provider_info = "Ollama (local)"



def _int_env(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


if OLLAMA_PROFILE == "balanced":
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_NUM_CTX = 1024
    DEFAULT_NUM_PREDICT = 160
    DEFAULT_TEMPERATURE = 0.2
else:
    DEFAULT_TIMEOUT = 20.0
    DEFAULT_NUM_CTX = 384
    DEFAULT_NUM_PREDICT = 80
    DEFAULT_TEMPERATURE = 0.1

OLLAMA_TIMEOUT_SECONDS = _float_env("OLLAMA_TIMEOUT_SECONDS", DEFAULT_TIMEOUT)
OLLAMA_NUM_CTX = _int_env("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX)
OLLAMA_NUM_PREDICT = _int_env("OLLAMA_NUM_PREDICT", DEFAULT_NUM_PREDICT)
OLLAMA_TEMPERATURE = _float_env("OLLAMA_TEMPERATURE", DEFAULT_TEMPERATURE)
OLLAMA_NUM_THREAD = _int_env(
    "OLLAMA_NUM_THREAD",
    max(1, min(4, os.cpu_count() or 2)),
)
OLLAMA_MAX_INPUT_CHARS = _int_env("OLLAMA_MAX_INPUT_CHARS", 6000)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "20m")


def _clip_text(text, max_chars):
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    clipped = text[: max_chars - 120]
    return (
        f"{clipped}\n\n[truncated {len(text) - len(clipped)} chars for faster inference]"
    )


def _chat_with_azure(prompt: str, max_tokens: int = None, timeout: int = None) -> str:
    """Call Azure OpenAI model via OpenAI SDK."""
    if not _ai_client:
        raise RuntimeError("Azure OpenAI client not initialized")

    try:
        response = _ai_client.chat.completions.create(
            model=AZURE_MODEL_DEPLOYMENT,
            messages=[{"role": "user", "content": prompt}],
            temperature=AZURE_TEMPERATURE,
            max_completion_tokens=max_tokens or AZURE_MAX_TOKENS,
            timeout=timeout or AZURE_CHAT_TIMEOUT_SECONDS,
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"Error calling Azure OpenAI: {e}")


def _chat_with_ollama(prompt: str) -> str:
    """Call Ollama model via HTTP."""
    from urllib import error, request
    
    compact_prompt = _clip_text(prompt, OLLAMA_MAX_INPUT_CHARS)
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "user", "content": compact_prompt}],
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {
                "num_ctx": OLLAMA_NUM_CTX,
                "num_predict": OLLAMA_NUM_PREDICT,
                "temperature": OLLAMA_TEMPERATURE,
                "num_thread": OLLAMA_NUM_THREAD,
            },
        }
    ).encode("utf-8")
    req = request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with request.urlopen(req, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
        response_body = json.loads(response.read().decode("utf-8"))
        return response_body["message"]["content"]


def _extract_bedrock_text(response: dict) -> str:
    """Extract text from a Bedrock Converse API response, handling format variations.

    The response content blocks can be:
      - {"text": "..."}                             — standard text output
      - {"reasoningContent": {"reasoningText": {"text": "..."}}} — chain-of-thought
    Some models (e.g. openai.gpt-oss) emit reasoning blocks first, followed by
    a plain text block.  We prefer the plain text; fall back to reasoning text.
    """
    output = response.get("output", {})
    message = output.get("message", {})
    content_blocks = message.get("content", [])

    texts = []
    reasoning_texts = []

    for block in content_blocks:
        if isinstance(block, dict):
            # Standard text block
            if "text" in block:
                texts.append(block["text"])
            # Reasoning / chain-of-thought block
            reasoning = block.get("reasoningContent", {})
            if isinstance(reasoning, dict):
                rt = reasoning.get("reasoningText", {})
                if isinstance(rt, dict) and "text" in rt:
                    reasoning_texts.append(rt["text"])
                elif isinstance(rt, str):
                    reasoning_texts.append(rt)
        elif isinstance(block, str):
            texts.append(block)

    # Prefer actual answer text; fall back to reasoning output
    if texts:
        return "\n".join(texts)
    if reasoning_texts:
        return "\n".join(reasoning_texts)

    raise RuntimeError(
        f"Bedrock returned empty content. Stop reason: "
        f"{response.get('stopReason', 'unknown')}. "
        f"Response keys: {list(response.keys())}"
    )


def _chat_with_bedrock(prompt: str, max_tokens: int = None) -> str:
    """Call an AWS Bedrock model (e.g. OpenAI gpt-oss-120b) via the Converse API.

    Automatically recreates the client on expired/invalid credential errors
    (common with SSO temporary tokens).
    """
    global _bedrock_client
    if not _bedrock_client:
        raise RuntimeError("AWS Bedrock client not initialized")

    def _invoke(client):
        return client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={
                "maxTokens": max_tokens or BEDROCK_MAX_TOKENS,
                "temperature": BEDROCK_TEMPERATURE,
            },
        )

    try:
        response = _invoke(_bedrock_client)
        return _extract_bedrock_text(response)
    except _bedrock_client.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("UnrecognizedClientException", "ExpiredTokenException",
                          "InvalidIdentityToken", "AccessDeniedException"):
            print(f"[agent] Bedrock credentials expired ({error_code}), refreshing session...")
            try:
                _bedrock_client = _create_bedrock_client()
                response = _invoke(_bedrock_client)
                return _extract_bedrock_text(response)
            except Exception as retry_err:
                profile_name = AWS_PROFILE or "default"
                raise RuntimeError(
                    f"Error calling AWS Bedrock after credential refresh: {retry_err}. "
                    f"Run 'aws sso login --profile {profile_name}' to re-authenticate."
                )
        raise RuntimeError(f"Error calling AWS Bedrock: {e}")
    except Exception as e:
        raise RuntimeError(f"Error calling AWS Bedrock: {e}")


def _chat_with_ai(prompt: str, max_tokens: int = None, timeout: int = None) -> str:
    """Route to the configured AI provider."""
    if _use_bedrock:
        return _chat_with_bedrock(prompt, max_tokens=max_tokens)
    elif _use_ollama:
        return _chat_with_ollama(prompt)
    else:
        return _chat_with_azure(prompt, max_tokens=max_tokens, timeout=timeout)


def build_fallback_analysis(issue_type, description, logs):
    """Return a fast deterministic diagnosis when model inference is too slow."""
    issue_type_lower = issue_type.lower()
    logs_lower = logs.lower()

    if "oomkilled" in issue_type_lower:
        return (
            "Root cause: The container was terminated due to memory pressure (OOMKilled).\n"
            "Issue classification: Resource limit / memory sizing\n"
            "Exact fix:\n"
            "1) Check current limits: kubectl describe pod <pod> -n <namespace>\n"
            "2) Increase memory requests/limits in deployment values/manifests\n"
            "3) Redeploy: kubectl rollout restart deployment/<deployment> -n <namespace>\n"
            "Prevention: Set realistic memory requests/limits and add memory usage alerts."
        )

    if "imagepullbackoff" in issue_type_lower:
        return (
            "Root cause: The node cannot pull the container image (bad tag, auth issue, or missing image).\n"
            "Issue classification: Image registry / deployment config\n"
            "Exact fix:\n"
            "1) Verify image: kubectl describe pod <pod> -n <namespace>\n"
            "2) Check imagePullSecrets and ACR/registry permissions\n"
            "3) Update image tag and redeploy\n"
            "Prevention: Use immutable tags and validate image availability in CI before deploy."
        )

    if "crashloopbackoff" in issue_type_lower:
        return (
            "Root cause: The container repeatedly exits after start, typically due to config/env/startup command issues.\n"
            "Issue classification: Application startup / configuration\n"
            "Exact fix:\n"
            "1) Inspect previous logs: kubectl logs <pod> -n <namespace> --previous\n"
            "2) Validate env/configmap/secret values used by the pod\n"
            "3) Restart deployment after fixing config: kubectl rollout restart deployment/<deployment> -n <namespace>\n"
            "Prevention: Add startup validation checks and fail-fast config validation in app boot."
        )

    if "liveness probe failure" in issue_type_lower or "liveness" in description.lower():
        return (
            "Root cause: Liveness probe is failing, so kubelet restarts the container repeatedly.\n"
            "Issue classification: Probe configuration / app health endpoint\n"
            "Exact fix:\n"
            "1) Check probe endpoint and port in deployment manifest\n"
            "2) Increase initialDelaySeconds and timeoutSeconds\n"
            "3) Verify endpoint inside pod: kubectl exec -n <namespace> <pod> -- curl -I http://127.0.0.1:<port>/<path>\n"
            "Prevention: Separate readiness/liveness behavior and tune probe timings for startup latency."
        )

    if "connection refused" in logs_lower or "timeout" in logs_lower:
        return (
            "Root cause: Application dependencies are unreachable or not ready (DB/Redis/API timeout).\n"
            "Issue classification: Dependency/network startup ordering\n"
            "Exact fix:\n"
            "1) Check service endpoints and DNS resolution from pod\n"
            "2) Validate network policies and service ports\n"
            "3) Add retry/backoff in app startup and dependency checks\n"
            "Prevention: Add dependency health checks and startup retry strategy."
        )

    return (
        "Root cause: Unable to complete AI inference in time; likely general runtime/config issue.\n"
        "Issue classification: Unknown (fallback mode)\n"
        "Exact fix:\n"
        "1) Run kubectl describe pod <pod> -n <namespace> and inspect Events section\n"
        "2) Run kubectl logs <pod> -n <namespace> --previous\n"
        "3) Verify env vars, secrets, image tag, and probes in deployment\n"
        "Prevention: Add monitoring for restarts, probe failures, and startup error rates."
    )


def analyze_logs(logs, description):
    """Analyze pod logs and description using configured AI provider (Azure or Ollama)"""

    issue_type = detect_issue(description)

    compact_description = _clip_text(description, 3000)
    compact_logs = _clip_text(logs, 3000)

    prompt = f"""You are a senior Kubernetes DevOps engineer with 10+ years of experience troubleshooting AKS clusters.

A pod is experiencing issues and needs your analysis.

ISSUE TYPE DETECTED: {issue_type}

Provide a concise analysis with:
1. Root cause (2-3 sentences)
2. Issue classification
3. Prevention tips
Do NOT include kubectl/helm commands or step-by-step fix instructions — those are
provided separately in the notification's remediation and action-guide sections.
Focus only on explaining the "why", not the "how".

Pod Description:
{compact_description}

Recent Logs:
{compact_logs}

Keep the response compact and focused on root cause."""

    try:
        return _chat_with_ai(prompt)
    except Exception as e:
        fallback = build_fallback_analysis(issue_type, description, logs)
        return (
            f"Error analyzing logs with {_ai_provider_info}: {e}\n\n"
            f"Returning fast fallback analysis:\n\n{fallback}"
        )


def analyze_namespace_operations(snapshot):
    """Step 2: Convert namespace snapshot into an operations priority view."""
    problematic = snapshot.get("problematic_pod_count", 0)
    restart_heavy = snapshot.get("high_restart_pod_count", 0)
    pending = snapshot.get("pending_pods", 0)

    priorities = []
    if problematic > 0:
        priorities.append("Stabilize failing pods first (CrashLoopBackOff/ImagePull/Pending).")
    if restart_heavy > 0:
        priorities.append("Investigate high-restart workloads to reduce churn and alert noise.")
    if pending > 0:
        priorities.append("Resolve scheduling bottlenecks (resources, taints, affinities).")
    if not priorities:
        priorities.append("Namespace is stable; focus on preventive reliability improvements.")

    fallback = {
        "summary": (
            f"Namespace {snapshot.get('namespace', 'default')} has "
            f"{problematic} problematic pods and {restart_heavy} high-restart pods."
        ),
        "priorities": priorities,
        "next_30_minutes": [
            "Review recent warning events and top failing pods.",
            "Run targeted describe/log checks on highest-impact services.",
            "Create short action owner list and ETA for fixes.",
        ],
    }

    prompt = f"""You are an AKS operations lead.

Turn this namespace snapshot into a concise operations brief with:
1) summary
2) top 3 priorities
3) immediate actions for next 30 minutes

Snapshot:
{json.dumps(snapshot, indent=2)}

Return compact JSON with keys: summary, priorities, next_30_minutes.
"""
    try:
        response = _chat_with_ai(prompt)
        return {"ai_response": response, "fallback": fallback}
    except Exception:
        return fallback


def generate_remediation_rationale(plan, description_short, logs_excerpt):
    """Step 3: Explain why the proposed remediation sequence is safe and useful."""
    commands = plan.get("commands", [])
    fallback_lines = [
        "This plan prioritizes read-only diagnostics before any restart action.",
        f"Detected issue type: {plan.get('issue_type', 'Unknown')}.",
        f"Planned commands: {len(commands)} total.",
    ]
    if plan.get("restart_suppressed"):
        fallback_lines.append(
            "Restart is intentionally suppressed due to high restart churn to avoid amplifying instability."
        )

    fallback_lines.append("Execution is limited to allowlisted kubectl commands for safety.")
    fallback = "\n".join(fallback_lines)

    prompt = f"""You are a reliability engineer.

Explain the safety and rationale for this remediation plan in under 180 words.
Focus on: risk reduction, command ordering, and why actions are safe.

Plan:
{json.dumps(plan, indent=2)}

Description snippet:
{description_short}

Logs excerpt:
{logs_excerpt}
"""
    try:
        return _chat_with_ai(prompt)
    except Exception:
        return fallback


def platform_engineering_advice(goal, snapshot, constraints=None):
    """Step 4: Provide platform engineering roadmap and KPI guidance."""
    constraints = constraints or "None provided"
    fallback = {
        "recommended_pattern": "Golden path with standardized deployment templates and SLO guardrails",
        "roadmap": [
            "0-30 days: Define service onboarding checklist, probe standards, and default alerts.",
            "30-60 days: Add reliability scorecard (restarts, availability, change failure rate).",
            "60-90 days: Automate remediation runbooks for top recurring incidents.",
        ],
        "kpis": [
            "MTTR",
            "Change failure rate",
            "Pod restart rate per workload",
            "SLO attainment for critical services",
        ],
        "goal": goal,
        "constraints": constraints,
    }

    prompt = f"""You are a platform engineering advisor for AKS.

User goal: {goal}
Constraints: {constraints}

Current namespace snapshot:
{json.dumps(snapshot, indent=2)}

Provide practical guidance with:
1) Recommended platform pattern
2) 90-day roadmap (3 phases)
3) 4 measurable KPIs/SLOs

Return compact JSON with keys: recommended_pattern, roadmap, kpis.
"""
    try:
        response = _chat_with_ai(prompt)
        return {"ai_response": response, "fallback": fallback}
    except Exception:
        return fallback


def monitor_and_notify_failures(namespace=None, k8s_context=None, raise_pr=None):
    """
    Step 1 (NEW): Monitor and notify pod failures.

    Detects pods with major impact issues (CrashLoopBackOff, OOMKilled,
    ImagePullBackOff, etc.), sends MS Teams notifications, and optionally
    raises an auto-fix PR in Azure DevOps (requires AZURE_DEVOPS_PAT).
    """
    from tools import monitor_and_notify_failing_pods

    if not k8s_context:
        k8s_context = os.getenv("K8S_CONTEXT")
    if namespace is None:
        namespace = os.getenv("K8S_NAMESPACE", "default")
    if raise_pr is None:
        raise_pr = os.getenv("RAISE_PR", "no").strip().lower() == "yes"

    try:
        result = monitor_and_notify_failing_pods(namespace, k8s_context, raise_pr=raise_pr)
        return {
            "status": "success",
            "data": result,
            "summary": result.get("summary", "")
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "summary": f"Failed to monitor and notify: {e}"
        }


def create_fix_pr(pod_name, namespace, k8s_context=None):
    """
    Analyse a failing pod, generate a Helm values fix, create a feature
    branch in the Azure DevOps repo, commit the fix, and open a PR to master.

    Requires AZURE_DEVOPS_PAT in .env with write + PR permissions.
    Skips system/infrastructure pods that are not managed by the devops repo.

    Returns a dict with keys: status, pr_url, branch, summary, error.
    """
    from tools import describe_pod, get_pod_logs, run_cmd
    from repo_context import AzureDevOpsRepoLoader, get_repo_context, format_repo_context_for_ai
    from datetime import datetime

    if not k8s_context:
        k8s_context = os.getenv("K8S_CONTEXT")

    try:
        loader = AzureDevOpsRepoLoader(k8s_context=k8s_context)

        # 0. Check if this deployment is managed by the devops repo.
        #    System pods (kube-system, azure-*, cert-manager, istio-*, etc.) won't have
        #    a values file in the repo — skip PR for those.
        deployment_name = "-".join(pod_name.split("-")[:-2]) or pod_name.split("-")[0]
        values_path = loader.find_helm_values_path(deployment_name, namespace)
        values_content = loader.get_file_content(values_path)
        if not values_content or values_content.startswith("Error"):
            return {
                "status": "skipped",
                "reason": "system-pod",
                "summary": (
                    f"Skipped PR for {pod_name} — no values file found in repo "
                    f"({loader.repo}). Likely a system/infrastructure pod."
                ),
            }

        # 1. Gather context — use previous logs (200 lines) to capture full stack trace
        pod_desc = describe_pod(pod_name, namespace, k8s_context)
        logs_current = run_cmd(
            f"kubectl logs {pod_name} -n {namespace} --tail=200 --all-containers=false",
            k8s_context
        )
        logs_previous = run_cmd(
            f"kubectl logs {pod_name} -n {namespace} --previous --tail=200 --all-containers=false",
            k8s_context
        )
        # Use whichever has more content, prefer previous (the crash)
        logs = logs_previous if len(logs_previous) > len(logs_current) else logs_current

        # Extract root cause chain ("Caused by:" lines) from Spring/Java stack traces
        root_cause_lines = [
            line.strip() for line in logs.splitlines()
            if any(kw in line for kw in ["Caused by:", "NullPointerException", "IllegalArgumentException",
                                          "BeanCreationException", "getEnvironment", "getProperty",
                                          "Cannot invoke", "is null", "was null", "No qualifying bean",
                                          "required a bean", "Could not resolve", "failed to start"])
        ]
        root_cause_summary = "\n".join(root_cause_lines[:30]) if root_cause_lines else ""

        repo_ctx = get_repo_context(pod_name, namespace, k8s_context=k8s_context)
        deployment_name = repo_ctx.get("deployment_name", pod_name.split("-")[0])

        # 2. Get the actual values file content via tree discovery
        helm_values_content = ""
        helm_values_path = loader.find_helm_values_path(deployment_name, namespace)
        existing_content = loader.get_file_content(helm_values_path)
        if existing_content and not existing_content.startswith("Error"):
            helm_values_content = existing_content

        # 3. Fetch peer environment files for comparison (to spot missing keys)
        peer_envs = [e for e in ["int", "stg", "dev", "prod"] if e != namespace]
        peer_sections = []
        for peer_env in peer_envs:
            peer_path = loader.find_helm_values_path(deployment_name, peer_env)
            peer_content = loader.get_file_content(peer_path)
            if peer_content and not peer_content.startswith("Error"):
                peer_sections.append(
                    f"=== PEER FILE ({peer_env}): {peer_path} ===\n{peer_content[:2000]}"
                )
        peer_comparison = "\n\n".join(peer_sections) if peer_sections else "(no peer files found)"

        ai_prompt = f"""You are a Kubernetes/Helm expert fixing a real production pod failure.

Pod: {pod_name} | Namespace: {namespace} | Context: {k8s_context}

=== ROOT CAUSE (extracted from stack trace) ===
{root_cause_summary if root_cause_summary else "(see full logs below)"}

=== FULL CRASH LOGS (last 200 lines) ===
{logs[-3000:]}

=== BROKEN FILE TO FIX: {helm_values_path} ===
{helm_values_content[:3000] if helm_values_content else "(not found — infer from peer files below)"}

=== PEER ENVIRONMENT FILES (same service, other environments) ===
{peer_comparison}

=== TASK ===
Output ONLY the corrected YAML content for {helm_values_path}.

Rules (strictly follow):
1. Raw YAML only — no markdown fences, no ``` blocks, no explanations, no inline comments
2. Reproduce the ENTIRE existing file — do NOT omit any existing keys
3. Determine the fix using this priority order:

   STEP A — Peer diff: Compare the broken file against peer env files.
   If a peer has a key/env var that the broken file is missing, add it with the correct value for namespace "{namespace}".

   STEP B — Stack trace derivation (use this when peers are structurally identical and offer no diff):
   For Spring Boot NullPointerException on a getter like `SomeProperties.getSomething()`:
   - The Spring property name is the class prefix + field: e.g. GatewayProperties.getEnvironment() → property "gateway.environment"
   - The env var equivalent (Spring Boot relaxed binding): GATEWAY_ENVIRONMENT
   - Derive the correct VALUE from context: if the property is "environment" or "profile", the value should be "{namespace}"
   - If the property is a URL/host/key, flag it as a secret and add a placeholder env var pointing to a Kubernetes secret
   For OOMKilled: increase resources.limits.memory
   For ImagePullBackOff: correct image.tag or image.repository

4. Minimal targeted fix only — change nothing that already works"""

        fixed_yaml = None
        for attempt in range(2):
            response = _chat_with_ai(ai_prompt, max_tokens=4096, timeout=120)
            if response and len(response.strip()) >= 20:
                fixed_yaml = response
                break

        if not fixed_yaml:
            return {
                "status": "error",
                "error": "AI did not return a valid Helm values fix after 2 attempts.",
                "summary": "PR not created — AI fix generation failed.",
            }

        # Strip accidental markdown fences if AI added them
        if fixed_yaml.strip().startswith("```"):
            lines = fixed_yaml.strip().splitlines()
            fixed_yaml = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            )

        # 3. Create branch
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"fix/{pod_name}-{namespace}-{timestamp}"
        loader.create_branch(branch_name, from_branch="master")

        # 4. Commit the fixed values file
        commit_msg = f"fix({namespace}): auto-remediate {pod_name} - {deployment_name}"
        loader.commit_file(
            file_path=helm_values_path,
            new_content=fixed_yaml,
            branch=branch_name,
            commit_message=commit_msg,
        )

        # 5. Open PR
        pr_title = f"[AI Fix] {deployment_name} pod failure in {namespace}"
        pr_description = (
            f"**Automated PR raised by AKS AI Agent**\n\n"
            f"- **Pod:** `{pod_name}`\n"
            f"- **Namespace:** `{namespace}`\n"
            f"- **Context:** `{k8s_context}`\n"
            f"- **File changed:** `{helm_values_path}`\n\n"
            f"### Root cause summary\n"
            f"{logs[:500]}\n\n"
            f"### What changed\n"
            f"AI-generated Helm values fix to resolve the pod failure. "
            f"Please review before merging."
        )
        pr = loader.create_pull_request(branch_name, pr_title, pr_description)

        return {
            "status": "success",
            "pr_url": pr["url"],
            "pr_id": pr["pr_id"],
            "branch": branch_name,
            "file": helm_values_path,
            "summary": f"PR #{pr['pr_id']} created: {pr['url']}",
        }

    except ValueError as e:
        return {"status": "error", "error": str(e), "summary": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e), "summary": f"PR creation failed: {e}"}
