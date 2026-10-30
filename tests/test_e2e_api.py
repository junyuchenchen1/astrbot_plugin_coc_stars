"""真实接口联调：标签规范化、资料查询、战争日志、404 分支。

需要 aiohttp 和可用的网络；第三方镜像偶发不稳定时跳过即可。
运行：python tests/test_e2e_api.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coc_api import (  # noqa: E402
    CocClient,
    PlayerNotFound,
    is_valid_tag,
    normalize_tag,
)
from coc_stats import aggregate, format_report  # noqa: E402

TAG = normalize_tag(os.environ.get("COC_TEST_TAG", ""))
if not TAG:
    print("跳过：请先设置 COC_TEST_TAG=#你的标签")
    raise SystemExit(0)


async def main():
    for raw in [TAG, TAG.lower(), "＃" + TAG.lstrip("#"), " " + TAG + " "]:
        assert normalize_tag(raw) == TAG, raw
    assert is_valid_tag(TAG)
    assert not is_valid_tag("#ABC"), "3 位应判为非法"
    assert not is_valid_tag("#ABC1"), "含 1 应判为非法"
    print("标签规范化 / 校验通过")

    client = CocClient(
        war_api_base="https://api.clashk.ing/v2",
        profile_api_base="https://clashapi.colinschmale.dev/v1",
    )
    try:
        profile = await client.fetch_profile(TAG)
        print(
            f"资料：{profile['name']} / {profile['townHallLevel']}本 / "
            f"{profile.get('role')} / {(profile.get('clan') or {}).get('name')}"
        )

        items = await client.fetch_war_stats(TAG)
        print(f"战争日志：{len(items)} 条")
        if items:
            stats = aggregate(items)
            print(
                format_report(
                    stats,
                    name=profile["name"],
                    tag=TAG,
                    town_hall=profile["townHallLevel"],
                    role=profile.get("role"),
                    clan_name=(profile.get("clan") or {}).get("name"),
                )
            )

        assert await client.fetch_war_stats("#AAAA") == [], "不存在的标签应返回空列表"
        print("不存在的标签：战争日志返回空列表（接口行为如此）")

        try:
            await client.fetch_profile("#AAAA")
        except PlayerNotFound:
            print("资料接口 404 正确抛出 PlayerNotFound")
        else:
            raise AssertionError("资料接口 404 没有抛错")
    finally:
        await client.close()
    print("\n端到端校验通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
