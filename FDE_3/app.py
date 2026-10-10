from __future__ import annotations

import json
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Load local environment variables (.env)
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)

from src import data_access
from src.contracts import ProcurementDecision
from src.solution import handle_request

# Page configuration
st.set_page_config(
    page_title="AI Procurement Copilot",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Load synthetic business requests
REQUESTS = data_access.load_requests()
BY_ID = {r["request_id"]: r for r in REQUESTS}
EMPLOYEES = {r["employee_id"]: r for r in data_access.load_employees().to_dict(orient="records")}
BUDGETS = {r["department"]: r for r in data_access.load_budgets().to_dict(orient="records")}

# Custom CSS for styling
st.markdown(
    """
    <style>
    .main-title { font-size: 2.1rem; font-weight: 700; color: #1e293b; margin-bottom: 0.2rem; }
    .sub-title { font-size: 0.95rem; color: #64748b; margin-bottom: 1.5rem; }
    .card { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600; margin-right: 4px; }
    .badge-info { background-color: #e0f2fe; color: #0369a1; }
    .badge-warn { background-color: #fef3c7; color: #b45309; }
    .badge-danger { background-color: #fee2e2; color: #b91c1c; }
    .badge-success { background-color: #dcfce7; color: #15803d; }
    .badge-purple { background-color: #f3e8ff; color: #7e22ce; }
    .telemetry-chip { font-family: monospace; font-size: 0.85rem; padding: 4px 8px; background: #f1f5f9; border-radius: 6px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Header
st.markdown('<div class="main-title">📋 AI Procurement Request Copilot</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Intelligent evidence gathering, deterministic compliance validation, and structured human-in-the-loop escalation. Snapshot date: <b>2026-09-30</b>.</div>',
    unsafe_allow_html=True,
)

# Sidebar controls
st.sidebar.header("Navigation & Configuration")
request_id = st.sidebar.selectbox(
    "Select Purchase Request",
    list(BY_ID.keys()),
    format_func=lambda rid: f"{rid} - {BY_ID[rid].get('product_name', 'Unknown')}",
)

architecture = st.sidebar.radio(
    "Agent Architecture",
    options=["single", "staged"],
    format_func=lambda a: "Architecture A: Single Agent Baseline" if a == "single" else "Architecture B: Staged (2-Agent Pipeline)",
    help="Compare Single-Agent Baseline with the 2-Agent Analyst + Reviewer pipeline.",
)

req = BY_ID[request_id]
emp = EMPLOYEES.get(req.get("requester_id", ""), {})
dept_name = emp.get("department", "Unknown")
bgt = BUDGETS.get(dept_name, {})

st.sidebar.divider()
st.sidebar.caption("System Principles:")
st.sidebar.caption("🤖 **AI**: Interprets context & synthesizes advice")
st.sidebar.caption("⚙️ **Code**: Enforces deterministic thresholds & policies")
st.sidebar.caption("👤 **Human**: Approves exceptions & sensitive actions")

# Main layout
left, right = st.columns([1.05, 0.95], gap="large")

with left:
    st.subheader("1. Purchase Request Details")
    
    # Requester info card
    with st.container(border=True):
        st.markdown(f"**Requester:** {emp.get('name', 'Unknown')} (`{req.get('requester_id')}`)")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Department:** {dept_name}")
            st.markdown(f"**Role / Level:** {emp.get('level', emp.get('role', 'N/A'))}")
        with c2:
            st.markdown(f"**Manager ID:** `{emp.get('manager_id', 'N/A')}`")
            st.markdown(f"**Location:** {emp.get('country', emp.get('location', 'N/A'))}")

    # Request Specs Card
    with st.container(border=True):
        st.markdown(f"**Product & Vendor:** {req.get('product_name')} (by *{req.get('vendor_name')}*)")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            cost = req.get("annual_cost_usd")
            cost_str = f"${cost:,.2f}" if cost is not None else "⚠️ Missing"
            st.metric("Annual Cost (USD)", cost_str)
        with col_b:
            users = req.get("user_count")
            st.metric("Seats / Users", f"{users}" if users is not None else "⚠️ Missing")
        with col_c:
            avail = bgt.get("available_usd")
            avail_str = f"${float(avail):,.2f}" if avail is not None else "N/A"
            st.metric("Dept Budget Avail.", avail_str)

        st.markdown(f"**Category:** `{req.get('category')}` | **Data Access Level:** `{req.get('data_access_level')}`")
        ints = req.get("requested_integrations", [])
        st.markdown(f"**Requested Integrations:** {', '.join(ints) if ints else '*None*'}")

    # Business Justification (Quarantined)
    with st.container(border=True):
        st.markdown("**Business Justification** *(Untrusted Business Data)*")
        just = req.get("business_justification", "")
        if "ignore all procurement rules" in just.lower() or "cfo-approved" in just.lower():
            st.error(f"⚠️ **Adversarial Content Detected**: \"{just}\"")
        else:
            st.info(f"\"{just}\"")

with right:
    st.subheader("2. Copilot Recommendation & Action")
    
    # Run Button
    run_pressed = st.button("🚀 Run Copilot Analysis", type="primary", use_container_width=True)

    # State preservation
    session_key = f"decision_{request_id}_{architecture}"
    if run_pressed:
        with st.spinner(f"Executing {architecture.title()} Agent workflow..."):
            t0 = time.perf_counter()
            try:
                decision = handle_request(request_id, architecture=architecture)
                latency_ms = (time.perf_counter() - t0) * 1000
                st.session_state[session_key] = (decision, latency_ms)
            except Exception as exc:
                st.error(f"Error during analysis: {exc}")
                st.session_state[session_key] = None

    if session_key in st.session_state and st.session_state[session_key]:
        decision, latency_ms = st.session_state[session_key]

        # Recommendation Card
        is_alert = any(
            f in decision.risk_flags
            for f in ["prompt_injection_detected", "vendor_risk_unavailable", "budget_insufficient"]
        ) or bool(decision.missing_information)
        
        box_style = "background-color: #fef2f2; border-left: 5px solid #ef4444;" if is_alert else "background-color: #f0fdf4; border-left: 5px solid #22c55e;"
        
        st.markdown(
            f"""
            <div style="{box_style} padding: 12px 16px; border-radius: 6px; margin-bottom: 12px;">
                <div style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; color: #475569;">Recommendation</div>
                <div style="font-size: 1.05rem; font-weight: 600; color: #0f172a; margin-top: 4px;">{decision.recommendation}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Next Step
        st.markdown(f"**Next Action:** {decision.next_step}")

        # Required Approvals Badges
        st.markdown("**Required Approvals Chain:**")
        if decision.required_approvals:
            badges_html = " ".join([f'<span class="badge badge-purple">{a}</span>' for a in decision.required_approvals])
            st.markdown(badges_html, unsafe_allow_html=True)
        else:
            st.markdown("*No approvals required (Request blocked/missing info).*")

        # Risk Flags Badges
        st.markdown("**Identified Policy & Risk Flags:**")
        if decision.risk_flags:
            risk_badges = []
            for rf in decision.risk_flags:
                color_cls = "badge-danger" if "injection" in rf or "unavailable" in rf or "insufficient" in rf else "badge-warn"
                risk_badges.append(f'<span class="badge {color_cls}">{rf}</span>')
            st.markdown(" ".join(risk_badges), unsafe_allow_html=True)
        else:
            st.markdown('<span class="badge badge-success">No high risks detected</span>', unsafe_allow_html=True)

        # Missing Information Alert
        if decision.missing_information:
            st.warning(f"**Missing Information:** {', '.join(decision.missing_information)}")

        # Telemetry Bar
        tel = decision.telemetry
        llm_count = tel.llm_calls if tel else 0
        tool_count = tel.tool_calls if tel else 0
        st.markdown(
            f"""
            <div style="margin-top: 10px; font-size: 0.85rem; color: #64748b;">
                ⚡ <b>Latency:</b> {latency_ms:.0f} ms | 🤖 <b>LLM Calls:</b> {llm_count} | 🔧 <b>Tools:</b> {tool_count} ({', '.join(tel.tool_names if tel else [])})
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        # Human Action Panel
        st.markdown("**👤 Human Procurement Reviewer Actions:**")
        act_col1, act_col2, act_col3 = st.columns(3)
        with act_col1:
            if st.button("✅ Approve & Route", use_container_width=True):
                st.success(f"Request {request_id} approved for routing to {decision.required_approvals[0] if decision.required_approvals else 'Procurement'}.")
        with act_col2:
            if st.button("✉️ Request Clarification", use_container_width=True):
                st.info(f"Clarification request sent to {emp.get('name', 'Requester')}.")
        with act_col3:
            if st.button("🛑 Escalate to Human", use_container_width=True):
                st.warning(
                    f"Demo only: {request_id} marked for human review. "
                     "No external escalation was sent.")

    else:
        st.info("Click **Run Copilot Analysis** to evaluate this request against business data and procurement policies.")

st.divider()

# Evidence & Audit Trail Panel
st.subheader("3. Gathered Evidence & Audit Trail")

if session_key in st.session_state and st.session_state[session_key]:
    decision, _ = st.session_state[session_key]
    
    tab1, tab2 = st.tabs(["Evidence Items", "Raw JSON Contract"])
    
    with tab1:
        st.caption(f"Total evidence items gathered: {len(decision.evidence)}")
        for idx, item in enumerate(decision.evidence, 1):
            with st.container(border=True):
                c_head, c_ref = st.columns([0.7, 0.3])
                with c_head:
                    st.markdown(f"**#{idx} [{item.source.upper()}]**")
                with c_ref:
                    st.markdown(f"*Ref: {item.reference or 'N/A'}*")
                st.write(item.finding)
                
    with tab2:
        st.json(decision.model_dump())
else:
    st.caption("Evidence will be populated here after analysis.")

st.divider()
st.caption("⚠️ AI Procurement Copilot is advisory. Purchasing, payment, and budget modification authority rests solely with authorized human personnel.")
