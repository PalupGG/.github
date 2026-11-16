#!/usr/bin/env python3
"""Baseline plan / apply / record for ADR-PLT-0028.

The record in `gitops/releases/<env>.yaml` is both the statement of intent
(`desired`) and the fact of what is deployed (`observed`). This script turns the
difference into one ordered, fail-fast list of executor dispatches, runs them,
and writes the result back.

Subcommands
  plan    --env E --mode deploy|rollback [--file F] [--to-ref R]
          [--components changed|all|a,b] [--dry-run]
  apply   --plan P [--dry-run]
  record  --file F --results R

Exit codes: 0 ok, 1 refused/failed, 2 missing credential (fail-closed).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

try:
    import yaml
except ModuleNotFoundError:  # `apply` needs JSON only; plan/record need PyYAML
    yaml = None


def need_yaml():
    if yaml is None:
        raise SystemExit("PyYAML required for this subcommand: pip install pyyaml")
    return yaml

ORDER_FILE = "releases/baseline-order.yaml"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# ---------------------------------------------------------------- helpers


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_yaml(path: str) -> dict:
    y = need_yaml()
    with open(path, encoding="utf-8") as fh:
        data = y.safe_load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: expected a mapping at top level")
    return data


def load_at_ref(ref: str, path: str) -> dict:
    """Read the record as it was at a git ref (rollback targets)."""
    need_yaml()
    out = subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise SystemExit(f"cannot read {path} at {ref}: {out.stderr.strip()}")
    data = need_yaml().safe_load(out.stdout)
    if not isinstance(data, dict):
        raise SystemExit(f"{path}@{ref}: expected a mapping at top level")
    return data


def order_for(component_names: list[str]) -> list[str]:
    order = load_yaml(ORDER_FILE).get("order") or []
    if not isinstance(order, list):
        raise SystemExit(f"{ORDER_FILE}: `order` must be a list")
    unknown = [n for n in component_names if n not in order]
    if unknown:
        raise SystemExit(
            f"components missing from {ORDER_FILE}: {', '.join(unknown)} — "
            "add them in dependency order before promoting"
        )
    return [n for n in order if n in component_names]


def same_run(observed: dict | None, target: dict | None) -> bool:
    """True when the environment already runs the target bytes."""
    if not observed or not target:
        return False
    return observed.get("digest") == target.get("digest") and observed.get(
        "commit"
    ) == target.get("commit")


def gh(*args: str, stdin: str | None = None) -> str:
    out = subprocess.run(
        ["gh", *args], input=stdin, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout


# ---------------------------------------------------------------- plan


def cmd_plan(args: argparse.Namespace) -> int:
    record = load_yaml(args.file)
    components = record.get("components") or {}
    if not components:
        raise SystemExit(f"{args.file}: no components")

    if args.mode == "rollback":
        if args.to_ref:
            target_record = load_at_ref(args.to_ref, args.file)
        else:
            target_record = None  # fall back to each component's `previous`
        source = f"rollback to {args.to_ref}" if args.to_ref else "rollback to previous"
    else:
        target_record = record
        source = "deploy desired"

    plan: list[dict] = []
    for name in order_for(list(components)):
        comp = components[name] or {}
        observed = comp.get("observed") or {}
        if args.mode == "rollback":
            if target_record is not None:
                target = ((target_record.get("components") or {}).get(name) or {}).get(
                    "observed"
                ) or {}
            else:
                target = (comp.get("previous") or {}).get("observed") or {}
            # a version id restores without the artifact; the digest is the fallback
            child_mode = "rollback" if target.get("worker_version") else "promote"
        else:
            target = comp.get("desired") or {}
            child_mode = "promote"

        if not target.get("commit"):
            raise SystemExit(
                f"{name}: no {args.mode} target (desired/observed empty) — "
                "nothing to dispatch, fix the record first"
            )

        kind = comp.get("kind")
        if kind != "worker":
            raise SystemExit(
                f"{name}: kind={kind!r} has no executor yet; image components deploy by "
                "overlay bump once ArgoCD is wired (ADR-PLT-0028 §3, plan E1)"
            )

        changed = not same_run(observed, target)
        plan.append(
            {
                "name": name,
                "kind": kind,
                "repo": comp["repo"],
                "executor": comp.get("executor") or "site-release.yml",
                "environment": record.get("env") or args.env,
                "child_mode": child_mode,
                "commit": target.get("commit"),
                "digest": target.get("digest"),
                "version": target.get("version"),
                "build_run": target.get("build_run") or "",
                "version_id": (target.get("worker_version") or "")
                if child_mode == "rollback"
                else "",
                # what is live right now: the rollback target once this run lands
                "previous_version_id": observed.get("worker_version") or "",
                "changed": changed,
            }
        )

    selection = args.components
    if selection == "changed":
        chosen = [c for c in plan if c["changed"]]
        if not chosen:
            print(f"nothing to do: {args.env} already matches the target ({source})")
    elif selection == "all":
        chosen = plan
    else:
        wanted = [s.strip() for s in selection.split(",") if s.strip()]
        chosen = [c for c in plan if c["name"] in wanted]
        missing = [w for w in wanted if w not in [c["name"] for c in plan]]
        if missing:
            raise SystemExit(f"unknown components: {', '.join(missing)}")

    doc = {
        "env": record.get("env") or args.env,
        "mode": args.mode,
        "source": source,
        "dry_run": args.dry_run,
        "components": chosen,
        "planned_at": now(),
    }
    print(json.dumps(doc, indent=2))

    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(f"### baseline plan — {doc['env']} ({args.mode}, {source})\n\n")
            if not chosen:
                fh.write("_nothing to do_\n")
            else:
                fh.write("| # | component | child mode | version | digest | changed |\n")
                fh.write("|---|---|---|---|---|---|\n")
                for i, c in enumerate(chosen, 1):
                    digest = (c["digest"] or "-")[:12]
                    fh.write(
                        f"| {i} | {c['name']} | {c['child_mode']} | {c['version']} | "
                        f"{digest} | {'yes' if c['changed'] else 'no'} |\n"
                    )
                fh.write("\n")
    return 0


# ---------------------------------------------------------------- apply


def epoch(iso: str) -> float:
    """`created_at` is ISO-8601 Z; compare on epoch seconds."""
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except (TypeError, ValueError):
        return 0.0


def wait_for_run(repo: str, executor: str, started: float, timeout: int) -> dict:
    """Find the dispatch this process just made, then wait for its conclusion."""
    deadline = time.time() + timeout
    run_id = None
    while time.time() < deadline:
        raw = gh(
            "api",
            f"repos/{repo}/actions/workflows/{executor}/runs?event=workflow_dispatch&per_page=30",
        )
        runs = json.loads(raw).get("workflow_runs") or []
        fresh = [r for r in runs if epoch(r.get("created_at")) >= started - 5]
        if fresh:
            run_id = max(fresh, key=lambda r: epoch(r["created_at"]))["id"]
            break
        time.sleep(5)
    if run_id is None:
        raise RuntimeError(f"{repo}: no dispatch run appeared for {executor}")

    while time.time() < deadline:
        raw = gh("api", f"repos/{repo}/actions/runs/{run_id}")
        run = json.loads(raw)
        if run.get("status") == "completed":
            return {
                "run_id": run_id,
                "conclusion": run.get("conclusion"),
                "html_url": run.get("html_url"),
            }
        time.sleep(10)
    raise RuntimeError(f"{repo}: run {run_id} did not finish within {timeout}s")


def version_from_log(repo: str, run_id: int) -> str:
    """The child prints `Worker Version ID: <uuid>`; that is the only channel today."""
    try:
        log = gh("run", "view", str(run_id), "-R", repo, "--log")
    except RuntimeError:
        return ""
    hits = UUID_RE.findall(log)
    return hits[-1] if hits else ""


def cmd_apply(args: argparse.Namespace) -> int:
    plan = json.load(open(args.plan, encoding="utf-8"))
    components = plan.get("components") or []
    dry = plan.get("dry_run") or args.dry_run
    token = os.environ.get("GH_TOKEN") or os.environ.get("BASELINE_TOKEN") or ""

    if not components:
        json.dump({"ok": True, "results": []}, open(args.results, "w"), indent=2)
        print("nothing to dispatch")
        return 0

    if not dry and not token:
        # fail-closed: no credential, no deploy
        json.dump({"ok": False, "error": "BASELINE_TOKEN missing"}, open(args.results, "w"))
        print("refusing: BASELINE_TOKEN is not set", file=sys.stderr)
        return 2

    results: list[dict] = []
    ok = True
    for comp in components:
        payload = {
            "ref": "main",
            "inputs": {
                "mode": comp["child_mode"],
                "environment": comp["environment"],
                "source_run_id": comp["build_run"],
                "expected_digest": comp["digest"] or "",
                "version_id": comp["version_id"] or "",
            },
        }
        endpoint = (
            f"repos/{comp['repo']}/actions/workflows/{comp['executor']}/dispatches"
        )
        if dry:
            print(
                f"[dry-run] POST {endpoint} mode={comp['child_mode']} "
                f"env={comp['environment']} digest={(comp['digest'] or '-')[:12]} "
                f"version_id={comp['version_id'] or '-'}"
            )
            results.append({**comp, "dry_run": True, "conclusion": "skipped"})
            continue

        started = time.time()
        os.environ["GH_TOKEN"] = token
        gh("api", "-X", "POST", endpoint, "--input", "-", stdin=json.dumps(payload))
        try:
            run = wait_for_run(
                comp["repo"], comp["executor"], started, int(os.environ.get("WAIT_SECONDS", "1800"))
            )
        except RuntimeError as exc:
            ok = False
            results.append({**comp, "conclusion": "unknown", "error": str(exc)})
            break
        version = version_from_log(comp["repo"], run["run_id"])
        results.append({**comp, **run, "worker_version": version})
        print(
            f"{comp['name']}: {run['conclusion']} run={run['run_id']} "
            f"version={version or '-'}"
        )
        if run["conclusion"] != "success":
            ok = False
            break  # fail-fast: later components are untouched

    payload = {
        "ok": ok,
        "mode": plan.get("mode"),
        "env": plan.get("env"),
        "partial": ok and len(results) < len(components),
        "results": results,
        "finished_at": now(),
    }
    json.dump(payload, open(args.results, "w"), indent=2)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write("| # | component | conclusion | run | version |\n|---|---|---|---|---|\n")
            for i, r in enumerate(results, 1):
                fh.write(
                    f"| {i} | {r['name']} | {r.get('conclusion')} | "
                    f"{r.get('html_url') or '-'} | {r.get('worker_version') or '-'} |\n"
                )
            fh.write("\n")
    return 0 if ok else 1


# ---------------------------------------------------------------- record


def cmd_record(args: argparse.Namespace) -> int:
    record = load_yaml(args.file)
    results = json.load(open(args.results, encoding="utf-8"))
    if results.get("dry_run") or any(r.get("dry_run") for r in results.get("results") or []):
        print("dry-run: record untouched")
        return 0
    if not results.get("ok"):
        print("run failed: record untouched (the environment is unchanged by us)", file=sys.stderr)
        return 1

    components = record.setdefault("components", {})
    rolled_back_from = {}
    for res in results.get("results") or []:
        name = res["name"]
        comp = components.get(name) or {}
        old = comp.get("observed") or {}
        if results.get("mode") == "rollback":
            # the intent changed too: a rollback is a new intent, not a hidden one
            rolled_back_from[name] = comp.get("desired") or {}
            comp["desired"] = {
                "version": res.get("version"),
                "commit": res.get("commit"),
                "digest": res.get("digest"),
                "build_run": res.get("build_run") or "",
            }
        if old:
            comp["previous"] = {"observed": old}
        comp["observed"] = {
            "version": res.get("version"),
            "commit": res.get("commit"),
            "digest": res.get("digest"),
            "worker_version": res.get("worker_version") or "",
            "deployed_at": results.get("finished_at") or now(),
            "status": "deployed",
            "run": res.get("run_id"),
        }
        components[name] = comp

    record["updated_at"] = results.get("finished_at") or now()
    record["updated_by"] = os.environ.get("RECORDED_BY", "palupgg-bot")
    if rolled_back_from:
        record["rolled_back_from"] = rolled_back_from

    with open(args.file, "w", encoding="utf-8") as fh:
        need_yaml().safe_dump(record, fh, sort_keys=False, default_flow_style=False, width=100)
    print(f"record updated: {args.file}")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(f"record updated for `{record.get('env')}`\n")
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    """Release body: what went out, and the exact rollback for each component."""
    plan = json.load(open(args.plan, encoding="utf-8"))
    results = json.load(open(args.results, encoding="utf-8"))
    env = plan.get("env")
    rows = results.get("results") or []
    out = [
        f"Baseline deploy to `{env}` ({plan.get('mode')}, {plan.get('source')}).",
        "",
        f"- plan: {plan.get('planned_at')}",
        f"- finished: {results.get('finished_at')}",
        f"- partial: {bool(results.get('partial'))}",
        "",
        "| component | version | commit | digest | Worker version |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r.get('name')} | {r.get('version')} | {r.get('commit')} | "
            f"`{(r.get('digest') or '-')[:12]}` | `{r.get('worker_version') or '-'}` |"
        )
    out += ["", "## Rollback", ""]
    if results.get("mode") == "rollback":
        out.append("This release *was* a rollback; the record carries `rolled_back_from`.")
    else:
        out.append(
            "Whole baseline, to the previous record:\n\n"
            f"```\ngh workflow run baseline.yml -R PalupGG/gitops \\\n"
            f"  -f environment={env} -f mode=rollback -f dry_run=false\n```\n"
        )
        out.append("Single component, by Worker version (seconds, no rebuild):\n")
        for r in rows:
            vid = r.get("previous_version_id")
            out.append(
                f"- `{r.get('name')}`: "
                + (
                    f"`gh workflow run site-release.yml -R {r.get('repo')} "
                    f"-f mode=rollback -f environment={env} -f version_id={vid}`"
                    if vid
                    else "_no previous Worker version recorded_"
                )
            )
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print(f"notes written: {args.out}")
    return 0


# ---------------------------------------------------------------- cli


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan")
    pl.add_argument("--env", required=True)
    pl.add_argument("--mode", choices=["deploy", "rollback"], required=True)
    pl.add_argument("--file", required=True)
    pl.add_argument("--to-ref", default="")
    pl.add_argument("--components", default="changed")
    pl.add_argument("--dry-run", action="store_true")
    pl.set_defaults(func=cmd_plan)

    ap = sub.add_parser("apply")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.set_defaults(func=cmd_apply)

    rc = sub.add_parser("record")
    rc.add_argument("--file", required=True)
    rc.add_argument("--results", required=True)
    rc.set_defaults(func=cmd_record)

    nt = sub.add_parser("notes")
    nt.add_argument("--plan", required=True)
    nt.add_argument("--results", required=True)
    nt.add_argument("--out", required=True)
    nt.set_defaults(func=cmd_notes)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
