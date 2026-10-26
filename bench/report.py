#!/usr/bin/env python3
"""Summarize a benchmark run: cost, pass rate and delegation per config.

    python3 bench/report.py               # latest run
    python3 bench/report.py results/<id>  # a specific run
"""
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def load(run_dir):
    return [json.loads(l) for l in (run_dir / "results.jsonl").read_text().splitlines() if l.strip()]


def money(x):
    return f"${x:.3f}" if x is not None else "n/a"


def summarize(records):
    costs = [r["cost_usd"] for r in records if r.get("cost_usd") is not None]
    passed = [r for r in records if r["passed"]]
    by_model = defaultdict(float)
    agents = Counter()
    for r in records:
        for m, c in (r.get("cost_by_model") or {}).items():
            by_model[m] += c
        agents.update(r.get("subagents") or {})
    return {
        "n": len(records),
        "pass": len(passed),
        "mean": statistics.mean(costs) if costs else None,
        "median": statistics.median(costs) if costs else None,
        "total": sum(costs),
        # Cost per successful outcome: a cheap failure isn't a saving.
        "per_pass": sum(costs) / len(passed) if passed else None,
        "turns": statistics.mean([r["num_turns"] for r in records if r.get("num_turns")] or [0]),
        "secs": statistics.mean([r["duration_s"] for r in records if r.get("duration_s")] or [0]),
        "by_model": dict(by_model),
        "agents": dict(agents),
    }


def main():
    run_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else max(RESULTS.iterdir())
    records = load(run_dir)
    configs = list(dict.fromkeys(r["config"] for r in records))
    tasks = list(dict.fromkeys(r["task"] for r in records))

    print(f"Run {run_dir.name}: {len(records)} runs\n")
    header = f"{'task':<10} {'config':<12} {'pass':>6} {'mean':>8} {'median':>8} {'per pass':>9} {'turns':>6} {'secs':>6}  subagents"
    print(header)
    print("-" * len(header))
    for task in tasks + ["ALL"]:
        for config in configs:
            rs = [r for r in records if r["config"] == config and (task == "ALL" or r["task"] == task)]
            if not rs:
                continue
            s = summarize(rs)
            agents = ", ".join(f"{a.split(':')[-1]}×{n}" for a, n in sorted(s["agents"].items())) or "-"
            print(f"{task:<10} {config:<12} {s['pass']:>2}/{s['n']:<3} {money(s['mean']):>8} {money(s['median']):>8} "
                  f"{money(s['per_pass']):>9} {s['turns']:>6.1f} {s['secs']:>6.0f}  {agents}")
        print()

    warm = [r for r in records if r.get("warmup_cost_usd") is not None]
    if warm:
        print("Long-session warm-ups (excluded from the costs above):")
        for config in configs:
            rs = [r for r in warm if r["config"] == config]
            if rs:
                print(f"  {config:<12} mean {money(statistics.mean(r['warmup_cost_usd'] for r in rs))} per warm-up, "
                      f"~{rs[0]['context_chars'] // 4 // 1000}k tokens of code read")
        leaky = sum(1 for r in warm if r.get("warmup_subagents"))
        if leaky:
            print(f"  {leaky} warm-up(s) used subagents, so less code reached the main context than intended.")
        print()

    print("Spend by model (all tasks):")
    for config in configs:
        s = summarize([r for r in records if r["config"] == config])
        parts = ", ".join(f"{m} {money(c)}" for m, c in sorted(s["by_model"].items(), key=lambda kv: -kv[1]))
        print(f"  {config:<12} {money(s['total'])} total: {parts}")

    base = "opus-solo"
    if base in configs:
        b = summarize([r for r in records if r["config"] == base])
        print(f"\nVersus {base}:")
        for config in configs:
            if config == base:
                continue
            s = summarize([r for r in records if r["config"] == config])
            if b["per_pass"] and s["per_pass"]:
                delta = (s["per_pass"] - b["per_pass"]) / b["per_pass"] * 100
                print(f"  {config:<12} cost per passing run {money(s['per_pass'])} vs {money(b['per_pass'])} "
                      f"({delta:+.0f}%), pass rate {s['pass']}/{s['n']} vs {b['pass']}/{b['n']}")
            else:
                print(f"  {config:<12} not comparable: no passing runs on one side")

    failures = [r for r in records if not r["passed"]]
    if failures:
        print("\nFailures:")
        for r in failures:
            why = r.get("error") or ", ".join(k for k, v in (r.get("checks") or {}).items() if not v) or r.get("stop")
            print(f"  {r['config']:<12} {r['task']:<9} rep {r['rep']}: {why}")
    denied = sum(r.get("permission_denials") or 0 for r in records)
    if denied:
        print(f"\n{denied} tool calls were denied; check the raw JSON files in {run_dir} before trusting these numbers.")


if __name__ == "__main__":
    main()
