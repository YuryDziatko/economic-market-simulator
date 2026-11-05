from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping

from .config import SimulationConfig
from .policy import POLICY_LIMITS, PolicyAction, PolicyState


@dataclass(frozen=True, slots=True)
class EconomicSnapshot:
    """Compact annual observation presented to a deterministic or future AI agent."""

    year: int
    real_gdp_growth: float
    inflation: float
    inflation_target: float
    unemployment_rate: float
    income_gini: float
    debt_to_gdp: float
    capacity_utilization: float
    household_savings_rate: float
    investment_share_of_gdp: float
    government_budget_balance_share: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AgentProfile:
    key: str
    name: str
    description: str
    priorities: Mapping[str, float]


class DeterministicPolicyAgent:
    """Base interface for reproducible annual policy rules."""

    profile: AgentProfile

    @property
    def key(self) -> str:
        return self.profile.key

    @property
    def name(self) -> str:
        return self.profile.name

    def decide(
        self,
        snapshot: EconomicSnapshot,
        state: PolicyState,
        config: SimulationConfig,
    ) -> PolicyAction:
        raise NotImplementedError


def _bounded_delta(field: str, requested: float, state: PolicyState) -> float:
    """Clip a requested change to both annual movement and absolute bounds."""
    limits = POLICY_LIMITS[field]
    requested = max(-limits.max_annual_change, min(limits.max_annual_change, requested))
    current = float(getattr(state, field))
    requested = min(requested, limits.maximum - current)
    requested = max(requested, limits.minimum - current)
    return float(requested)


def _fiscal_deltas(
    state: PolicyState,
    *,
    government_change: float = 0.0,
    transfer_change: float = 0.0,
) -> tuple[float, float]:
    """Create bounded fiscal-share changes while preserving non-negative reserve."""
    g = _bounded_delta("government_consumption_share", government_change, state)
    t = _bounded_delta("general_transfer_share", transfer_change, state)
    max_total = 1.0
    new_total = state.government_consumption_share + g + state.general_transfer_share + t
    if new_total > max_total:
        excess = new_total - max_total
        # Reduce the larger positive proposal first; do not reverse intended cuts.
        if g > 0 and g >= t:
            cut = min(g, excess)
            g -= cut
            excess -= cut
        if excess > 0 and t > 0:
            t -= min(t, excess)
    return float(g), float(t)


def _reason(name: str, snapshot: EconomicSnapshot, actions: list[str]) -> str:
    signals = (
        f"GDP growth {snapshot.real_gdp_growth:.1%}, inflation {snapshot.inflation:.1%}, "
        f"unemployment {snapshot.unemployment_rate:.1%}, Gini {snapshot.income_gini:.3f}, "
        f"debt/GDP {snapshot.debt_to_gdp:.1%}."
    )
    if not actions:
        return f"{name}: hold policy. {signals}"
    return f"{name}: " + "; ".join(actions) + ". " + signals


class TechnocraticAgent(DeterministicPolicyAgent):
    profile = AgentProfile(
        "technocratic", "Technocratic",
        "Balances inflation, employment, growth and fiscal sustainability with gradual changes.",
        {"growth": 0.25, "employment": 0.25, "inflation": 0.25, "debt": 0.15, "equality": 0.10},
    )

    def decide(self, s: EconomicSnapshot, state: PolicyState, config: SimulationConfig) -> PolicyAction:
        actions: list[str] = []
        rate = 0.0
        gov = 0.0
        transfers = 0.0
        benefit = 0.0

        gap = s.inflation - s.inflation_target
        if gap > 0.015:
            rate = 0.01 if gap < 0.04 else 0.02
            actions.append("raise the policy rate to cool inflation")
        elif gap < -0.015 or (s.real_gdp_growth < 0 and s.inflation < s.inflation_target):
            rate = -0.01
            actions.append("lower the policy rate to support demand")

        if s.unemployment_rate > 0.08:
            gov += 0.02
            benefit += 0.02
            actions.append("support employment with purchases and unemployment benefits")
        elif s.unemployment_rate < 0.035 and s.inflation > s.inflation_target:
            gov -= 0.01
            actions.append("slightly restrain government demand")

        if s.debt_to_gdp > 0.80 and s.government_budget_balance_share < -0.03:
            gov -= 0.02
            transfers -= 0.01
            actions.append("reduce the fiscal deficit because debt is high")

        gov, transfers = _fiscal_deltas(state, government_change=gov, transfer_change=transfers)
        return PolicyAction(
            interest_rate=_bounded_delta("interest_rate", rate, state),
            government_consumption_share=gov,
            general_transfer_share=transfers,
            unemployment_transfer_rate=_bounded_delta("unemployment_transfer_rate", benefit, state),
            reason=_reason(self.name, s, actions),
        )


