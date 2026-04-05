"""
Lightweight tracing helpers for orchestrator and tool execution.
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.agent_tool import AgentTool
from typing_extensions import override

logger = logging.getLogger(__name__)


def trace_fields_from_state(state) -> dict[str, str]:
    return {
        "task_id": state.get("task_id", ""),
        "context_id": state.get("context_id", ""),
        "message_id": state.get("message_id", ""),
        "patient_id": state.get("patient_id", ""),
    }


class TracingAgentTool(AgentTool):
    """AgentTool wrapper that logs orchestrator sub-agent invocations."""

    @override
    async def run_async(self, *, args: dict[str, Any], tool_context) -> Any:
        trace = trace_fields_from_state(tool_context.state)
        logger.info(
            "agent_tool_start agent=%s task_id=%s context_id=%s message_id=%s patient_id=%s arg_keys=%s",
            self.agent.name,
            trace["task_id"],
            trace["context_id"],
            trace["message_id"],
            trace["patient_id"],
            sorted(args.keys()),
        )
        result = await super().run_async(args=args, tool_context=tool_context)
        logger.info(
            "agent_tool_finish agent=%s task_id=%s context_id=%s message_id=%s patient_id=%s result_type=%s",
            self.agent.name,
            trace["task_id"],
            trace["context_id"],
            trace["message_id"],
            trace["patient_id"],
            type(result).__name__,
        )
        return result
