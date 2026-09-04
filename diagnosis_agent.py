import os
import json
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

DIAGNOSIS_SYSTEM_PROMPT = """You are a payment failure diagnosis agent for an Indian merchant platform.
Given details about a failed or abandoned payment, determine the root cause and recommend ONE action.

Respond ONLY with valid JSON, no markdown, no preamble, in this exact schema:
{
  "root_cause": "one of: insufficient_funds | bank_timeout | expired_card | otp_dropoff | unknown",
  "confidence": 0.0 to 1.0,
  "recommended_action": "one of: retry_link | sms_nudge | escalate_human | skip_no_action",
  "reasoning": "one short sentence explaining why"
}

Guidance:
- insufficient_funds -> recommend retry_link (customer may have funds later) but lower confidence if retry_count is already high
- bank_timeout -> recommend retry_link, usually transient
- expired_card -> recommend sms_nudge (ask customer to update card), retry_link won't help
- otp_dropoff -> recommend sms_nudge (reminder to complete authentication)
- if retry_count >= 3, recommend escalate_human regardless of cause (avoid annoying the customer)
- if gateway_response is ambiguous or doesn't match known patterns, use root_cause "unknown" with confidence <= 0.4 and recommend escalate_human
"""


def call_with_retry(user_input, max_retries=5):
    """
    Free tier allows 5 requests/minute. On a 429, wait and retry
    rather than crashing the whole batch.
    """
    for attempt in range(max_retries):
        try:
            return client.interactions.create(
                model=MODEL_NAME,
                system_instruction=DIAGNOSIS_SYSTEM_PROMPT,
                input=user_input,
            )
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "RateLimitError" in error_str or "quota" in error_str.lower():
                wait_time = 30 + (attempt * 30)  # escalating backoff: 30s, 60s, 90s...
                print(f"  Rate limited, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                raise
    raise RuntimeError("Max retries exceeded due to rate limiting.")


def diagnose_payment(payment):
    """
    payment: dict with keys - amount, failure_code, gateway_response, retry_count
    Returns parsed dict matching the schema above.
    """
    user_input = f"""Payment details:
- Amount: {payment['amount']}
- Failure code (from system): {payment['failure_code']}
- Gateway response: {payment['gateway_response']}
- Retry count so far: {payment['retry_count']}
"""

    interaction = call_with_retry(user_input)

    raw_text = interaction.output_text.strip()

    # Defensive parsing: strip markdown fences if the model adds them anyway
    if raw_text.startswith("```"):
        raw_text = raw_text.strip("`")
        if raw_text.startswith("json"):
            raw_text = raw_text[4:].strip()

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # Fail-safe: if parsing fails, escalate rather than crash the batch
        result = {
            "root_cause": "unknown",
            "confidence": 0.0,
            "recommended_action": "escalate_human",
            "reasoning": "Diagnosis agent output could not be parsed; escalating for safety.",
        }

    return result


if __name__ == "__main__":
    # quick manual test
    sample = {
        "amount": 2499.0,
        "failure_code": "otp_dropoff",
        "gateway_response": "3DS authentication abandoned",
        "retry_count": 0,
    }
    print(json.dumps(diagnose_payment(sample), indent=2))