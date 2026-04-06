# This module runs the GA4 analysis agent and routes SQL tool calls.

from __future__ import annotations

import json
import os
import time
from typing import Any
from uuid import uuid4

import anthropic

from logs.agent_logging import (
    begin_agent_trace,
    end_agent_trace,
    extract_usage_fields,
    log_agent_debug,
    log_agent_event,
    log_agent_warning,
    truncate_text,
)
from backend.ai.prompts import (
    AGENT_SYSTEM_PROMPT,
    BUTTON_PROMPTS,
    REPORT_CONTEXT_LABEL,
    USER_QUESTION_LABEL,
)
from backend.ai.tools.sql import (
    build_report_catalog,
    build_report_tables,
    build_explore_tool_schema,
    explore_table_data,
)


MAX_AGENT_STEPS = 10                                                         # Max tool-call turns per request (increased to handle SQL syntax errors during debugging)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)                                            # Rough heuristic for Claude tokens


def _payload_metrics(system_prompt: str, messages: list, tools: list) -> dict:
    system_len = len(system_prompt or "")
    messages_json = json.dumps(messages, ensure_ascii=True, default=str)
    tools_json = json.dumps(tools, ensure_ascii=True, default=str)
    total_len = system_len + len(messages_json) + len(tools_json)
    approx_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(messages_json) + _estimate_tokens(tools_json)
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


def build_agent_prompt(
    selected_reports: list[dict],
    user_question: str,
    prompt_key: str | None,
    prompt_template_override: str | None = None,
) -> str:
    if prompt_template_override and str(prompt_template_override).strip():
        template = str(prompt_template_override)
        instruction_text = template.replace("{USER_QUESTION}", user_question)
    elif prompt_key:
        template = BUTTON_PROMPTS.get(prompt_key, user_question)
        instruction_text = template.replace("{USER_QUESTION}", user_question)
    else:
        instruction_text = user_question
    catalog_json = json.dumps(
        {"reports": build_report_catalog(selected_reports)},
        ensure_ascii=True,
        default=str,
    )
    return (
        f"{REPORT_CONTEXT_LABEL}\n"
        f"{catalog_json}\n\n"
        f"{USER_QUESTION_LABEL}\n"
        f"{instruction_text}"
    )


