#!/usr/bin/env python3
"""Benchmark model-router against a single-model baseline.

Runs each task under each config in a fresh sandbox (a copy of fixture/, a
local bare repo as origin, and a fake `gh`), then grades the result and records
cost per model from Claude Code's headless JSON output.

    python3 bench/run.py --reps 3
    python3 bench/report.py
"""
import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BENCH = Path(__file__).resolve().parent
PLUGIN = BENCH.parent / "plugins" / "model-router"
RESULTS = BENCH / "results"

CONFIGS = {
    # The baseline: one model for everything, no routing.
    "opus-solo": {"model": "opus", "plugin": False},
    # The routed setup: a cheaper main model that delegates to pinned agents.
    "routed": {"model": "sonnet", "plugin": True},
    # Opus main session that still delegates chores (PRs, tickets) down.
    "routed-opus": {"model": "opus", "plugin": True},
}


# --- sandbox helpers -------------------------------------------------------

def sh(cmd, cwd, env=None, check=True):
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, text=True, capture_output=True)


def gh_calls(box, *prefix):
    log = box / "gh.log"
    if not log.exists():
        return []
    calls = [json.loads(l) for l in log.read_text().splitlines() if l.strip()]
    return [c for c in calls if c["argv"][: len(prefix)] == list(prefix)]


def tests_pass(box, env, start_dir="tests"):
    r = sh([sys.executable, "-m", "unittest", "discover", "-s", start_dir, "-t", start_dir],
           cwd=box / "repo", env={**env, "PYTHONPATH": str(box / "repo")}, check=False)
    return r.returncode == 0


def origin_branches(box, env):
    r = sh(["git", "--git-dir", str(box / "origin.git"), "branch", "--format=%(refname:short)"], cwd=box, env=env)
    return [b for b in r.stdout.split() if b != "main"]


def worktree_clean(box, env):
    return sh(["git", "status", "--porcelain"], cwd=box / "repo", env=env).stdout.strip() == ""


# --- tasks -----------------------------------------------------------------

def setup_open_pr(box, env):
    src = box / "repo" / "textstats" / "__init__.py"
    src.write_text(src.read_text() + '''

def char_count(text, include_spaces=True):
    """Return the number of characters in text, optionally ignoring whitespace."""
    if include_spaces:
        return len(text)
    return sum(1 for c in text if not c.isspace())
''')
    test = box / "repo" / "tests" / "test_char_count.py"
    test.write_text('''import unittest

from textstats import char_count


class TestCharCount(unittest.TestCase):
    def test_char_count(self):
        self.assertEqual(char_count("a b"), 3)
        self.assertEqual(char_count("a b", include_spaces=False), 2)


if __name__ == "__main__":
    unittest.main()
''')


def check_feature(box, env):
    hidden = box / "hidden"
    shutil.copytree(BENCH / "hidden", hidden)
    return {
        "read_ticket": bool(gh_calls(box, "issue", "view")),
        "existing_tests_pass": tests_pass(box, env),
        "hidden_tests_pass": tests_pass(box, env, start_dir=str(hidden)),
        "branch_pushed": bool(origin_branches(box, env)),
        "pr_opened": bool(gh_calls(box, "pr", "create")),
    }


def check_file_bug(box, env):
    created = gh_calls(box, "issue", "create")
    text = " ".join(f"{c.get('title') or ''} {c.get('body') or ''}" for c in created)
    unchanged = sh(["git", "diff", "--quiet", "HEAD", "--", "textstats"], cwd=box / "repo", env=env, check=False)
    return {
        "issue_created": bool(created),
        "mentions_function": "word_count" in text,
        "code_untouched": unchanged.returncode == 0,
    }


def check_open_pr(box, env):
    pushed = origin_branches(box, env)
    has_change = any(
        "char_count" in sh(["git", "--git-dir", str(box / "origin.git"), "show", f"{b}:textstats/__init__.py"],
                           cwd=box, env=env, check=False).stdout
        for b in pushed
    )
    return {
        "worktree_clean": worktree_clean(box, env),
        "change_pushed": has_change,
        "pr_opened": bool(gh_calls(box, "pr", "create")),
    }


FEATURE = "Pull GitHub issue #12, plan the change, implement it with tests, make sure the " \
          "test suite passes, then commit it on a new branch and open a PR for it."
FILE_BUG = "word_count returns 1 for an empty string, but it should return 0. Don't fix it, " \
           "just open a GitHub issue describing the bug."
