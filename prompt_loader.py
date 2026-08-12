"""
AKS Operations Copilot - Prompt Loader

The actual prompt wording lives in prompts.md (plain markdown, easy to
review/edit without touching code). This module just parses that file and
exposes one `build_*_prompt()` function per template, matching the call
sites in agent.py.

prompts.md format:
    Each template is wrapped between `<!--PROMPT:name-->` and `<!--END-->`
    markers and uses `$variable` placeholders (Python string.Template
    syntax — chosen over str.format because prompt bodies can contain
    literal `{` `}` from YAML/JSON snippets).
"""

import json
import re
from pathlib import Path
from string import Template

_PROMPTS_PATH = Path(__file__).parent / "prompts.md"
_BLOCK_RE = re.compile(r"<!--PROMPT:(\w+)-->\n(.*?)\n<!--END-->", re.DOTALL)


def _load_templates() -> dict:
    text = _PROMPTS_PATH.read_text(encoding="utf-8")
    return {name: Template(body) for name, body in _BLOCK_RE.findall(text)}


# Loaded once at import time. prompts.md changes require a process restart —
# consistent with how the old prompts.py constants worked.
_TEMPLATES = _load_templates()

GUARDRAILS = _TEMPLATES["guardrails"].template


def build_log_analysis_prompt(issue_type: str, compact_description: str, compact_logs: str) -> str:
    """Prompt for analyze_logs(): root-cause explanation for a failing pod."""
    return _TEMPLATES["log_analysis"].substitute(
        issue_type=issue_type,
        compact_description=compact_description,
        compact_logs=compact_logs,
        guardrails=GUARDRAILS,
    )


def build_namespace_ops_prompt(snapshot: dict) -> str:
    """Prompt for analyze_namespace_operations(): namespace snapshot -> ops brief."""
    return _TEMPLATES["namespace_ops"].substitute(
        snapshot_json=json.dumps(snapshot, indent=2),
        guardrails=GUARDRAILS,
    )


def build_remediation_rationale_prompt(plan: dict, description_short: str, logs_excerpt: str) -> str:
    """Prompt for generate_remediation_rationale(): why a remediation plan is safe."""
    return _TEMPLATES["remediation_rationale"].substitute(
        plan_json=json.dumps(plan, indent=2),
        description_short=description_short,
        logs_excerpt=logs_excerpt,
        guardrails=GUARDRAILS,
    )


def build_platform_advice_prompt(goal: str, constraints: str, snapshot: dict) -> str:
    """Prompt for platform_engineering_advice(): roadmap + KPI guidance."""
    return _TEMPLATES["platform_advice"].substitute(
        goal=goal,
        constraints=constraints,
        snapshot_json=json.dumps(snapshot, indent=2),
        guardrails=GUARDRAILS,
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
    return _TEMPLATES["helm_fix"].substitute(
        pod_name=pod_name,
        namespace=namespace,
        k8s_context=k8s_context,
        root_cause_summary=root_cause_summary or "(see full logs below)",
        logs_tail=logs_tail,
        helm_values_path=helm_values_path,
        helm_values_content=helm_values_content or "(not found — infer from peer files below)",
        peer_comparison=peer_comparison,
    )
