"""Independent static/watch plotting of native PerfRace run directories."""

from __future__ import annotations
import time
from pathlib import Path
from typing import Annotated
import typer
from perfrace.run.progress import (
    _run_baselines,
    _load_completed_job,
    _group,
    _aggregate_curve,
    _aggregate_average_token_curve,
    _expected_candidate_attempts,
)


def render(runs: list[Path], output: Path) -> list[Path]:
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    fig_time, ax_time = plt.subplots(figsize=(6, 3.5))
    fig_tokens, ax_tokens = plt.subplots(figsize=(6, 3.5))
    count = 0
    for run in runs:
        baselines = _run_baselines(run)
        if not baselines:
            continue
        ts, tokens = _load_completed_job(run, baselines)
        if not ts:
            continue
        expected = tuple(sorted(baselines))
        x, y = _aggregate_curve(_group(ts), expected_instances=expected)
        ax_time.step([v / 60 for v in x], y, where="post", label=run.name)
        x, y = _aggregate_average_token_curve(
            _group(ts),
            _group(tokens),
            expected_instances=expected,
            expected_attempts=_expected_candidate_attempts(run, len(expected)),
        )
        ax_tokens.step(x, y, where="post", label=run.name)
        count += 1
    saved = []
    try:
        if count:
            for fig, ax, label, filename in (
                (fig_time, ax_time, "Task time (h)", "speedup-vs-time.pdf"),
                (fig_tokens, ax_tokens, "Mean tokens per run (M)", "speedup-vs-tokens.pdf"),
            ):
                ax.set(xlabel=label, ylabel="Best-so-far correct speedup")
                ax.axhline(1, color="0.7", lw=0.7)
                ax.legend(frameon=False)
                fig.tight_layout()
                dest = output / filename
                temp = dest.with_suffix(".tmp.pdf")
                fig.savefig(temp)
                temp.replace(dest)
                saved.append(dest)
    finally:
        plt.close(fig_time)
        plt.close(fig_tokens)
    return saved


def plot(
    runs: Annotated[list[Path], typer.Argument(help="One or more native run directories.")],
    watch: Annotated[bool, typer.Option("--watch", help="Refresh until interrupted.")] = False,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Plot recorded progress without starting, stopping or modifying an experiment."""
    runs = [p.expanduser().resolve() for p in runs]
    for run in runs:
        if not run.is_dir():
            raise typer.BadParameter(f"Run directory does not exist: {run}")
    output = output or runs[0] / "plots"
    try:
        while True:
            saved = render(runs, output)
            if not watch:
                if not saved:
                    raise typer.BadParameter(
                        "No scored submissions with completed baseline records yet"
                    )
                for path in saved:
                    typer.echo(path)
                return
            time.sleep(10)
    except KeyboardInterrupt:
        return