class MarketLiberalAgent(DeterministicPolicyAgent):
    profile = AgentProfile(
        "market_liberal", "Market Liberal",
        "Prioritizes private investment, lower tax burdens and restrained transfers while reacting to inflation.",
        {"growth": 0.30, "investment": 0.25, "employment": 0.20, "inflation": 0.15, "debt": 0.10},
    )

    def decide(self, s: EconomicSnapshot, state: PolicyState, config: SimulationConfig) -> PolicyAction:
        actions: list[str] = []
        income_tax = -0.01 if state.tax_rate > 0.12 and s.debt_to_gdp < 0.70 else 0.0
        corp_tax = -0.015 if state.corporate_profit_tax_rate > 0.10 and s.debt_to_gdp < 0.70 else 0.0
        retention = 0.03 if s.capacity_utilization > 0.78 or s.investment_share_of_gdp < 0.10 else 0.01
        transfers = -0.015 if state.general_transfer_share > 0.08 else 0.0
        gov = -0.01 if s.unemployment_rate < 0.08 else 0.0
        rate = 0.01 if s.inflation > s.inflation_target + 0.02 else (-0.005 if s.real_gdp_growth < 0 else 0.0)

        if income_tax or corp_tax:
            actions.append("reduce tax rates to strengthen private incentives")
        if retention:
            actions.append("increase retained business income for investment")
        if transfers or gov:
            actions.append("restrain transfer/government shares")
        if rate > 0:
            actions.append("raise rates against inflation")
        elif rate < 0:
            actions.append("lower rates during contraction")

        gov, transfers = _fiscal_deltas(state, government_change=gov, transfer_change=transfers)
        return PolicyAction(
            tax_rate=_bounded_delta("tax_rate", income_tax, state),
            corporate_profit_tax_rate=_bounded_delta("corporate_profit_tax_rate", corp_tax, state),
            interest_rate=_bounded_delta("interest_rate", rate, state),
            government_consumption_share=gov,
            general_transfer_share=transfers,
            profit_retention_rate=_bounded_delta("profit_retention_rate", retention, state),
            reason=_reason(self.name, s, actions),
        )


class SocialDemocraticAgent(DeterministicPolicyAgent):
    profile = AgentProfile(
        "social_democratic", "Social Democratic",
        "Prioritizes employment and lower inequality using transfers and public demand, financed with progressive-style aggregate tax changes.",
        {"equality": 0.30, "employment": 0.25, "growth": 0.20, "inflation": 0.15, "debt": 0.10},
    )

    def decide(self, s: EconomicSnapshot, state: PolicyState, config: SimulationConfig) -> PolicyAction:
        actions: list[str] = []
        tax = 0.01 if s.income_gini > 0.38 and state.tax_rate < 0.40 else 0.0
        corp = 0.005 if s.income_gini > 0.42 and s.real_gdp_growth > 0 else 0.0
        transfers = 0.02 if s.income_gini > 0.36 else 0.0
        benefit = 0.02 if s.unemployment_rate > 0.06 else 0.0
        gov = 0.02 if s.unemployment_rate > 0.07 or s.real_gdp_growth < 0 else 0.0
        rate = 0.01 if s.inflation > s.inflation_target + 0.03 else (-0.005 if s.unemployment_rate > 0.09 and s.inflation <= s.inflation_target else 0.0)

        if transfers or benefit:
            actions.append("increase social transfers because inequality or unemployment is elevated")
        if gov:
            actions.append("increase public demand to support employment")
        if tax or corp:
            actions.append("raise aggregate tax rates modestly to finance redistribution")
        if rate > 0:
            actions.append("tighten monetary policy against high inflation")
        elif rate < 0:
            actions.append("ease rates while unemployment is high")

        gov, transfers = _fiscal_deltas(state, government_change=gov, transfer_change=transfers)
        return PolicyAction(
            tax_rate=_bounded_delta("tax_rate", tax, state),
            corporate_profit_tax_rate=_bounded_delta("corporate_profit_tax_rate", corp, state),
            interest_rate=_bounded_delta("interest_rate", rate, state),
            government_consumption_share=gov,
            general_transfer_share=transfers,
            unemployment_transfer_rate=_bounded_delta("unemployment_transfer_rate", benefit, state),
            reason=_reason(self.name, s, actions),
        )


