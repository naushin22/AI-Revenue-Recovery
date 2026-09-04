import time
from datetime import datetime
from models import get_session, Payment, Intervention, AuditLog
from diagnosis_agent import diagnose_payment
from policy_gate import evaluate_gate

# Free-tier limits vary by model; 2s spacing is safe for higher-RPM Flash-Lite models
SECONDS_BETWEEN_CALLS = 2


def log(session, entity_type, entity_id, actor, decision, rationale):
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        decision=decision,
        rationale=rationale,
        timestamp=datetime.utcnow(),
    )
    session.add(entry)


def execute_action(action_type, payment):
    """
    Simulated execution -- in a real build this would call Razorpay Payment Links API,
    send an SMS/email, etc. For the hackathon, we simulate outcomes probabilistically
    so the batch produces realistic recovered/failed results.
    """
    import random
    if action_type == "retry_link":
        return "recovered" if random.random() < 0.35 else "no_response"
    if action_type == "sms_nudge":
        return "recovered" if random.random() < 0.25 else "no_response"
    if action_type == "escalate_human":
        return "pending_human_review"
    if action_type == "skip_no_action":
        return "skipped"
    return "unknown_action"


def run_batch():
    session = get_session()

    at_risk_payments = session.query(Payment).filter(
        Payment.status.in_(["failed", "abandoned"])
    ).all()

    print(f"Detected {len(at_risk_payments)} at-risk payments.\n")

    results = {
        "recovered": 0,
        "no_response": 0,
        "escalated": 0,
        "skipped": 0,
        "recovered_amount": 0.0,
        "total_at_risk_amount": 0.0,
    }

    for payment in at_risk_payments:
        results["total_at_risk_amount"] += payment.amount

        log(session, "payment", payment.id, "detector_agent", "flagged",
            f"status={payment.status}, failure_code={payment.failure_code}")

        payment_dict = {
            "amount": payment.amount,
            "failure_code": payment.failure_code,
            "gateway_response": payment.gateway_response,
            "retry_count": payment.retry_count,
        }
        diagnosis = diagnose_payment(payment_dict)
        time.sleep(SECONDS_BETWEEN_CALLS)

        log(session, "payment", payment.id, "diagnosis_agent", "diagnosed",
            f"root_cause={diagnosis['root_cause']}, confidence={diagnosis['confidence']}, "
            f"recommended={diagnosis['recommended_action']}, reasoning={diagnosis['reasoning']}")

        gate_result = evaluate_gate(payment_dict, diagnosis, last_intervention_time=None)

        gate_decision = "gate_pass" if gate_result["allowed"] else "gate_block"
        log(session, "payment", payment.id, "policy_gate", gate_decision, gate_result["gate_reason"])

        outcome = execute_action(gate_result["final_action"], payment)

        intervention = Intervention(
            payment_id=payment.id,
            action_type=gate_result["final_action"],
            reason=diagnosis["reasoning"],
            confidence=diagnosis["confidence"],
            decided_at=datetime.utcnow(),
            executed_at=datetime.utcnow(),
            outcome=outcome,
            cost=0.0,
        )
        session.add(intervention)
        session.flush()

        log(session, "intervention", intervention.id, "recovery_agent", "executed",
            f"action={gate_result['final_action']}, outcome={outcome}")

        if outcome == "recovered":
            results["recovered"] += 1
            results["recovered_amount"] += payment.amount
        elif outcome == "no_response":
            results["no_response"] += 1
        elif outcome == "pending_human_review":
            results["escalated"] += 1
        elif outcome == "skipped":
            results["skipped"] += 1

        print(f"Payment {payment.id} | {payment.failure_code} | "
              f"cause={diagnosis['root_cause']} (conf={diagnosis['confidence']}) | "
              f"gate={gate_decision} | action={gate_result['final_action']} | outcome={outcome}")

    session.commit()

    print("\n--- Batch summary ---")
    print(f"Total at-risk amount: {results['total_at_risk_amount']:.2f}")
    print(f"Recovered: {results['recovered']} payments, {results['recovered_amount']:.2f} amount")
    print(f"No response: {results['no_response']}")
    print(f"Escalated to human: {results['escalated']}")
    print(f"Skipped (cooldown): {results['skipped']}")
    recovery_rate = (results['recovered_amount'] / results['total_at_risk_amount'] * 100) if results['total_at_risk_amount'] > 0 else 0
    print(f"Recovery rate: {recovery_rate:.1f}%")

    session.close()
    return results


if __name__ == "__main__":
    run_batch()