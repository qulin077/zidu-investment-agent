"""财务比率只做除法。缺数就空着，不让模型心算。"""
from __future__ import annotations


def _div(numerator, denominator):
    if numerator is None or denominator in (None, 0, 0.0):
        return None
    return float(numerator) / float(denominator)


def growth(current, previous):
    if current is None or previous in (None, 0, 0.0):
        return None
    return (float(current) - float(previous)) / float(previous)


def gross_margin(gross_profit, revenue):
    return _div(gross_profit, revenue)


def operating_margin(operating_profit, revenue):
    return _div(operating_profit, revenue)


def cash_conversion(operating_cash_flow, net_income):
    return _div(operating_cash_flow, net_income)


def capex_intensity(capex, revenue):
    return _div(capex, revenue)


def leverage(debt, equity):
    return _div(debt, equity)


def debt_to_assets(liabilities, assets):
    return _div(liabilities, assets)


def current_ratio(current_assets, current_liabilities):
    return _div(current_assets, current_liabilities)


def return_on_equity(net_income, average_equity):
    return _div(net_income, average_equity)


def return_on_invested_capital(nopat, invested_capital):
    return _div(nopat, invested_capital)


def share(part, total):
    return _div(part, total)


def pe(price, eps):
    return _div(price, eps)


def ps(price, sales_per_share):
    return _div(price, sales_per_share)


def snapshot(row: dict) -> dict:
    return {
        "revenue_growth": growth(row.get("revenue"), row.get("revenue_prev")),
        "gross_margin": gross_margin(row.get("gross_profit"), row.get("revenue")),
        "operating_margin": operating_margin(row.get("operating_profit"), row.get("revenue")),
        "cash_conversion": cash_conversion(row.get("operating_cash_flow"), row.get("net_income")),
        "capex_intensity": capex_intensity(row.get("capex"), row.get("revenue")),
        "leverage": leverage(row.get("debt"), row.get("equity")),
        "pe": pe(row.get("price"), row.get("eps")),
        "ps": ps(row.get("price"), row.get("sales_per_share")),
    }
