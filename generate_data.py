import random
from datetime import datetime, timedelta
from models import get_session, Payment

random.seed(42)

MERCHANTS = ["merchant_A", "merchant_B", "merchant_C"]

FAILURE_PROFILES = {
    "insufficient_funds": {
        "gateway_responses": ["Insufficient balance in account", "Funds unavailable"],
        "weight": 0.30,
    },
    "bank_timeout": {
        "gateway_responses": ["Gateway timeout - no response from issuer", "Request timed out"],
        "weight": 0.25,
    },
    "expired_card": {
        "gateway_responses": ["Card expired", "Invalid expiry date"],
        "weight": 0.20,
    },
    "otp_dropoff": {
        "gateway_responses": ["OTP not entered", "3DS authentication abandoned"],
        "weight": 0.25,
    },
}


def weighted_failure_code():
    codes = list(FAILURE_PROFILES.keys())
    weights = [FAILURE_PROFILES[c]["weight"] for c in codes]
    return random.choices(codes, weights=weights, k=1)[0]


def generate_batch(n=60):
    session = get_session()

    for i in range(n):
        failure_code = weighted_failure_code()
        profile = FAILURE_PROFILES[failure_code]
        gateway_response = random.choice(profile["gateway_responses"])

        days_ago = random.randint(0, 14)
        created_at = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))

        payment = Payment(
            merchant_id=random.choice(MERCHANTS),
            amount=round(random.uniform(199, 15000), 2),
            status=random.choice(["failed", "failed", "abandoned"]),  # failed more common
            failure_code=failure_code,
            gateway_response=gateway_response,
            customer_contact=f"customer_{i}@example.com",
            retry_count=random.choices([0, 1, 2, 3], weights=[0.5, 0.3, 0.15, 0.05])[0],
            created_at=created_at,
        )
        session.add(payment)

    session.commit()
    print(f"Generated {n} synthetic payment records.")
    session.close()


if __name__ == "__main__":
    generate_batch(60)