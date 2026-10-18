import unittest

from chaos.backends.sim import SimBackend
from chaos.catalog import FAULTS, PLAYBOOKS
from chaos.config import Config
from chaos.metrics import aggregate
from chaos.runner import run_experiment


def run(name, **kw):
    cfg = Config(**kw)
    return run_experiment(SimBackend(cfg), FAULTS[name], cfg), cfg


class PlatformTests(unittest.TestCase):
    def test_every_fault_has_playbook_and_recovers(self):
        for name, spec in FAULTS.items():
            self.assertIn(spec.signal, PLAYBOOKS, name)
            r, _ = run(name)
            self.assertTrue(r.recovered, name)
            self.assertTrue(r.detected, name)
            self.assertLessEqual(r.mttd_s, 5, name)

    def test_database_failover_loses_async_writes_but_sync_does_not(self):
        r, _ = run("database_failure")
        self.assertGreater(r.data_loss_records, 0)
        r2, _ = run("database_failure", sync_replication=True)
        self.assertEqual(r2.data_loss_records, 0)
        self.assertTrue(r2.rpo_met)

    def test_escalates_when_actions_always_fail(self):
        r, _ = run("cpu_exhaustion", action_success_prob=0.0, max_duration_s=120)
        self.assertFalse(r.recovered)
        self.assertTrue(r.escalated)
        self.assertFalse(r.rto_met)

    def test_pod_termination_self_heals_if_controller_fails(self):
        r, _ = run("pod_termination", action_success_prob=0.0)
        self.assertTrue(r.recovered)
        self.assertTrue(r.self_healed)

    def test_metrics_consistent(self):
        r, cfg = run("node_failure")
        self.assertAlmostEqual(r.rto_actual_s, r.mttd_s + r.mttr_s, places=1)
        self.assertLess(r.availability_pct, 100)
        agg = aggregate([r], cfg)
        self.assertEqual(agg["recovery_success_rate_pct"], 100.0)

    def test_deterministic_for_seed(self):
        a, _ = run("dns_failure", seed=3)
        b, _ = run("dns_failure", seed=3)
        self.assertEqual(a.rto_actual_s, b.rto_actual_s)


if __name__ == "__main__":
    unittest.main()
