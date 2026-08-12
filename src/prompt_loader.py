"""
Kubernetes Operations Copilot - Prompt Loader

The actual prompt wording lives in prompts.md (plain markdown, easy to
review/edit without touching code). This module just parses that file and
exposes one `build_*_prompt()` function per template, matching the call
sites in agent.py.

prompts.md format:
    Each template is wrapped between `<!--PROMPT:name-->` and `<!--END-->`
    markers and uses `$variable` placeholders (Python string.Template
    syntax — chosen over str.format because prompt bodies can contain
    literal `{` `}` from YAML/JSON snippets).

Shared prefix:
    The `base` template holds one persona line plus the safety guardrails,
    shared across every prompt. Every build_*_prompt() function prepends
    it to the task-specific template instead of each template repeating
    its own persona line and re-appending the guardrails separately. This
    keeps the shared prefix byte-for-byte identical across calls, which
    also happens to be the shape required for prompt caching if the AI
    provider supports it.
"""

import json
import re
from pathlib import Path
from string import Template

_PROMPTS_PATH = Path(__file__).parent.parent / "prompts" / "prompts.md"
_BLOCK_RE = re.compile(r"<!--PROMPT:(\w+)-->\n(.*?)\n<!--END-->", re.DOTALL)


def _load_templates() -> dict:
    text = _PROMPTS_PATH.read_text(encoding="utf-8")
    return {name: Template(body) for name, body in _BLOCK_RE.findall(text)}


# Loaded once at import time. prompts.md changes require a process restart —
# consistent with how the old prompts.py constants worked.
_TEMPLATES = _load_templates()

# Shared persona + guardrails, prepended to every task-specific prompt below.
BASE = _TEMPLATES["base"].template


def _render(task_name: str, **kwargs) -> str:
    """Substitute a task template and prepend the shared base prefix."""
    task_text = _TEMPLATES[task_name].substitute(**kwargs)
    return f"{BASE}\n{task_text}"


def build_log_analysis_prompt(issue_type: str, compact_description: str, compact_logs: str) -> str:
    """Prompt for analyze_logs(): root-cause explanation for a failing pod."""
    return _render(
        "log_analysis",
        issue_type=issue_type,
        compact_description=compact_description,
        compact_logs=compact_logs,
    )


def build_namespace_ops_prompt(snapshot: dict) -> str:
    """Prompt for analyze_namespace_operations(): namespace snapshot -> ops brief."""
    return _render(
        "namespace_ops",
        snapshot_json=json.dumps(snapshot, indent=2),
    )


def build_remediation_rationale_prompt(plan: dict, description_short: str, logs_excerpt: str) -> str:
    """Prompt for generate_remediation_rationale(): why a remediation plan is safe."""
    return _render(
        "remediation_rationale",
        plan_json=json.dumps(plan, indent=2),
        description_short=description_short,
        logs_excerpt=logs_excerpt,
    )


def build_platform_advice_prompt(goal: str, constraints: str, snapshot: dict) -> str:
    """Prompt for platform_engineering_advice(): roadmap + KPI guidance."""
    return _render(
        "platform_advice",
        goal=goal,
        constraints=constraints,
        snapshot_json=json.dumps(snapshot, indent=2),
    )


def build_helm_fix_prompt(
    pod_name: str,
    namespace: str,
    k8s_context: str,
    root_cause_summary: str,
    logs_tail: str,
    helm_values_path: str,
    helm_values_content: str,
    peer_comparison: str,
) -> str:
    """Prompt for create_fix_pr(): generate a corrected Helm values YAML file."""
    return _render(
        "helm_fix",
        pod_name=pod_name,
        namespace=namespace,
        k8s_context=k8s_context,
        root_cause_summary=root_cause_summary or "(see full logs below)",
        logs_tail=logs_tail,
        helm_values_path=helm_values_path,
        helm_values_content=helm_values_content or "(not found — infer from peer files below)",
        peer_comparison=peer_comparison,
    )
