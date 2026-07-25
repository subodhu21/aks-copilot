"""
AKS AI Agent — Streamlit Dashboard
AI-Powered Kubernetes Health Monitor with real-time pod diagnostics.
"""

import os
import sys
import json
import streamlit as st
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

# Lazy imports after dotenv so env vars are available
from tools import detect_failing_pods, _build_notification_content, run_cmd
from agent import _ai_provider_info

# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI-Powered K8s Health Monitor",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Global ─────────────────────────────────────────────────── */
.block-container { padding-top: 1.5rem; }

/* ── Hero banner ────────────────────────────────────────────── */
.hero {
    background: linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%);
    border-radius: 14px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    color: #ffffff;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25);
}
.hero h1 {
    margin: 0 0 .3rem 0;
    font-size: 2rem;
    font-weight: 700;
    letter-spacing: -0.5px;
}
.hero p {
    margin: 0;
    opacity: 0.85;
    font-size: 1.05rem;
}
.hero .cluster-badge {
    display: inline-block;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 8px;
    padding: 0.3rem 0.8rem;
    margin-top: 0.8rem;
    font-size: 0.9rem;
    font-family: monospace;
}

/* ── Metric cards ───────────────────────────────────────────── */
.metric-card {
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    text-align: center;
    box-shadow: 0 2px 12px rgba(0,0,0,0.18);
    border-left: 4px solid;
}
.metric-card.total   { border-color: #4fc3f7; }
.metric-card.healthy { border-color: #66bb6a; }
.metric-card.failing { border-color: #ef5350; }
.metric-card .label {
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #ffffff;
    opacity: 0.85;
    margin-bottom: 0.3rem;
}
.metric-card .value {
    font-size: 2.4rem;
    font-weight: 700;
    line-height: 1;
}
.metric-card.total   .value { color: #4fc3f7; }
.metric-card.healthy .value { color: #66bb6a; }
.metric-card.failing .value { color: #ef5350; }

/* ── Pod cards ──────────────────────────────────────────────── */
.pod-header {
    background: linear-gradient(135deg, #1e1e2f, #2a2a40);
    border-radius: 10px;
    padding: 1rem 1.3rem;
    margin-bottom: 1rem;
    border-left: 4px solid;
    display: flex;
    align-items: center;
    gap: 1rem;
}
.pod-header.failing { border-color: #ef5350; }
.pod-header.healthy { border-color: #66bb6a; }
.pod-header .dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
}
.pod-header.failing .dot { background: #ef5350; box-shadow: 0 0 8px #ef5350; }
.pod-header.healthy .dot { background: #66bb6a; box-shadow: 0 0 8px #66bb6a; }
.pod-header .pod-name {
    font-weight: 600;
    font-size: 1.05rem;
    color: #ffffff;
}
.pod-header .pod-reason {
    opacity: 0.7;
    font-size: 0.9rem;
    margin-left: auto;
    font-family: monospace;
}

/* ── Section headers inside expanders ───────────────────────── */
.section-label {
    background: rgba(255,255,255,0.05);
    border-radius: 8px;
    padding: 0.5rem 0.9rem;
    margin: 1rem 0 0.5rem 0;
    font-weight: 600;
    font-size: 0.95rem;
    border-left: 3px solid;
}
.section-label.logs     { border-color: #ffa726; color: #ffa726; }
.section-label.rca      { border-color: #ab47bc; color: #ab47bc; }
.section-label.solution { border-color: #26c6da; color: #26c6da; }
.section-label.playbook { border-color: #66bb6a; color: #66bb6a; }

/* ── Sidebar polish ─────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f2027 0%, #203a43 100%);
}
section[data-testid="stSidebar"] .stMarkdown { color: #e0e0e0; }
section[data-testid="stSidebar"] .stTextInput label { color: #ffffff !important; }
.sidebar-info {
    background: rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 0.9rem 1rem;
    margin-bottom: 1rem;
    font-size: 0.88rem;
    line-height: 1.6;
}
.sidebar-info .label { opacity: 0.6; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.5px; }
.sidebar-info .val   { font-family: monospace; }

/* ── Healthy pod row ────────────────────────────────────────── */
.healthy-row {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.35rem 0;
    font-size: 0.92rem;
}
.healthy-row .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #66bb6a;
    box-shadow: 0 0 4px #66bb6a;
    flex-shrink: 0;
}

/* ── Timestamp / footer ─────────────────────────────────────── */
.analysis-footer {
    text-align: right;
    opacity: 0.5;
    font-size: 0.78rem;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid rgba(255,255,255,0.1);
}
</style>
""", unsafe_allow_html=True)

# ── Env vars ──────────────────────────────────────────────────────────────
K8S_CONTEXT = os.getenv("K8S_CONTEXT", "").strip() or None
K8S_NAMESPACE = os.getenv("K8S_NAMESPACE", "default").strip()
BEDROCK_MODEL = os.getenv("BEDROCK_MODEL_ID", "unknown")

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧠 AI K8s Monitor")
    st.markdown(f"""
    <div class="sidebar-info">
        <div><span class="label">Cluster</span><br><span class="val">{K8S_CONTEXT or 'current-context'}</span></div>
    </div>
    """, unsafe_allow_html=True)

    namespace = st.text_input("🏷️ Namespace", value=K8S_NAMESPACE)
    st.markdown("")
    analyse = st.button("⚡ Analyse Namespace", type="primary", use_container_width=True)
    st.markdown("---")
    st.caption("Powered by AWS Bedrock + Claude")

# ── Hero banner ───────────────────────────────────────────────────────────
st.markdown(f"""
<div class="hero">
    <h1>🧠 AI-Powered Kubernetes Health Monitor</h1>
    <p>Real-time cluster diagnostics with intelligent root-cause analysis</p>
</div>
""", unsafe_allow_html=True)

# ── Main content ──────────────────────────────────────────────────────────
if analyse:
    # ── Step 1: Detect failing pods ───────────────────────────────────
    with st.status("🔍 Scanning namespace for failing pods…", expanded=True) as status_ui:
        st.write(f"Querying pods in **{namespace}**…")
        detection = detect_failing_pods(namespace, K8S_CONTEXT)
        failing = detection.get("failing_pods", [])
        total = detection.get("failing_pods_count", 0)

        # Get all pods for healthy list
        all_pods_json = run_cmd(
            f"kubectl get pods -n {namespace} -o json", K8S_CONTEXT
        )
        all_pods = []
        try:
            pod_list = json.loads(all_pods_json)
            all_pods = [
                {
                    "name": p["metadata"]["name"],
                    "phase": p["status"].get("phase", "Unknown"),
                    "ready": sum(
                        1 for c in p["status"].get("containerStatuses", []) if c.get("ready")
                    ),
                    "total": len(
                        p["status"].get("containerStatuses", [])
                        or p["spec"].get("containers", [])
                    ),
                    "restarts": sum(
                        c.get("restartCount", 0)
                        for c in p["status"].get("containerStatuses", [])
                    ),
                }
                for p in pod_list.get("items", [])
            ]
        except Exception:
            pass

        failing_names = {p["pod_name"] for p in failing}
        healthy_pods = [p for p in all_pods if p["name"] not in failing_names]

        status_ui.update(
            label=f"✅ Scan complete — {total} failing, {len(healthy_pods)} healthy",
            state="complete",
        )

    # ── Metric cards ──────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class="metric-card total">
            <div class="label">Total Pods</div>
            <div class="value">{len(all_pods)}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card healthy">
            <div class="label">Healthy</div>
            <div class="value">{len(healthy_pods)}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card failing">
            <div class="label">Failing</div>
            <div class="value">{total}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("")

    # ── Healthy pods ──────────────────────────────────────────────────
    if healthy_pods:
        with st.expander(f"✅ Healthy Pods ({len(healthy_pods)})", expanded=False):
            for p in healthy_pods:
                st.markdown(
                    f'<div class="healthy-row">'
                    f'<div class="dot"></div>'
                    f'<strong>{p["name"]}</strong>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Failing pods with AI analysis ─────────────────────────────────
    if failing:
        st.markdown("---")
        st.markdown(f"### 🚨 Failing Pods  ({total})")

        # Run AI analysis for ALL pods in parallel to cut wait time
        def _analyse_pod(pod):
            return _build_notification_content(
                pod["pod_name"], namespace, pod["status"], pod["reason"],
                pod.get("error_logs", "No logs available"),
                k8s_context=K8S_CONTEXT,
            )

        ai_results = {}
        with st.spinner(f"🧠 AI analysing {total} pod(s) in parallel…"):
            with ThreadPoolExecutor(max_workers=len(failing)) as pool:
                futures = {pool.submit(_analyse_pod, p): p["pod_name"] for p in failing}
                for fut in as_completed(futures):
                    ai_results[futures[fut]] = fut.result()

        for pod in failing:
            pod_name = pod["pod_name"]
            reason = pod["reason"]
            pod_status = pod["status"]
            error_logs = pod.get("error_logs", "No logs available")
            content = ai_results[pod_name]

            # Pod header card
            st.markdown(
                f'<div class="pod-header failing">'
                f'<div class="dot"></div>'
                f'<span class="pod-name">{pod_name}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Tabs for each analysis section
            tab_logs, tab_rca, tab_fix, tab_play = st.tabs([
                "📋 Log Evidence", "🧠 RCA", "💡 AI Prescription", "🛠️ Recovery Playbook"
            ])

            with tab_logs:
                st.markdown(
                    '<div class="section-label logs">🔍 Captured Signal — Log Evidence</div>',
                    unsafe_allow_html=True,
                )
                st.code(error_logs[:3000], language="log")

            with tab_rca:
                st.markdown(
                    '<div class="section-label rca">🧠 Intelligent RCA — AI-Powered Insights</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(content["ai_explanation"])

            with tab_fix:
                st.markdown(
                    f'<div class="section-label solution">💡 AI Prescription — {content["issue_category"]}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(content["ai_solution"])

            with tab_play:
                st.markdown(
                    '<div class="section-label playbook">🛠️ AI-Generated Recovery Playbook</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(content["action_guide"])

            st.markdown(
                f'<div class="analysis-footer">Analysed at {content["timestamp"]} · Model: {BEDROCK_MODEL}</div>',
                unsafe_allow_html=True,
            )
            st.markdown("")

    else:
        st.success("🎉 All pods healthy — no issues detected in this namespace.")

else:
    # ── Landing state ─────────────────────────────────────────────────
    st.markdown("")
    lc, mc, rc = st.columns([1, 2, 1])
    with mc:
        st.markdown("""
        <div style="text-align:center; padding:3rem 0;">
            <div style="font-size:4rem; margin-bottom:1rem;">☸️</div>
            <h3 style="opacity:0.8;">Ready to Analyse</h3>
            <p style="opacity:0.5;">Select a namespace and click <strong>⚡ Analyse Namespace</strong> to begin AI-powered diagnostics.</p>
        </div>
        """, unsafe_allow_html=True)
