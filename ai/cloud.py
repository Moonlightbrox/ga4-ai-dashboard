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


def analyze_selected_reports(
    selected_reports: list[dict],
    user_question: str,
    prompt_key: str | None = None,
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

    report_context = []
    for report in selected_reports:
        report_df = report.get("data")
        report_rows = (
            report_df.head(200).to_dict(orient="records")
            if report_df is not None
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

    prompt = (
        f"{SYSTEM_ROLE_PROMPT}\n\n"
        f"{REPORT_CONTEXT_LABEL}\n"
        f"{report_context_json}\n\n"
        f"{USER_QUESTION_LABEL}\n"
        f"{instruction_text}\n\n"
        f"{ANALYSIS_RULES_PROMPT}"
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
