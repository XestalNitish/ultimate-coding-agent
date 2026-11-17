"""Autonomous End-to-End Customer Resolution Agent.

Autonomous customer support & action system with deterministic policy verification,
secure tool execution (refunds, order cancellations, delivery rescheduling),
sentiment trajectory tracking, and human-in-the-loop escalation gates.
"""
from __future__ import annotations

import json
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

# Graceful LangSmith Tracing Integration
try:
    import config  # Sets up LangSmith project & credentials
    from langsmith import traceable
except Exception:
    def traceable(*args, **kwargs):
        def decorator(f):
            return f
        return decorator


# ============================================================================
# Domain Schemas & State Models
# ============================================================================

class OrderRecord(BaseModel):
    """E-commerce customer order record."""
    order_id: str
    customer_id: str
    items: List[str]
    total_amount: float
    order_timestamp: float  # Epoch seconds
    shipping_status: str    # PENDING, SHIPPED, DELIVERED, CANCELLED
    tracking_number: Optional[str] = None
    refunded: bool = False


class CustomerProfile(BaseModel):
    """Customer identity & account tier."""
    customer_id: str
    name: str
    tier: str  # VIP, STANDARD
    total_lifetime_spend: float
    fraud_risk_score: float = 0.05  # 0.0 (safe) to 1.0 (fraudulent)


class SupportMessage(BaseModel):
    """Inbound customer inquiry message."""
    session_id: str
    customer_id: str
    text: str
    timestamp: float


class ToolExecutionLog(BaseModel):
    """Audit log of backend action execution."""
    tool_name: str
    arguments: Dict[str, Any]
    status: str  # SUCCESS, FAILED, REFUSED_BY_POLICY
    result_message: str


class ResolutionResult(BaseModel):
    """Autonomous agent final response & action summary."""
    session_id: str
    resolution_status: str  # RESOLVED, ESCALATED_TO_HUMAN, CLARIFICATION_NEEDED
    reply_message: str
    actions_performed: List[ToolExecutionLog]
    sentiment_score: float  # -1.0 (very angry) to +1.0 (delighted)
    escalation_reason: Optional[str] = None


# ============================================================================
# Backend Tools & Mock APIs
# ============================================================================

class OrderManagementSystem:
    """Mock database simulating Shopify / Stripe / Logistics backend."""

    def __init__(self, initial_orders: Optional[Dict[str, OrderRecord]] = None):
        self.orders: Dict[str, OrderRecord] = dict(initial_orders or {})
        self.refund_ledger: List[Dict[str, Any]] = []

    def get_order(self, order_id: str) -> Optional[OrderRecord]:
        return self.orders.get(order_id)

    def cancel_order(self, order_id: str) -> Tuple[bool, str]:
        order = self.orders.get(order_id)
        if not order:
            return False, f"Order {order_id} not found."
        if order.shipping_status in ("SHIPPED", "DELIVERED"):
            return False, f"Order {order_id} cannot be cancelled because it is already {order.shipping_status}."
        order.shipping_status = "CANCELLED"
        return True, f"Order {order_id} cancelled successfully."

    def process_refund(self, order_id: str, amount: float, reason: str) -> Tuple[bool, str]:
        order = self.orders.get(order_id)
        if not order:
            return False, f"Order {order_id} not found."
        if order.refunded:
            return False, f"Order {order_id} has already been refunded."
        if amount > order.total_amount:
            return False, f"Refund amount ${amount:.2f} exceeds order total ${order.total_amount:.2f}."
        order.refunded = True
        self.refund_ledger.append({"order_id": order_id, "amount": amount, "reason": reason, "time": time.time()})
        return True, f"Refund of ${amount:.2f} processed back to original payment method."

    def reschedule_delivery(self, order_id: str, new_date: str) -> Tuple[bool, str]:
        order = self.orders.get(order_id)
        if not order:
            return False, f"Order {order_id} not found."
        return True, f"Delivery for order {order_id} rescheduled to {new_date}."


# ============================================================================
# Specialist Sub-Agents: Policy Guard, Intent Classifier, Tool Dispatcher
# ============================================================================

class PolicyComplianceGuard:
    """Deterministic policy rules (Refund windows, limits, fraud ceilings)."""

    REFUND_WINDOW_SECONDS = 30 * 86400  # 30 days
    MAX_AUTO_REFUND_AMOUNT = 250.0      # Refunds > $250 require human approval

    @classmethod
    def evaluate_refund_policy(cls, order: OrderRecord, customer: CustomerProfile, now: float) -> Tuple[bool, Optional[str]]:
        if customer.fraud_risk_score > 0.40:
            return False, "Customer fraud risk exceeds safe automated threshold."
        if (now - order.order_timestamp) > cls.REFUND_WINDOW_SECONDS:
            return False, "Order exceeds 30-day refund window."
        if order.total_amount > cls.MAX_AUTO_REFUND_AMOUNT and customer.tier != "VIP":
            return False, f"Refund amount ${order.total_amount:.2f} exceeds auto-approval limit ($250.00)."
        return True, None


