import streamlit as st
import pandas as pd
from models import get_session, Payment, Intervention, AuditLog
from audit_trail import get_trace

st.set_page_config(page_title="Revenue Recovery Console", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.stApp { background-color: #0B0E14; }

section[data-testid="stSidebar"] {
    background-color: #10141C;
    border-right: 1px solid #1E2530;
}

h1, h2, h3 { color: #E8EAED !important; font-weight: 600 !important; letter-spacing: -0.01em; }
h1 { font-size: 1.6rem !important; border-bottom: 1px solid #1E2530; padding-bottom: 0.75rem; }
h2 { font-size: 1.05rem !important; margin-top: 2rem !important; color: #9CA3AF !important; text-transform: none; }

p, li, span, div { color: #C7CBD1; }

/* Ledger-style metric strip */
div[data-testid="stMetric"] {
    background-color: #141922;
    border: 1px solid #1E2530;
    border-left: 3px solid #2D3440;
    border-radius: 4px;
    padding: 14px 18px;
}
div[data-testid="stMetricLabel"] { color: #7A8290 !important; font-size: 0.78rem !important; text-transform: uppercase; letter-spacing: 0.04em; }
div[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-variant-numeric: tabular-nums;
    color: #E8EAED !important;
    font-size: 1.35rem !important;
    white-space: nowrap;
    overflow: visible;
}

/* Dataframe / table */
div[data-testid="stDataFrame"] { border: 1px solid #1E2530; border-radius: 4px; }

/* Divider hairlines instead of big gaps */
hr { border-color: #1E2530 !important; margin: 1.2rem 0 !important; }

/* Selectbox */
div[data-baseweb="select"] > div {
    background-color: #141922 !important;
    border-color: #2D3440 !important;
}

/* Buttons */
.stButton > button {
    background-color: #141922;
    color: #E8EAED;
    border: 1px solid #2D3440;
    border-radius: 4px;
    font-weight: 500;
}
.stButton > button:hover { border-color: #4ADE80; color: #4ADE80; }

/* Decision chain entries -- monospace actor tags */
.decision-actor { font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; color: #9CA3AF; }
.decision-tag-pass { color: #4ADE80; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; background: rgba(74,222,128,0.1); padding: 2px 8px; border-radius: 3px; }
.decision-tag-block { color: #F59E0B; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; background: rgba(245,158,11,0.1); padding: 2px 8px; border-radius: 3px; }
.decision-rationale { color: #C7CBD1; font-size: 0.9rem; font-style: italic; margin: 4px 0; }
.decision-time { color: #545B66; font-size: 0.75rem; font-family: 'JetBrains Mono', monospace; }
.trace-divider { border: none; border-top: 1px solid #1E2530; margin: 12px 0; }

.eyebrow { color: #545B66; font-size: 0.75rem; letter-spacing: 0.03em; margin-bottom: -0.5rem; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="eyebrow">AI REVENUE RECOVERY</p>', unsafe_allow_html=True)
st.title("Recovery Console")

session = get_session()

# ---------- Sidebar: run batch ----------
st.sidebar.header("Batch control")
if st.sidebar.button("Run batch now (calls Gemini, ~2-3 min)"):
    from batch_runner import run_batch
    with st.spinner("Running detect -> diagnose -> gate -> act pipeline..."):
        run_batch()
    st.sidebar.success("Batch complete. Refresh below.")

# ---------- Overview metrics ----------
st.header("Batch overview")

payments = session.query(Payment).all()
interventions = session.query(Intervention).all()

total_at_risk = sum(p.amount for p in payments if p.status in ("failed", "abandoned"))
recovered_amount = sum(
    i.payment.amount for i in interventions if i.outcome == "recovered"
)
recovery_rate = (recovered_amount / total_at_risk * 100) if total_at_risk > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("At-risk amount", f"Rs {total_at_risk:,.0f}")
col2.metric("Recovered", f"Rs {recovered_amount:,.0f}")
col3.metric("Recovery rate", f"{recovery_rate:.1f}%")
col4.metric("Payments processed", len(interventions))

# ---------- Outcome breakdown chart ----------
st.header("Outcomes by category")
outcome_counts = pd.Series([i.outcome for i in interventions]).value_counts()
chart_df = outcome_counts.reset_index()
chart_df.columns = ["outcome", "count"]
# Pivot so each outcome is its own column -- lets st.bar_chart assign a distinct color per series
pivoted = pd.DataFrame({row["outcome"]: [row["count"]] for _, row in chart_df.iterrows()})
pivoted = pivoted.rename(columns={"pending_human_review": "escalated"})
outcome_color_map = {
    "recovered": "#4ADE80",
    "no_response": "#EF4444",
    "escalated": "#F59E0B",
    "skipped": "#545B66",
}
colors = [outcome_color_map.get(col, "#7A8290") for col in pivoted.columns]
st.bar_chart(pivoted, color=colors, height=280)

# ---------- Failure type breakdown ----------
st.header("At-risk payments by failure type")
failure_counts = pd.Series([p.failure_code for p in payments]).value_counts()
failure_df = failure_counts.reset_index()
failure_df.columns = ["failure_code", "count"]
st.bar_chart(failure_df.set_index("failure_code"), color="#F59E0B", height=280)

# ---------- Exceptions list (escalated / unresolved) ----------
st.header("Exceptions -- could not auto-resolve")
escalated = [i for i in interventions if i.outcome == "pending_human_review"]
if escalated:
    exc_data = [
        {
            "payment_id": i.payment_id,
            "amount": i.payment.amount,
            "action": i.action_type,
            "reason": i.reason,
            "confidence": i.confidence,
        }
        for i in escalated
    ]
    st.dataframe(pd.DataFrame(exc_data), use_container_width=True)
else:
    st.write("No escalations in current batch.")

# ---------- Audit trail viewer ----------
st.header("Audit trail viewer")
st.write("Select a payment to see its full decision chain: detected, diagnosed, gated, acted.")

payment_ids = [p.id for p in payments]
selected_id = st.selectbox("Payment ID", payment_ids)

if selected_id:
    trace = get_trace(selected_id)
    p = trace["payment"]

    st.subheader(f"Payment {p['id']} -- {p['merchant_id']}")
    st.write(f"**Amount:** Rs {p['amount']:,.2f} | **Status:** {p['status']} | **Failure code:** {p['failure_code']}")
    st.write(f"**Gateway response:** {p['gateway_response']} | **Retry count:** {p['retry_count']}")

    st.markdown("#### Decision chain")
    for entry in trace["log"]:
        tag_class = "decision-tag-pass" if entry["decision"] in ("flagged", "diagnosed", "gate_pass", "executed") else "decision-tag-block"
        st.markdown(
            f"<span class='decision-actor'>{entry['actor']}</span> &rarr; "
            f"<span class='{tag_class}'>{entry['decision']}</span><br>"
            f"<span class='decision-rationale'>{entry['rationale']}</span><br>"
            f"<span class='decision-time'>{entry['timestamp']}</span>",
            unsafe_allow_html=True
        )
        st.markdown("<hr class='trace-divider'>", unsafe_allow_html=True)

    st.markdown("#### Intervention outcome")
    for i in trace["interventions"]:
        st.write(f"**Action:** {i['action_type']} | **Confidence:** {i['confidence']} | **Outcome:** {i['outcome']}")
        st.write(f"**Reasoning:** {i['reason']}")

session.close()