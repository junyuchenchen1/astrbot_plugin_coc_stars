"""部落冲突数据接口封装（aiohttp 异步实现）。

两个接口都来自第三方镜像（不需要官方开发者 Token）：
- 战争日志：api.clashk.ing/v2/player/{tag}/war/stats
- 玩家资料：clashapi.colinschmale.dev/v1/players/{tag}（需要 apikey）

接口地址和 apikey 都放在插件配置里，镜像挂了可以直接换。
"""

from __future__ import annotations

import asyncio
import re

import aiohttp

# 游戏标签只使用这些字符（没有 1、I、O 等易混字符）
TAG_CHARS = re.compile(r"[0289PYLQGRJCUV]{3,12}")

DEFAULT_UA = "Dart/3.8 (dart:io)"


class CocApiError(Exception):
    """接口调用失败（网络、鉴权、限流等）。"""


class PlayerNotFound(CocApiError):
    """标签不存在。"""


def normalize_tag(raw: str | None) -> str:
    """把用户输入规范成 #XXXX 形式；不做合法性校验。"""
    text = (raw or "").strip().upper().replace("＃", "#")
    if text.startswith("#"):
        text = text[1:]
    text = text.strip()
    return f"#{text}" if text else ""


def is_valid_tag(tag: str) -> bool:
    return bool(TAG_CHARS.fullmatch(tag.lstrip("#")))


class CocClient:
    def __init__(
        self,
        *,
        war_api_base: str,
        profile_api_base: str,
        api_key: str = "",
        timeout: int = 25,
    ) -> None:
        self.war_api_base = war_api_base.rstrip("/")
        self.profile_api_base = profile_api_base.rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = max(5, int(timeout))
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={
                    "User-Agent": DEFAULT_UA,
                    "Accept-Encoding": "gzip",
                },
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get_json(self, url: str, *, headers: dict | None = None):
        session = await self._get_session()
        last_error: Exception | None = None
        for attempt in range(2):  # 5xx / 超时重试一次
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    if resp.status == 404:
                        raise PlayerNotFound("标签不存在")
                    if resp.status in (401, 403):
                        raise CocApiError("接口鉴权失败，请检查插件配置里的 api_key")
                    if resp.status == 429:
                        raise CocApiError("接口请求过于频繁，请稍后再试")
                    if resp.status >= 500:
                        last_error = CocApiError(f"数据接口异常（HTTP {resp.status}）")
                    else:
                        raise CocApiError(f"数据接口返回异常（HTTP {resp.status}）")
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = CocApiError(f"网络请求失败：{exc}")
            if attempt == 0:
                await asyncio.sleep(1)
        raise last_error or CocApiError("数据接口请求失败")

    async def fetch_war_stats(self, tag: str) -> list[dict]:
        """拉取玩家的战争日志（够新就够用，服务端最多返回 500 条）。"""
        clean = tag.lstrip("#")
        url = (
            f"{self.war_api_base}/player/%23{clean}/war/stats"
            "?limit=1000&time%5Bafter%5D=2010-01-01&time%5Bbefore%5D=2100-01-01"
        )
        data = await self._get_json(url)
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise CocApiError("数据接口返回格式异常")
        return items

    async def fetch_profile(self, tag: str) -> dict:
        """拉取玩家资料（名字、大本等级、部落、职位）。"""
        clean = tag.lstrip("#")
        url = f"{self.profile_api_base}/players/%23{clean}"
        headers = {"apikey": self.api_key} if self.api_key else None
        data = await self._get_json(url, headers=headers)
        if not isinstance(data, dict) or not data.get("tag"):
            raise CocApiError("玩家资料接口返回格式异常")
        return data
