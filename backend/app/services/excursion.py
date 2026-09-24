"""温度异常业务规则：状态流转、字段校验、筛选口径与超限判定都收在这里。

超限判定口径（按异常类型分别配置）：
- 每种异常类型可配置「允许超限时长上限（分钟）」与「允许最高温度上限（℃）」；
- 事件实测值任意一项超过对应上限，即判定为「需要处置」；两项都在标准之内才允许直接结单；
- 某异常类型没有配置规则，或配置项缺失/无法解析为有效数值时，沿用系统默认口径
  （DEFAULT_RULE），并在判定依据里说明原因，保证规则缺失或填写无效时仍有原有判定可用。
"""
from __future__ import annotations

import threading
from typing import Any

from app.store import store

MODULE = "excursion"
REQUIRED_FIELDS = ["事件编号", "关联运单", "异常类型"]
OPTIONAL_FIELDS = ["超限时长", "最高温度", "发生时间", "处置人"]
STATUS_ORDER = ["待处置", "处置中", "已闭环", "已忽略"]
ACTION_RULES = {"受理事件": "处置中", "提交处置": "已闭环", "忽略事件": "已忽略"}
NEGATIVE_ACTIONS = ["忽略事件"]
OPEN_STATUSES = ("待处置", "处置中")

# 系统默认口径：规则缺失或填写无效时保留的原有判定。
DEFAULT_RULE: dict[str, float] = {"maxDuration": 30.0, "maxTemperature": 8.0}
DEFAULT_RULE_LABEL = "系统默认口径：超限时长≤30分钟且最高温度≤8℃"

# 按异常类型配置的判定规则，key 为异常类型名称。
RULES: dict[str, dict[str, float]] = {
    "冷藏超限": {"maxDuration": 30.0, "maxTemperature": 8.0},
    "冷冻超限": {"maxDuration": 20.0, "maxTemperature": -15.0},
    "开门超时": {"maxDuration": 10.0, "maxTemperature": 8.0},
}

_rules_lock = threading.Lock()


