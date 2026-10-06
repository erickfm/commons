"""Run many scenarios on many models in parallel, skipping any pair that already has a finished log.

    uv run python -m commons.batch experiments/x/scenarios/*.yaml \\
        --model anthropic/claude-haiku-4-5-20251001 --model openai/gpt-5-mini \\
        --epochs 10 --log-dir logs/x --workers 8

`--effort low --effort high` repeats every run at each reasoning effort (basic agents only).

Each (scenario, model, effort) is one `inspect eval` run, with its log in <log-dir>/<model short name>/. A run
whose log already finished successfully is skipped, so an interrupted batch can be started again with the
same command. Environment variables (API keys, DOCKER_HOST, ...) are passed through to every run.
"""

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml
from inspect_ai.log import read_eval_log


def short(model: str) -> str:
    return model.split("/")[-1].replace(".", "_")


def task_name(scenario: str) -> str:
    return yaml.safe_load(Path(scenario).read_text())["name"]


def finished(log_dir: Path, task: str, model: str, effort: str | None = None) -> bool:
    for f in log_dir.glob("*.eval"):
        try:
            h = read_eval_log(f, header_only=True)
        except Exception:
            continue
        args = h.eval.task_args
        if h.eval.task == task and args.get("model") == model and args.get("effort") == effort and h.status == "success":
            return True
    return False


def run(scenario: str, model: str, effort: str | None, args) -> str:
    log_dir = Path(args.log_dir) / short(model)
    label = f"{scenario} {model}" + (f" effort={effort}" if effort else "")
    if finished(log_dir, task_name(scenario), model, effort):
        return f"skip  {label}"
    cmd = ["uv", "run", "inspect", "eval", "commons/tasks.py", "-T", f"scenario={scenario}", "-T", f"model={model}",
           *(["-T", f"effort={effort}"] if effort else []),
           "--model", model, "--epochs", str(args.epochs), "--max-samples", str(args.max_samples),
           "--log-dir", str(log_dir), "--display", "plain"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return f"{'done ' if r.returncode == 0 else 'FAIL '} {label}" + ("" if r.returncode == 0 else "\n" + r.stderr[-2000:])


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="+")
    ap.add_argument("--model", action="append", required=True, help="repeat for several models")
    ap.add_argument("--effort", action="append", help="reasoning effort for basic agents; repeat for several")
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--log-dir", required=True)
    ap.add_argument("--workers", type=int, default=4, help="inspect runs at once")
    ap.add_argument("--max-samples", type=int, default=4, help="epochs at once within each run")
    args = ap.parse_args(argv)
    jobs = [(s, m, e) for m in args.model for e in (args.effort or [None]) for s in args.scenarios]
    with ThreadPoolExecutor(args.workers) as pool:
        for line in pool.map(lambda job: run(*job, args), jobs):
            print(line, flush=True)


if __name__ == "__main__":
    sys.exit(main())
