# This module builds prompts from GA4 report data and sends them to Claude.       
# It also trims report rows for token control and estimates prompt size.         

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


# ============================================================================
# Row Selection Helpers
# ============================================================================
# This section picks the most important rows so prompts stay focused and small.

# This function chooses the best metric to rank rows by importance.
def _find_importance_metric(report_df) -> str | None:
    metric_priority = [                                                       # Priority groups for ranking by business impact
        ["purchaseRevenue", "revenue", "totalRevenue", "value"],
        ["transactions", "purchases", "conversions"],
        ["sessions", "totalUsers", "activeUsers", "users", "newUsers"],
        ["userEngagementDuration", "engagementDuration", "views"],
    ]
    try:
        columns = set(report_df.columns)                                      # Column names used to find a matching metric
    except AttributeError:                                                    # Handles non-DataFrame input without columns
        return None                                                           # Return None when no columns are available

    for group in metric_priority:
        for metric in group:
            if metric in columns:
                return metric                                                 # Return the first high-priority metric found
    return None                                                               # Return None when no priority metric exists


# This function trims a DataFrame based on coverage percentage.
def _select_rows_by_coverage(report_df, coverage_pct: int):
    if report_df is None:
        return report_df                                                      # Return original input when data is missing

    if coverage_pct >= 100:
        return report_df                                                      # Return all rows when full coverage is requested

    try:
        if report_df.empty:
            return report_df                                                  # Return empty DataFrame without extra work
    except AttributeError:                                                    # Handles non-DataFrame input safely
        return report_df                                                      # Return original input when no DataFrame methods exist

    importance_metric = _find_importance_metric(report_df)                    # Metric used to rank row importance
    if not importance_metric:
        try:
            row_count = len(report_df)                                        # Total rows used for simple percentage slicing
        except TypeError:                                                     # Handles objects without length
            return report_df                                                  # Return original input when length is unknown
        target_rows = max(1, int(round(row_count * (coverage_pct / 100))))    # Ensure at least one row remains
        return report_df.head(target_rows)                                    # Return the top rows by position

    try:
        metric_series = report_df[importance_metric]                          # Series used to rank rows by value
    except Exception:                                                         # Handles missing column or invalid access
        return report_df                                                      # Return original input if ranking metric fails

    metric_series = metric_series.fillna(0)                                   # Replace missing values so sorting is safe
    try:
        metric_values = metric_series.astype(float)                           # Convert to numbers for sorting and sums
    except (TypeError, ValueError):                                           # Handles non-numeric data safely
        metric_values = metric_series                                         # Fall back to original values

    total_metric = metric_values.sum()                                        # Total used to compute coverage threshold
    if total_metric <= 0:
        return report_df                                                      # Return original input when totals are invalid

    sorted_df = report_df.assign(_metric=metric_values).sort_values(            # Create and sort by temporary rank column
        "_metric",                                                            # Temporary column for sorting
        ascending=False,                                                      # Keep highest values first
    )
    cumulative = sorted_df["_metric"].cumsum()                                # Running total to measure coverage
    threshold = total_metric * (coverage_pct / 100)                           # Coverage target in metric units
    selected_df = sorted_df[cumulative <= threshold]                          # Keep rows inside coverage threshold
    if selected_df.empty:
        selected_df = sorted_df.head(1)                                       # Keep at least one row

    return selected_df.drop(columns=["_metric"])                               # Return filtered DataFrame without temp column


# ============================================================================
# Prompt Construction and Token Estimation
# ============================================================================
# This section builds the prompt text and estimates its size for UI hints.

