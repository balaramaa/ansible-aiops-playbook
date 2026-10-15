#!/usr/bin/env python3
"""
cloud_cost_analyzer.py — Chapter 9, Listing 9-9
AI-driven cloud cost governance and right-sizing recommendations.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Mock mode (no AWS credentials needed)
    python3 cloud_cost_analyzer.py --mock

    # Live AWS analysis
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    python3 cloud_cost_analyzer.py --region us-east-1

    # JSON output for pipeline integration
    python3 cloud_cost_analyzer.py --mock --json

    # Auto-apply safe recommendations (stop idle instances)
    python3 cloud_cost_analyzer.py --mock --apply-safe

Requirements:
    pip3 install boto3 botocore
"""

import argparse, json, logging, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "../../ch04-llm-playbook-generation/scripts")
from llm_provider import get_provider

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

COST_ANALYST_PROMPT = """
You are a cloud cost optimization expert analyzing AWS EC2 utilization data.
Return ONLY this JSON structure — no prose, no markdown:

{
  "monthly_waste_estimate_usd": <float>,
  "recommendations": [
    {
      "instance_id": "<id>",
      "instance_name": "<name>",
      "issue": "over_provisioned|idle|untagged|legacy_type",
      "current_type": "<type>",
      "recommended_action": "downsize|stop|terminate|tag|convert_reserved",
      "recommended_type": "<type or null>",
      "monthly_savings_usd": <float>,
      "confidence": "high|medium|low",
      "safe_to_automate": true|false,
      "rationale": "One sentence explanation"
    }
  ],
  "quick_wins": [
    "Immediate action description (saves $X/month)"
  ],
  "summary": "One paragraph executive summary"
}

Right-sizing guidelines:
- avg CPU < 2%  AND max CPU < 10%: idle → recommend stop or terminate
- avg CPU < 10% AND max CPU < 30%: over-provisioned → downsize one size
- avg CPU < 20%: likely over-provisioned → consider downsizing
- avg CPU > 70%: may be under-provisioned → monitor but do not downsize
- Missing CostCenter tag: tag compliance issue → recommend tagging
- Older than 180 days AND avg CPU < 5%: strong stop/terminate candidate
- safe_to_automate=true only for: stop of idle non-production instances
"""

# Approximate hourly costs by instance type (USD, us-east-1, on-demand)
INSTANCE_COSTS_PER_HOUR = {
    "t3.micro":    0.0104, "t3.small":    0.0208, "t3.medium":   0.0416,
    "t3.large":    0.0832, "t3.xlarge":   0.1664, "t3.2xlarge":  0.3328,
    "m5.large":    0.0960, "m5.xlarge":   0.1920, "m5.2xlarge":  0.3840,
    "m5.4xlarge":  0.7680, "m5.8xlarge":  1.5360,
    "r5.large":    0.1260, "r5.xlarge":   0.2520, "r5.2xlarge":  0.5040,
    "r5.4xlarge":  1.0080, "r5.8xlarge":  2.0160,
    "c5.large":    0.0850, "c5.xlarge":   0.1700, "c5.2xlarge":  0.3400,
}