OPEN_PR = "My changes are done. Commit them on a new branch, push, and open a PR."

TASKS = {
    "feature": {"prompt": FEATURE, "setup": None, "check": check_feature, "warmup": False},
    "file-bug": {"prompt": FILE_BUG, "setup": None, "check": check_file_bug, "warmup": False},
    "open-pr": {"prompt": OPEN_PR, "setup": setup_open_pr, "check": check_open_pr, "warmup": False},
    # The same chores at the end of a long session (see WARMUP_PROMPT).
    "file-bug-long": {"prompt": FILE_BUG, "setup": None, "check": check_file_bug, "warmup": True},
    "open-pr-long": {"prompt": OPEN_PR, "setup": setup_open_pr, "check": check_open_pr, "warmup": True},
}
SHORT_TASKS = [name for name, t in TASKS.items() if not t["warmup"]]


# --- long-session warm-up --------------------------------------------------

WARMUP_PROMPT = (
    "I'm new to this repo. Read every file under legacy/ in full with the Read tool yourself, "
    "ten files at a time in parallel; don't skim, grep, sample or use subagents. Then give me a "
    "one-line summary of each module and a short paragraph on how they fit together."
)

NOUNS = ["invoice", "ledger", "account", "shipment", "order", "customer", "payment", "refund",
         "warehouse", "carrier", "tariff", "quote", "contract", "vendor", "batch", "report"]
VERBS = ["reconcile", "validate", "normalize", "aggregate", "export", "schedule", "merge",
         "split", "audit", "price", "route", "archive"]
FIELDS = ["amount", "weight", "quantity", "discount", "tax", "balance", "fee", "score"]


def legacy_module(rng, index):
    """Return one plausible but synthetic business-logic module (~10 KB)."""
    noun = NOUNS[index % len(NOUNS)]
    lines = [f'"""{noun.capitalize()} processing helpers (module {index:02d})."""', "",
             "import datetime", "import logging", "", "log = logging.getLogger(__name__)", ""]
    lines += [f"class {noun.capitalize()}Store:",
              f'    """In-memory store of {noun} records keyed by id."""', "",
              "    def __init__(self):", "        self._items = {}", "",
              "    def put(self, item_id, record):", "        self._items[item_id] = dict(record)", "",
              "    def get(self, item_id):", "        return self._items.get(item_id)", "",
              "    def all(self):", "        return list(self._items.values())", ""]
    for j in range(14):
        verb, field, other = rng.choice(VERBS), rng.choice(FIELDS), rng.choice(FIELDS)
        threshold, factor = rng.randint(1, 500), rng.choice([0.5, 1.1, 1.25, 2, 3])
        name = f"{verb}_{noun}_{field}_{j}"
        lines += [
            "", f"def {name}(records, threshold={threshold}, today=None):",
            f'    """{verb.capitalize()} {noun} records on {field}, weighting by {other} above {threshold}."""',
            "    today = today or datetime.date.today()",
            "    total = 0.0",
            "    kept = []",
            "    for record in records:",
            f'        value = record.get("{field}", 0)',
            f'        if record.get("{other}", 0) > threshold:',
            f"            value *= {factor}",
            '        if record.get("expires") and record["expires"] < today:',
            f'            log.debug("skipping expired {noun} %s", record.get("id"))',
            "            continue",
            "        total += value",
            "        kept.append(record)",
            "    if not kept:",
            "        return {\"total\": 0.0, \"count\": 0, \"mean\": 0.0}",
            "    return {\"total\": round(total, 2), \"count\": len(kept), \"mean\": round(total / len(kept), 2)}",
        ]
    return "\n".join(lines) + "\n"


def add_legacy_code(box, env, files):
    """Commit a synthetic legacy/ package to the sandbox repo; return its size in characters."""
    stash = sh(["git", "stash", "-u"], cwd=box / "repo", env=env).stdout  # keep task setup out of this commit
    legacy = box / "repo" / "legacy"
    legacy.mkdir()
    rng = random.Random(1234)  # Same code in every sandbox, so configs see identical context.
    size = 0
    for i in range(files):
        text = legacy_module(rng, i)
        (legacy / f"{NOUNS[i % len(NOUNS)]}_{i:02d}.py").write_text(text)
        size += len(text)
    sh(["git", "add", "legacy"], cwd=box / "repo", env=env)
    sh(["git", "commit", "-qm", "Add legacy modules"], cwd=box / "repo", env=env)
    sh(["git", "push", "-q", "origin", "main"], cwd=box / "repo", env=env)
    if "Saved" in stash:
        sh(["git", "stash", "pop", "-q"], cwd=box / "repo", env=env)
    return size