def analyze_selected_reports(
    selected_reports: list[dict],
    user_question: str,
    prompt_key: str | None = None,
    prompt_template_override: str | None = None,
    system_prompt_override: str | None = None,
    request_id: str | None = None,
    collect_trace: bool = True,
) -> tuple[str, list[dict[str, Any]], str]:
    """Returns (answer_text, structured_trace_events, request_id)."""
    rid = request_id or str(uuid4())
    if collect_trace:
        trace_buf = begin_agent_trace()
    else:
        trace_buf = []
    try:
        effective_system = (
            system_prompt_override.strip()
            if system_prompt_override and str(system_prompt_override).strip()
            else AGENT_SYSTEM_PROMPT
        )

        prompt = build_agent_prompt(
            selected_reports=selected_reports,
            user_question=user_question,
            prompt_key=prompt_key,
            prompt_template_override=prompt_template_override,
        )

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            log_agent_warning(
                "agent_missing_api_key",
                request_id=rid,
                prompt_key=prompt_key,
            )
            return (
                (
                    "AI is not configured. Set ANTHROPIC_API_KEY to enable responses.\n\n"
                    "Prompt preview:\n"
                    f"{prompt}"
                ),
                trace_buf,
                rid,
            )

        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        report_ids = [r.get("id") for r in selected_reports if r.get("id")]

        log_agent_event(
            "agent_run_start",
            request_id=rid,
            model=model,
            prompt_key=prompt_key,
            report_ids=report_ids,
            max_steps=MAX_AGENT_STEPS,
            user_question_chars=len(user_question or ""),
        )

        tables = build_report_tables(selected_reports)
        tools = [build_explore_tool_schema()]
        client = anthropic.Anthropic(api_key=api_key)

        messages = [{"role": "user", "content": prompt}]
        last_message = None

        initial_metrics = _payload_metrics(effective_system, messages, tools)
        log_agent_event("agent_payload_size", request_id=rid, phase="initial", **initial_metrics)

        for step in range(MAX_AGENT_STEPS):
            t0 = time.monotonic()
            message = client.messages.create(
                model=model,
                max_tokens=2048,
                tools=tools,
                system=effective_system,
                messages=messages,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            last_message = message
            tool_uses = _extract_tool_uses(message)
            messages.append({"role": "assistant", "content": message.content})

            usage = extract_usage_fields(message)
            log_agent_event(
                "agent_step_complete",
                request_id=rid,
                step=step,
                tool_calls=len(tool_uses),
                duration_ms=elapsed_ms,
                **usage,
            )

            if not tool_uses:
                text = _extract_text_blocks(message)
                if text:
                    log_agent_event(
                        "agent_run_end",
                        request_id=rid,
                        outcome="text_reply",
                        steps_used=step + 1,
                        reply_chars=len(text),
                    )
                    return text, trace_buf, rid
                log_agent_warning(
                    "agent_empty_assistant_no_tools",
                    request_id=rid,
                    step=step,
                )
                break

            tool_results = []
            for tool_use in tool_uses:
                if isinstance(tool_use.input, dict):
                    intent = tool_use.input.get("intent")
                else:
                    intent = None
                action = None
                table_name = None
                if tool_use.name == "explore_table_data":
                    params = tool_use.input if isinstance(tool_use.input, dict) else {}
                    action = params.get("action")
                    table_name = params.get("table_name")
                    query = params.get("query")
                    if query:
                        log_agent_debug(
                            "agent_tool_sql",
                            request_id=rid,
                            step=step,
                            action=action,
                            table_name=table_name,
                            query=truncate_text(query, 800),
                        )
                    result = explore_table_data(params, tables)
                else:
                    result = {"error": f"Unknown tool: {tool_use.name}."}
                result_json = json.dumps(result, ensure_ascii=True, default=str)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result_json,
                })
                err = result.get("error") if isinstance(result, dict) else None
                log_agent_event(
                    "agent_tool_result",
                    request_id=rid,
                    step=step,
                    tool_name=tool_use.name,
                    intent=intent,
                    action=action if tool_use.name == "explore_table_data" else None,
                    table_name=table_name if tool_use.name == "explore_table_data" else None,
                    result_ok=err is None,
                    result_error=err,
                    result_chars=len(result_json),
                )

            messages.append({"role": "user", "content": tool_results})
            post_metrics = _payload_metrics(effective_system, messages, tools)
            log_agent_event("agent_payload_size", request_id=rid, phase="after_tools", step=step, **post_metrics)

            if step == MAX_AGENT_STEPS - 1:
                log_agent_warning(
                    "agent_max_steps_reached",
                    request_id=rid,
                    max_steps=MAX_AGENT_STEPS,
                )

        fallback_text = _extract_text_blocks(last_message)
        if fallback_text:
            log_agent_event(
                "agent_run_end",
                request_id=rid,
                outcome="fallback_last_assistant",
                reply_chars=len(fallback_text),
            )
            return fallback_text, trace_buf, rid

        t0 = time.monotonic()
        forced_message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=effective_system,
            messages=messages + [{
                "role": "user",
                "content": "Provide the final answer now. Do not call tools.",
            }],
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        usage = extract_usage_fields(forced_message)
        log_agent_event(
            "agent_forced_final_call",
            request_id=rid,
            duration_ms=elapsed_ms,
            **usage,
        )
        forced_text = _extract_text_blocks(forced_message)
        if forced_text:
            log_agent_event(
                "agent_run_end",
                request_id=rid,
                outcome="forced_final_message",
                reply_chars=len(forced_text),
            )
            return forced_text, trace_buf, rid
        log_agent_warning("agent_run_end", request_id=rid, outcome="no_text")
        return "No response generated. The agent did not produce a final text answer.", trace_buf, rid
    finally:
        if collect_trace:
            end_agent_trace()
