"""部落冲突战绩统计（纯逻辑，不依赖 AstrBot / aiohttp，方便单独测试）。

数据来源是玩家战争日志里的单条记录，形如：

    {
      "type": "random" | "cwl",
      "attacksPerMember": 2,
      "endTime": "20261019T110116.000Z",
      "clan": {"name": "..."},
      "player": {"name": "...", "townhallLevel": 18},
      "attacks": [{"stars": 3, ...}, ...],
    }

统计口径与 Excel 工具保持一致：
- 三星率 = 三星次数 / 有效进攻次数（未进攻不计入分母，单独统计）
- 部落战（random）和联赛（cwl）分开统计，各取最近 N 场
"""

from __future__ import annotations

from typing import Any, Iterable

# 游戏内角色 -> 中文
ROLE_NAMES = {
    "leader": "首领",
    "coLeader": "副首领",
    "admin": "长老",
    "member": "成员",
}

# 与 Excel 工具一致的评价档位（按部落战三星率）
EVAL_TIERS = (
    (0.9, "六星大佬"),
    (0.8, "优秀"),
    (0.6, "良好"),
    (0.5, "一般"),
    (0.4, "平平无奇"),
    (0.0, "菜就多练"),
)


def _empty_bucket() -> dict[str, int]:
    return {"wars": 0, "attacks": 0, "s3": 0, "s2": 0, "s1": 0, "s0": 0, "missed": 0}


def _rate(bucket: dict[str, int]) -> float:
    return bucket["s3"] / bucket["attacks"] if bucket["attacks"] else 0.0


def evaluate(rate: float) -> str:
    for threshold, label in EVAL_TIERS:
        if rate >= threshold:
            return label
    return EVAL_TIERS[-1][1]


def _sorted_items(items: Iterable[Any]) -> list[dict]:
    """按结束时间倒序，保证「最近 N 场」取得的是最新的。"""
    valid = [i for i in items if isinstance(i, dict)]
    return sorted(valid, key=lambda i: str(i.get("endTime") or ""), reverse=True)


def aggregate(
    items: Iterable[Any],
    war_count: int = 10,
    cwl_count: int = 14,
) -> dict[str, Any]:
    """把战争日志聚合成部落战 / 联赛 / 综合三份统计。"""
    war_count = max(0, int(war_count))
    cwl_count = max(0, int(cwl_count))

    buckets = {"random": _empty_bucket(), "cwl": _empty_bucket()}
    limits = {"random": war_count, "cwl": cwl_count}

    for item in _sorted_items(items):
        war_type = item.get("type")
        if war_type not in buckets:
            continue
        bucket = buckets[war_type]
        if bucket["wars"] >= limits[war_type]:
            continue

        bucket["wars"] += 1
        bucket["missed"] += _missed_attacks(item, war_type)
        for attack in item.get("attacks") or []:
            stars = attack.get("stars")
            if not isinstance(stars, int) or stars not in (0, 1, 2, 3):
                stars = 0
            bucket[f"s{stars}"] += 1
            bucket["attacks"] += 1

    total = _empty_bucket()
    total["wars"] = buckets["random"]["wars"] + buckets["cwl"]["wars"]
    for key in ("attacks", "s3", "s2", "s1", "s0", "missed"):
        total[key] = buckets["random"][key] + buckets["cwl"][key]

    for bucket in (buckets["random"], buckets["cwl"], total):
        bucket["rate"] = _rate(bucket)

    # 评价以部落战为准；没有部落战记录时退回联赛
    base = buckets["random"] if buckets["random"]["attacks"] else buckets["cwl"]
    evaluation = evaluate(base["rate"]) if base["attacks"] else "暂无记录"

    return {
        "random": buckets["random"],
        "cwl": buckets["cwl"],
        "total": total,
        "evaluation": evaluation,
    }


def _missed_attacks(item: dict, war_type: str) -> int:
    """该场未使用的进攻次数（普通战 2 次/人，联赛 1 次/人）。"""
    default_apm = 2 if war_type == "random" else 1
    try:
        apm = int(item.get("attacksPerMember") or default_apm)
    except (TypeError, ValueError):
        apm = default_apm
    attacks = item.get("attacks") or []
    return max(0, apm - len(attacks))


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def _bucket_lines(title: str, bucket: dict[str, int], limit: int) -> list[str]:
    if not bucket["attacks"]:
        return [f"{title} · 近{limit}场", "  暂无有效进攻记录"]
    lines = [
        f"{title} · 近{bucket['wars']}场",
        (
            f"  三星 {bucket['s3']} ｜ 两星 {bucket['s2']} ｜ "
            f"一星 {bucket['s1']} ｜ 黑三 {bucket['s0']}"
        ),
        (
            f"  三星率 {_pct(bucket['rate'])}（{bucket['attacks']}次进攻）"
            f" ｜ 未进攻 {bucket['missed']} 次"
        ),
    ]
    return lines


def format_report(
    stats: dict[str, Any],
    *,
    name: str,
    tag: str,
    town_hall: int | None = None,
    role: str | None = None,
    clan_name: str | None = None,
    war_count: int = 10,
    cwl_count: int = 14,
    show_cwl: bool = True,
) -> str:
    """把统计结果拼成适合群聊发送的纯文本。"""
    head = [f"👤 {name}（{tag}）"]
    meta = []
    if town_hall:
        meta.append(f"{town_hall}本")
    if role:
        meta.append(ROLE_NAMES.get(role, role))
    if meta:
        head.append("   " + " · ".join(meta))
    if clan_name:
        head.append(f"   🏰 {clan_name}")

    lines = ["⚔️ 部落冲突 · 三星率报告", *head, ""]
    lines += _bucket_lines("⚔️ 部落战", stats["random"], war_count)
    if stats["random"]["attacks"]:
        lines[-1] += f" ｜ 评价：{stats['evaluation']}"

    if show_cwl:
        lines.append("")
        lines += _bucket_lines("🏆 联赛", stats["cwl"], cwl_count)

    total = stats["total"]
    if total["attacks"]:
        lines += [
            "",
            (
                f"📈 综合 {total['attacks']} 次进攻"
                f" ｜ 三星率 {_pct(total['rate'])}"
                f" ｜ 未进攻 {total['missed']} 次"
            ),
        ]
    else:
        lines += ["", "📈 最近没有查到有效进攻记录"]
    return "\n".join(lines)
