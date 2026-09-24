"""温度异常业务规则：状态流转、字段校验、可配置判定规则与结论口径都收在这里。

判定口径：按「异常类型」分别配置允许的超限时长上限与最高温度上限，
任意一项越界即判为需要处置，两项都在标准之内才允许直接结单。
规则缺失或填写无效（含事件数值无法解析）时保留原有判定，并在结论中说明原因。
"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "excursion"
REQUIRED_FIELDS = ["事件编号", "关联运单", "异常类型"]
STATUS_ORDER = ["待处置", "处置中", "已闭环", "已忽略"]
ACTION_RULES = {"受理事件": "处置中", "提交处置": "已闭环", "忽略事件": "已忽略"}
NEGATIVE_ACTIONS = ["忽略事件"]

DURATION_FIELD = "超限时长"
TEMP_FIELD = "最高温度"

# 出厂默认判定规则：异常类型 -> {超限时长上限（分钟）, 最高温度上限（℃）}
DEFAULT_RULES: dict[str, dict[str, float]] = {
    "高温超限": {"超限时长上限": 30, "最高温度上限": 8.0},
    "温升异常": {"超限时长上限": 15, "最高温度上限": 6.0},
}

# 判定结论三态：规则可用且两项达标 / 规则可用且任一越界 / 规则不可用回退原有判定
CONCLUSION_CLOSE = "允许直接结单"
CONCLUSION_HANDLE = "需要处置"
CONCLUSION_FALLBACK = "沿用原有判定"


def _to_number(value: Any) -> float | None:
    """把列表里字符串或数字形态的度量值解析成数字；解析不了返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_limit(value: float) -> str:
    """规则值回显：整数不带小数点，非整数保留原值。"""
    return str(int(value)) if float(value).is_integer() else str(value)


class ExcursionService:
    def __init__(self) -> None:
        # 规则与事件数据分开存：规则只服务于温度异常判定，不进总览模块计数
        self._rules: dict[str, dict[str, float]] = {
            name: dict(rule) for name, rule in DEFAULT_RULES.items()
        }

    # ---------- 判定规则 ----------
    def list_rules(self) -> list[dict[str, Any]]:
        """返回当前生效的判定规则，按异常类型排序便于页面稳定展示。"""
        return [
            {
                "异常类型": name,
                "超限时长上限": _format_limit(rule["超限时长上限"]),
                "最高温度上限": _format_limit(rule["最高温度上限"]),
                "配置状态": "已配置",
            }
            for name, rule in sorted(self._rules.items())
        ]

    def upsert_rule(
        self,
        abnormal_type: str,
        duration_limit: Any,
        temp_limit: Any,
    ) -> tuple[dict[str, Any] | None, str]:
        """新增或刷新一条按异常类型配置的判定规则；填写无效时说明原因且不覆盖原规则。"""
        name = str(abnormal_type or "").strip()
        if not name:
            return None, "异常类型不能为空"
        duration = _to_number(duration_limit)
        temperature = _to_number(temp_limit)
        problems: list[str] = []
        if duration is None:
            problems.append("超限时长上限需填写为不小于 0 的数字")
        elif duration < 0:
            problems.append("超限时长上限不能为负数")
        if temperature is None:
            problems.append("最高温度上限需填写为不小于 0 的数字")
        elif temperature < 0:
            problems.append("最高温度上限不能为负数")
        if problems:
            # 保留原有判定：拒绝写入，已存在的规则继续生效
            return None, f"规则「{name}」未生效：{'；'.join(problems)}"
        rule = {"超限时长上限": duration, "最高温度上限": temperature}
        self._rules[name] = rule
        return {
            "异常类型": name,
            "超限时长上限": _format_limit(duration),
            "最高温度上限": _format_limit(temperature),
            "配置状态": "已配置",
        }, f"判定规则「{name}」已刷新，处置中的事件将按新规则再评估"

    def evaluate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """按当前规则评估单条事件，产出列表页与详情页共用的结论口径。

        结论每次读取时实时计算，因此规则刷新后，处置中的事件重新进入页面
        （重新拉取列表或详情）时自动按新规则再评估，两端结论天然对得上。
        """
        abnormal_type = str(entry.get("异常类型") or "").strip()
        rule = self._rules.get(abnormal_type)
        if rule is None:
            reason = f"异常类型「{abnormal_type or '未填写'}」未配置判定规则，保留原有判定"
            return {"判定结论": CONCLUSION_FALLBACK, "判定依据": reason, "规则状态": "规则缺失"}

        duration = _to_number(entry.get(DURATION_FIELD))
        temperature = _to_number(entry.get(TEMP_FIELD))
        missing: list[str] = []
        if duration is None:
            missing.append("超限时长")
        if temperature is None:
            missing.append("最高温度")
        if missing:
            reason = (
                f"{'、'.join(missing)}缺失或不是有效数字，无法按规则核算，保留原有判定"
            )
            return {"判定结论": CONCLUSION_FALLBACK, "判定依据": reason, "规则状态": "数据无效"}

        over: list[str] = []
        if duration > rule["超限时长上限"]:
            over.append(
                f"超限时长 {_format_limit(duration)} 分钟 > 上限 "
                f"{_format_limit(rule['超限时长上限'])} 分钟"
            )
        if temperature > rule["最高温度上限"]:
            over.append(
                f"最高温度 {_format_limit(temperature)}℃ > 上限 "
                f"{_format_limit(rule['最高温度上限'])}℃"
            )
        if over:
            return {
                "判定结论": CONCLUSION_HANDLE,
                "判定依据": "；".join(over),
                "规则状态": "已按规则评估",
            }
        return {
            "判定结论": CONCLUSION_CLOSE,
            "判定依据": (
                f"超限时长 {_format_limit(duration)} 分钟 ≤ 上限 "
                f"{_format_limit(rule['超限时长上限'])} 分钟，最高温度 "
                f"{_format_limit(temperature)}℃ ≤ 上限 "
                f"{_format_limit(rule['最高温度上限'])}℃"
            ),
            "规则状态": "已按规则评估",
        }

    def _decorate(self, entry: dict[str, Any]) -> dict[str, Any]:
        """把判定结论挂到事件上，列表与详情走同一出口，保证显示口径一致。"""
        entry.update(self.evaluate(entry))
        return entry

    # ---------- 事件维护 ----------
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
        page_rows = [self._decorate(dict(row)) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._decorate(dict(entry)) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 超限时长、最高温度按选填度量值登记，供判定规则核算
        entry[DURATION_FIELD] = values.get(DURATION_FIELD)
        entry[TEMP_FIELD] = values.get(TEMP_FIELD)
        entry["发生时间"] = values.get("发生时间")
        entry["处置人"] = values.get("处置人")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._decorate(dict(entry)), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"温度异常事件 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于温度异常可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if action == "提交处置":
            # 结单卡口：两项都在标准之内才放行；规则不可用时保留原有判定（放行并说明原因）
            verdict = self.evaluate(entry)
            if verdict["判定结论"] == CONCLUSION_HANDLE:
                return None, f"不允许直接结单：{verdict['判定依据']}"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "提交处置":
            verdict = self.evaluate(entry)
            if verdict["判定结论"] == CONCLUSION_FALLBACK:
                return self._decorate(dict(entry)), f"已按原流程结单：{verdict['判定依据']}"
            return self._decorate(dict(entry)), "温度异常事件已提交处置并闭环"
        return self._decorate(dict(entry)), f"温度异常事件已{action}"
