from .catalog import FaultSpec
from .config import Config
from .metrics import Detector, baseline_latency, error_budget_total
from .models import ExperimentResult
from .recovery import RecoveryController


def run_experiment(backend, spec: FaultSpec, cfg: Config) -> ExperimentResult:
    probes = []
    for _ in range(cfg.warmup_s):                     # healthy baseline
        backend.tick(1)
        probes.append(backend.probe())
    base = baseline_latency(probes)
    det = Detector(base, cfg)

    t0 = backend.now()
    loss0 = backend.data_loss()
    backend.inject(spec)
    ctrl = RecoveryController(backend, cfg, t0)
    t_detect = t_recover = None
    streak = 0

    while backend.now() - t0 < cfg.max_duration_s:
        backend.tick(1)
        p = backend.probe()
        probes.append(p)
        now = backend.now()
        if t_detect is None and det.observe(p):
            t_detect = now
            ctrl.start(now)
        if t_detect is not None:
            ctrl.step(now)
        streak = 0 if det.unhealthy(p) else streak + 1
        if streak >= cfg.stable_s:
            t_recover = now - (cfg.stable_s - 1)
            break
    backend.cleanup()

    post = [p for p in probes if p.t > t0]
    req = sum(p.requests for p in post) or 1
    fail = sum(p.failures for p in post)
    healthy_post = sum(not det.unhealthy(p) for p in post)
    loss = backend.data_loss() - loss0
    rpo = loss / cfg.write_rate if cfg.write_rate else 0.0
    recovered = t_recover is not None
    peak_lat = max(p.latency_ms for p in post)
    r = ExperimentResult(
        fault=spec.name, description=spec.description, signal=spec.signal,
        rto_target_s=spec.rto_s, rpo_target_s=spec.rpo_s,
        detected=t_detect is not None, recovered=recovered,
        escalated=ctrl.escalated or not recovered,
        baseline_latency_ms=round(base, 1),
        data_loss_records=loss, rpo_actual_s=round(rpo, 2), rpo_met=rpo <= spec.rpo_s,
        availability_pct=round(100 * healthy_post / len(post), 2),
        failure_rate_pct=round(100 * fail / req, 2),
        error_budget_consumed_pct=round(100 * fail / error_budget_total(cfg), 3),
        peak_error_rate_pct=round(100 * max(1 - p.success_rate for p in post), 1),
        peak_latency_ms=round(peak_lat, 1),
        degradation_pct=round(100 * (peak_lat / base - 1), 1),
        actions=ctrl.log,
        series=[[round(p.t - t0, 1), round(p.success_rate, 3), round(p.latency_ms, 1)] for p in probes],
        probes_total=len(probes),
        probes_healthy=sum(not det.unhealthy(p) for p in probes),
        requests_total=sum(p.requests for p in probes),
        failed_total=sum(p.failures for p in probes),
    )
    if t_detect is not None:
        r.mttd_s = round(t_detect - t0, 1)
    if recovered:
        r.rto_actual_s = round(t_recover - t0, 1)
        r.rto_met = r.rto_actual_s <= spec.rto_s
        if t_detect is not None:
            r.mttr_s = round(max(0.0, t_recover - t_detect), 1)
        r.self_healed = not any(a["ok"] and a["end_s"] is not None and a["end_s"] <= t_recover - t0
                                for a in ctrl.log)
        r.escalated = False
    return r
