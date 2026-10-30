"""部落冲突（Clash of Clans）成员三星率查询插件。

群员先绑定自己的游戏标签，之后在群里发 /coc查询，机器人就会 @ 他并返回
部落战和联赛的三星率统计。统计口径与原 Excel 工具一致。

数据来源为第三方镜像接口，地址和 apikey 可在 WebUI 插件配置里修改。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Plain
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.config.astrbot_config import AstrBotConfig

from .coc_api import CocApiError, CocClient, PlayerNotFound, is_valid_tag, normalize_tag
from .coc_stats import aggregate, format_report

PLUGIN_NAME = "astrbot_plugin_coc_stars"

BINDINGS_FILE = "bindings.json"
PROFILE_CACHE_TTL = 1800  # 玩家资料缓存 30 分钟，名字/部落不会频繁变

HELP_TEXT = """📖 部落冲突三星率
/coc绑定 #标签 —— 绑定你的游戏标签（游戏内「设置 → 我的标签」复制）
/coc查询 —— 查自己的三星率，会 @ 你
/coc查询 #标签 —— 查指定玩家
/coc查询 #标签 10 14 —— 顺便指定部落战/联赛取最近几场
/coc解绑 —— 解除绑定"""


class CocStarsPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context, config)
        self.conf = config or {}
        self.client = CocClient(
            war_api_base=self._str("war_api_base", "https://api.clashk.ing/v2"),
            profile_api_base=self._str(
                "profile_api_base", "https://clashapi.colinschmale.dev/v1"
            ),
            api_key=self._str("api_key", ""),
            timeout=self._int("request_timeout", 25),
        )
        self._data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        self._bindings_path = Path(self._data_dir) / BINDINGS_FILE
        self._bindings: dict[str, dict] = self._load_bindings()
        self._save_lock = asyncio.Lock()
        self._stats_cache: dict[str, tuple[float, list]] = {}
        self._profile_cache: dict[str, tuple[float, dict]] = {}

    # ---------- 配置读取 ----------

    def _str(self, key: str, default: str) -> str:
        value = self.conf.get(key, default)
        return str(value) if value is not None else default

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.conf.get(key, default))
        except (TypeError, ValueError):
            return default

    def _bool(self, key: str, default: bool) -> bool:
        value = self.conf.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    # ---------- 绑定存储 ----------

    def _load_bindings(self) -> dict[str, dict]:
        try:
            with open(self._bindings_path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception as exc:  # 文件损坏时不要让插件起不来
            logger.warning(f"读取绑定数据失败：{exc}")
            return {}

    async def _save_bindings(self) -> None:
        async with self._save_lock:
            tmp = self._bindings_path.with_suffix(".tmp")
            try:
                os.makedirs(self._bindings_path.parent, exist_ok=True)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self._bindings, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._bindings_path)
            except Exception as exc:
                logger.error(f"保存绑定数据失败：{exc}")

    @staticmethod
    def _user_key(event: AstrMessageEvent) -> str:
        platform = event.get_platform_id() or event.get_platform_name()
        return f"{platform}:{event.get_sender_id()}"

    # ---------- 数据获取 ----------

    async def _fetch_stats(self, tag: str) -> list:
        ttl = max(0, self._int("cache_ttl", 300))
        now = time.time()
        cached = self._stats_cache.get(tag)
        if cached and now - cached[0] < ttl:
            return cached[1]

        items = await self.client.fetch_war_stats(tag)
        if len(self._stats_cache) > 500:
            self._stats_cache.clear()
        self._stats_cache[tag] = (now, items)
        return items

    async def _fetch_profile(self, tag: str, fallback: dict | None = None) -> dict:
        now = time.time()
        cached = self._profile_cache.get(tag)
        if cached and now - cached[0] < PROFILE_CACHE_TTL:
            return cached[1]
        try:
            data = await self.client.fetch_profile(tag)
        except PlayerNotFound:
            raise
        except CocApiError as exc:
            logger.warning(f"拉取玩家资料失败（{tag}）：{exc}")
            return fallback or {}
        info = {
            "name": data.get("name") or "",
            "townHallLevel": data.get("townHallLevel"),
            "role": data.get("role") or "",
            "clan_name": (data.get("clan") or {}).get("name") or "",
        }
        self._profile_cache[tag] = (now, info)
        return info

    @staticmethod
    def _info_from_items(items: list) -> dict:
        """资料接口不可用时，用战争日志里的最新一条兜底。"""
        if not items:
            return {}
        latest = items[0]
        player = latest.get("player") or {}
        clan = latest.get("clan") or {}
        return {
            "name": player.get("name") or "",
            "townHallLevel": player.get("townhallLevel"),
            "role": "",
            "clan_name": clan.get("name") or "",
        }

    # ---------- 回复 ----------

    def _reply(self, event: AstrMessageEvent, text: str):
        if (
            self._bool("at_sender", True)
            and event.get_platform_name() == "aiocqhttp"
            and not event.is_private_chat()
        ):
            try:
                return event.chain_result(
                    [At(qq=event.get_sender_id()), Plain("\n" + text)]
                )
            except Exception:  # 个别适配器不支持 At，退回纯文本
                pass
        return event.plain_result(text)

    # ---------- 指令 ----------

    @filter.command("coc帮助", alias={"coc", "coc菜单"})
    async def coc_help(self, event: AstrMessageEvent):
        """查看部落冲突插件用法"""
        yield event.plain_result(HELP_TEXT)

    @filter.command("coc绑定", alias={"绑定部落", "cocbind"})
    async def coc_bind(self, event: AstrMessageEvent, tag: str = ""):
        """绑定你的部落冲突游戏标签，例如 /coc绑定 #8P0YQ2L9V"""
        key = self._user_key(event)
        if not tag:
            bound = self._bindings.get(key)
            if bound:
                yield event.plain_result(
                    f"你已绑定 {bound.get('name') or '未知玩家'}（{bound['tag']}）。\n"
                    "发 /coc查询 看三星率；要换绑就发 /coc绑定 #新标签。"
                )
            else:
                yield event.plain_result(
                    "用法：/coc绑定 #你的标签\n"
                    "标签在游戏内「设置 → 我的标签」里复制，形如 #8P0YQ2L9V。"
                )
            return

        normalized = normalize_tag(tag)
        if not is_valid_tag(normalized):
            yield event.plain_result(
                f"标签格式不对：{tag}\n游戏标签只包含 0/2/8/9/P/Y/L/Q/G/R/J/C/U/V 这些字符，"
                "形如 #8P0YQ2L9V。"
            )
            return

        try:
            info = await self._fetch_profile(normalized)
            if not info.get("name"):
                info = self._info_from_items(await self._fetch_stats(normalized))
        except PlayerNotFound:
            yield event.plain_result(f"找不到标签 {normalized}，请检查有没有输错。")
            return
        except CocApiError as exc:
            yield event.plain_result(f"❌ 绑定失败：{exc}，请稍后再试。")
            return
        except Exception:
            logger.exception("绑定标签时出现异常")
            yield event.plain_result("❌ 绑定失败，请稍后再试。")
            return

        if not info.get("name"):
            yield event.plain_result(
                f"标签 {normalized} 查询不到玩家资料，确认一下是不是这个标签？"
            )
            return

        self._bindings[key] = {
            "tag": normalized,
            "name": info.get("name", ""),
            "town_hall": info.get("townHallLevel"),
            "clan_name": info.get("clan_name", ""),
            "bound_at": int(time.time()),
        }
        await self._save_bindings()

        detail = " · ".join(
            part
            for part in (
                info.get("name"),
                f"{info['townHallLevel']}本" if info.get("townHallLevel") else "",
                info.get("clan_name"),
            )
            if part
        )
        yield event.plain_result(
            f"✅ 绑定成功：{detail}（{normalized}）\n发 /coc查询 就能看三星率了。"
        )

    @filter.command("coc解绑", alias={"解绑部落", "cocunbind"})
    async def coc_unbind(self, event: AstrMessageEvent):
        """解除标签绑定"""
        key = self._user_key(event)
        if self._bindings.pop(key, None):
            await self._save_bindings()
            yield event.plain_result("已解除绑定，需要时再 /coc绑定 #标签。")
        else:
            yield event.plain_result("你还没有绑定过标签。")

    @filter.command("coc查询", alias={"三星率", "查三星率"})
    async def coc_query(
        self,
        event: AstrMessageEvent,
        tag: str = "",
        war_count: int = 0,
        cwl_count: int = 0,
    ):
        """查询部落战 / 联赛三星率：/coc查询 [标签] [部落战场次] [联赛场次]"""
        key = self._user_key(event)
        bound = self._bindings.get(key)

        # 允许 "/coc查询 20" 直接把第一个参数当部落战场次
        if tag and not tag.startswith(("#", "＃")) and tag.isdigit():
            if war_count:
                cwl_count = war_count
            war_count, tag = int(tag), ""

        if not tag:
            if not bound:
                yield event.plain_result(
                    "你还没绑定标签。先发 /coc绑定 #你的标签，再发 /coc查询。"
                )
                return
            tag = bound["tag"]
        else:
            tag = normalize_tag(tag)
            if not is_valid_tag(tag):
                yield event.plain_result(
                    f"标签格式不对：{tag}，形如 #8P0YQ2L9V。"
                )
                return

        fetch_war = war_count if war_count > 0 else self._int("war_count", 10)
        fetch_cwl = cwl_count if cwl_count > 0 else self._int("cwl_count", 14)

        try:
            items = await self._fetch_stats(tag)
        except PlayerNotFound:
            yield event.plain_result(f"找不到标签 {tag}，请检查有没有输错。")
            return
        except CocApiError as exc:
            yield event.plain_result(f"❌ 查询失败：{exc}")
            return
        except Exception:
            logger.exception("查询战争日志时出现异常")
            yield event.plain_result("❌ 查询失败，请稍后再试。")
            return

        if bound and bound.get("tag") == tag and bound.get("name"):
            fallback = {
                "name": bound.get("name", ""),
                "townHallLevel": bound.get("town_hall"),
                "clan_name": bound.get("clan_name", ""),
                "role": "",
            }
        else:
            fallback = self._info_from_items(items)
        try:
            info = await self._fetch_profile(tag, fallback)
        except PlayerNotFound:
            # 战争日志接口对不存在的标签也返回空列表，资料接口才是权威判断
            if not items:
                yield event.plain_result(f"找不到标签 {tag}，请检查有没有输错。")
                return
            info = fallback or {}
        if not info.get("name"):
            info = self._info_from_items(items)

        if not items:
            yield self._reply(
                event,
                f"👤 {info.get('name') or '该玩家'}（{tag}）\n"
                "最近查不到任何部落战 / 联赛记录。",
            )
            return

        stats = aggregate(items, fetch_war, fetch_cwl)
        text = format_report(
            stats,
            name=info.get("name") or "未知玩家",
            tag=tag,
            town_hall=info.get("townHallLevel"),
            role=info.get("role"),
            clan_name=info.get("clan_name"),
            war_count=fetch_war,
            cwl_count=fetch_cwl,
            show_cwl=self._bool("show_cwl", True),
        )
        yield self._reply(event, text)

    async def terminate(self):
        """插件被停用 / 重载时释放连接。"""
        await self.client.close()
