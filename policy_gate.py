from datetime import datetime, timedelta

# --- Policy constants (tune these, and mention them explicitly in your demo) ---
MAX_RETRY_COUNT = 3
MIN_CONFIDENCE_TO_ACT = 0.5
MAX_AUTO_ACTION_AMOUNT = 10000.0       # above this, always escalate to human
COOLDOWN_HOURS = 6                      # don't re-contact same customer within this window


def evaluate_gate(payment, diagnosis, last_intervention_time=None):
    """
    payment: dict with amount, retry_count, created_at
    diagnosis: dict from diagnosis_agent (root_cause, confidence, recommended_action, reasoning)
    last_intervention_time: datetime of last action taken on this payment, or None

    Returns: dict with keys - allowed (bool), final_action (str), gate_reason (str)
    This is pure code -- no LLM call here. Every check is independently auditable.
    """
    # Check 1: retry count ceiling
    if payment["retry_count"] >= MAX_RETRY_COUNT:
        return {
            "allowed": False,
            "final_action": "escalate_human",
            "gate_reason": f"retry_count ({payment['retry_count']}) >= max allowed ({MAX_RETRY_COUNT})",
        }

    # Check 2: confidence floor
    if diagnosis["confidence"] < MIN_CONFIDENCE_TO_ACT:
        return {
            "allowed": False,
            "final_action": "escalate_human",
            "gate_reason": f"confidence ({diagnosis['confidence']}) below threshold ({MIN_CONFIDENCE_TO_ACT})",
        }

    # Check 3: high-value payments require human approval
    if payment["amount"] > MAX_AUTO_ACTION_AMOUNT:
        return {
            "allowed": False,
            "final_action": "escalate_human",
            "gate_reason": f"amount ({payment['amount']}) exceeds auto-action cap ({MAX_AUTO_ACTION_AMOUNT})",
        }

    # Check 4: cooldown window
    if last_intervention_time is not None:
        elapsed = datetime.utcnow() - last_intervention_time
        if elapsed < timedelta(hours=COOLDOWN_HOURS):
            return {
                "allowed": False,
                "final_action": "skip_no_action",
                "gate_reason": f"within cooldown window ({elapsed} < {COOLDOWN_HOURS}h since last attempt)",
            }

    # Check 5: root cause "unknown" always escalates regardless of confidence trick
    if diagnosis["root_cause"] == "unknown":
        return {
            "allowed": False,
            "final_action": "escalate_human",
            "gate_reason": "root_cause could not be determined",
        }

    # All checks passed -- allow the diagnosis agent's recommended action
    return {
        "allowed": True,
        "final_action": diagnosis["recommended_action"],
        "gate_reason": "passed all policy checks",
    }