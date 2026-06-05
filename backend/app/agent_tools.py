from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class CustomerContext:
    id: int
    name: str
    level: str
    notes: str
    profile: dict
    tags: list[str]
    interactions: list[str]


def build_customer_profile(ctx: CustomerContext, variant: int = 0) -> dict:
    text = context_text(ctx)
    profile = {
        "姓名": ctx.name,
        "客户等级": ctx.level,
        "消费偏好": infer_preferences(text),
        "预算区间": infer_budget(text),
        "家庭与社交": infer_family(text),
        "关键诉求": infer_need(text),
        "沟通风格": infer_style(text),
        "风险提醒": infer_risk(text),
    }
    if variant:
        profile["本次更新重点"] = "重新生成版本：更强调客户近期需求和下一步销售动作。"
    return profile


def generate_customer_tags(ctx: CustomerContext, variant: int = 0) -> list[str]:
    text = context_text(ctx)
    tags = [f"{ctx.level}级客户"]
    if "茅台" in text or "五粮液" in text or "白酒" in text:
        tags.append("白酒偏好")
    if "红酒" in text:
        tags.append("红酒可推荐")
    if "预算" in text:
        tags.append("预算明确")
    if "家庭" in text or "父亲" in text or "儿子" in text:
        tags.append("家庭场景")
    if "年会" in text or "商务" in text or "对公" in text:
        tags.append("商务宴请")
    if "物流" in text or "发货" in text or "交付" in text:
        tags.append("交付敏感")
    if "定制" in text:
        tags.append("定制服务")
    if variant:
        tags.append("需二次确认")
    return dedupe(tags)


def generate_chat_advice(ctx: CustomerContext, variant: int = 0) -> dict:
    profile = build_customer_profile(ctx, variant)
    need = profile["关键诉求"]
    preference = "、".join(profile["消费偏好"])
    opening = f"好的{ctx.name}，我先按您这次“{need}”的需求准备方案。"
    if variant:
        opening = f"{ctx.name}您好，我重新梳理了一版更稳妥的沟通建议，先确认预算和送达时间。"
    message = (
        f"{opening}结合您过往偏好（{preference}），我建议准备2-3个档位："
        "一档稳妥体面，一档性价比高，一档适合送礼或宴请。"
        "我会同时确认库存、包装和送达时间，避免临时变动影响安排。"
    )
    return {
        "建议话术": message,
        "使用场景": "微信跟进 / 电话前准备",
        "销售意图": "先承接需求，再用历史偏好降低决策成本，最后推进确认。",
    }


def generate_service_advice(ctx: CustomerContext, variant: int = 0) -> dict:
    text = context_text(ctx)
    actions = ["确认客户本次预算、送达时间和收货地址", "给出2-3个可选方案并标注库存状态"]
    if "发货" in text or "物流" in text or "交付" in text:
        actions.append("主动同步物流保护措施和发货节点")
    if "发票" in text or "对公" in text:
        actions.append("提前确认开票抬头、税号和合同流程")
    if "定制" in text:
        actions.append("发送定制样稿并设置确认截止时间")
    if variant:
        actions.append("重新生成建议：增加一次售后回访提醒")
    return {
        "服务动作": actions,
        "优先级": "高" if ctx.level in {"A", "S"} else "中",
        "注意事项": "重要承诺需要在系统中留痕，避免只停留在聊天记录。",
    }


def generate_schedule_advice(ctx: CustomerContext, variant: int = 0) -> dict:
    text = context_text(ctx)
    if "明天上午10点" in text:
        time = "明天上午 09:20"
        title = "商务宴请用酒方案确认"
    elif "年会" in text:
        time = "本周五 15:00"
        title = "年会采购方案与开票信息确认"
    else:
        time = "明天 10:00"
        title = "客户需求跟进"
    if variant:
        time = "明天 09:00"
    return {
        "日程标题": title,
        "建议时间": time,
        "提醒内容": f"跟进{ctx.name}的需求，确认预算、方案、库存和交付节点。",
        "原因": "根据客户最近咨询和历史偏好生成，防止关键跟进节点遗漏。",
    }


def context_text(ctx: CustomerContext) -> str:
    return "\n".join([ctx.notes, *ctx.interactions, json.dumps(ctx.profile, ensure_ascii=False)])


def infer_preferences(text: str) -> list[str]:
    preferences = []
    for item in ["茅台", "五粮液", "红酒", "白酒", "礼盒", "果酒", "茶点", "定制瓶身"]:
        if item in text:
            preferences.append(item)
    return preferences or ["品质稳定", "服务可靠"]


def infer_budget(text: str) -> str:
    numbers = [int(value) for value in re.findall(r"(\d+)元", text)]
    if len(numbers) >= 2:
        return f"{min(numbers)}-{max(numbers)}元"
    if numbers:
        return f"约{numbers[0]}元"
    if "预算较高" in text:
        return "高预算"
    return "未明确"


def infer_family(text: str) -> str:
    clues = []
    for item in ["儿子", "父亲", "家庭聚会", "商务宴请", "年会"]:
        if item in text:
            clues.append(item)
    return "、".join(clues) if clues else "暂无明显家庭/社交信息"


def infer_need(text: str) -> str:
    if "商务宴请" in text:
        return "商务宴请用酒"
    if "年会" in text:
        return "企业年会采购"
    if "端午" in text or "礼盒" in text:
        return "节日礼盒采购"
    if "物流" in text:
        return "物流与售后确认"
    return "商品推荐与跟进"


def infer_style(text: str) -> str:
    if "不喜欢过度推销" in text:
        return "克制、直接、强调性价比"
    if "面子" in text or "商务" in text:
        return "重视体面与专业感"
    if "交付时间" in text:
        return "偏结果导向，需要明确排期"
    return "友好、简洁、给选择"


def infer_risk(text: str) -> str:
    if "发货" in text or "物流" in text or "交付" in text:
        return "需提前同步物流与交付节点"
    if "发票" in text:
        return "需确认开票资料和合同流程"
    return "暂无高风险，建议保持主动跟进"


def dedupe(items: list[str]) -> list[str]:
    result = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