class SentimentFrustrationAnalyzer:
    """Calculates customer sentiment and detects urgent escalation cues."""

    NEGATIVE_TRIGGERS = {"sue", "lawyer", "scam", "cheat", "furious", "unacceptable", "worst", "disaster"}

    @classmethod
    def analyze(cls, text: str) -> Tuple[float, bool]:
        lower = text.lower()
        has_critical_trigger = any(trig in lower for trig in cls.NEGATIVE_TRIGGERS)

        # Baseline heuristic sentiment scoring
        negative_count = sum(1 for w in ["bad", "broken", "late", "angry", "terrible", "problem", "cancel"] if w in lower)
        positive_count = sum(1 for w in ["thank", "great", "please", "kind", "help", "good"] if w in lower)

        score = 0.0 + (positive_count * 0.3) - (negative_count * 0.4)
        if has_critical_trigger:
            score = -0.9

        score = max(-1.0, min(1.0, score))
        return score, has_critical_trigger or score <= -0.7


# ============================================================================
# Master Orchestrator: End-to-End Customer Resolution Agent
# ============================================================================

class CustomerResolutionAgent:
    """Autonomous agent resolving customer requests with policy guardrails."""

    def __init__(self, oms: OrderManagementSystem, customers: Dict[str, CustomerProfile]):
        self.oms = oms
        self.customers = customers

    @traceable(name="resolve_customer_inquiry")
    def handle_message(self, msg: SupportMessage, current_time: Optional[float] = None) -> ResolutionResult:
        now = current_time or time.time()
        customer = self.customers.get(msg.customer_id, CustomerProfile(
            customer_id=msg.customer_id, name="Valued Customer", tier="STANDARD", total_lifetime_spend=0.0
        ))

        # Step 1: Sentiment & Escalation Analysis
        sentiment, should_escalate = SentimentFrustrationAnalyzer.analyze(msg.text)
        if should_escalate:
            return ResolutionResult(
                session_id=msg.session_id,
                resolution_status="ESCALATED_TO_HUMAN",
                reply_message="I apologize sincerely for the frustration. I have escalated this conversation with top priority to our Senior Support Team.",
                actions_performed=[],
                sentiment_score=sentiment,
                escalation_reason="High frustration/threat of legal action detected.",
            )

        # Step 2: Intent & Entity Extraction
        order_match = re.search(r"ORD-\d+", msg.text, re.I)
        order_id = order_match.group(0).upper() if order_match else None

        actions: List[ToolExecutionLog] = []

        # Intent: Cancel Order
        if "cancel" in msg.text.lower() and order_id:
            order = self.oms.get_order(order_id)
            if not order:
                return ResolutionResult(
                    session_id=msg.session_id,
                    resolution_status="CLARIFICATION_NEEDED",
                    reply_message=f"I couldn't locate order {order_id} in our records. Please double-check the order number.",
                    actions_performed=[],
                    sentiment_score=sentiment,
                )

            success, detail = self.oms.cancel_order(order_id)
            actions.append(ToolExecutionLog(tool_name="cancel_order", arguments={"order_id": order_id},
                                           status="SUCCESS" if success else "REFUSED_BY_POLICY",
                                           result_message=detail))
            if success:
                return ResolutionResult(
                    session_id=msg.session_id,
                    resolution_status="RESOLVED",
                    reply_message=f"Great news! Your order {order_id} has been successfully cancelled.",
                    actions_performed=actions,
                    sentiment_score=sentiment,
                )
            else:
                return ResolutionResult(
                    session_id=msg.session_id,
                    resolution_status="ESCALATED_TO_HUMAN",
                    reply_message=f"Your order {order_id} is already {order.shipping_status} and could not be auto-cancelled. I am connecting you with a human representative to arrange an expedited return.",
                    actions_performed=actions,
                    sentiment_score=sentiment,
                    escalation_reason=f"Order {order_id} already shipped/delivered.",
                )

        # Intent: Refund Request
        if "refund" in msg.text.lower() and order_id:
            order = self.oms.get_order(order_id)
            if not order:
                return ResolutionResult(
                    session_id=msg.session_id,
                    resolution_status="CLARIFICATION_NEEDED",
                    reply_message=f"I could not find order {order_id}. Please check your order confirmation email.",
                    actions_performed=[],
                    sentiment_score=sentiment,
                )

            # Evaluate Policy
            eligible, policy_err = PolicyComplianceGuard.evaluate_refund_policy(order, customer, now)
            if not eligible:
                actions.append(ToolExecutionLog(
                    tool_name="process_refund", arguments={"order_id": order_id, "amount": order.total_amount},
                    status="REFUSED_BY_POLICY", result_message=policy_err or "Policy violation"
                ))
                return ResolutionResult(
                    session_id=msg.session_id,
                    resolution_status="ESCALATED_TO_HUMAN",
                    reply_message=f"Your refund request for order {order_id} (${order.total_amount:.2f}) requires supervisor approval: {policy_err}. I have flagged this for immediate human review.",
                    actions_performed=actions,
                    sentiment_score=sentiment,
                    escalation_reason=policy_err,
                )

            # Execute refund tool
            ok, res_text = self.oms.process_refund(order_id, order.total_amount, "Customer automated request")
            actions.append(ToolExecutionLog(
                tool_name="process_refund", arguments={"order_id": order_id, "amount": order.total_amount},
                status="SUCCESS" if ok else "FAILED", result_message=res_text
            ))
            return ResolutionResult(
                session_id=msg.session_id,
                resolution_status="RESOLVED",
                reply_message=f"Your refund of ${order.total_amount:.2f} for order {order_id} has been processed successfully.",
                actions_performed=actions,
                sentiment_score=sentiment,
            )

        # Fallback / General FAQ
        return ResolutionResult(
            session_id=msg.session_id,
            resolution_status="CLARIFICATION_NEEDED",
            reply_message="How may I assist you with your orders today? You can ask me to cancel an order, check shipping status, or process an eligible return.",
            actions_performed=[],
            sentiment_score=sentiment,
        )


