import json
import os

import anthropic

from ai.prompts import (
    ANALYSIS_RULES_PROMPT,
    BUTTON_PROMPTS,
    REPORT_CONTEXT_LABEL,
    SYSTEM_ROLE_PROMPT,
    USER_QUESTION_LABEL,
)


def _find_importance_metric(report_df) -> str | None:
    metric_priority = [
        ["purchaseRevenue", "revenue", "totalRevenue", "value"],
        ["transactions", "purchases", "conversions"],
        ["sessions", "totalUsers", "activeUsers", "users", "newUsers"],
        ["userEngagementDuration", "engagementDuration", "views"],
    ]
    try:
        columns = set(report_df.columns)
    except AttributeError:
        return None

    for group in metric_priority:
        for metric in group:
            if metric in columns:
                return metric
    return None


def _select_rows_by_coverage(report_df, coverage_pct: int):
    if report_df is None:
        return report_df

    if coverage_pct >= 100:
        return report_df

    try:
        if report_df.empty:
            return report_df
    except AttributeError:
        return report_df

    importance_metric = _find_importance_metric(report_df)
    if not importance_metric:
        try:
            row_count = len(report_df)
        except TypeError:
            return report_df
        target_rows = max(1, int(round(row_count * (coverage_pct / 100))))
        return report_df.head(target_rows)

    try:
        metric_series = report_df[importance_metric]
    except Exception:
        return report_df

    metric_series = metric_series.fillna(0)
    try:
        metric_values = metric_series.astype(float)
    except (TypeError, ValueError):
        metric_values = metric_series

    total_metric = metric_values.sum()
    if total_metric <= 0:
        return report_df

    sorted_df = report_df.assign(_metric=metric_values).sort_values(
        "_metric",
        ascending=False,
    )
    cumulative = sorted_df["_metric"].cumsum()
    threshold = total_metric * (coverage_pct / 100)
    selected_df = sorted_df[cumulative <= threshold]
    if selected_df.empty:
        selected_df = sorted_df.head(1)

    return selected_df.drop(columns=["_metric"])


def build_prompt(
    selected_reports: list[dict],
    user_question: str,
    prompt_key: str | None,
    coverage_pct: int = 100,
) -> str:
    report_context = []
    for report in selected_reports:
        report_df = report.get("data")
        report_rows = []
        if report_df is not None:
            selected_df = _select_rows_by_coverage(report_df, coverage_pct)
            report_rows = (
                selected_df.to_dict(orient="records")
                if selected_df is not None
                else []
            )
        report_context.append({
            "report_id": report["id"],
            "report_name": report["name"],
            "description": report["description"],
            "data": report_rows,
        })

    report_context_json = json.dumps(
        {"reports": report_context},
        ensure_ascii=True,
        default=str,
    )

    instruction_text = (
        BUTTON_PROMPTS.get(prompt_key, user_question)
        if prompt_key
        else user_question
    )

    return (
        f"{SYSTEM_ROLE_PROMPT}\n\n"
        f"{REPORT_CONTEXT_LABEL}\n"
        f"{report_context_json}\n\n"
        f"{USER_QUESTION_LABEL}\n"
        f"{instruction_text}\n\n"
        f"{ANALYSIS_RULES_PROMPT}"
    )


def estimate_tokens(prompt: str) -> int:
    return max(1, len(prompt) // 4)


def get_estimated_tokens(
    selected_reports: list[dict],
    user_question: str,
    prompt_key: str | None,
    coverage_pct: int = 100,
) -> int:
    prompt = build_prompt(
        selected_reports=selected_reports,
        user_question=user_question,
        prompt_key=prompt_key,
        coverage_pct=coverage_pct,
    )
    return estimate_tokens(prompt)


def analyze_selected_reports(
    selected_reports: list[dict],
    user_question: str,
    prompt_key: str | None = None,
    coverage_pct: int = 100,
) -> str:
    """
    Analyze selected analytics reports using an LLM.

    Args:
        selected_reports: List of report dictionaries, each containing:
            - id
            - name
            - description
            - data (pandas DataFrame)
        user_question: The user's natural language question.
        prompt_key: Optional prompt key for predefined button prompts.

    Returns:
        A plain-text AI response.
    """

    prompt = build_prompt(
        selected_reports=selected_reports,
        user_question=user_question,
        prompt_key=prompt_key,
        coverage_pct=coverage_pct,
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return (
            "AI is not configured. Set ANTHROPIC_API_KEY to enable responses.\n\n"
            "Prompt preview:\n"
            f"{prompt}"
        )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": prompt,
        }],
    )

    return message.content[0].text
