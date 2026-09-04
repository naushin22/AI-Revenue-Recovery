from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

Base = declarative_base()


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    merchant_id = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False)          # failed, abandoned, recovered
    failure_code = Column(String, nullable=False)     # insufficient_funds, timeout, expired_card, otp_dropoff
    gateway_response = Column(String)
    customer_contact = Column(String)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    interventions = relationship("Intervention", back_populates="payment")


class Intervention(Base):
    __tablename__ = "interventions"

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    action_type = Column(String)         # retry_link, escalate, skip, sms_nudge
    reason = Column(String)              # root cause from diagnosis agent
    confidence = Column(Float)
    decided_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)
    outcome = Column(String, nullable=True)   # recovered, no_response, failed_again
    cost = Column(Float, default=0.0)

    payment = relationship("Payment", back_populates="interventions")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String)   # "payment" or "intervention"
    entity_id = Column(Integer)
    actor = Column(String)         # "detector_agent", "diagnosis_agent", "policy_gate", "recovery_agent"
    decision = Column(String)      # "flagged", "diagnosed", "gate_pass", "gate_block", "executed"
    rationale = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)


def get_session(db_path="sqlite:///revenue_recovery.db"):
    engine = create_engine(db_path)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()