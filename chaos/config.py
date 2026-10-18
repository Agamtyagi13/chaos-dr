from dataclasses import dataclass


@dataclass
class Config:
    seed: int = 7
    qps: int = 200                  # simulated / expected request rate
    warmup_s: int = 10              # healthy baseline before each injection
    max_duration_s: int = 240       # give up (escalate to human) after this
    stable_s: int = 5               # consecutive healthy probes == recovered
    detect_after: int = 3           # consecutive unhealthy probes == detected
    success_threshold: float = 0.98
    latency_factor: float = 1.5     # latency > factor * baseline == unhealthy
    verify_s: int = 10              # wait after an action before escalating
    max_retries: int = 2            # retries per action before next action
    action_success_prob: float = 0.93
    slo: float = 0.999
    budget_days: int = 30
    write_rate: int = 50            # writes/sec (used for RPO / data loss)
    repl_lag_s: float = 2.0         # async replication lag
    sync_replication: bool = False