# --- runner ----------------------------------------------------------------

def make_sandbox():
    box = Path(tempfile.mkdtemp(prefix="model-router-bench-"))
    gitconfig = box / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Bench Bot\n\temail = bench@example.com\n[init]\n\tdefaultBranch = main\n")
    env = {
        **os.environ,
        "PATH": f"{BENCH / 'shims'}{os.pathsep}{os.environ['PATH']}",
        "GH_LOG": str(box / "gh.log"),
        "GIT_CONFIG_GLOBAL": str(gitconfig),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    repo = box / "repo"
    shutil.copytree(BENCH / "fixture", repo)
    sh(["git", "init", "-q", "--bare", str(box / "origin.git")], cwd=box, env=env)
    sh(["git", "init", "-q"], cwd=repo, env=env)
    sh(["git", "add", "-A"], cwd=repo, env=env)
    sh(["git", "commit", "-qm", "Initial commit"], cwd=repo, env=env)
    sh(["git", "remote", "add", "origin", str(box / "origin.git")], cwd=repo, env=env)
    sh(["git", "push", "-q", "-u", "origin", "main"], cwd=repo, env=env)
    return box, env


def claude_cmd(config, budget, permission_mode, effort, extra=()):
    cmd = [
        "claude", "-p",
        "--model", config["model"],
        "--no-session-persistence",
        # Runs happen in a throwaway sandbox with a local origin and a fake gh.
        # An allowlist would penalize whichever model phrases commands in a way
        # the rules don't match (heredocs, && chains), skewing the comparison.
        "--permission-mode", permission_mode,
        # Only project settings, and the installed copy of the plugin disabled,
        # so both configs see the same environment apart from --plugin-dir.
        "--setting-sources", "project",
        "--settings", json.dumps({"enabledPlugins": {"model-router@model-router": False}}),
        "--strict-mcp-config",
        "--max-budget-usd", str(budget),
        *extra,
    ]
    if config["plugin"]:
        cmd += ["--plugin-dir", str(PLUGIN)]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def converse(cmd, prompts, cwd, env, log_path):
    """Send prompts one after another to a single live session; return each turn's result event.

    One process keeps the prompt cache warm between messages, as in a real
    session (resuming a saved session rebuilds the cache instead).
    """
    cmd = cmd + ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    results = []
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, text=True, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=log)
        try:
            for prompt in prompts:
                proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
                proc.stdin.flush()
                for line in proc.stdout:
                    # Tool managers such as mise may print banners on stdout.
                    if line.startswith("{") and json.loads(line).get("type") == "result":
                        results.append(json.loads(line))
                        break
                else:
                    break  # process exited without a result
                if results[-1].get("is_error"):
                    break
        finally:
            proc.stdin.close()
            proc.wait()
    return results


def model_costs(result):
    return {m: u.get("costUSD", 0) for m, u in (result.get("modelUsage") or {}).items()}


