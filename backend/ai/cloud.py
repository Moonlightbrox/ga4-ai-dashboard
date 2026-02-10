# This module runs the GA4 analysis agent and routes SQL tool calls.

import json
import os

import anthropic

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


MAX_AGENT_STEPS = 20                                                         # Max tool-call turns per request


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)                                            # Rough heuristic for Claude tokens


def _payload_size_summary(system_prompt: str, messages: list, tools: list) -> str:
    system_len = len(system_prompt or "")
    messages_json = json.dumps(messages, ensure_ascii=True, default=str)
    tools_json = json.dumps(tools, ensure_ascii=True, default=str)
    total_len = system_len + len(messages_json) + len(tools_json)
    approx_tokens = _estimate_tokens(system_prompt) + _estimate_tokens(messages_json) + _estimate_tokens(tools_json)
    return (
        f"Payload chars: system={system_len}, messages={len(messages_json)}, tools={len(tools_json)}, "
        f"total={total_len}, approx_tokens={approx_tokens}"
    )


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
) -> str:
    if prompt_key:
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
    selected_reports: list[dict],                                             # Reports to include in the AI prompt
    user_question: str,                                                       # The user's question in plain language
    prompt_key: str | None = None,                                            # Optional template key for button prompts
) -> str:
    prompt = build_agent_prompt(
        selected_reports=selected_reports,
        user_question=user_question,
        prompt_key=prompt_key,
    )

    api_key = os.getenv("ANTHROPIC_API_KEY")                                  # API key for Anthropic Claude
    if not api_key:
        return (
            "AI is not configured. Set ANTHROPIC_API_KEY to enable responses.\n\n"
            "Prompt preview:\n"
            f"{prompt}"
        )

    tables = build_report_tables(selected_reports)
    tools = [build_explore_tool_schema()]
    client = anthropic.Anthropic(api_key=api_key)

    messages = [{"role": "user", "content": prompt}]
    last_message = None
    print(_payload_size_summary(AGENT_SYSTEM_PROMPT, messages, tools))        # Debug: payload size

    for step in range(MAX_AGENT_STEPS):
        print("AI agent step started.")                                       # Debug: track agent steps
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            tools=tools,
            system=AGENT_SYSTEM_PROMPT,
            messages=messages,
        )
        last_message = message
        tool_uses = _extract_tool_uses(message)
        messages.append({"role": "assistant", "content": message.content})
        print(f"AI agent tool calls: {len(tool_uses)}")                       # Debug: tool call count

        if not tool_uses:
            text = _extract_text_blocks(message)
            if text:
                return text
            print("AI agent returned no text output.")                        # Debug: no text
            break

        tool_results = []
        for tool_use in tool_uses:
            if isinstance(tool_use.input, dict):
                intent = tool_use.input.get("intent")
                if intent:
                    print(f"Tool intent ({tool_use.name}): {intent}")         # Debug: tool intent
            if tool_use.name == "explore_table_data":
                params = tool_use.input if isinstance(tool_use.input, dict) else {}
                action = params.get("action")
                table_name = params.get("table_name")
                query = params.get("query")
                if action:
                    print(f"Explore action: {action}")                         # Debug: explore action
                if table_name:
                    print(f"Explore table: {table_name}")                      # Debug: explore table name
                if query:
                    print(f"SQL query: {query}")                               # Debug: SQL query text
                result = explore_table_data(params, tables)
            else:
                result = {"error": f"Unknown tool: {tool_use.name}."}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": json.dumps(result, ensure_ascii=True, default=str),
            })
            print(f"Tool result for {tool_use.name}: {result.get('error', 'ok')}")  # Debug: tool result status

        messages.append({"role": "user", "content": tool_results})
        print(_payload_size_summary(AGENT_SYSTEM_PROMPT, messages, tools))    # Debug: payload size

        if step == MAX_AGENT_STEPS - 1:
            print("AI agent reached max steps; forcing final answer.")        # Debug: forced final answer

    fallback_text = _extract_text_blocks(last_message)
    if fallback_text:
        return fallback_text

    forced_message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=AGENT_SYSTEM_PROMPT,
        messages=messages + [{
            "role": "user",
            "content": "Provide the final answer now. Do not call tools.",
        }],
    )
    forced_text = _extract_text_blocks(forced_message)
    if forced_text:
        return forced_text
    return "No response generated. The agent did not produce a final text answer."
