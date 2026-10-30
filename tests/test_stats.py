"""统计口径离线校验：用仓库内的样例战争日志暴力重算一遍，与 aggregate() 逐项比对。

运行：python tests/test_stats.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coc_stats import aggregate, format_report  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "war_stats_sample.json"


def brute_force(items, war_count, cwl_count):
    items = sorted(items, key=lambda i: i.get("endTime", ""), reverse=True)
    out = {}
    for kind, limit in (("random", war_count), ("cwl", cwl_count)):
        picked = [i for i in items if i.get("type") == kind][:limit]
        s3 = s2 = s1 = s0 = missed = 0
        for war in picked:
            apm = war.get("attacksPerMember") or (2 if kind == "random" else 1)
            attacks = war.get("attacks") or []
            missed += max(0, apm - len(attacks))
            for a in attacks:
                stars = a.get("stars", 0)
                if stars == 3:
                    s3 += 1
                elif stars == 2:
                    s2 += 1
                elif stars == 1:
                    s1 += 1
                else:
                    s0 += 1
        out[kind] = {
            "wars": len(picked),
            "attacks": s3 + s2 + s1 + s0,
            "s3": s3,
            "s2": s2,
            "s1": s1,
            "s0": s0,
            "missed": missed,
        }
    return out


def main():
    items = json.loads(FIXTURE.read_text(encoding="utf-8"))["items"]
    print(f"样例日志：{len(items)} 场")

    stats = aggregate(items, 10, 8)
    expect = brute_force(items, 10, 8)

    failures = []
    for kind in ("random", "cwl"):
        for key in ("wars", "attacks", "s3", "s2", "s1", "s0", "missed"):
            got, want = stats[kind][key], expect[kind][key]
            if got != want:
                failures.append(f"{kind}.{key}: got {got}, want {want}")
        print(
            f"{kind}: {stats[kind]['wars']}场 进攻{stats[kind]['attacks']} "
            f"三星{stats[kind]['s3']} 两星{stats[kind]['s2']} "
            f"一星{stats[kind]['s1']} 黑三{stats[kind]['s0']} "
            f"未进攻{stats[kind]['missed']} 三星率{stats[kind]['rate']:.4f}"
        )

    total = stats["total"]
    assert total["attacks"] == sum(stats[k]["attacks"] for k in ("random", "cwl")), (
        "综合进攻数不等于两部分之和"
    )
    print(
        f"综合: {total['attacks']}次进攻 三星率{total['rate']:.4f} "
        f"评价{stats['evaluation']}"
    )

    # 场次截断
    limited = aggregate(items, 3, 2)
    assert limited["random"]["wars"] == 3
    assert limited["cwl"]["wars"] == 2
    print("场次截断检查通过：random 3 场 / cwl 2 场")

    # 空日志
    empty = aggregate([], 10, 14)
    assert empty["total"]["attacks"] == 0
    assert empty["evaluation"] == "暂无记录"
    print("空日志检查通过")

    # 全部未进攻：2 场 × 2 次 = 4
    idle = aggregate(
        [
            {"type": "random", "attacksPerMember": 2, "attacks": []},
            {"type": "random", "attacksPerMember": 2, "attacks": []},
        ],
        10,
        14,
    )
    assert idle["random"]["missed"] == 4, idle["random"]["missed"]
    assert idle["random"]["wars"] == 2
    print("未进攻计数检查通过")

    report = format_report(
        stats,
        name="样例玩家",
        tag="#8P0YQ2L9V",
        town_hall=18,
        role="leader",
        clan_name="样例部落",
        war_count=10,
        cwl_count=8,
    )
    print("\n--- 报告预览 ---")
    print(report)

    if failures:
        print("\n失败项：")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print("\n全部校验通过 ✅")


if __name__ == "__main__":
    main()