def get_ec2_utilization(region: str = "us-east-1", days: int = 14) -> list:
    """Retrieve EC2 utilization data from CloudWatch."""
    try:
        import boto3
        ec2 = boto3.client("ec2", region_name=region)
        cw  = boto3.client("cloudwatch", region_name=region)
    except ImportError:
        log.error("pip3 install boto3 botocore")
        sys.exit(1)

    reservations = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )

    end   = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    results = []

    for r in reservations["Reservations"]:
        for inst in r["Instances"]:
            iid   = inst["InstanceId"]
            itype = inst["InstanceType"]
            tags  = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
            launch = inst.get("LaunchTime", end)

            # CloudWatch CPU metrics
            cpu_data = cw.get_metric_statistics(
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": iid}],
                StartTime=start, EndTime=end,
                Period=86400, Statistics=["Average", "Maximum"]
            ).get("Datapoints", [])

            avg_cpu = (sum(d["Average"] for d in cpu_data) /
                      len(cpu_data)) if cpu_data else 0.0
            max_cpu = max((d["Maximum"] for d in cpu_data), default=0.0)

            hourly_cost = INSTANCE_COSTS_PER_HOUR.get(itype, 0.0)
            monthly_cost = hourly_cost * 24 * 30

            results.append({
                "instance_id":    iid,
                "instance_name":  tags.get("Name", "unnamed"),
                "instance_type":  itype,
                "environment":    tags.get("Environment", "unknown"),
                "cost_center":    tags.get("CostCenter", "UNTAGGED"),
                "managed_by":     tags.get("ManagedBy", "unknown"),
                "avg_cpu_pct":    round(avg_cpu, 1),
                "max_cpu_pct":    round(max_cpu, 1),
                "monthly_cost_usd": round(monthly_cost, 2),
                "days_running":   (end - launch).days,
                "missing_tags":   [t for t in
                    ["Name", "Environment", "CostCenter", "ManagedBy", "Team"]
                    if t not in tags],
                "launch_time":    launch.isoformat(),
            })

    log.info(f"Retrieved utilization for {len(results)} instances")
    return results


def _mock_utilization() -> list:
    """Realistic mock data for lab exercises."""
    return [
        {
            "instance_id":      "i-0abc001",
            "instance_name":    "prod-web-01",
            "instance_type":    "m5.xlarge",
            "environment":      "production",
            "cost_center":      "IT-001",
            "managed_by":       "ansible",
            "avg_cpu_pct":      3.2,
            "max_cpu_pct":      8.1,
            "monthly_cost_usd": 138.24,
            "days_running":     210,
            "missing_tags":     [],
            "launch_time":      "2024-01-15T10:00:00+00:00",
        },
        {
            "instance_id":      "i-0abc002",
            "instance_name":    "dev-db-01",
            "instance_type":    "r5.2xlarge",
            "environment":      "development",
            "cost_center":      "UNTAGGED",
            "managed_by":       "unknown",
            "avg_cpu_pct":      1.1,
            "max_cpu_pct":      3.2,
            "monthly_cost_usd": 362.88,
            "days_running":     240,
            "missing_tags":     ["CostCenter", "Team"],
            "launch_time":      "2023-12-10T08:00:00+00:00",
        },
        {
            "instance_id":      "i-0abc003",
            "instance_name":    "bastion-01",
            "instance_type":    "t3.micro",
            "environment":      "production",
            "cost_center":      "IT-001",
            "managed_by":       "ansible",
            "avg_cpu_pct":      0.3,
            "max_cpu_pct":      1.2,
            "monthly_cost_usd": 7.49,
            "days_running":     540,
            "missing_tags":     [],
            "launch_time":      "2023-06-01T00:00:00+00:00",
        },
        {
            "instance_id":      "i-0abc004",
            "instance_name":    "jenkins-build-01",
            "instance_type":    "c5.2xlarge",
            "environment":      "development",
            "cost_center":      "DEV-002",
            "managed_by":       "ansible",
            "avg_cpu_pct":      8.4,
            "max_cpu_pct":      85.2,
            "monthly_cost_usd": 244.80,
            "days_running":     90,
            "missing_tags":     [],
            "launch_time":      "2024-04-01T12:00:00+00:00",
        },
    ]


def analyze_costs(utilization: list) -> dict:
    """Use AI to analyze utilization and generate cost recommendations."""
    provider = get_provider()

    total_monthly = sum(i.get("monthly_cost_usd", 0) for i in utilization)

    prompt = f"""Analyze this EC2 utilization data and identify cost optimization opportunities.

Total monthly spend: ${total_monthly:,.2f}
Analysis period: 14 days
Instance count: {len(utilization)}

Utilization data:
{json.dumps(utilization, indent=2)}

Identify:
1. Idle instances (avg CPU < 2%) — recommend stop/terminate
2. Over-provisioned instances (avg CPU < 10%, max < 30%) — recommend downsize
3. Untagged instances — compliance risk and cost attribution issue
4. Legacy instance types — recommend modernization

Quantify monthly savings for each recommendation."""

    response = provider.generate(
        COST_ANALYST_PROMPT, prompt,
        temperature=0.0, max_tokens=2048
    )
    raw = response.content.strip()
    if raw.startswith("```"): raw = raw.split("\n", 1)[1]
    if raw.endswith("```"):   raw = raw.rsplit("\n", 1)[0]

    analysis = json.loads(raw.strip())
    analysis["analyzed_at"]        = datetime.now(timezone.utc).isoformat()
    analysis["analyzed_by"]        = response.model
    analysis["total_monthly_spend"] = total_monthly
    analysis["instance_count"]      = len(utilization)
    return analysis


