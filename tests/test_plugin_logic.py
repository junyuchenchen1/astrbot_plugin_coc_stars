"""在 AstrBot 的 Python 环境里直接调用插件 Handler（假 event，绕过消息管线）。

验证：绑定 -> 查询（带 @）-> 解绑，以及配置读取、数据落盘。
需要先把本插件放进 AstrBot 的 data/plugins/ 下，并设置环境变量：

    set ASTRBOT_CORE=C:\\path\\to\\AstrBot\\core
    %ASTRBOT_CORE%\\..\\venv\\Scripts\\python.exe tests\\test_plugin_logic.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

CORE = Path(os.environ.get("ASTRBOT_CORE", ""))
if not (CORE / "astrbot").is_dir():
    print("跳过：请设置 ASTRBOT_CORE 指向 AstrBot 的 core 目录")
    raise SystemExit(0)

sys.path.insert(0, str(CORE))
PLUGIN_DIR = CORE / "data" / "plugins" / "astrbot_plugin_coc_stars"
if not (PLUGIN_DIR / "main.py").exists():
    print(f"跳过：{PLUGIN_DIR} 不存在，请先把插件放进 data/plugins/")
    raise SystemExit(0)

TAG = os.environ.get("COC_TEST_TAG", "").strip()
if not TAG:
    print("跳过：请先设置 COC_TEST_TAG=#你的标签")
    raise SystemExit(0)


class FakeEvent:
    def __init__(self, uid="10001"):
        self.uid = uid

    def get_platform_id(self) -> str:
        return "fake-platform"

    def get_platform_name(self) -> str:
        return "aiocqhttp"

    def get_sender_id(self) -> str:
        return self.uid

    def is_private_chat(self) -> bool:
        return False

    def plain_result(self, text):
        return {"kind": "plain", "text": text}

    def chain_result(self, chain):
        return {"kind": "chain", "chain": chain}


async def collect(gen):
    return [item async for item in gen]


def render(result):
    if result["kind"] == "plain":
        return result["text"]
    parts = []
    for comp in result["chain"]:
        parts.append(getattr(comp, "text", None) or f"<at {getattr(comp, 'qq', '')}>")
    return "\n".join(parts)


async def main():
    from data.plugins.astrbot_plugin_coc_stars.main import CocStarsPlugin

    class Ctx:
        pass

    tag = TAG
    plugin = CocStarsPlugin(Ctx(), {"war_count": 10, "cwl_count": 14, "at_sender": True})
    print("数据目录：", plugin._bindings_path)

    event = FakeEvent()
    key = plugin._user_key(event)

    results = await collect(plugin.coc_bind(event, tag))
    print("[绑定]", render(results[0]))
    assert key in plugin._bindings
    saved = json.loads(plugin._bindings_path.read_text(encoding="utf-8"))
    assert saved[key]["tag"] == tag

    results = await collect(plugin.coc_query(event))
    text = render(results[0])
    print("\n[查询结果]\n" + text)
    assert tag in text and "三星率" in text

    results = await collect(plugin.coc_bind(event, "#ABCD"))
    print("\n[非法标签]", render(results[0]))

    results = await collect(plugin.coc_query(FakeEvent("10002")))
    print("[未绑定查询]", render(results[0]))

    results = await collect(plugin.coc_unbind(event))
    print("\n[解绑]", render(results[0]))
    assert key not in plugin._bindings

    saved.pop(key, None)
    plugin._bindings_path.write_text(
        json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    await plugin.terminate()
    print("\nHandler 流程校验通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())
