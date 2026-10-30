# 部落冲突三星率（astrbot_plugin_coc_stars）

![AstrBot](https://img.shields.io/badge/AstrBot-%3E%3D4.16-6f42c1)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-3776ab)

给 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 用的部落冲突（Clash of Clans）战绩查询插件。
群员绑定自己的游戏标签后，在群里发一条指令，机器人就会 **@ 他** 并返回最近的部落战 / 联赛三星率。

统计口径与常见的「部落战三星率 Excel 工具」一致：三星率 = 三星次数 ÷ 有效进攻次数，
未进攻单独统计、不计入分母。

## 效果

> 以下为示例数据，昵称、标签、部落名均为虚构。

```
⚔️ 部落冲突 · 三星率报告
👤 示例玩家（#8P0YQ2L9V）
   16本 · 成员
   🏰 示例部落

⚔️ 部落战 · 近10场
  三星 19 ｜ 两星 1 ｜ 一星 0 ｜ 黑三 0
  三星率 95.0%（20次进攻） ｜ 未进攻 0 次 ｜ 评价：六星大佬

🏆 联赛 · 近14场
  三星 14 ｜ 两星 0 ｜ 一星 0 ｜ 黑三 0
  三星率 100.0%（14次进攻） ｜ 未进攻 0 次

📈 综合 34 次进攻 ｜ 三星率 97.1% ｜ 未进攻 0 次
```

## 指令

| 指令 | 说明 |
| --- | --- |
| `/coc绑定 #标签` | 绑定游戏标签，会先查一次资料确认标签存在 |
| `/coc查询` | 查自己，回复时 @ 你 |
| `/coc查询 #标签` | 查指定玩家（不用绑定） |
| `/coc查询 #标签 10 14` | 顺便指定「部落战取近 10 场、联赛取近 14 场」 |
| `/coc解绑` | 解除绑定 |
| `/coc` 或 `/coc帮助` | 指令菜单 |

> 指令前缀以 AstrBot 的 `wake_prefix` 为准（默认 `/`），也可以直接 @机器人 再说指令。
> 回复时的 @ 只在 QQ 群聊里生效，私聊会自动改成纯文本（避免部分适配器报错）。

## 安装

### 方式一：git clone（推荐，方便更新）

```bash
cd AstrBot/data/plugins
git clone <本仓库地址> astrbot_plugin_coc_stars
```

### 方式二：手动下载

下载仓库 ZIP，解压后把 `astrbot_plugin_coc_stars` 整个文件夹放进 `AstrBot/data/plugins/`。

放好后在 AstrBot WebUI 的「插件」页刷新列表，找到「部落冲突三星率」并启用。
之后改代码只需要点插件卡片上的刷新（重载）图标，不用重启 AstrBot。

依赖只有 `aiohttp`，AstrBot 自带；如果提示缺库，用 AstrBot 的 Python 环境执行：

```bash
pip install -r requirements.txt
```

## 配置

WebUI 插件页 →「部落冲突三星率」→ 设置：

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `war_count` | 10 | 部落战统计最近几场 |
| `cwl_count` | 14 | 联赛统计最近几场 |
| `cache_ttl` | 300 | 同一标签的查询缓存秒数，避免频繁打接口 |
| `at_sender` | true | 回复时 @ 查询人（仅 QQ/aiocqhttp 群聊生效） |
| `show_cwl` | true | 结果里是否显示联赛部分 |
| `request_timeout` | 25 | 接口超时秒数 |
| `war_api_base` | `https://api.clashk.ing/v2` | 战争日志接口 |
| `profile_api_base` | `https://clashapi.colinschmale.dev/v1` | 玩家资料接口 |
| `api_key` | 空 | 资料接口的 apikey，当前镜像不校验，留空即可 |

## 数据存放

绑定关系保存在**插件数据目录**（不是插件目录，更新插件不会丢）：

```
AstrBot/data/plugin_data/astrbot_plugin_coc_stars/bindings.json
```

以 `平台实例ID:QQ号` 为键，多机器人 / 多平台不会互相覆盖。删掉这个文件等于全员解绑。

## 统计口径

- **部落战**：`type == "random"` 的最近 `war_count` 场，每场每人 2 次进攻。
- **联赛**：`type == "cwl"` 的最近 `cwl_count` 场，每场每人 1 次进攻。
- **三星率** = 三星次数 ÷（三星 + 两星 + 一星 + 黑三），未进攻不计入分母。
- **未进攻** = 每场（该场进攻次数上限 − 实际进攻次数）之和。
- **评价**按部落战三星率分档：≥90% 六星大佬、≥80% 优秀、≥60% 良好、≥50% 一般、
  ≥40% 平平无奇，其余「菜就多练」；没有部落战记录时退回联赛，两样都没有则显示暂无记录。

## 数据接口说明

用的是两个第三方镜像，不需要官方开发者 Token，也不用 IP 白名单：

- 战争日志：`api.clashk.ing/v2/player/{tag}/war/stats`
- 玩家资料：`clashapi.colinschmale.dev/v1/players/{tag}`

注意：

1. 这类镜像随时可能限流或下线。真挂了，把上面两个地址换成能用的镜像即可（配置里可改），
   或者改 `coc_api.py` 接官方 API（需要到 Supercell 开发者平台申请 token 并绑定公网 IP）。
2. 战争日志接口对**不存在的标签也返回空列表**，所以「标签是否存在」以玩家资料接口为准。
3. 查询有缓存（默认 5 分钟），刚打完的战争可能要等一会儿，或把 `cache_ttl` 调小。

## 项目结构

```
astrbot_plugin_coc_stars/
├── main.py              # 插件入口：指令、绑定存储、@ 回复
├── coc_api.py           # aiohttp 接口封装（标签规范化、错误分类）
├── coc_stats.py         # 统计与排版（纯函数，无第三方依赖）
├── _conf_schema.json    # WebUI 可视化配置
├── metadata.yaml        # 插件元数据
├── logo.png             # 插件图标
└── tests/               # 自测脚本（不会被打进插件运行逻辑）
```

## 测试

```bash
# 1) 统计口径：用样例日志暴力重算对照，纯标准库
python tests/test_stats.py

# 2) 真实接口联调（需要 aiohttp 和网络，先填一个真实标签）
set COC_TEST_TAG=#你的标签
python tests/test_e2e_api.py

# 3) Handler 流程：绑定 → 查询 → 解绑，需要先在 AstrBot 里装好本插件
set ASTRBOT_CORE=C:\path\to\AstrBot\core
set COC_TEST_TAG=#你的标签
%ASTRBOT_CORE%\..\venv\Scripts\python.exe tests\test_plugin_logic.py
```

## 已知限制

- 只统计**已结束**的战争，进行中的战争不会出现在日志里。
- 联赛按「场」计数，一次联赛通常 7 场，默认取 14 场是为了覆盖两次联赛；按需改 `cwl_count`。
- 纯文本输出，没有做图片卡片（见下）。

## 后续可以加的功能

- `/coc部落 #部落标签`：拉全族成员按三星率排行（`coc_api.py` 加个 `fetch_clan` 就能复用现有统计）。
- 图片卡片：把 `format_report()` 的结果交给 `self.text_to_image()` 渲染成图。
- 绑定后自动同步游戏昵称。

## License

[MIT](LICENSE)