# This function builds the full AI prompt from reports and the user question.
def build_prompt(
    selected_reports: list[dict],                                             # Reports chosen by the user/UI
    user_question: str,                                                       # Natural-language question from the user
    prompt_key: str | None,                                                   # Optional template key for button prompts
    coverage_pct: int = 100,                                                  # Percent of rows to include from each report
) -> str:
    report_context = []                                                       # List of serialized report payloads
    for report in selected_reports:
        report_df = report.get("data")                                        # DataFrame for this report
        report_rows = []                                                      # Row data to embed in the prompt
        if report_df is not None:
            selected_df = _select_rows_by_coverage(report_df, coverage_pct)   # Reduce rows based on coverage
            report_rows = (                                                   # Convert rows into JSON-friendly records
                selected_df.to_dict(orient="records")
                if selected_df is not None
                else []
            )
        report_context.append({
            "report_id": report["id"],                                        # Stable ID used across the app
            "report_name": report["name"],                                    # Human-readable report name
            "description": report["description"],                             # Short description shown in UI
            "data": report_rows,                                              # Selected data rows for AI
        })

    report_context_json = json.dumps(
        {"reports": report_context},                                          # Wrap all report payloads together
        ensure_ascii=True,                                                    # Keep output ASCII-safe for prompts
        default=str,                                                          # Convert unknown objects to strings
    )

    instruction_text = (
        BUTTON_PROMPTS.get(prompt_key, user_question)                         # Use template prompt when available
        if prompt_key                                                        # Only if a template key was provided
        else user_question                                                    # Otherwise use the raw question
    )

    return (
        f"{SYSTEM_ROLE_PROMPT}\n\n"                                           # System instructions for the AI
        f"{REPORT_CONTEXT_LABEL}\n"                                           # Label for the report JSON block
        f"{report_context_json}\n\n"                                          # Serialized report data
        f"{USER_QUESTION_LABEL}\n"                                            # Label for the user question
        f"{instruction_text}\n\n"                                            # The actual question/prompt text
        f"{ANALYSIS_RULES_PROMPT}"                                            # Guardrails for AI behavior
    )                                                                         # Return the complete prompt string


# This function estimates token count using a simple character heuristic.
def estimate_tokens(prompt: str) -> int:
    return max(1, len(prompt) // 4)                                           # Return a minimum estimate of 1 token


# This function estimates prompt size for selected reports and a question.
def get_estimated_tokens(
    selected_reports: list[dict],                                             # Reports chosen by the user/UI
    user_question: str,                                                       # Natural-language question from the user
    prompt_key: str | None,                                                   # Optional template key for button prompts
    coverage_pct: int = 100,                                                  # Percent of rows to include from each report
) -> int:
    prompt = build_prompt(
        selected_reports=selected_reports,                                    # Reports to include in the prompt
        user_question=user_question,                                          # User question or template label
        prompt_key=prompt_key,                                                # Optional prompt template key
        coverage_pct=coverage_pct,                                            # Row coverage control
    )
    return estimate_tokens(prompt)                                            # Return the estimated token count


# ============================================================================
# AI Analysis Execution
# ============================================================================
# This section sends the prompt to Claude and returns the AI response text.

# This function runs the end-to-end AI analysis request.
def analyze_selected_reports(
    selected_reports: list[dict],                                             # Reports to include in the AI prompt
    user_question: str,                                                       # The user's question in plain language
    prompt_key: str | None = None,                                            # Optional template key for button prompts
    coverage_pct: int = 100,                                                  # Percent of report rows to include
) -> str:

    prompt = build_prompt(
        selected_reports=selected_reports,                                    # Chosen report data
        user_question=user_question,                                          # User request text
        prompt_key=prompt_key,                                                # Optional prompt template
        coverage_pct=coverage_pct,                                            # Row sampling coverage
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")                                  # API key for Anthropic Claude
    if not api_key:
        return (                                                              # Return a helpful error with prompt preview
            "AI is not configured. Set ANTHROPIC_API_KEY to enable responses.\n\n"
            "Prompt preview:\n"
            f"{prompt}"
        )                                                                     # Return when API key is missing

    client = anthropic.Anthropic(api_key=api_key)                             # Create Claude API client
    message = client.messages.create(
        model="claude-sonnet-4-20250514",                                     # Claude model selection
        max_tokens=4096,                                                       # Limit response length to control cost
        messages=[{                                                           # Single user message payload
            "role": "user",                                                   # Message role for Claude API
            "content": prompt,                                                # Prompt text sent to Claude
        }],
    )

    return message.content[0].text                                            # Return the assistant response text
