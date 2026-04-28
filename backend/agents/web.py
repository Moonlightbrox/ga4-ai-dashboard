"""Web Analyst AI entrypoint.

Reads the ``site_*`` summary tables built by
:mod:`backend.bigquery.materialize_web` and produces either:

- a Deep Scan narrative report (when ``mode='deep_scan'``), or
- a free-form chat answer to ``user_question`` (when ``mode='chat'``).

Both paths use the same ``WEB_SYSTEM_PROMPT`` and the same single tool
(``explore_bigquery``); only the user message changes.
"""

from __future__ import annotations

from typing import Any, Literal

from backend.agents.prompts import WEB_ORCHESTRATOR_PROMPT, WEB_SYSTEM_PROMPT
from backend.agents.runner import AgentResult, build_user_message, run_agent
from backend.agents.tools import explore_bigquery


WebMode = Literal["deep_scan", "chat"]


def run_web_agent(
    *,
    property_id: str,
    mode: WebMode,
    user_question: str | None = None,
    request_id: str | None = None,
    collect_trace: bool = True,
) -> AgentResult:
    """Run the Web Analyst AI for a property.

    ``mode='deep_scan'`` ignores ``user_question`` and uses
    :data:`WEB_ORCHESTRATOR_PROMPT` as the task body. ``mode='chat'`` requires
    ``user_question`` and uses it verbatim. Both are wrapped with the standard
    ``USER_QUESTION:`` marker by :func:`build_user_message`.
    """
    if mode == "deep_scan":
        body = WEB_ORCHESTRATOR_PROMPT
    elif mode == "chat":
        body = (user_question or "").strip()
        if not body:
            raise ValueError("Web Analyst chat requires a non-empty question.")
    else:  # pragma: no cover - defensive
        raise ValueError(f"Unsupported web mode: {mode!r}")

    def dispatch(params: dict[str, Any]) -> dict[str, Any]:
        return explore_bigquery(
            params,
            property_id,
            include_web_summary=True,
        )

    return run_agent(
        agent_label="web_agent",
        system_prompt=WEB_SYSTEM_PROMPT,
        user_message=build_user_message(body),
        dispatch=dispatch,
        request_id=request_id,
        collect_trace=collect_trace,
    )
