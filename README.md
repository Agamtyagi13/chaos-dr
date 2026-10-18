# Large-Scale Chaos Engineering & Autonomous Disaster Recovery System

A platform that **intentionally injects failures** into a distributed system, **detects** them,
**recovers autonomously**, and **measures** how the infrastructure behaves.

```
            ┌────────────┐  inject   ┌────────────────────────┐
            │  Runner    │──────────▶│ Backend (sim | k8s)     │
            │ (experiment│◀──probe───│  sim: virtual cluster   │
            │  lifecycle)│           │  k8s: Chaos Mesh + API  │
            └─────┬──────┘           └───────────▲────────────┘
        detect    │ signals                      │ actions
      ┌───────────▼──────────┐   playbooks   ┌───┴──────────────┐
      │ Detector (SLO probes)│──────────────▶│ RecoveryController│
      └───────────┬──────────┘               │ diagnose→act→verify│
                  │                          │ →retry→escalate    │
                  ▼                          └────────────────────┘
        Metrics → results.json + report.html
```

## Quick start (no cluster needed)
```bash
python3 main.py list
python3 main.py run --repeat 3 --out reports      # all 14 faults x3
python3 main.py run --faults database_failure,dns_failure --action-success 0.5
python3 -m unittest -v
open reports/report.html
```
Python 3.9+, standard library only for the simulator.

## Failure scenarios (14)
pod termination · node failure · CPU exhaustion · memory exhaustion · network latency · packet loss ·
DNS failure · database failure · Redis failure · service-dependency failure · availability-zone failure ·
application crash · certificate failure · disk exhaustion (see `chaos/catalog.py`).

## Measurements
| Metric | Definition |
|---|---|
| **MTTD** | injection → detection (N consecutive unhealthy probes) |
| **MTTR** | detection → recovered (stable healthy probes) |
| **RTO** | actual = injection → recovered, compared with per-fault target |
| **RPO** | lost writes ÷ write rate (async replication lag at DB failover), vs target |
| **Availability** | healthy probes ÷ probes (campaign figure includes only fault windows + 10 s baselines, so it is intentionally low) |
| **Error budget** | failed requests ÷ budget of a 99.9 % / 30-day SLO |
| **Failure rate** | failed ÷ total requests |
| **Recovery success rate** | experiments recovered ÷ experiments (self-healed counted separately) |
| **Service degradation** | peak latency increase vs baseline + peak error rate |
| **Data loss** | records lost during failover |

## Autonomous recovery
1. Detector flags SLO breach (success < 98 % or latency > 1.5× baseline).
2. Controller reads **signals** (e.g. `OOMKilled`, `NodeNotReady`) and picks a **playbook** (`PLAYBOOKS`).
3. Executes action → verifies → retries (`max_retries`) → escalates to the next action → finally pages a human.
4. Some playbooks deliberately start with an imperfect action (DNS: restart CoreDNS, then fallback resolver) to exercise escalation.

## Running on Kubernetes (experimental)
```bash
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm install chaos-mesh chaos-mesh/chaos-mesh -n chaos-mesh --create-namespace
kubectl apply -f k8s/sample-app.yaml
pip install -r requirements.txt
python3 main.py run --backend k8s --namespace chaos-demo --target-url http://localhost:8080/healthz \
  --hook failover_db="kubectl -n chaos-demo exec postgres-0 -- patronictl failover --force" \
  --hook failover_redis="..." --hook use_fallback_dns="..."
# in-cluster: docker build -t chaos-dr . && kubectl apply -f k8s/controller.yaml
```
**Caveat:** the simulator is tested (`unittest`); the Kubernetes backend was written against the
Chaos Mesh / Kubernetes APIs but has **not been run against a real cluster** here. Expect to tune
selectors, image names, secret names and the DB/Redis failover hooks for your environment.
Failure signals in K8s mode partly come from the injected experiment labels; replace with Prometheus/Alertmanager in production.

## Layout
```
main.py              CLI            chaos/catalog.py   faults, playbooks
chaos/runner.py      lifecycle      chaos/recovery.py  autonomous controller
chaos/metrics.py     detector+KPIs  chaos/report.py    HTML/JSON reports
chaos/backends/      sim.py, k8s.py k8s/               sample app, RBAC, Job
tests/               unit tests
```
