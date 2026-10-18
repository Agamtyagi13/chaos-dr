"""Fault catalog, recovery playbooks and action costs."""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class FaultSpec:
    name: str
    description: str
    signal: str                 # symptom the controller observes
    cap: float                  # remaining capacity multiplier (sim)
    lat: float                  # latency multiplier (sim)
    err: float                  # extra error probability (sim)
    self_heal_s: Optional[float]
    rto_s: int                  # recovery time objective
    rpo_s: int                  # recovery point objective
    cures: Tuple[str, ...]      # recovery actions that really fix it (sim)


_F = FaultSpec
FAULTS = {f.name: f for f in [
    _F("pod_termination", "Kill an application pod", "PodTerminated", .67, 1.3, .05, 20, 30, 0, ("restart_pod",)),
    _F("node_failure", "Worker node goes NotReady", "NodeNotReady", .5, 1.6, .15, 300, 60, 0, ("drain_reschedule",)),
    _F("cpu_exhaustion", "CPU stress on app pods", "CPUThrottling", .6, 3.0, .08, None, 60, 0, ("scale_out",)),
    _F("memory_exhaustion", "Memory pressure / OOM kills", "OOMKilled", .5, 2.0, .2, None, 60, 0, ("raise_limits_restart",)),
    _F("network_latency", "Inject +300ms network delay", "HighNetworkRTT", 1, 4.0, .03, None, 30, 0, ("remove_netem",)),
    _F("packet_loss", "Inject 30% packet loss", "PacketLoss", .9, 2.0, .12, None, 30, 0, ("remove_netem",)),
    _F("dns_failure", "Cluster DNS resolution errors", "DNSResolutionFailure", .3, 1.5, .6, None, 45, 0, ("use_fallback_dns",)),
    _F("database_failure", "Primary database unavailable", "DBUnavailable", .1, 1.2, .9, None, 90, 5, ("failover_db",)),
    _F("redis_failure", "Cache tier unavailable", "CacheUnavailable", .8, 5.0, .1, None, 45, 0, ("failover_redis", "bypass_cache")),
    _F("dependency_failure", "Downstream service down", "UpstreamDown", .6, 2.0, .5, None, 30, 0, ("open_circuit_breaker",)),
    _F("az_failure", "Whole availability zone lost", "AZUnavailable", .5, 1.4, .3, None, 60, 0, ("shift_traffic_zone",)),
    _F("app_crash", "Bad release crash-loops", "CrashLoopBackOff", .4, 1.5, .4, None, 90, 0, ("rollback_restart",)),
    _F("cert_failure", "TLS certificate invalid/expired", "TLSHandshakeFailure", 1, 1.0, .95, None, 60, 0, ("rotate_cert",)),
    _F("disk_exhaustion", "Disk full (ENOSPC)", "DiskPressure", .8, 1.3, .5, None, 90, 0, ("cleanup_expand_volume",)),
]}

# signal -> ordered recovery actions (primary first, then escalations).
PLAYBOOKS = {
    "PodTerminated": ["restart_pod"],
    "NodeNotReady": ["drain_reschedule"],
    "CPUThrottling": ["scale_out"],
    "OOMKilled": ["raise_limits_restart"],
    "HighNetworkRTT": ["remove_netem"],
    "PacketLoss": ["remove_netem"],
    "DNSResolutionFailure": ["restart_coredns", "use_fallback_dns"],
    "DBUnavailable": ["failover_db"],
    "CacheUnavailable": ["failover_redis", "bypass_cache"],
    "UpstreamDown": ["open_circuit_breaker"],
    "AZUnavailable": ["shift_traffic_zone"],
    "CrashLoopBackOff": ["rollback_restart"],
    "TLSHandshakeFailure": ["rotate_cert"],
    "DiskPressure": ["cleanup_expand_volume"],
}

# Typical wall-clock cost (seconds) of each action.
ACTION_COST = {
    "restart_pod": 8, "drain_reschedule": 25, "scale_out": 20,
    "raise_limits_restart": 30, "remove_netem": 3, "restart_coredns": 10,
    "use_fallback_dns": 12, "failover_db": 35, "failover_redis": 12,
    "bypass_cache": 6, "open_circuit_breaker": 4, "shift_traffic_zone": 15,
    "rollback_restart": 40, "rotate_cert": 18, "cleanup_expand_volume": 25,
}