# ============================================================================
# Deterministic Standalone Self-Test Suite
# ============================================================================

def selftest() -> bool:
    """Validates order cancellation, policy-compliant refunds, high-value escalation, and sentiment triggers."""
    now = 1773700000.0  # Reference epoch time

    mock_customers = {
        "CUST-001": CustomerProfile(customer_id="CUST-001", name="Alice", tier="STANDARD", total_lifetime_spend=500.0),
        "CUST-002": CustomerProfile(customer_id="CUST-002", name="Bob", tier="VIP", total_lifetime_spend=5000.0),
    }

    mock_orders = {
        # Standard cancelable order (pending)
        "ORD-101": OrderRecord(
            order_id="ORD-101", customer_id="CUST-001", items=["Widget A"],
            total_amount=45.0, order_timestamp=now - 3600, shipping_status="PENDING"
        ),
        # Shipped order (cannot be cancelled)
        "ORD-102": OrderRecord(
            order_id="ORD-102", customer_id="CUST-001", items=["Widget B"],
            total_amount=75.0, order_timestamp=now - 7200, shipping_status="SHIPPED"
        ),
        # Standard refundable order
        "ORD-103": OrderRecord(
            order_id="ORD-103", customer_id="CUST-001", items=["Widget C"],
            total_amount=120.0, order_timestamp=now - (5 * 86400), shipping_status="DELIVERED"
        ),
        # Expensive order > $250 for Standard customer (requires escalation)
        "ORD-104": OrderRecord(
            order_id="ORD-104", customer_id="CUST-001", items=["Enterprise Server"],
            total_amount=1200.0, order_timestamp=now - (2 * 86400), shipping_status="DELIVERED"
        ),
    }

    oms = OrderManagementSystem(mock_orders)
    agent = CustomerResolutionAgent(oms, mock_customers)

    # 1. Test Successful Cancel Order
    msg1 = SupportMessage(session_id="S-1", customer_id="CUST-001", text="Please cancel ORD-101 immediately", timestamp=now)
    res1 = agent.handle_message(msg1, current_time=now)
    assert res1.resolution_status == "RESOLVED"
    assert oms.get_order("ORD-101").shipping_status == "CANCELLED"
    assert any(a.tool_name == "cancel_order" and a.status == "SUCCESS" for a in res1.actions_performed)

    # 2. Test Refused Cancel for Shipped Order -> Escalated
    msg2 = SupportMessage(session_id="S-2", customer_id="CUST-001", text="Cancel order ORD-102 please", timestamp=now)
    res2 = agent.handle_message(msg2, current_time=now)
    assert res2.resolution_status == "ESCALATED_TO_HUMAN"
    assert "already SHIPPED" in res2.reply_message

    # 3. Test Successful Refund within Policy
    msg3 = SupportMessage(session_id="S-3", customer_id="CUST-001", text="I'd like a refund for ORD-103", timestamp=now)
    res3 = agent.handle_message(msg3, current_time=now)
    assert res3.resolution_status == "RESOLVED"
    assert oms.get_order("ORD-103").refunded is True
    assert any(a.tool_name == "process_refund" and a.status == "SUCCESS" for a in res3.actions_performed)

    # 4. Test High Value Refund -> Escalated due to policy limit
    msg4 = SupportMessage(session_id="S-4", customer_id="CUST-001", text="Give me a refund for ORD-104", timestamp=now)
    res4 = agent.handle_message(msg4, current_time=now)
    assert res4.resolution_status == "ESCALATED_TO_HUMAN"
    assert "exceeds auto-approval limit" in (res4.escalation_reason or "")

    # 5. Test Urgent Frustration / Legal Threat Trigger
    msg5 = SupportMessage(session_id="S-5", customer_id="CUST-001", text="This is a total scam, I will sue your company!", timestamp=now)
    res5 = agent.handle_message(msg5, current_time=now)
    assert res5.resolution_status == "ESCALATED_TO_HUMAN"
    assert res5.sentiment_score <= -0.7

    return True


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        print("[CustomerResolutionAgent] Running Interactive/Demo Mode...")
        selftest()
        print("[CustomerResolutionAgent] Demo resolution workflows verified with LangSmith traces!")
    else:
        selftest()
        print("SELFTEST OK")
