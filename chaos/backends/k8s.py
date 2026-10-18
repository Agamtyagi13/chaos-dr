"""Kubernetes backend (Chaos Mesh for injection). EXPERIMENTAL - not exercised in CI.

Requires: pip install kubernetes ; Chaos Mesh installed in the cluster.
App-specific actions (failover_db, failover_redis, use_fallback_dns) must be
supplied as shell hooks (--hook failover_db="..."); otherwise they fail and
the controller escalates.
"""
import subprocess
import time
import urllib.request
from typing import List

from .base import Backend
from ..catalog import FaultSpec
from ..models import Probe

GROUP, VER = "chaos-mesh.org", "v1alpha1"
KINDS = {"podchaos": "PodChaos", "stresschaos": "StressChaos", "networkchaos": "NetworkChaos",
         "dnschaos": "DNSChaos", "iochaos": "IOChaos"}


class K8sBackend(Backend):
    name = "k8s"

    def __init__(self, cfg, namespace, target_url, zone="zone-a", hooks=None, probe_requests=20,
                 app="api", db="postgres", cache="redis", dependency="payments", duration="120s"):
        from kubernetes import client, config as kcfg
        try:
            kcfg.load_incluster_config()
        except Exception:
            kcfg.load_kube_config()
        self.cfg, self.ns, self.url, self.zone = cfg, namespace, target_url, zone
        self.hooks, self.n, self.duration = hooks or {}, probe_requests, duration
        self.app, self.db, self.cache, self.dep = app, db, cache, dependency
        self.core, self.apps = client.CoreV1Api(), client.AppsV1Api()
        self.crd = client.CustomObjectsApi()
        self.created, self.cordoned, self.restore = [], [], []

    # ---- time / measurement -------------------------------------------------
    def now(self): return time.time()
    def tick(self, dt=1.0): time.sleep(dt)

    def probe(self) -> Probe:
        fails, lat = 0, []
        for _ in range(self.n):
            t = time.time()
            try:
                with urllib.request.urlopen(self.url, timeout=1.0) as r:
                    fails += r.status >= 500
            except Exception:
                fails += 1
            lat.append((time.time() - t) * 1000)
        return Probe(time.time(), self.n, fails, sum(lat) / len(lat))

    # ---- injection ----------------------------------------------------------
    def _sel(self, app):
        return {"namespaces": [self.ns], "labelSelectors": {"app": app}}

    def _chaos(self, plural, name, spec):
        if spec.get("action") != "pod-kill":
            spec["duration"] = self.duration
        body = {"apiVersion": f"{GROUP}/{VER}", "kind": KINDS[plural],
                "metadata": {"name": name, "namespace": self.ns,
                             "labels": {"chaos-platform/injected": "true"}}, "spec": spec}
        self.crd.create_namespaced_custom_object(GROUP, VER, self.ns, plural, body)
        self.created.append((plural, name))

    def _app_pods(self, label="app", value=None):
        return self.core.list_namespaced_pod(self.ns, label_selector=f"{label}={value or self.app}").items

    def inject(self, f: FaultSpec):
        n, s = f.name.replace("_", "-"), self._sel
        pk = lambda a, sel, mode="one": ("podchaos", {"action": a, "mode": mode, "selector": sel})
        table = {
            "pod_termination": pk("pod-kill", s(self.app)),
            "cpu_exhaustion": ("stresschaos", {"mode": "all", "selector": s(self.app),
                                               "stressors": {"cpu": {"workers": 2, "load": 100}}}),
            "memory_exhaustion": ("stresschaos", {"mode": "all", "selector": s(self.app),
                                                  "stressors": {"memory": {"workers": 1, "size": "512MB"}}}),
            "network_latency": ("networkchaos", {"action": "delay", "mode": "all", "selector": s(self.app),
                                                 "delay": {"latency": "300ms", "jitter": "50ms"}}),
            "packet_loss": ("networkchaos", {"action": "loss", "mode": "all", "selector": s(self.app),
                                             "loss": {"loss": "30", "correlation": "25"}}),
            "dns_failure": ("dnschaos", {"action": "error", "mode": "all", "selector": s(self.app),
                                         "patterns": ["*"]}),
            "database_failure": pk("pod-failure", s(self.db), "all"),
            "redis_failure": pk("pod-failure", s(self.cache), "all"),
            "dependency_failure": ("networkchaos", {"action": "partition", "mode": "all", "direction": "to",
                                                    "selector": s(self.app),
                                                    "target": {"mode": "all", "selector": s(self.dep)}}),
            "az_failure": pk("pod-kill", {"namespaces": [self.ns],
                                          "nodeSelectors": {"topology.kubernetes.io/zone": self.zone}}, "all"),
            "disk_exhaustion": ("iochaos", {"action": "fault", "mode": "all", "selector": s(self.db),
                                            "volumePath": "/var/lib/postgresql/data", "errno": 28, "percent": 100}),
        }
        if f.name in table:
            plural, spec = table[f.name]
            self._chaos(plural, n, spec)
        elif f.name == "node_failure":                       # cordon + evict everything on one node
            node = self._app_pods()[0].spec.node_name
            self.core.patch_node(node, {"spec": {"unschedulable": True}})
            self.cordoned.append(node)
            for p in self.core.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node}").items:
                if p.metadata.namespace == self.ns:
                    self.core.delete_namespaced_pod(p.metadata.name, self.ns)
        elif f.name == "app_crash":                          # ship a bad image
            d = self.apps.read_namespaced_deployment(self.app, self.ns)
            self.restore.append(("image", d.spec.template.spec.containers[0].image))
            self._patch_container({"image": "invalid/does-not-exist:broken"})
        elif f.name == "cert_failure":                       # corrupt the TLS secret
            sec = self.core.read_namespaced_secret("tls-cert", self.ns)
            self.restore.append(("secret", sec.data))
            self.core.patch_namespaced_secret("tls-cert", self.ns, {"data": {"tls.crt": "aW52YWxpZA=="}})

    def _patch_container(self, patch):
        patch = {"name": self.app, **patch}
        self.apps.patch_namespaced_deployment(self.app, self.ns,
                                              {"spec": {"template": {"spec": {"containers": [patch]}}}})

    def cleanup(self):
        for plural, name in self.created:
            try:
                self.crd.delete_namespaced_custom_object(GROUP, VER, self.ns, plural, name)
            except Exception:
                pass
        for node in self.cordoned:
            self.core.patch_node(node, {"spec": {"unschedulable": False}})
        for kind, val in self.restore:
            if kind == "image":
                self._patch_container({"image": val})
            elif kind == "secret":
                self.core.patch_namespaced_secret("tls-cert", self.ns, {"data": val})
        self.created, self.cordoned, self.restore = [], [], []

    # ---- observation: cluster state + injected-experiment labels -------------
    def signals(self) -> List[str]:
        out = []
        for p in self.core.list_namespaced_pod(self.ns).items:
            for cs in (p.status.container_statuses or []):
                w = cs.state.waiting
                if w and w.reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
                    out.append("CrashLoopBackOff")
                t = (cs.last_state.terminated if cs.last_state else None)
                if t and t.reason == "OOMKilled":
                    out.append("OOMKilled")
        for node in self.core.list_node().items:
            ready = next((c.status for c in node.status.conditions if c.type == "Ready"), "True")
            if ready != "True":
                out.append("NodeNotReady")
        # Chaos Mesh objects carry the ground truth; swap for Prometheus alerts in production.
        mapping = {"cpu-exhaustion": "CPUThrottling", "network-latency": "HighNetworkRTT",
                   "packet-loss": "PacketLoss", "dns-failure": "DNSResolutionFailure",
                   "database-failure": "DBUnavailable", "redis-failure": "CacheUnavailable",
                   "dependency-failure": "UpstreamDown", "az-failure": "AZUnavailable",
                   "disk-exhaustion": "DiskPressure", "pod-termination": "PodTerminated"}
        out += [mapping[n] for _, n in self.created if n in mapping]
        if any(k == "secret" for k, _ in self.restore):
            out.append("TLSHandshakeFailure")
        return list(dict.fromkeys(out))

    # ---- recovery actions -----------------------------------------------------
    def _hook(self, action):
        cmd = self.hooks.get(action)
        if not cmd:
            raise NotImplementedError(f"no hook configured for {action}")
        subprocess.run(cmd, shell=True, check=True, timeout=120)

    def _rollout_restart(self, deploy=None):
        ts = {"kubectl.kubernetes.io/restartedAt": time.strftime("%FT%TZ", time.gmtime())}
        self.apps.patch_namespaced_deployment(deploy or self.app, self.ns,
            {"spec": {"template": {"metadata": {"annotations": ts}}}})

    def _delete_chaos(self, *plurals):
        for plural, name in list(self.created):
            if plural in plurals:
                self.crd.delete_namespaced_custom_object(GROUP, VER, self.ns, plural, name)
                self.created.remove((plural, name))

    def _set_env(self, **env):
        self._patch_container({"env": [{"name": k, "value": v} for k, v in env.items()]})

    def start_action(self, action):
        self.action_error = None
        try:
            {
                "restart_pod": self._rollout_restart,
                "drain_reschedule": lambda: [self.core.delete_namespaced_pod(p.metadata.name, self.ns)
                                             for p in self._app_pods()],
                "scale_out": lambda: self.apps.patch_namespaced_deployment_scale(
                    self.app, self.ns, {"spec": {"replicas": self.apps.read_namespaced_deployment(
                        self.app, self.ns).spec.replicas + 2}}),
                "raise_limits_restart": lambda: self._patch_container(
                    {"resources": {"limits": {"memory": "1Gi"}}}),
                "remove_netem": lambda: self._delete_chaos("networkchaos"),
                "restart_coredns": lambda: self.apps.patch_namespaced_deployment(
                    "coredns", "kube-system", {"spec": {"template": {"metadata": {"annotations": {
                        "restartedAt": str(time.time())}}}}}),
                "rollback_restart": lambda: self.cleanup_bad_release(),
                "rotate_cert": lambda: self.core.delete_namespaced_secret("tls-cert", self.ns),  # cert-manager reissues
                "shift_traffic_zone": lambda: self._rollout_restart(),
                "cleanup_expand_volume": lambda: self._delete_chaos("iochaos"),
                "bypass_cache": lambda: self._set_env(CACHE_ENABLED="false"),
                "open_circuit_breaker": lambda: self._set_env(CIRCUIT_BREAKER_OPEN="true"),
            }.get(action, lambda: self._hook(action))()
        except Exception as e:                                  # noqa: BLE001
            self.action_error = e

    def cleanup_bad_release(self):
        for kind, val in list(self.restore):
            if kind == "image":
                self._patch_container({"image": val})
                self.restore.remove((kind, val))

    def finish_action(self, action) -> bool:
        return self.action_error is None
