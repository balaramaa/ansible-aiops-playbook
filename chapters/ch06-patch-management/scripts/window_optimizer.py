#!/usr/bin/env python3
"""
window_optimizer.py — Chapter 6, Listing 6-5
Predict optimal maintenance windows from historical Prometheus telemetry.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    python3 window_optimizer.py --group prod_web --risk-tier medium
    python3 window_optimizer.py --group lab --risk-tier critical --mock
"""

import argparse, json, logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
import requests

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PROMETHEUS_URL = "http://prometheus.company.com:9090"
DAY_NAMES      = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]


def query_prometheus(query, start, end, step="1h"):
    """Execute a PromQL range query."""
    params = {
        "query": query,
        "start": start.isoformat(),
        "end":   end.isoformat(),
        "step":  step,
    }
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query_range",
        params=params, timeout=30
    )
    response.raise_for_status()
    return response.json().get("data", {}).get("result", [])


def analyze_traffic_patterns(host_group: str, days: int = 30) -> dict:
    """Analyze historical CPU load by hour-of-week."""
    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    query = (
        f'avg by (instance) ('
        f'rate(node_cpu_seconds_total{{'
        f'job="node-exporter",mode!="idle",'
        f'instance=~"{host_group}.*"}}[5m])'
        f')'
    )
    results = query_prometheus(query, start, end)

    hourly_load: dict = defaultdict(list)
    for series in results:
        for ts, value in series["values"]:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            how = dt.weekday() * 24 + dt.hour
            hourly_load[how].append(float(value))

    avg_load = {
        h: (sum(v)/len(v))*100
        for h, v in hourly_load.items()
    }

    scored = {}
    for hour, load in avg_load.items():
        dow = hour // 24
        hod = hour % 24
        score = 100 - load
        if dow >= 5 and 0 <= hod <= 6: score += 20   # Weekend nights
        if dow < 5 and 8 <= hod <= 18: score -= 30   # Business hours
        scored[hour] = round(min(max(score, 0), 100), 1)

    return scored


def recommend_windows(host_group: str,
                      risk_tier: str,
                      n: int = 3,
                      mock: bool = False) -> list:
    """
    Recommend top N maintenance windows.

    Returns list of dicts with window label and score.
    """
    if mock:
        scored = _default_windows()
    else:
        try:
            scored = analyze_traffic_patterns(host_group)
        except Exception as e:
            log.warning(f"Prometheus unavailable ({e}) — using default windows")
            scored = _default_windows()

    # Critical risk: find earliest available window (next 6 hours)
    if risk_tier == "critical":
        log.warning("CRITICAL risk — recommending earliest low-load window")
        now_how = _hour_of_week(datetime.now(timezone.utc))
        candidates = {h: s for h, s in scored.items()
                      if now_how < h <= now_how + 6}
        if candidates:
            scored = candidates

    top = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:n]

    recommendations = []
    for how, score in top:
        day  = DAY_NAMES[how // 24]
        hour = how % 24
        recommendations.append({
            "window":     f"{day} {hour:02d}:00–{(hour+2)%24:02d}:00 UTC",
            "score":      score,
            "risk_tier":  risk_tier,
            "day":        day,
            "hour":       hour,
        })
    return recommendations


def _hour_of_week(dt: datetime) -> int:
    return dt.weekday() * 24 + dt.hour


def _default_windows() -> dict:
    """Fallback when Prometheus is unavailable."""
    return {
        6*24+2: 95,   # Sun 02:00
        5*24+2: 90,   # Sat 02:00
        6*24+4: 85,   # Sun 04:00
        5*24+4: 80,   # Sat 04:00
        0*24+2: 60,   # Mon 02:00
    }


def main():
    parser = argparse.ArgumentParser(description="Maintenance window optimizer")
    parser.add_argument("--group",     required=True)
    parser.add_argument("--risk-tier", default="medium",
                        choices=["critical","high","medium","low"])
    parser.add_argument("--count",     type=int, default=3)
    parser.add_argument("--mock",      action="store_true")
    args = parser.parse_args()

    windows = recommend_windows(
        args.group, args.risk_tier, args.count, args.mock)

    print(f"\nTop {args.count} maintenance windows for '{args.group}' "
          f"(risk: {args.risk_tier}):")
    print(f"{'─'*50}")
    for i, w in enumerate(windows, 1):
        print(f"  {i}. {w['window']:25} Score: {w['score']}/100")


if __name__ == "__main__":
    main()
