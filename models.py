from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class Meta:
    statement_period: str = ""
    cas_type: str = ""

@dataclass
class InvestorInfo:
    name: str = ""
    email: str = ""
    mobile: str = ""
    pan: str = ""
    address: List[str] = field(default_factory=list)

@dataclass
class MutualFund:
    folio: str
    scheme: str
    isin: str
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    current_value: float = 0.0

@dataclass
class PortfolioSummary:
    total_value: float = 0.0
    mutual_funds: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CASData:
    meta: Meta = field(default_factory=Meta)
    investor_info: InvestorInfo = field(default_factory=InvestorInfo)
    mutual_funds: List[MutualFund] = field(default_factory=list)
    portfolio_summary: PortfolioSummary = field(default_factory=PortfolioSummary)
