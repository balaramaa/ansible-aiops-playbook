#!/usr/bin/env python3
"""
anomaly_detector.py — Chapter 11, Listings 11-10 & 11-11
Statistical and AI-powered anomaly detection and capacity forecasting.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Detect anomalies (mock mode — no Prometheus needed)
    python3 anomaly_detector.py --metric node_cpu_seconds_total --mock

    # Detect anomalies (live Prometheus)
    python3 anomaly_detector.py --metric node_cpu_seconds_total \
        --prometheus http://prometheus:9090

    # Capacity forecasting
    python3 anomaly_detector.py --forecast \
        --metric node_filesystem_avail_bytes --mock

    # JSON output for pipeline integration
    python3 anomaly_detector.py --mock --json
"""

import argparse, json, logging, math, os, statistics, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ANOMALY_ANALYST_PROMPT = """
You are an infrastructure reliability engineer analyzing metric anomalies.
Given hosts with unusual metric behavior, return ONLY this JSON structure:

{
  "anomalies": [
    {
      "host": "<hostname>",
      "metric": "<metric_name>",
      "severity": "critical|high|medium|low",
      "description": "What is anomalous in plain English",
      "likely_cause": "Most probable root cause",
      "recommended_action": "What to investigate or do",
      "auto_investigate": true|false
    }
  ],
  "fleet_health": "healthy|degraded|critical",
  "summary": "One sentence fleet health status"
}

Context: Enterprise Linux servers managed by Ansible.
Baselines — CPU: 5-60% avg | Memory: 20-80% | Disk: 20-85%.
Anomaly = value deviating >2.5 standard deviations from 30-day baseline.
auto_investigate=true for medium/low severity anomalies only.
"""


def query_prometheus(query: str, prometheus_url: str) -> list:
    """Execute a PromQL instant query."""
    try:
        import requests
        response = requests.get(
            f"{prometheus_url}/api/v1/query",
            params={"query": query},
            timeout=30
        )
        response.raise_for_status()
        return response.json().get("data", {}).get("result", [])
    except Exception as e:
        log.error(f"Prometheus query failed: {e}")
        return []


def query_range(query: str, prometheus_url: str, days: int = 30,
                step: str = "1h") -> list:
    """Execute a PromQL range query."""
    try:
        import requests
        end   = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        response = requests.get(
            f"{prometheus_url}/api/v1/query_range",
            params={
                "query": query,
                "start": start.timestamp(),
                "end":   end.timestamp(),
                "step":  step,
            },
            timeout=60
        )
        response.raise_for_status()
        return response.json().get("data", {}).get("result", [])
    except Exception as e:
        log.error(f"Prometheus range query failed: {e}")
        return []


