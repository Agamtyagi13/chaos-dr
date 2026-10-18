"""MTTD / MTTR / RTO / RPO / availability / error budget / etc."""
from statistics import median


class Detector:
    def __init__(self, baseline_latency, cfg):
        self.base, self.cfg, self.bad = baseline_latency, cfg, 0

    def unhealthy(self, p):
        return (p.success_rate < self.cfg.success_threshold
                or p.latency_ms > self.cfg.latency_factor * self.base)

    def observe(self, p):
        self.bad = self.bad + 1 if self.unhealthy(p) else 0
        return self.bad >= self.cfg.detect_after


def baseline_latency(probes):
    return median(p.latency_ms for p in probes)


def error_budget_total(cfg):
    return (1 - cfg.slo) * cfg.qps * 86400 * cfg.budget_days


def aggregate(results, cfg):
    n = len(results)
    rec = [r for r in results if r.recovered]

    def mean(xs):
        xs = list(xs)
        return round(sum(xs) / len(xs), 2) if xs else None

    tp = sum(r.probes_total for r in results) or 1
    rq = sum(r.requests_total for r in results) or 1
    return {
        "experiments": n,
        "recovery_success_rate_pct": round(100 * len(rec) / n, 1) if n else 0,
        "self_healed": sum(r.self_healed for r in results),
        "escalated_to_human": sum(r.escalated and not r.recovered for r in results),
        "mttd_s": mean(r.mttd_s for r in results if r.mttd_s is not None),
        "mttr_s": mean(r.mttr_s for r in rec),
        "avg_rto_actual_s": mean(r.rto_actual_s for r in rec),
        "max_rto_actual_s": max((r.rto_actual_s for r in rec), default=None),
        "rto_met_pct": round(100 * sum(r.rto_met for r in results) / n, 1) if n else 0,
        "rpo_met_pct": round(100 * sum(r.rpo_met for r in results) / n, 1) if n else 0,
        "availability_pct": round(100 * sum(r.probes_healthy for r in results) / tp, 3),
        "failure_rate_pct": round(100 * sum(r.failed_total for r in results) / rq, 3),
        "error_budget_consumed_pct": round(sum(r.error_budget_consumed_pct for r in results), 2),
        "worst_degradation_pct": max((r.degradation_pct for r in results), default=0),
        "total_data_loss_records": sum(r.data_loss_records for r in results),
        "slo": cfg.slo,
    }
