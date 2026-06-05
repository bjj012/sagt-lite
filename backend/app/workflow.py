from __future__ import annotations

import json

from .agent_tools import (
    CustomerContext,
    build_customer_profile,
    generate_chat_advice,
    generate_customer_tags,
    generate_schedule_advice,
    generate_service_advice,
)


TASK_LABELS = {
    "profile": "生成客户画像",
    "tags": "生成客户标签",
    "chat_advice": "生成聊天建议",
    "service_advice": "生成客服建议",
    "schedule_advice": "生成日程建议",
}


class SalesAgentWorkflow:
    """A small LangGraph-style state machine for a sales assistant demo."""

    def run(self, ctx: CustomerContext, task_type: str, variant: int = 0) -> dict:
        if task_type not in TASK_LABELS:
            raise ValueError(f"Unsupported task_type: {task_type}")

        state = {
            "task": TASK_LABELS[task_type],
            "customer": ctx.name,
            "steps": [],
            "result": None,
            "reasoning": "",
        }
        self.intent_node(state, task_type)
        self.memory_node(state, ctx)
        self.tool_node(state, ctx, task_type, variant)
        self.review_node(state)
        return state

    def intent_node(self, state: dict, task_type: str) -> None:
        state["steps"].append({"node": "intent", "message": f"识别任务类型：{TASK_LABELS[task_type]}"})

    def memory_node(self, state: dict, ctx: CustomerContext) -> None:
        state["steps"].append(
            {
                "node": "memory",
                "message": f"读取客户长期记忆：{len(ctx.interactions)} 条互动记录，{len(ctx.tags)} 个历史标签。",
            }
        )

    def tool_node(self, state: dict, ctx: CustomerContext, task_type: str, variant: int) -> None:
        tools = {
            "profile": build_customer_profile,
            "tags": generate_customer_tags,
            "chat_advice": generate_chat_advice,
            "service_advice": generate_service_advice,
            "schedule_advice": generate_schedule_advice,
        }
        result = tools[task_type](ctx, variant=variant)
        state["result"] = result
        state["steps"].append({"node": "tool", "message": f"调用工具完成：{TASK_LABELS[task_type]}"})

    def review_node(self, state: dict) -> None:
        state["steps"].append({"node": "human_review", "message": "等待销售确认、放弃或重新生成。"})
        state["reasoning"] = " -> ".join(step["message"] for step in state["steps"])


def to_json(data) -> str:
    return json.dumps(data, ensure_ascii=False)
