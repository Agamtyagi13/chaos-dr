"""Autonomous recovery: diagnose from signals, run playbook, verify, escalate."""
from .catalog import PLAYBOOKS


class RecoveryController:
    def __init__(self, backend, cfg, t_inject):
        self.b, self.cfg, self.t0 = backend, cfg, t_inject
        self.plan, self.tries, self.log = [], {}, []
        self.current = None          # (action, finish_time)
        self.verify_until = None
        self.escalated = False

    def start(self, now):
        for sig in self.b.signals():                 # diagnose
            for action in PLAYBOOKS.get(sig, []):
                if action not in self.plan:
                    self.plan.append(action)
        self._next(now)

    def _next(self, now):
        self.verify_until = None
        if not self.plan:
            self.escalated = True                    # page a human
            self.current = None
            return
        action = self.plan[0]
        self.b.start_action(action)
        self.current = (action, now + self.b.action_duration(action))
        self.log.append({"action": action, "start_s": round(now - self.t0, 1),
                         "end_s": None, "ok": None})

    def step(self, now):
        if self.current:
            action, finish = self.current
            if now >= finish:
                ok = self.b.finish_action(action)
                self.log[-1].update(end_s=round(now - self.t0, 1), ok=ok)
                self.current = None
                if ok:
                    self.verify_until = now + self.cfg.verify_s
                else:
                    self.tries[action] = self.tries.get(action, 0) + 1
                    if self.tries[action] >= self.cfg.max_retries:
                        self.plan.pop(0)
                    self._next(now)
        elif self.verify_until is not None and now >= self.verify_until:
            self.plan.pop(0)                          # action ran but did not help
            self._next(now)
