"""Pytest validation suite for the 5 Real-World Problem Solving AI Agents.

Tests:
1. SWE Bug Resolver & PR Reviewer Agent
2. B2B Invoice & Expense Audit Agent
3. Deep Research & Competitive Intelligence Agent
4. End-to-End Customer Resolution Agent
5. Clinical Doctor's Co-pilot & Patient Care Agent
"""
import pytest
from output.swe_bug_resolver_agent import selftest as _swe_selftest
from output.invoice_audit_agent import selftest as _invoice_selftest
from output.deep_research_agent import selftest as _research_selftest
from output.customer_resolution_agent import selftest as _customer_selftest
from output.clinical_copilot_agent import selftest as _clinical_selftest


def test_01_swe_bug_resolver_agent():
    """Verify triage, AST patch validation, sandbox test runner, and PR synthesis."""
    assert _swe_selftest() is True


def test_02_invoice_audit_agent():
    """Verify 3-way matching, duplicate detection, and dispute resolution."""
    assert _invoice_selftest() is True


def test_03_deep_research_agent():
    """Verify query planning, crawler gathering, fact-checking, and markdown report."""
    assert _research_selftest() is True


def test_04_customer_resolution_agent():
    """Verify policy compliance, tool execution (refund/cancel), and sentiment triggers."""
    assert _customer_selftest() is True


def test_05_clinical_copilot_agent():
    """Verify SOAP clinical notes, drug-drug conflicts, and patient follow-up scheduling."""
    assert _clinical_selftest() is True