class StateDirectedAgent(DeterministicPolicyAgent):
    profile = AgentProfile(
        "state_directed", "State Directed",
        "Uses larger public-demand and retention levers to push capacity expansion and employment, accepting more intervention.",
        {"growth": 0.25, "employment": 0.25, "investment": 0.25, "stability": 0.15, "equality": 0.10},
    )

    def decide(self, s: EconomicSnapshot, state: PolicyState, config: SimulationConfig) -> PolicyAction:
        actions: list[str] = []
        gov = 0.03 if (s.capacity_utilization < 0.90 or s.unemployment_rate > 0.05) else 0.01
        retention = 0.04 if s.investment_share_of_gdp < 0.18 else 0.02
        corp = 0.005 if s.debt_to_gdp > 0.60 else 0.0
        transfers = 0.01 if s.income_gini > 0.40 else 0.0
        rate = 0.01 if s.inflation > s.inflation_target + 0.04 else 0.0

        if gov:
            actions.append("increase public purchases to support strategic demand")
        if retention:
            actions.append("raise retained earnings to accelerate capital formation")
        if transfers:
            actions.append("add targeted redistribution when inequality is high")
        if rate:
            actions.append("tighten rates only when inflation is materially above target")

        gov, transfers = _fiscal_deltas(state, government_change=gov, transfer_change=transfers)
        return PolicyAction(
            corporate_profit_tax_rate=_bounded_delta("corporate_profit_tax_rate", corp, state),
            interest_rate=_bounded_delta("interest_rate", rate, state),
            government_consumption_share=gov,
            general_transfer_share=transfers,
            profit_retention_rate=_bounded_delta("profit_retention_rate", retention, state),
            reason=_reason(self.name, s, actions),
        )


class HybridAgent(DeterministicPolicyAgent):
    profile = AgentProfile(
        "hybrid", "Hybrid",
        "Uses moderate market and social-policy responses, emphasizing gradual adjustments rather than a single doctrine.",
        {"growth": 0.25, "employment": 0.25, "inflation": 0.20, "equality": 0.15, "debt": 0.15},
    )

    def decide(self, s: EconomicSnapshot, state: PolicyState, config: SimulationConfig) -> PolicyAction:
        actions: list[str] = []
        rate = 0.0
        gov = 0.0
        transfers = 0.0
        tax = 0.0
        corp = 0.0
        retention = 0.0
        benefit = 0.0

        if s.inflation > s.inflation_target + 0.02:
            rate = 0.01
            actions.append("raise rates moderately")
        elif s.real_gdp_growth < 0 and s.inflation <= s.inflation_target:
            rate = -0.005
            actions.append("ease rates during contraction")

        if s.unemployment_rate > 0.075:
            gov = 0.015
            benefit = 0.01
            actions.append("support jobs with a moderate fiscal response")
        if s.income_gini > 0.40:
            transfers += 0.01
            tax += 0.005
            actions.append("increase redistribution modestly")
        if s.investment_share_of_gdp < 0.12 and s.capacity_utilization > 0.75:
            retention = 0.02
            corp -= 0.005
            actions.append("support private capital formation")
        if s.debt_to_gdp > 0.75 and s.government_budget_balance_share < -0.03:
            gov -= 0.015
            transfers -= 0.005
            tax += 0.005
            actions.append("partly consolidate fiscal policy because debt is elevated")

        gov, transfers = _fiscal_deltas(state, government_change=gov, transfer_change=transfers)
        return PolicyAction(
            tax_rate=_bounded_delta("tax_rate", tax, state),
            corporate_profit_tax_rate=_bounded_delta("corporate_profit_tax_rate", corp, state),
            interest_rate=_bounded_delta("interest_rate", rate, state),
            government_consumption_share=gov,
            general_transfer_share=transfers,
            unemployment_transfer_rate=_bounded_delta("unemployment_transfer_rate", benefit, state),
            profit_retention_rate=_bounded_delta("profit_retention_rate", retention, state),
            reason=_reason(self.name, s, actions),
        )


AGENT_CLASSES = {
    cls.profile.key: cls
    for cls in (TechnocraticAgent, MarketLiberalAgent, SocialDemocraticAgent, StateDirectedAgent, HybridAgent)
}


def get_agent(name: str) -> DeterministicPolicyAgent:
    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    try:
        return AGENT_CLASSES[key]()
    except KeyError as exc:
        raise ValueError(f"Unknown deterministic policy agent {name!r}. Available: {', '.join(sorted(AGENT_CLASSES))}") from exc


def agent_catalog() -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "name": cls.profile.name,
            "description": cls.profile.description,
            "priorities": dict(cls.profile.priorities),
        }
        for key, cls in AGENT_CLASSES.items()
    ]
