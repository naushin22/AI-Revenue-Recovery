import streamlit as st
import pandas as pd
from models import get_session, Payment, Intervention, AuditLog
from audit_trail import get_trace

st.set_page_config(page_title="AI Revenue Recovery", layout="wide")
st.title("AI Revenue Recovery Agent")

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
col1.metric("Total at-risk amount", f"Rs {total_at_risk:,.0f}")
col2.metric("Recovered amount", f"Rs {recovered_amount:,.0f}")
col3.metric("Recovery rate", f"{recovery_rate:.1f}%")
col4.metric("Total payments processed", len(interventions))

# ---------- Outcome breakdown chart ----------
outcome_counts = pd.Series([i.outcome for i in interventions]).value_counts()
st.subheader("Outcomes by category")
st.bar_chart(outcome_counts)

# ---------- Failure type breakdown ----------
st.subheader("At-risk payments by failure type")
failure_counts = pd.Series([p.failure_code for p in payments]).value_counts()
st.bar_chart(failure_counts)

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
        st.markdown(f"**{entry['actor']}** -> `{entry['decision']}`  \n"
                    f"_{entry['rationale']}_  \n"
                    f"<span style='color:gray;font-size:12px'>{entry['timestamp']}</span>",
                    unsafe_allow_html=True)
        st.divider()

    st.markdown("#### Intervention outcome")
    for i in trace["interventions"]:
        st.write(f"**Action:** {i['action_type']} | **Confidence:** {i['confidence']} | **Outcome:** {i['outcome']}")
        st.write(f"**Reasoning:** {i['reason']}")

session.close()