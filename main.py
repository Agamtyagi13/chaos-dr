#!/usr/bin/env python3
"""Chaos Engineering & Autonomous Disaster Recovery platform – CLI."""
import argparse
import sys

from chaos.catalog import FAULTS
from chaos.config import Config
from chaos.metrics import aggregate
from chaos.report import write_reports
from chaos.runner import run_experiment


def build_backend(args, cfg):
    if args.backend == "sim":
        from chaos.backends.sim import SimBackend
        return SimBackend(cfg)
    from chaos.backends.k8s import K8sBackend
    hooks = dict(h.split("=", 1) for h in args.hook)
    return K8sBackend(cfg, args.namespace, args.target_url, zone=args.zone, hooks=hooks)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list available fault scenarios")
    r = sub.add_parser("run", help="run chaos experiments")
    r.add_argument("--backend", choices=["sim", "k8s"], default="sim")
    r.add_argument("--faults", default="all", help="comma separated names or 'all'")
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--action-success", type=float, default=0.93)
    r.add_argument("--out", default="reports")
    r.add_argument("--namespace", default="chaos-demo")
    r.add_argument("--target-url", default="http://localhost:8080/healthz")
    r.add_argument("--zone", default="zone-a")
    r.add_argument("--hook", action="append", default=[], metavar="ACTION=CMD",
                   help="shell command for app-specific actions (failover_db, ...)")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        for f in FAULTS.values():
            print(f"{f.name:20} {f.signal:22} RTO<={f.rto_s:>3}s RPO<={f.rpo_s}s  {f.description}")
        return 0

    names = list(FAULTS) if a.faults == "all" else a.faults.split(",")
    unknown = [n for n in names if n not in FAULTS]
    if unknown:
        sys.exit(f"unknown fault(s): {', '.join(unknown)}")
    cfg = Config(seed=a.seed, action_success_prob=a.action_success)
    backend = build_backend(a, cfg)
    results = []
    for _ in range(a.repeat):
        for n in names:
            res = run_experiment(backend, FAULTS[n], cfg)
            results.append(res)
            state = "self-healed" if res.self_healed else "recovered" if res.recovered else "ESCALATED"
            print(f"{n:20} detect={res.mttd_s}s mttr={res.mttr_s}s rto={res.rto_actual_s}/{res.rto_target_s}s "
                  f"avail={res.availability_pct}% loss={res.data_loss_records} -> {state}")
    summary = aggregate(results, cfg)
    write_reports(results, summary, a.out, {"backend": a.backend, "seed": a.seed})
    print("\nSUMMARY"); [print(f"  {k}: {v}") for k, v in summary.items()]
    print(f"\nReports written to {a.out}/report.html and results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