def run_one(config_name, task_name, rep, budget, keep, permission_mode, effort, warmup_files):
    config, task = CONFIGS[config_name], TASKS[task_name]
    box, env = make_sandbox()
    if task["setup"]:
        task["setup"](box, env)
    record = {"config": config_name, "task": task_name, "rep": rep, "effort": effort, "sandbox": str(box)}

    prompts = [task["prompt"]]
    if task["warmup"]:
        # Build a long session first, then ask for the chore in the same session
        # and count only the chore's cost: the case where a PR or ticket comes at
        # the end of real work with a large context already loaded.
        record["context_chars"] = add_legacy_code(box, env, warmup_files)
        prompts.insert(0, WARMUP_PROMPT)

    started = time.time()
    results = converse(claude_cmd(config, budget, permission_mode, effort), prompts,
                       box / "repo", env, box / "claude-stderr.log")
    record["wall_s"] = round(time.time() - started, 1)
    if len(results) < len(prompts) or any(r.get("is_error") for r in results):
        last = results[-1] if results else {}
        error = last.get("result") or (box / "claude-stderr.log").read_text()[-2000:]
        stage = "warm-up" if task["warmup"] and len(results) <= 1 else "task"
        record.update(error=f"{stage}: {error}", passed=False, cost_usd=last.get("total_cost_usd"))
        return record, last or None

    out = results[-1]
    # Costs and subagent counts are cumulative over the session, so the
    # chore's share is what it added on top of the warm-up.
    before = results[0] if task["warmup"] else {}
    if task["warmup"]:
        record["warmup_cost_usd"] = before.get("total_cost_usd")
        record["warmup_subagents"] = (before.get("subagent_stats") or {}).get("spawned", 0)
    warm_models, warm_agents = model_costs(before), Counter((before.get("subagent_stats") or {}).get("by_type", {}))
    agents = Counter((out.get("subagent_stats") or {}).get("by_type", {}))
    agents.subtract(warm_agents)

    checks = task["check"](box, env)
    record.update(
        passed=all(checks.values()),
        checks=checks,
        cost_usd=round(out.get("total_cost_usd", 0) - before.get("total_cost_usd", 0), 6),
        cost_by_model={m: round(c - warm_models.get(m, 0), 6) for m, c in model_costs(out).items()},
        num_turns=out.get("num_turns"),
        duration_s=round((out.get("duration_ms") or 0) / 1000, 1),
        subagents={a: n for a, n in agents.items() if n > 0},
        permission_denials=len(out.get("permission_denials") or []),
        stop=out.get("terminal_reason") or out.get("subtype"),
    )
    if not keep:
        shutil.rmtree(box, ignore_errors=True)
        record.pop("sandbox")
    return record, out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--configs", default="opus-solo,routed", help=f"comma-separated, from: {', '.join(CONFIGS)}")
    p.add_argument("--tasks", default=",".join(SHORT_TASKS),
                   help=f"comma-separated, from: {', '.join(TASKS)} (default: the short ones)")
    p.add_argument("--warmup-files", type=int, default=40,
                   help="legacy modules read in the warm-up of *-long tasks, ~3k tokens each (default 40)")
    p.add_argument("--reps", type=int, default=3, help="runs per config and task (default 3)")
    p.add_argument("--jobs", type=int, default=3, help="runs in parallel (default 3)")
    p.add_argument("--budget", type=float, default=3.0, help="max USD per run (default 3)")
    p.add_argument("--keep", action="store_true", help="keep sandboxes for inspection")
    p.add_argument("--permission-mode", default="bypassPermissions", choices=["bypassPermissions", "auto"],
                   help="bypassPermissions (default) never blocks a command; auto keeps Claude Code's "
                        "safety classifier on, at the risk of the odd denied command")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"],
                   help="effort for the main session (default: Claude Code's default); "
                        "agents use the effort in their own frontmatter")
    args = p.parse_args()

    configs, tasks = args.configs.split(","), args.tasks.split(",")
    for name in configs:
        if name not in CONFIGS:
            p.error(f"unknown config {name!r}")
    for name in tasks:
        if name not in TASKS:
            p.error(f"unknown task {name!r}")

    run_id = time.strftime("%Y%m%d-%H%M%S")
    out_dir = RESULTS / run_id
    out_dir.mkdir(parents=True)
    # Interleave configs so drift over time (load, cache) hits both evenly.
    jobs = [(c, t, r) for r in range(args.reps) for t in tasks for c in configs]
    print(f"{len(jobs)} runs -> {out_dir}", flush=True)

    with ThreadPoolExecutor(args.jobs) as pool, open(out_dir / "results.jsonl", "w") as f:
        futures = [pool.submit(run_one, c, t, r, args.budget, args.keep, args.permission_mode, args.effort, args.warmup_files)
                   for c, t, r in jobs]
        for fut in futures:
            record, raw = fut.result()
            f.write(json.dumps(record) + "\n")
            f.flush()
            if raw:
                (out_dir / f"{record['config']}-{record['task']}-{record['rep']}.json").write_text(json.dumps(raw, indent=2))
            cost = f"${record['cost_usd']:.3f}" if record.get("cost_usd") is not None else "n/a"
            status = "PASS" if record["passed"] else "FAIL"
            print(f"{status}  {record['config']:<12} {record['task']:<9} rep {record['rep']}  {cost}  "
                  f"{record.get('subagents') or ''}{'  ' + record['error'][:200] if record.get('error') else ''}", flush=True)

    print(f"\npython3 {BENCH / 'report.py'} {out_dir}")


if __name__ == "__main__":
    main()
