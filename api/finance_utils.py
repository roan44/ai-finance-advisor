
from math import pow

def monthly_total(amount: float, frequency_per_month: float) -> float:
    return amount * frequency_per_month

def yearly_total(amount: float, frequency_per_month: float) -> float:
    return monthly_total(amount, frequency_per_month) * 12

def future_value_monthly_contrib(contrib_per_month: float, annual_rate: float, years: int) -> float:
    """
    Future Value of a monthly contribution with monthly compounding.
    contrib_per_month: euros per month
    annual_rate: e.g. 0.07 for 7%
    years: number of years
    """
    if annual_rate <= -1:
        return 0.0
    r = annual_rate / 12.0
    n = years * 12
    if r == 0:
        return contrib_per_month * n
    return contrib_per_month * (((1 + r) ** n - 1) / r)
