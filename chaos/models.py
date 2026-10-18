from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Probe:
    t: float
    requests: int
    failures: int
    latency_ms: float

    @property
    def success_rate(self) -> float:
        return 1 - self.failures / self.requests if self.requests else 0.0


@dataclass
class ExperimentResult:
    fault: str
    description: str
    signal: str
    rto_target_s: int
    rpo_target_s: int
    detected: bool = False
    recovered: bool = False
    self_healed: bool = False
    escalated: bool = False
    mttd_s: Optional[float] = None       # inject -> detection
    mttr_s: Optional[float] = None       # detection -> recovery
    rto_actual_s: Optional[float] = None  # inject -> recovery (total outage)
    rto_met: bool = False
    rpo_actual_s: float = 0.0
    rpo_met: bool = True
    data_loss_records: int = 0
    availability_pct: float = 100.0      # healthy probes / probes, post-injection
    failure_rate_pct: float = 0.0        # failed requests / requests, post-injection
    error_budget_consumed_pct: float = 0.0
    peak_error_rate_pct: float = 0.0
    peak_latency_ms: float = 0.0
    degradation_pct: float = 0.0         # peak latency increase vs baseline
    baseline_latency_ms: float = 0.0
    actions: list = field(default_factory=list)
    series: list = field(default_factory=list)  # [t_rel, success_rate, latency_ms]
    probes_total: int = 0
    probes_healthy: int = 0
    requests_total: int = 0
    failed_total: int = 0