def compute_baseline(metric: str, prometheus_url: str,
                     days: int = 30) -> dict:
    """Compute per-host baseline statistics for a metric."""
    query   = f"avg_over_time({metric}[5m])"
    results = query_range(query, prometheus_url, days=days)

    baselines = {}
    for series in results:
        host   = (series["metric"].get("instance", "")
                  .split(":")[0] or
                  series["metric"].get("host", "unknown"))
        values = [float(v[1]) for v in series["values"]
                  if v[1] not in ("NaN", "+Inf", "-Inf")]
        if len(values) < 10:
            continue
        sorted_v = sorted(values)
        baselines[host] = {
            "mean":    round(statistics.mean(values), 2),
            "stddev":  round(statistics.stdev(values), 2)
                       if len(values) > 1 else 0.01,
            "p50":     round(sorted_v[len(sorted_v)//2], 2),
            "p95":     round(sorted_v[int(len(sorted_v)*0.95)], 2),
            "samples": len(values),
        }
    return baselines


def detect_anomalies(metric: str,
                     prometheus_url: str,
                     threshold: float = 2.5,
                     mock: bool = False) -> list:
    """Detect hosts with anomalous current metric values."""
    if mock:
        return _mock_anomalies(metric)

    baselines = compute_baseline(metric, prometheus_url)
    current   = query_prometheus(f"avg_over_time({metric}[5m])", prometheus_url)

    anomalies = []
    for series in current:
        host  = series["metric"].get("instance","").split(":")[0]
        try:
            value = float(series["value"][1])
        except (ValueError, IndexError):
            continue

        if host not in baselines:
            continue

        base = baselines[host]
        if base["stddev"] < 0.01:
            continue

        z_score = abs(value - base["mean"]) / base["stddev"]
        if z_score >= threshold:
            anomalies.append({
                "host":             host,
                "metric":           metric,
                "current_value":    round(value, 2),
                "baseline_mean":    base["mean"],
                "baseline_stddev":  base["stddev"],
                "z_score":          round(z_score, 2),
                "direction":        "above" if value > base["mean"] else "below",
            })

    log.info(f"Detected {len(anomalies)} anomalies for metric '{metric}'")
    return anomalies


def ai_classify_anomalies(anomalies: list) -> dict:
    """Use AI to classify anomalies and recommend actions."""
    if not anomalies:
        return {
            "anomalies":    [],
            "fleet_health": "healthy",
            "summary":      "No anomalies detected — fleet operating normally"
        }

    provider = get_provider()
    prompt = f"""Analyze these infrastructure metric anomalies:

{json.dumps(anomalies, indent=2)}

Classify severity and provide remediation recommendations."""

    response = provider.generate(
        ANOMALY_ANALYST_PROMPT, prompt,
        temperature=0.0, max_tokens=1024
    )
    raw = response.content.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]
    result = json.loads(raw.strip())
    result["analyzed_by"] = response.model
    return result


def forecast_capacity(metric: str,
                      prometheus_url: str,
                      forecast_days: int = 30,
                      mock: bool = False) -> list:
    """Forecast when hosts will hit resource limits using linear regression."""
    if mock:
        return _mock_forecasts(metric)

    results   = query_range(metric, prometheus_url, days=30, step="6h")
    forecasts = []

    for series in results:
        host   = series["metric"].get("instance","").split(":")[0]
        points = [(float(v[0]), float(v[1]))
                  for v in series["values"]
                  if v[1] not in ("NaN", "+Inf", "-Inf")]
        if len(points) < 20:
            continue

        x = [p[0] for p in points]
        y = [p[1] for p in points]
        n = len(points)
        x_mean = sum(x) / n
        y_mean = sum(y) / n

        num = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
        den = sum((xi - x_mean)**2 for xi in x)
        if den == 0:
            continue

        slope = num / den  # change per second
        slope_per_day = slope * 86400
        current = y[-1]

        if slope_per_day > 0.1:
            days_to_90  = math.ceil((90  - current) / slope_per_day)
            days_to_100 = math.ceil((100 - current) / slope_per_day)

            if 0 < days_to_90 <= forecast_days:
                forecasts.append({
                    "host":           host,
                    "metric":         metric,
                    "current_pct":    round(current, 1),
                    "trend_per_day":  round(slope_per_day, 2),
                    "days_to_90pct":  days_to_90,
                    "days_to_100pct": days_to_100,
                    "action":         f"Plan capacity expansion within {days_to_90} days",
                })

    return sorted(forecasts, key=lambda x: x["days_to_90pct"])


def _mock_anomalies(metric: str) -> list:
    return [
        {"host": "node02", "metric": metric, "current_value": 94.2,
         "baseline_mean": 42.1, "baseline_stddev": 8.3,
         "z_score": 6.3, "direction": "above"},
        {"host": "node03", "metric": metric, "current_value": 1.1,
         "baseline_mean": 38.7, "baseline_stddev": 5.2,
         "z_score": 7.2, "direction": "below"},
    ]


def _mock_forecasts(metric: str) -> list:
    return [
        {"host": "node01", "metric": metric,
         "current_pct": 78.3, "trend_per_day": 0.8,
         "days_to_90pct": 14, "days_to_100pct": 27,
         "action": "Plan capacity expansion within 14 days"},
    ]


def main():
    parser = argparse.ArgumentParser(
        description="AI-powered infrastructure anomaly detection"
    )
    parser.add_argument("--metric",
                        default="node_cpu_seconds_total")
    parser.add_argument("--prometheus",
                        default=os.environ.get("PROMETHEUS_URL",
                                               "http://localhost:9090"))
    parser.add_argument("--threshold",   type=float, default=2.5,
                        help="Z-score threshold for anomaly detection")
    parser.add_argument("--mock",        action="store_true")
    parser.add_argument("--forecast",    action="store_true",
                        help="Run capacity forecasting instead of anomaly detection")
    parser.add_argument("--days",        type=int, default=30)
    parser.add_argument("--json",        action="store_true")
    args = parser.parse_args()

    if args.forecast:
        forecasts = forecast_capacity(
            args.metric, args.prometheus, args.days, args.mock)
        if args.json:
            print(json.dumps(forecasts, indent=2))
        else:
            print(f"\nCapacity Forecast — {args.metric}")
            print(f"{'='*55}")
            if not forecasts:
                print("No capacity concerns within forecast horizon.")
            for f in forecasts:
                print(f"  HOST: {f['host']}")
                print(f"    Current: {f['current_pct']}% | "
                      f"Trend: +{f['trend_per_day']}%/day")
                print(f"    Hits 90%: {f['days_to_90pct']} days | "
                      f"Hits 100%: {f['days_to_100pct']} days")
                print(f"    Action: {f['action']}")
    else:
        anomalies  = detect_anomalies(
            args.metric, args.prometheus, args.threshold, args.mock)
        classified = ai_classify_anomalies(anomalies)

        if args.json:
            print(json.dumps(classified, indent=2))
        else:
            health = classified.get("fleet_health", "unknown")
            print(f"\nAnomaly Detection Report — {args.metric}")
            print(f"{'='*55}")
            print(f"Fleet health : {health.upper()}")
            print(f"Summary      : {classified.get('summary','')}")

            for a in classified.get("anomalies", []):
                sev = a.get("severity","?").upper()
                print(f"\n  [{sev}] {a['host']}")
                print(f"    Issue : {a['description']}")
                print(f"    Cause : {a['likely_cause']}")
                print(f"    Action: {a['recommended_action']}")

        if classified.get("fleet_health") == "critical":
            sys.exit(1)


if __name__ == "__main__":
    main()
