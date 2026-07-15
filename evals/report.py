"""Writes a markdown metrics report (evals/reports/<date>.md) for local runs and CI PR comments.

Consumes the optional JSON `--output` files that `run_retrieval_eval.py`
and `run_answer_eval.py` can write. Either or both may be missing (e.g. a
retrieval-only local run) — the report notes whichever section was skipped
rather than failing, since this script is also used to render a partial
report as a PR comment when only path-filtered evals ran (§14 Phase 4).
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

REPORTS_DIR = Path(__file__).parent / "reports"


def _load_json(path: Path | None) -> dict[str, object] | None:
    if path is None or not path.exists():
        return None
    result: dict[str, object] = json.loads(path.read_text())
    return result


def _render_retrieval_section(data: dict[str, object] | None) -> str:
    if data is None:
        return "## Retrieval eval\n\n_Not run for this report._\n"

    lines = [
        "## Retrieval eval",
        "",
        "| mode | recall@5 | recall@20 | MRR | nDCG@10 | must-refuse avg top score |",
        "|------|---------:|----------:|----:|--------:|---------------------------:|",
    ]
    for label, metrics in data.items():
        assert isinstance(metrics, dict)
        refusal_score = metrics.get("refusal_item_avg_top_score")
        refusal_cell = f"{refusal_score:.3f}" if isinstance(refusal_score, int | float) else "—"
        lines.append(
            f"| {label} | {metrics['recall_at_5']:.3f} | {metrics['recall_at_20']:.3f} | "
            f"{metrics['mrr']:.3f} | {metrics['ndcg_at_10']:.3f} | {refusal_cell} |"
        )
    lines.append("")
    return "\n".join(lines)


def _render_answer_section(data: dict[str, object] | None) -> str:
    if data is None:
        return "## Answer eval\n\n_Not run for this report._\n"

    aggregate = data["aggregate"]
    assert isinstance(aggregate, dict)

    def _fmt(key: str) -> str:
        value = aggregate.get(key)
        return f"{value:.3f}" if isinstance(value, int | float) else "—"

    lines = [
        "## Answer eval",
        "",
        f"Items evaluated: {aggregate.get('n_items', '—')}",
        "",
        "| metric | value |",
        "|--------|------:|",
        f"| false-answer rate (answered a must-refuse item) | {_fmt('false_answer_rate')} |",
        f"| false-refusal rate (refused an answerable item) | {_fmt('false_refusal_rate')} |",
        f"| avg citation precision | {_fmt('avg_citation_precision')} |",
        f"| avg faithfulness score (judge) | {_fmt('avg_faithfulness_score')} |",
        f"| avg ideal-point coverage (judge) | {_fmt('avg_citation_recall')} |",
        "",
    ]
    return "\n".join(lines)


def _render_diff_section(
    current_retrieval: dict[str, object] | None,
    baseline_retrieval: dict[str, object] | None,
    current_answer: dict[str, object] | None,
    baseline_answer: dict[str, object] | None,
    threshold: float,
) -> str:
    """Render a regression-flagged diff table, if a baseline was supplied."""
    if baseline_retrieval is None and baseline_answer is None:
        return ""

    lines = ["## Diff vs. baseline", "", f"Regression threshold: {threshold:.3f}", ""]
    flagged: list[str] = []

    if current_retrieval is not None and baseline_retrieval is not None:
        for label, metrics in current_retrieval.items():
            baseline_metrics = baseline_retrieval.get(label)
            if not isinstance(baseline_metrics, dict) or not isinstance(metrics, dict):
                continue
            for metric_name in ("recall_at_5", "recall_at_20", "mrr", "ndcg_at_10"):
                current_value = metrics.get(metric_name)
                baseline_value = baseline_metrics.get(metric_name)
                if not isinstance(current_value, int | float) or not isinstance(
                    baseline_value, int | float
                ):
                    continue
                delta = current_value - baseline_value
                if delta < -threshold:
                    flagged.append(
                        f"- **{label}.{metric_name}** dropped {abs(delta):.3f} "
                        f"({baseline_value:.3f} -> {current_value:.3f})"
                    )

    if current_answer is not None and baseline_answer is not None:
        current_aggregate = current_answer.get("aggregate")
        baseline_aggregate = baseline_answer.get("aggregate")
        if isinstance(current_aggregate, dict) and isinstance(baseline_aggregate, dict):
            for metric_name, higher_is_better in (
                ("avg_faithfulness_score", True),
                ("avg_citation_precision", True),
                ("avg_citation_recall", True),
                ("false_answer_rate", False),
                ("false_refusal_rate", False),
            ):
                current_value = current_aggregate.get(metric_name)
                baseline_value = baseline_aggregate.get(metric_name)
                if not isinstance(current_value, int | float) or not isinstance(
                    baseline_value, int | float
                ):
                    continue
                delta = current_value - baseline_value
                regressed = (delta < -threshold) if higher_is_better else (delta > threshold)
                if regressed:
                    flagged.append(
                        f"- **{metric_name}** regressed by {abs(delta):.3f} "
                        f"({baseline_value:.3f} -> {current_value:.3f})"
                    )

    if flagged:
        lines.append("**Regressions detected:**")
        lines.extend(flagged)
    else:
        lines.append("No regressions above threshold.")
    lines.append("")
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retrieval-results", type=Path, default=None)
    parser.add_argument("--answer-results", type=Path, default=None)
    parser.add_argument("--baseline-retrieval-results", type=Path, default=None)
    parser.add_argument("--baseline-answer-results", type=Path, default=None)
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.02,
        help="Absolute-value regression threshold applied per metric (default 0.02).",
    )
    parser.add_argument("--output", type=Path, default=None, help="Defaults to reports/<date>.md")
    return parser.parse_args()


def main() -> None:
    """Render evals/reports/<date>.md from whichever eval result JSON files are available."""
    args = _parse_args()
    retrieval_data = _load_json(args.retrieval_results)
    answer_data = _load_json(args.answer_results)
    baseline_retrieval_data = _load_json(args.baseline_retrieval_results)
    baseline_answer_data = _load_json(args.baseline_answer_results)

    today = datetime.now(UTC).date().isoformat()
    sections = [
        f"# Kanuni eval report — {today}",
        "",
        _render_retrieval_section(retrieval_data),
        _render_answer_section(answer_data),
        _render_diff_section(
            retrieval_data,
            baseline_retrieval_data,
            answer_data,
            baseline_answer_data,
            args.threshold,
        ),
    ]
    report_text = "\n".join(section for section in sections if section)

    output_path = args.output or (REPORTS_DIR / f"{today}.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text)
    print(f"Wrote report to {output_path}")
    print()
    print(report_text)


if __name__ == "__main__":
    main()
