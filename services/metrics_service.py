# =========================
# services/metrics_service.py
# Sistema de métricas (Pro+)
# =========================

import time
import threading
from typing import Dict, Any

from utils.logger import log_event


# =========================
# STORAGE
# =========================
_metrics = {}
_metrics_lock = threading.Lock()


# =========================
# INIT
# =========================
def _init_metric(name: str):
    if name not in _metrics:
        _metrics[name] = {
            "count": 0,
            "total_time": 0.0,
            "max_time": 0.0,
            "min_time": None,
            "last_value": None,
        }


# =========================
# COUNTER
# =========================
def increment(metric_name: str, value: int = 1):
    with _metrics_lock:
        _init_metric(metric_name)
        _metrics[metric_name]["count"] += value


# =========================
# TIMING
# =========================
def record_time(metric_name: str, duration: float):
    with _metrics_lock:
        _init_metric(metric_name)

        m = _metrics[metric_name]
        m["count"] += 1
        m["total_time"] += duration
        m["last_value"] = duration

        if duration > m["max_time"]:
            m["max_time"] = duration

        if m["min_time"] is None or duration < m["min_time"]:
            m["min_time"] = duration


# =========================
# DECORATOR
# =========================
def track_time(metric_name: str):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            duration = time.time() - start

            record_time(metric_name, duration)

            log_event(
                "METRIC_TIME",
                metric=metric_name,
                duration=round(duration, 4)
            )

            return result
        return wrapper
    return decorator


# =========================
# GAUGE
# =========================
def set_value(metric_name: str, value: Any):
    with _metrics_lock:
        _init_metric(metric_name)
        _metrics[metric_name]["last_value"] = value


# =========================
# GET METRICS
# =========================
def get_metrics() -> Dict[str, Any]:
    with _metrics_lock:
        result = {}

        for name, m in _metrics.items():
            avg_time = 0
            if m["count"] > 0:
                avg_time = m["total_time"] / m["count"]

            result[name] = {
                "count": m["count"],
                "avg_time": round(avg_time, 4),
                "max_time": round(m["max_time"], 4),
                "min_time": round(m["min_time"], 4) if m["min_time"] else None,
                "last_value": m["last_value"],
            }

        return result


# =========================
# RESET
# =========================
def reset_metrics():
    global _metrics
    with _metrics_lock:
        _metrics = {}
    log_event("METRICS_RESET")


# =========================
# HEALTH SNAPSHOT
# =========================
def metrics_health():
    data = get_metrics()

    status = "healthy"

    for name, m in data.items():
        if m["avg_time"] > 2:  # ejemplo threshold
            status = "slow"

    return {
        "status": status,
        "metrics": data
    }