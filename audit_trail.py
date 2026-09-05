from models import get_session, Payment, Intervention, AuditLog


def get_trace(payment_id):
    """
    Returns the full decision chain for one payment:
    the payment itself, its interventions, and every audit log entry
    tied to the payment or its interventions -- in chronological order.
    """
    session = get_session()

    payment = session.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        session.close()
        return None

    interventions = session.query(Intervention).filter(
        Intervention.payment_id == payment_id
    ).all()
    intervention_ids = [i.id for i in interventions]

    payment_logs = session.query(AuditLog).filter(
        AuditLog.entity_type == "payment",
        AuditLog.entity_id == payment_id,
    ).all()

    intervention_logs = session.query(AuditLog).filter(
        AuditLog.entity_type == "intervention",
        AuditLog.entity_id.in_(intervention_ids) if intervention_ids else False,
    ).all()

    all_logs = sorted(payment_logs + intervention_logs, key=lambda l: l.timestamp)

    trace = {
        "payment": {
            "id": payment.id,
            "merchant_id": payment.merchant_id,
            "amount": payment.amount,
            "status": payment.status,
            "failure_code": payment.failure_code,
            "gateway_response": payment.gateway_response,
            "retry_count": payment.retry_count,
            "created_at": payment.created_at,
        },
        "interventions": [
            {
                "id": i.id,
                "action_type": i.action_type,
                "reason": i.reason,
                "confidence": i.confidence,
                "outcome": i.outcome,
            }
            for i in interventions
        ],
        "log": [
            {
                "actor": l.actor,
                "decision": l.decision,
                "rationale": l.rationale,
                "timestamp": l.timestamp,
            }
            for l in all_logs
        ],
    }

    session.close()
    return trace


def print_trace(payment_id):
    trace = get_trace(payment_id)
    if trace is None:
        print(f"No payment found with id={payment_id}")
        return

    p = trace["payment"]
    print(f"\n=== Payment {p['id']} ===")
    print(f"Merchant: {p['merchant_id']} | Amount: {p['amount']} | Status: {p['status']}")
    print(f"Failure code: {p['failure_code']} | Gateway response: {p['gateway_response']}")
    print(f"Retry count: {p['retry_count']} | Created: {p['created_at']}")

    print("\n--- Decision chain ---")
    for entry in trace["log"]:
        print(f"[{entry['timestamp']}] {entry['actor']} -> {entry['decision']}")
        print(f"    reason: {entry['rationale']}")

    print("\n--- Interventions ---")
    for i in trace["interventions"]:
        print(f"  action={i['action_type']} | confidence={i['confidence']} | outcome={i['outcome']}")
        print(f"  reason: {i['reason']}")


if __name__ == "__main__":
    import sys
    pid = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print_trace(pid)