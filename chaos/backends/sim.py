"""Deterministic in-memory cluster simulator on a virtual clock."""
import random
from typing import List

from .base import Backend
from ..catalog import FaultSpec, ACTION_COST
from ..config import Config
from ..models import Probe

BASE_LATENCY_MS = 40.0


class SimBackend(Backend):
    name = "sim"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self._t = 0.0
        self._loss = 0
        self.active = {}  # fault name -> (spec, injected_at)

    def now(self):
        return self._t

    def tick(self, dt=1.0):
        self._t += dt
        for name, (spec, t0) in list(self.active.items()):
            if spec.self_heal_s and self._t - t0 >= spec.self_heal_s:
                del self.active[name]          # k8s self-healing

    def inject(self, spec: FaultSpec):
        self.active[spec.name] = (spec, self._t)

    def cleanup(self):
        self.active.clear()

    def probe(self) -> Probe:
        cap, lat, ok = 1.0, 1.0, 0.999
        for spec, _ in self.active.values():
            cap *= spec.cap
            lat *= spec.lat
            ok *= 1 - spec.err
        ok *= min(1.0, cap / 0.6)               # load shedding when capacity is low
        ok = min(1.0, max(0.0, ok + self.rng.uniform(-0.002, 0.002)))
        reqs = self.cfg.qps
        return Probe(self._t, reqs, int(round(reqs * (1 - ok))),
                     BASE_LATENCY_MS * lat * self.rng.uniform(0.95, 1.05))

    def signals(self) -> List[str]:
        return [s.signal for s, _ in self.active.values()]

    def start_action(self, action):
        pass

    def action_duration(self, action):
        return ACTION_COST.get(action, 20) * self.rng.uniform(0.8, 1.25)

    def finish_action(self, action) -> bool:
        if self.rng.random() > self.cfg.action_success_prob:
            return False
        for name, (spec, _) in list(self.active.items()):
            if action in spec.cures:
                if action == "failover_db" and not self.cfg.sync_replication:
                    self._loss += int(self.cfg.write_rate * self.cfg.repl_lag_s
                                      * self.rng.uniform(0.5, 1.5))
                del self.active[name]
        return True

    def data_loss(self):
        return self._loss
