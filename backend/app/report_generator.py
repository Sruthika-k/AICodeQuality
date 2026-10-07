"""Report generator module for creating Markdown reports of optimization runs."""

from typing import Optional
from datetime import datetime


def generate_markdown_report(
    prompt: str,
    initial_code: Optional[str],
    iterations: list,
    final_code: str,
    metrics_summary: Optional[dict],
    converged: bool,
    total_iterations: int,
    iteration_cap: int,
    pylint_threshold: float,
    mode: str = "generate",
) -> str:
    """Generate a comprehensive Markdown report for an optimization run.

    Args:
        prompt: The user prompt or review instruction
        initial_code: Initial code (if review mode)
        iterations: List of iteration data
        final_code: Final optimized code
        metrics_summary: Before/after metrics summary
        converged: Whether convergence was achieved
        total_iterations: Number of iterations run
        iteration_cap: Maximum iterations allowed
        pylint_threshold: Pylint score threshold
        mode: "generate" or "review"

    Returns:
        Markdown formatted report string
    """
    lines = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Header
    lines.append(f"# AICodeQuality Optimization Report")
    lines.append(f"\n**Generated:** {timestamp}")
    lines.append(f"**Mode:** {mode.capitalize()}")
    lines.append(f"**Converged:** {'[YES]' if converged else '[NO]'}")
    lines.append(f"**Iterations:** {total_iterations} / {iteration_cap}")
    lines.append(f"**Pylint Threshold:** {pylint_threshold}/10.0")

    # Input Section
    lines.append("\n---")
    lines.append("\n## Input")
    if mode == "generate":
        lines.append("\n### Prompt")
        lines.append(f"\n```\n{prompt}\n```")
    else:
        lines.append("\n### Initial Code")
        lines.append(f"\n```python\n{initial_code}\n```")

    # Iteration Summary Table
    lines.append("\n---")
    lines.append("\n## Iteration Summary")
    lines.append("\n| Iteration | Pylint Score | Bandit H/M | Total Issues | Threshold Met | Status |")
    lines.append("|-----------|--------------|-----------|--------------|---------------|--------|")

    for it in iterations:
        status = "[ACCEPTED]" if it.get("threshold_met") else "[REJECTED]"
        lines.append(
            f"| {it.get('iteration')} | {it.get('pylint_score', 0):.2f} | "
            f"{it.get('bandit_high_medium_count', 0)} | {it.get('total_issues_count', 0)} | "
            f"{'Yes' if it.get('threshold_met') else 'No'} | {status} |"
        )

    # Per-Iteration Details
    lines.append("\n---")
    lines.append("\n## Iteration Details")

    for i, it in enumerate(iterations):
        iter_num = it.get("iteration", i + 1)
        lines.append(f"\n### Iteration {iter_num}")
        lines.append(f"\n**Pylint Score:** {it.get('pylint_score', 0):.2f}/10.0")
        lines.append(f"**Bandit High/Med Issues:** {it.get('bandit_high_medium_count', 0)}")
        lines.append(f"**Total Issues:** {it.get('total_issues_count', 0)}")
        lines.append(f"**Threshold Met:** {'Yes' if it.get('threshold_met') else 'No'}")

        # Issues
        issues = it.get("issues", [])
        if issues:
            lines.append(f"\n**Issues ({len(issues)}):**")
            lines.append("\n| Tool | Severity | Line | Rule ID | Message |")
            lines.append("|------|----------|------|---------|---------|")
            for issue in issues[:20]:  # Limit to first 20 issues
                lines.append(
                    f"| {issue.get('tool')} | {issue.get('severity')} | "
                    f"{issue.get('line')} | {issue.get('rule_id')} | {issue.get('message')} |"
                )
            if len(issues) > 20:
                lines.append(f"| ... | ... | ... | ... | ... ({len(issues) - 20} more issues) |")

        # Diff (if not first iteration)
        if i > 0 and it.get("diff"):
            lines.append(f"\n**Changes from Iteration {iter_num - 1}:**")
            lines.append(f"\n```diff\n{it.get('diff')}\n```")

    # Before/After Summary
    if metrics_summary:
        lines.append("\n---")
        lines.append("\n## Before/After Summary")
        lines.append(f"\n```\n{metrics_summary.get('table', 'No summary available')}\n```")

        if metrics_summary.get("initial_avg_complexity") is not None:
            lines.append("\n### Complexity Metrics")
            lines.append(f"\n- **Avg Complexity:** {metrics_summary.get('initial_avg_complexity', 0):.2f} → {metrics_summary.get('final_avg_complexity', 0):.2f}")
            lines.append(f"- **Max Complexity:** {metrics_summary.get('initial_max_complexity', 0)} → {metrics_summary.get('final_max_complexity', 0)}")
            lines.append(f"- **Maintainability Index:** {metrics_summary.get('initial_maintainability_index', 0):.2f} → {metrics_summary.get('final_maintainability_index', 0):.2f}")

    # Final Code
    lines.append("\n---")
    lines.append("\n## Final Optimized Code")
    lines.append(f"\n```python\n{final_code}\n```")

    # Footer
    lines.append("\n---")
    lines.append("\n*Report generated by AICodeQuality - Automated Python Code Enhancement Loop*")

    return "\n".join(lines)
