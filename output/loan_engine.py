"""Financial EMI, amortization, DTI risk, and prepayment engine using standard library only."""

import sys
from decimal import Decimal, ROUND_HALF_UP


class EMICalculator:
    """Calculates monthly EMI payments using Decimal arithmetic for penny accuracy."""

    def __init__(self, principal: Decimal, annual_rate: Decimal, monthly_payment_periods: int):
        self.principal = Decimal(str(principal))
        self.annual_rate = Decimal(str(annual_rate))
        self.monthly_payment_periods = int(monthly_payment_periods)
        self.monthly_rate = self.annual_rate / Decimal(12)

    def calculate_emi(self) -> Decimal:
        """Calculate the monthly EMI payment with exact Decimal precision."""
        r = self.monthly_rate
        n = self.monthly_payment_periods
        if r == 0:
            return (self.principal / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        num = self.principal * r
        den = Decimal(1) - (Decimal(1) + r) ** Decimal(-n)
        return (num / den).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class AmortizationSchedule:
    """Generates a full amortization schedule with month, payment, principal, interest, and remaining balance."""

    def __init__(self, principal: Decimal, annual_rate: Decimal, monthly_payment_periods: int):
        self.principal = Decimal(str(principal))
        self.annual_rate = Decimal(str(annual_rate))
        self.monthly_payment_periods = int(monthly_payment_periods)
        self.monthly_rate = self.annual_rate / Decimal(12)
        self.emi = EMICalculator(principal, annual_rate, monthly_payment_periods).calculate_emi()

    def generate(self) -> list:
        """Generate the full amortization schedule terminating with zero remaining balance."""
        schedule = []
        balance = self.principal
        total_principal = Decimal("0.00")
        for m in range(1, self.monthly_payment_periods + 1):
            interest = (balance * self.monthly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if m == self.monthly_payment_periods:
                principal_pay = balance
                payment = principal_pay + interest
                balance = Decimal("0.00")
            else:
                principal_pay = self.emi - interest
                balance = balance - principal_pay
                payment = self.emi
            total_principal += principal_pay
            schedule.append({
                "month": m,
                "payment": payment,
                "principal": principal_pay,
                "interest": interest,
                "remaining_balance": balance,
            })
        return schedule


class DTIRiskScorer:
    """Scores debt-to-income ratio into deterministic low, medium, or high risk tiers."""

    def __init__(self, dti_ratio: Decimal):
        self.dti_ratio = Decimal(str(dti_ratio))

    def score(self) -> str:
        """Return the risk tier based on the DTI ratio."""
        if self.dti_ratio < Decimal("0.36"):
            return "low"
        if self.dti_ratio < Decimal("0.43"):
            return "medium"
        return "high"


class PrepaymentCalculator:
    """Calculates savings from extra prepayment on an existing loan schedule."""

    def __init__(self, principal: Decimal, annual_rate: Decimal, monthly_payment_periods: int, prepayment_amount: Decimal):
        self.principal = Decimal(str(principal))
        self.annual_rate = Decimal(str(annual_rate))
        self.monthly_payment_periods = int(monthly_payment_periods)
        self.prepayment_amount = Decimal(str(prepayment_amount))

    def calculate_savings(self) -> dict:
        """Calculate reduced payment and interest savings from extra prepayment."""
        orig_schedule = AmortizationSchedule(self.principal, self.annual_rate, self.monthly_payment_periods).generate()
        orig_interest = sum(item["interest"] for item in orig_schedule)
        new_principal = self.principal - self.prepayment_amount
        new_schedule = AmortizationSchedule(new_principal, self.annual_rate, self.monthly_payment_periods).generate()
        new_interest = sum(item["interest"] for item in new_schedule)
        return {
            "reduced_final_payment": new_schedule[0]["payment"],
            "total_interest_saved": orig_interest - new_interest,
            "remaining_balance_after_prepayment": new_principal,
        }


def run_selftest() -> None:
    """Run deterministic selftests asserting penny-accurate calculations and schedule termination."""
    principal = Decimal("100000.00")
    annual_rate = Decimal("0.12")
    periods = 120

    emi = EMICalculator(principal, annual_rate, periods).calculate_emi()
    assert emi == Decimal("1434.71"), "EMI payment must be penny-accurate"

    schedule = AmortizationSchedule(principal, annual_rate, periods).generate()
    assert len(schedule) == periods, "Schedule must contain exactly the required number of months"
    assert schedule[-1]["remaining_balance"] == Decimal("0.00"), "Schedule must terminate with zero remaining balance"
    assert sum(item["principal"] for item in schedule) == principal, "Total principal payments must equal initial principal"

    dti_ratio = Decimal("0.30")
    risk = DTIRiskScorer(dti_ratio).score()
    assert risk == "low", "DTI ratio below 0.36 must be low risk"

    prepayment_amount = Decimal("20000.00")
    prepayment = PrepaymentCalculator(principal, annual_rate, periods, prepayment_amount).calculate_savings()
    assert prepayment["reduced_final_payment"] > Decimal("0.00"), "Reduced final payment must be positive"
    assert prepayment["total_interest_saved"] > Decimal("0.00"), "Total interest saved must be positive"

    print("SELFTEST OK")


if __name__ == "__main__":
    run_selftest()