def apply_safe_recommendations(analysis: dict, region: str, dry_run: bool = True) -> None:
    """Apply recommendations flagged as safe_to_automate=true."""
    try:
        import boto3
        ec2 = boto3.client("ec2", region_name=region)
    except ImportError:
        log.error("pip3 install boto3")
        return

    safe = [r for r in analysis.get("recommendations", [])
            if r.get("safe_to_automate") and
            r.get("recommended_action") in ("stop", "terminate")]

    if not safe:
        log.info("No safe-to-automate recommendations found")
        return

    for rec in safe:
        iid    = rec["instance_id"]
        action = rec["recommended_action"]
        log.info(f"{'[DRY RUN] ' if dry_run else ''}"
                 f"{action.upper()} {iid}: {rec['rationale']}")
        if not dry_run:
            if action == "stop":
                ec2.stop_instances(InstanceIds=[iid])
            elif action == "terminate":
                ec2.terminate_instances(InstanceIds=[iid])


def print_report(analysis: dict) -> None:
    """Print a human-readable cost analysis report."""
    print(f"\n{'='*60}")
    print(f"CLOUD COST ANALYSIS REPORT")
    print(f"{'='*60}")
    print(f"Analyzed : {analysis.get('instance_count', 0)} instances")
    print(f"Monthly spend: ${analysis.get('total_monthly_spend', 0):,.2f}")
    print(f"Estimated waste: ${analysis.get('monthly_waste_estimate_usd', 0):,.2f}/month")
    print(f"\nSummary: {analysis.get('summary', '')}")

    if analysis.get("quick_wins"):
        print(f"\nQuick Wins:")
        for qw in analysis["quick_wins"]:
            print(f"  • {qw}")

    recs = analysis.get("recommendations", [])
    if recs:
        sorted_recs = sorted(recs, key=lambda x: -x.get("monthly_savings_usd", 0))
        print(f"\nRecommendations ({len(recs)} total):")
        print(f"{'─'*60}")
        for r in sorted_recs:
            auto = "✔ AUTO" if r.get("safe_to_automate") else "  MANUAL"
            print(f"[{r.get('confidence','?').upper():6}] [{auto}] "
                  f"{r['instance_id']} / {r.get('instance_name','')}")
            print(f"  Action : {r.get('recommended_action','?').upper()} "
                  f"({r.get('current_type','')} → "
                  f"{r.get('recommended_type') or 'N/A'})")
            print(f"  Savings: ${r.get('monthly_savings_usd', 0):,.2f}/month")
            print(f"  Why    : {r.get('rationale','')}")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="AI-driven cloud cost analyzer"
    )
    parser.add_argument("--mock",        action="store_true",
                        help="Use mock data (no AWS credentials needed)")
    parser.add_argument("--region",      default="us-east-1")
    parser.add_argument("--days",        type=int, default=14)
    parser.add_argument("--json",        action="store_true")
    parser.add_argument("--apply-safe",  action="store_true",
                        help="Apply safe-to-automate recommendations")
    parser.add_argument("--dry-run",     action="store_true", default=True)
    args = parser.parse_args()

    log.info(f"Cloud Cost Analyzer — region={args.region} mock={args.mock}")

    utilization = _mock_utilization() if args.mock else \
                  get_ec2_utilization(args.region, args.days)

    analysis = analyze_costs(utilization)

    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print_report(analysis)

    if args.apply_safe:
        apply_safe_recommendations(
            analysis, args.region,
            dry_run=not args.mock
        )


if __name__ == "__main__":
    main()
