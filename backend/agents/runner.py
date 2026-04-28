"""Shared Anthropic loop for the Web + Game analyst agents.

Both agents are identical at the loop level: they use the same single tool
(``explore_bigquery``), the same step budget, and the same fallback strategy
(``last assistant message`` -> ``forced final turn``). They differ only in
which describe payload they want and what their system prompt teaches them.

This module owns:
    * the per-step Anthropic loop,
    * payload-size + usage telemetry,
    * BigQuery cost rollup (per-query bytes billed -> USD estimate),
    * structured request tracing.

Everything agent-specific (system prompt, describe flags, filtered-game
table prep) lives in :mod:`backend.agents.web` / :mod:`backend.agents.game`.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

import anthropic

from backend.agents.prompts import USER_QUESTION_LABEL
from backend.agents.tools import build_explore_tool_schema
from backend.bigquery.runner import (
    estimate_bq_on_demand_usd,
    resolve_bq_on_demand_usd_per_tb,
    resolve_max_bytes,
)
from backend.config import get_anthropic_api_key, get_anthropic_model
from backend.logs.agent_logging import (
    begin_agent_trace,
    end_agent_trace,
    extract_usage_fields,
    log_agent_debug,
    log_agent_event,
    log_agent_warning,
    truncate_text,
)


# Both agents support long-form narrative output (Deep Scan reports), so
# default to the larger token budget. Chat answers are still bounded by the
# per-step ``max_tokens`` here even when the operator asks a short question.
MAX_AGENT_STEPS = 20
MAX_TOKENS = 4096


@dataclass
class AgentResult:
    """Return shape from :func:`run_agent`."""

    answer: str
    trace: list[dict[str, Any]]
    request_id: str
    cost_summary: dict[str, Any]


@dataclass
class _CostState:
    """Mutable per-run cost rollup."""

    per_query: list[dict[str, Any]] = field(default_factory=list)
    total_bytes: int = 0
    seq: int = 0


# ---------------------------------------------------------------------------
# Internal helpers (token / payload metrics, usage rollup)
# ---------------------------------------------------------------------------

def _accumulate_usage(totals: dict[str, int], usage: dict[str, Any]) -> None:
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ):
        if key in usage and usage[key] is not None:
            totals[key] = totals.get(key, 0) + int(usage[key])


def _cost_estimate_usd(totals: dict[str, int]) -> float | None:
    """Optional rough Anthropic USD using env prices (per million tokens)."""
    raw_in = os.getenv("ANTHROPIC_PRICE_INPUT_PER_M")
    raw_out = os.getenv("ANTHROPIC_PRICE_OUTPUT_PER_M")
    if not raw_in or not raw_out:
        return None
    try:
        inp = float(raw_in)
        out = float(raw_out)
    except ValueError:
        return None
    if inp < 0 or out < 0:
        return None
    i = totals.get("input_tokens", 0) / 1_000_000.0 * inp
    o = totals.get("output_tokens", 0) / 1_000_000.0 * out
    return round(i + o, 6)


def _usage_end_fields(totals: dict[str, int], api_calls: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "usage_totals": {
            "input_tokens": totals.get("input_tokens", 0),
            "output_tokens": totals.get("output_tokens", 0),
            "cache_creation_input_tokens": totals.get("cache_creation_input_tokens", 0),
            "cache_read_input_tokens": totals.get("cache_read_input_tokens", 0),
        },
        "api_calls": api_calls,
    }
    est = _cost_estimate_usd(totals)
    if est is not None:
        out["estimated_cost_usd"] = est
    return out


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _payload_metrics(system_prompt: str, messages: list, tools: list) -> dict:
    system_len = len(system_prompt or "")
    messages_json = json.dumps(messages, ensure_ascii=True, default=str)
    tools_json = json.dumps(tools, ensure_ascii=True, default=str)
    total_len = system_len + len(messages_json) + len(tools_json)
    approx_tokens = (
        _estimate_tokens(system_prompt)
        + _estimate_tokens(messages_json)
        + _estimate_tokens(tools_json)
    )
    return {
        "system_chars": system_len,
        "messages_chars": len(messages_json),
        "tools_chars": len(tools_json),
        "total_chars": total_len,
        "approx_context_tokens": approx_tokens,
    }


def _extract_text_blocks(message) -> str:
    parts = []
    for block in getattr(message, "content", []):
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _extract_tool_uses(message) -> list:
    tool_uses = []
    for block in getattr(message, "content", []):
        if getattr(block, "type", None) == "tool_use":
            tool_uses.append(block)
    return tool_uses


def _bq_cost_summary(state: _CostState) -> dict[str, Any]:
    """Final BigQuery cost rollup attached to every run."""
    total_est = estimate_bq_on_demand_usd(state.total_bytes)
    cap = resolve_max_bytes()
    return {
        "bigquery": {
            "query_count": len(state.per_query),
            "total_bytes_billed": state.total_bytes,
            "total_est_cost_usd": (
                round(total_est, 6) if total_est is not None else None
            ),
            "max_bytes_billed_cap": cap,
            "usd_per_tb_assumed": resolve_bq_on_demand_usd_per_tb(),
            "per_query": state.per_query,
        },
        "note": (
            "BigQuery est_cost_usd uses on-demand $/TB "
            "(GA4_BQ_ON_DEMAND_USD_PER_TB; default 6.25). Only "
            "explore_bigquery action=query jobs are counted; describe uses "
            "metadata APIs. Actual GCP invoices may differ."
        ),
    }


def _accumulate_query_cost(
    state: _CostState,
    *,
    step: int,
    intent: str | None,
    bytes_billed: int | None,
) -> None:
    if not isinstance(bytes_billed, int):
        return
    state.seq += 1
    state.total_bytes += bytes_billed
    cap = resolve_max_bytes()
    pct_cap = round(100.0 * bytes_billed / cap, 2) if cap > 0 else None
    est = estimate_bq_on_demand_usd(bytes_billed)
    state.per_query.append(
        {
            "seq": state.seq,
            "step": step,
            "intent": intent,
            "bytes_billed": bytes_billed,
            "est_cost_usd": round(est, 6) if est is not None else None,
            "bytes_billed_pct_of_cap": pct_cap,
        }
    )


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

# A dispatcher takes the raw tool-call input dict and returns the JSON-safe
# tool result. ``run_agent`` is otherwise tool-name agnostic.
ToolDispatcher = Callable[[dict[str, Any]], dict[str, Any]]


def build_user_message(body: str) -> str:
    """Wrap a free-form task / orchestrator with the standard task marker."""
    return f"{USER_QUESTION_LABEL}\n{body}"


def run_agent(
    *,
    agent_label: str,
    system_prompt: str,
    user_message: str,
    dispatch: ToolDispatcher,
    max_steps: int = MAX_AGENT_STEPS,
    max_tokens: int = MAX_TOKENS,
    request_id: str | None = None,
    collect_trace: bool = True,
) -> AgentResult:
    """Run the Anthropic tool-call loop for a single agent request.

    ``agent_label`` is used as a structured log prefix (e.g. ``web_agent`` ->
    ``web_agent_run_start``). ``dispatch`` handles every ``tool_use`` block on
    every step; the runner only knows that the model produces tool calls and
    expects a result back, with the optional ``bytes_billed`` field on
    ``action=query`` results used to roll up BigQuery cost.
    """
    rid = request_id or str(uuid4())
    trace_buf: list[dict[str, Any]] = (
        begin_agent_trace() if collect_trace else []
    )
    cost_state = _CostState()
    try:
        api_key = get_anthropic_api_key()
        if not api_key:
            log_agent_warning(
                f"{agent_label}_missing_api_key",
                request_id=rid,
            )
            return AgentResult(
                answer=(
                    "AI is not configured. Set ANTHROPIC_API_KEY to enable "
                    f"responses.\n\nPrompt preview:\n{user_message}"
                ),
                trace=trace_buf,
                request_id=rid,
                cost_summary=_bq_cost_summary(cost_state),
            )

        model = get_anthropic_model()
        tools = [build_explore_tool_schema()]
        client = anthropic.Anthropic(api_key=api_key)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]
        last_message = None

        log_agent_event(
            f"{agent_label}_run_start",
            request_id=rid,
            model=model,
            max_steps=max_steps,
            max_tokens=max_tokens,
            user_message_chars=len(user_message),
            effective_system_chars=len(system_prompt),
        )

        usage_totals: dict[str, int] = {}
        api_calls = 0

        initial_metrics = _payload_metrics(system_prompt, messages, tools)
        log_agent_event(
            f"{agent_label}_payload_size",
            request_id=rid,
            phase="initial",
            **initial_metrics,
        )

        for step in range(max_steps):
            t0 = time.monotonic()
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                tools=tools,
                system=system_prompt,
                messages=messages,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            last_message = message
            tool_uses = _extract_tool_uses(message)
            messages.append({"role": "assistant", "content": message.content})

            usage = extract_usage_fields(message)
            _accumulate_usage(usage_totals, usage)
            api_calls += 1
            log_agent_event(
                f"{agent_label}_step_complete",
                request_id=rid,
                step=step,
                tool_calls=len(tool_uses),
                duration_ms=elapsed_ms,
                **usage,
            )

            if not tool_uses:
                text = _extract_text_blocks(message)
                if text:
                    cs = _bq_cost_summary(cost_state)
                    log_agent_event(
                        f"{agent_label}_run_end",
                        request_id=rid,
                        outcome="text_reply",
                        steps_used=step + 1,
                        reply_chars=len(text),
                        bq_cost=cs["bigquery"],
                        **_usage_end_fields(usage_totals, api_calls),
                    )
                    return AgentResult(text, trace_buf, rid, cs)
                log_agent_warning(
                    f"{agent_label}_empty_assistant_no_tools",
                    request_id=rid,
                    step=step,
                )
                break

            tool_results = []
            for tool_use in tool_uses:
                params = (
                    tool_use.input if isinstance(tool_use.input, dict) else {}
                )
                intent = params.get("intent")
                action = params.get("action")
                query = params.get("query")
                if query:
                    log_agent_debug(
                        f"{agent_label}_tool_sql",
                        request_id=rid,
                        step=step,
                        action=action,
                        query=truncate_text(query, 800),
                    )

                if tool_use.name == "explore_bigquery":
                    result = dispatch(params)
                    if (
                        action == "query"
                        and isinstance(result, dict)
                        and not result.get("error")
                    ):
                        _accumulate_query_cost(
                            cost_state,
                            step=step,
                            intent=intent,
                            bytes_billed=result.get("bytes_billed"),
                        )
                else:
                    result = {"error": f"Unknown tool: {tool_use.name}."}

                result_json = json.dumps(result, ensure_ascii=True, default=str)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_json,
                    }
                )
                err = result.get("error") if isinstance(result, dict) else None
                log_agent_event(
                    f"{agent_label}_tool_result",
                    request_id=rid,
                    step=step,
                    tool_name=tool_use.name,
                    intent=intent,
                    action=action,
                    result_ok=err is None,
                    result_error=err,
                    result_chars=len(result_json),
                )

            messages.append({"role": "user", "content": tool_results})
            post_metrics = _payload_metrics(system_prompt, messages, tools)
            log_agent_event(
                f"{agent_label}_payload_size",
                request_id=rid,
                phase="after_tools",
                step=step,
                **post_metrics,
            )

            if step == max_steps - 1:
                log_agent_warning(
                    f"{agent_label}_max_steps_reached",
                    request_id=rid,
                    max_steps=max_steps,
                )

        # Out of steps without a plain text answer: try the last assistant
        # message's text blocks, then force one final tool-less turn.
        fallback_text = _extract_text_blocks(last_message)
        if fallback_text:
            cs = _bq_cost_summary(cost_state)
            log_agent_event(
                f"{agent_label}_run_end",
                request_id=rid,
                outcome="fallback_last_assistant",
                reply_chars=len(fallback_text),
                bq_cost=cs["bigquery"],
                **_usage_end_fields(usage_totals, api_calls),
            )
            return AgentResult(fallback_text, trace_buf, rid, cs)

        t0 = time.monotonic()
        forced_message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages
            + [
                {
                    "role": "user",
                    "content": (
                        "You have enough data. Write the final answer now. "
                        "Do not call tools."
                    ),
                }
            ],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        usage = extract_usage_fields(forced_message)
        _accumulate_usage(usage_totals, usage)
        api_calls += 1
        log_agent_event(
            f"{agent_label}_forced_final_call",
            request_id=rid,
            duration_ms=elapsed_ms,
            **usage,
        )
        forced_text = _extract_text_blocks(forced_message)
        if forced_text:
            cs = _bq_cost_summary(cost_state)
            log_agent_event(
                f"{agent_label}_run_end",
                request_id=rid,
                outcome="forced_final_message",
                reply_chars=len(forced_text),
                bq_cost=cs["bigquery"],
                **_usage_end_fields(usage_totals, api_calls),
            )
            return AgentResult(forced_text, trace_buf, rid, cs)

        cs = _bq_cost_summary(cost_state)
        log_agent_event(
            f"{agent_label}_run_end",
            request_id=rid,
            outcome="no_text",
            bq_cost=cs["bigquery"],
            **_usage_end_fields(usage_totals, api_calls),
        )
        return AgentResult(
            "No response generated. The agent did not produce a final text answer.",
            trace_buf,
            rid,
            cs,
        )
    finally:
        if collect_trace:
            end_agent_trace()
