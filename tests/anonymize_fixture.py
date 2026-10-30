"""把样例日志里的真实玩家/部落名与标签替换为虚构值（保持结构不变）。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from coc_stats import aggregate  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "war_stats_sample.json"
ALPHABET = "0289PYLQGRJCUV"

tag_map: dict[str, str] = {}
name_map: dict[str, str] = {}
counters = {"player": 0, "clan": 0}


def fake_tag(real: str) -> str:
    if real not in tag_map:
        n = len(tag_map)
        digits = []
        value = n
        for _ in range(6):
            digits.append(ALPHABET[value % len(ALPHABET)])
            value //= len(ALPHABET)
        tag_map[real] = "#9P0Y" + "".join(reversed(digits))
    return tag_map[real]


def fake_name(real: str, kind: str) -> str:
    key = (kind, real)
    if key not in name_map:
        counters[kind] += 1
        name_map[key] = ("玩家" if kind == "player" else "部落") + str(counters[kind])
    return name_map[key]


def clean(obj, kind=None):
    if isinstance(obj, list):
        return [clean(v, kind) for v in obj]
    if not isinstance(obj, dict):
        return obj

    this_kind = kind
    if "townhallLevel" in obj or "expLevel" in obj or "role" in obj:
        this_kind = "player"
    if "clanLevel" in obj or "badgeUrls" in obj:
        this_kind = "clan"

    out = {}
    for key, value in obj.items():
        if key in ("clan", "opponent"):
            out[key] = clean(value, "clan")
        elif key in ("player", "members", "memberList"):
            out[key] = clean(value, "player")
        elif key == "name" and isinstance(value, str):
            out[key] = fake_name(value, this_kind or "player")
        elif key == "tag" and isinstance(value, str):
            out[key] = fake_tag(value)
        else:
            out[key] = clean(value, this_kind)
    return out


def main():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    before = aggregate(data["items"], 10, 8)

    data["items"] = clean(data["items"])
    after = aggregate(data["items"], 10, 8)

    for kind in ("random", "cwl"):
        for key in ("wars", "attacks", "s3", "s2", "s1", "s0", "missed"):
            assert before[kind][key] == after[kind][key], (kind, key)
    assert before["evaluation"] == after["evaluation"]
    print("统计结果未受匿名化影响")

    FIXTURE.write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    text = FIXTURE.read_text(encoding="utf-8")
    for bad in ("焚魂千圣", "GGG08GLVR", "二十四桥", "UVY2P9P8"):
        assert bad not in text, bad
    print(f"已匿名化：{len(tag_map)} 个标签、{sum(counters.values())} 个名称")


if __name__ == "__main__":
    main()
