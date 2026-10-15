"""`oca-index` command line: refresh the OCA summary data and build the skill."""

import argparse
import os
import sys

from .config import load_settings


def cmd_sync(args: argparse.Namespace) -> int:
    from .sync import sync

    return 0 if sync(load_settings()) else 1


def cmd_prepare(args: argparse.Namespace) -> int:
    from .summaries import prepare

    batches = prepare(load_settings())
    print(f"{len(batches)} batch files of modules needing a summary in work/pending/")
    return 0


def cmd_summarize(args: argparse.Namespace) -> int:
    from .summaries import summarize_api

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY isn't set. Without one, summarize in Claude Code instead"
            " (see README.md)."
        )
    failed = summarize_api(load_settings())
    print(f"{failed} requests failed" if failed else "All summaries returned")
    return 0


def cmd_agent_prompts(args: argparse.Namespace) -> int:
    from .summaries import PENDING, RESULTS, agent_instructions

    RESULTS.mkdir(parents=True, exist_ok=True)
    for batch in sorted(PENDING.glob("batch_*.md")):
        print(f"--- {batch.name}\n{agent_instructions(batch, RESULTS / f'{batch.stem}.jsonl')}\n")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    from .summaries import PENDING, ingest

    added, problems = ingest()
    for p in problems:
        print(f"  {p}")
    left = len(list(PENDING.glob("batch_*.md")))
    print(f"Added {added} summaries; {len(problems)} problems; {left} batch files still pending")
    return 1 if problems else 0


def cmd_migrations(args: argparse.Namespace) -> int:
    from .migrations import scan

    count, failed = scan(load_settings())
    print(f"{count} open PRs bringing a module to a tracked version; {len(failed)} queries failed")
    return 1 if failed else 0


def cmd_build(args: argparse.Namespace) -> int:
    from .build import build

    target, count, unsummarized = build(load_settings())
    print(f"{count} modules -> {target} ({target.stat().st_size:,} bytes)")
    if unsummarized:
        print(f"{len(unsummarized)} modules left out, no summary yet (run `oca-index update`)")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Every step in order; stops before building if summaries are still needed."""
    from .summaries import PENDING

    steps = [cmd_sync, cmd_prepare]
    for step in steps:
        if step(args):
            return 1
    if any(PENDING.glob("batch_*.md")):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "Modules need summaries. Without an API key, ask Claude Code in this repo to"
                " 'summarize the pending OCA batches', then run `oca-index update` again."
            )
            return 1
        if cmd_summarize(args) or cmd_ingest(args):
            return 1
    if cmd_migrations(args):
        print("Some migration queries failed; building with what was found.")
    return cmd_build(args)


COMMANDS = {
    "update": (cmd_update, "sync, summarize what's new, scan migrations, build the skill"),
    "sync": (cmd_sync, "fetch OCA and parse modules"),
    "prepare": (cmd_prepare, "write batch files of modules needing a summary"),
    "summarize": (cmd_summarize, "summarize pending batches with the Batch API"),
    "agent-prompts": (cmd_agent_prompts, "print a Claude Code subagent prompt per pending batch"),
    "ingest": (cmd_ingest, "add finished batch results to data/summaries.jsonl"),
    "migrations": (cmd_migrations, "scan open OCA PRs for pending migrations"),
    "build": (cmd_build, "write the skill data and zip"),
}


def main() -> None:
    parser = argparse.ArgumentParser(prog="oca-index")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (func, help_text) in COMMANDS.items():
        sub.add_parser(name, help=help_text).set_defaults(func=func)
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