def _to_number(value: Any) -> float | None:
    """把前端/数据里的实测值解析成数字；空值或无法解析时返回 None。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    # 容忍「35 分钟」「-12 ℃」这类带单位的写法。
    text = text.replace("分钟", "").replace("℃", "").replace("°C", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _resolve_rule(abnormal_type: str) -> tuple[dict[str, float], str | None]:
    """取异常类型对应的有效规则；缺失或无效时回退默认口径并给出原因。"""
    rule = RULES.get(str(abnormal_type or "").strip())
    if not rule:
        return dict(DEFAULT_RULE), f"异常类型「{abnormal_type}」尚未配置判定规则，沿用{DEFAULT_RULE_LABEL}"
    issues: list[str] = []
    duration = _to_number(rule.get("maxDuration"))
    temperature = _to_number(rule.get("maxTemperature"))
    if duration is None or duration < 0:
        issues.append("超限时长上限缺失或不是不小于 0 的数字")
    if temperature is None:
        issues.append("最高温度上限缺失或不是有效数字")
    if issues:
        return dict(DEFAULT_RULE), (
            f"异常类型「{abnormal_type}」的判定规则无效（{'、'.join(issues)}），沿用{DEFAULT_RULE_LABEL}"
        )
    return {"maxDuration": duration, "maxTemperature": temperature}, None


def evaluate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """按当前规则评估单条事件，返回判定结论与依据。

    - 已闭环/已忽略事件沿用结单时冻结的结论，口径刷新不翻历史账；
    - 进行中的事件每次都按最新规则重新评估（刷新规则后重新进入即可看到新结论）；
    - 实测值缺失或无法解析时不猜测，标记待人工核定并保留原有判定。
    """
    status = str(entry.get("status") or "")
    if status not in OPEN_STATUSES and entry.get("判定结论"):
        return {
            "verdict": entry.get("判定结论"),
            "reasons": entry.get("判定依据"),
            "ruleSource": entry.get("规则口径"),
            "ruleInvalid": bool(entry.get("规则异常")),
            "snapshot": True,
        }

    abnormal_type = str(entry.get("异常类型") or "").strip()
    duration = _to_number(entry.get("超限时长"))
    temperature = _to_number(entry.get("最高温度"))
    rule, rule_issue = _resolve_rule(abnormal_type)

    reasons: list[str] = []
    if rule_issue:
        reasons.append(rule_issue)

    if duration is None or temperature is None:
        missing: list[str] = []
        if duration is None:
            missing.append("超限时长")
        if temperature is None:
            missing.append("最高温度")
        reasons.append(
            f"实测{'、'.join(missing)}缺失或无法解析为数字，无法自动比对，按原有判定转人工核定"
        )
        return {
            "verdict": "待人工核定",
            "reasons": "；".join(reasons),
            "ruleSource": "系统默认口径" if rule_issue else f"{abnormal_type}专属规则",
            "ruleInvalid": bool(rule_issue),
            "snapshot": False,
        }

    over_duration = duration > rule["maxDuration"]
    over_temperature = temperature > rule["maxTemperature"]
    if over_duration:
        reasons.append(
            f"超限时长 {duration:g} 分钟，超过允许上限 {rule['maxDuration']:g} 分钟"
        )
    else:
        reasons.append(
            f"超限时长 {duration:g} 分钟，在允许上限 {rule['maxDuration']:g} 分钟以内"
        )
    if over_temperature:
        reasons.append(
            f"最高温度 {temperature:g}℃，超过允许上限 {rule['maxTemperature']:g}℃"
        )
    else:
        reasons.append(
            f"最高温度 {temperature:g}℃，在允许上限 {rule['maxTemperature']:g}℃以内"
        )

    verdict = "需要处置" if (over_duration or over_temperature) else "允许结单"
    if verdict == "需要处置":
        reasons.append("任一项越界，判定为需要处置")
    else:
        reasons.append("两项均在标准之内，允许直接结单")
    source = "系统默认口径" if rule_issue else f"{abnormal_type}专属规则"
    return {
        "verdict": verdict,
        "reasons": "；".join(reasons),
        "ruleSource": source,
        "ruleInvalid": bool(rule_issue),
        "snapshot": False,
    }


def _annotate(entry: dict[str, Any]) -> dict[str, Any]:
    """把判定结论写进返回数据，列表与详情共用同一口径；内部字段不外泄。"""
    result = {key: value for key, value in entry.items() if not key.startswith("_")}
    result.update(evaluate_entry(entry))
    return result


class ExcursionService:
    def __init__(self) -> None:
        # 记录处置中事件按当前口径得出的结论，作为规则刷新后统计结论变化的基线。
        for row in store.rows(MODULE):
            if row.get("status") == "处置中":
                row["_lastVerdict"] = evaluate_entry(row)["verdict"]

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("事件编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [_annotate(row) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _annotate(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in OPTIONAL_FIELDS:
            if values.get(field) is not None:
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _annotate(entry), []

    def list_rules(self) -> list[dict[str, Any]]:
        """返回全部异常类型的规则及当前可用性说明。"""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for abnormal_type in [str(row.get("异常类型") or "").strip() for row in store.rows(MODULE)]:
            if abnormal_type and abnormal_type not in seen:
                seen.add(abnormal_type)
                result.append(self._rule_view(abnormal_type))
        for abnormal_type in RULES:
            if abnormal_type not in seen:
                seen.add(abnormal_type)
                result.append(self._rule_view(abnormal_type))
        return result

    def _rule_view(self, abnormal_type: str) -> dict[str, Any]:
        rule = RULES.get(abnormal_type, {})
        duration = _to_number(rule.get("maxDuration"))
        temperature = _to_number(rule.get("maxTemperature"))
        issues: list[str] = []
        if abnormal_type not in RULES:
            issues.append("规则缺失，当前沿用系统默认口径")
        else:
            if duration is None or duration < 0:
                issues.append("超限时长上限缺失或不是不小于 0 的数字")
            if temperature is None:
                issues.append("最高温度上限缺失或不是有效数字")
        return {
            "abnormalType": abnormal_type,
            "maxDuration": rule.get("maxDuration"),
            "maxTemperature": rule.get("maxTemperature"),
            "valid": not issues,
            "message": "规则有效" if not issues else "；".join(issues),
        }

    def save_rule(
        self, abnormal_type: str, max_duration: Any, max_temperature: Any
    ) -> tuple[dict[str, Any] | None, str]:
        """新增/更新某异常类型的判定规则；填写无效时拒绝写入并说明原因。"""
        abnormal_type = str(abnormal_type or "").strip()
        if not abnormal_type:
            return None, "异常类型不能为空"
        duration = _to_number(max_duration)
        temperature = _to_number(max_temperature)
        if duration is None or duration < 0:
            return None, "允许超限时长上限必须是不小于 0 的数字（单位：分钟）"
        if temperature is None:
            return None, "允许最高温度上限必须是有效数字（单位：℃）"
        with _rules_lock:
            RULES[abnormal_type] = {"maxDuration": duration, "maxTemperature": temperature}
        # 口径刷新：进行中的事件按新规则重新评估，统计结论变化数量。
        rechecked = self.refresh_open_entries()
        view = self._rule_view(abnormal_type)
        view["rechecked"] = rechecked
        return view, "判定规则已保存并刷新，进行中的事件已按新口径重新评估"

    def delete_rule(self, abnormal_type: str) -> tuple[bool, str]:
        """删除某异常类型的专属规则；删除后相关事件回退到系统默认口径。"""
        abnormal_type = str(abnormal_type or "").strip()
        with _rules_lock:
            if abnormal_type not in RULES:
                return False, f"异常类型「{abnormal_type}」尚未配置规则"
            del RULES[abnormal_type]
        self.refresh_open_entries()
        return True, "判定规则已删除，相关事件恢复沿用系统默认口径"

    def refresh_open_entries(self) -> dict[str, int]:
        """按最新规则重评所有进行中事件，返回处置中事件结论变化情况。"""
        affected = 0
        verdict_changed = 0
        for row in store.rows(MODULE):
            if row.get("status") not in OPEN_STATUSES:
                continue
            if row.get("status") == "处置中":
                before = row.get("_lastVerdict")
                after = evaluate_entry(row)["verdict"]
                affected += 1
                if before is not None and before != after:
                    verdict_changed += 1
                row["_lastVerdict"] = after
        return {"affected": affected, "verdictChanged": verdict_changed}

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"温度异常事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于温度异常可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        # 提交处置（结单）前必须过最新判定：任一项越界或无法自动核定时拦截。
        if target == "已闭环":
            verdict = evaluate_entry(entry)
            if verdict["verdict"] != "允许结单":
                if verdict["verdict"] == "待人工核定":
                    return None, (
                        "暂不能结单：实测数据不完整或无法解析，请补齐超限时长与最高温度后再提交"
                    )
                return None, "暂不能结单：" + verdict["reasons"]

        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if target in OPEN_STATUSES:
            # 受理后进入处置中：按最新口径评估并记录基线，供后续规则刷新比对。
            if target == "处置中":
                entry["_lastVerdict"] = evaluate_entry(entry)["verdict"]
        else:
            # 结单/忽略时冻结当时的判定结论，保证历史账与口径刷新解耦。
            verdict = evaluate_entry({**entry, "status": STATUS_ORDER[1]})
            entry["判定结论"] = verdict["verdict"]
            entry["判定依据"] = verdict["reasons"]
            entry["规则口径"] = verdict["ruleSource"]
            entry["规则异常"] = verdict["ruleInvalid"]
            entry.pop("_lastVerdict", None)
        return _annotate(entry), f"温度异常事件已{action}"
