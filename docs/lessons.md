# 踩坑与经验记录

本文件记录本项目开发过程中的关键错误与处理办法（对应 AGENTS.md 的「关键错误、经验记录到 docs/ 下」）。
流水线各步骤的说明见 [pipeline.md](pipeline.md)。

## 1. 结构抽取

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `viewBox` 失效、渐变/裁剪不显示 | 标准库 `html.parser` 把 SVG 标签与属性名统一转小写（`viewBox`→`viewbox`、`clipPath`→`clippath`） | `extract.py` 里维护 `SVG_TAG_CASE` / `SVG_ATTR_CASE` 还原表，序列化时回填；`verify_extract.py` 再用 XML 解析全量校验 |
| 抽取自检报「漏字」，但人读没丢 | 原文里的 `&nbsp;`、`&#8594;` 等实体在两侧处理方式不同；SVG 内部文字被算进原文 | 比对前先剥掉 `<svg>`、解码实体，再做归一化；只把真实差异当问题 |
| 摘要里「180 幅插图」是错的 | 早期用 `grep -o '<svg'` 把每章的左右翻页导航图标也数进去了 | 只统计 `document-page` 内、且作为 `device-view` 直接子元素出现的 `<svg>`：实际 56 幅 |

## 2. 翻译与校对流水线

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 校验把 `improvements`、`chosen by parliament` 当虚构语言放过 | 最初用「全小写」判定泽国语罗马字 | 改为按词表判定（`build_conlang_vocab.py`）：locked 片段 + Chorus 字体 span + 「整条全小写且每词 ≤4 字母」或「单词条 ≤3 字母」 |
| 纯泽国语片段（倒计时播报）被误判「未翻译」 | 校验脚本 `strip_tags` 直接删除 `<br/>`，把相邻词粘连成新词 | `<br/>` 先替换成空格再剥标签；并把「无可识别英文词」也视为合规 |
| 「预测分数」被改写成「预测分数数」 | 术语别名用 `str.replace` 做全局替换，而别名本身是目标词的子串 | 别名表加「别名不得是目标子串」的自检；此类情形改用 `fixups.json` 的正则 + 负向断言 |
| 改稿成果被规范化脚本回退 | `fixups.json` 里留着与后来术语表相反的旧规则（如「参议院→议会」） | 每轮术语调整后同步清理 `fixups.json`；`normalize_zh.py` 每次运行都先在 `sources/work/backup/` 留备份以便比对 |
| 各章术语各自为政（tick 三种写法、符/符记、社媒/社交媒体…） | 32 章由不同 subagent 并行翻译 | 三级收敛：①各章 `new_terms` 合并进术语表；②`merge_terms.py` 报冲突；③`glossary.json` 的 `aliases` + `fixups.json` 做全书统一，最后由 `validate_translation.py` 兜底 |
| 中文与数字之间该不该加空格反复摇摆 | 两份调研结论不同（CY/T 154 允许两种，只要统一） | 定为：拉丁词（≥2 字母）与汉字之间加一个半角空格；数字与汉字之间不加（`3724年雪月3日`、`约2公里`）。由 `normalize_zh.py` 统一 |

## 3. 插图（视觉模型）

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 调用网关返回 `HTTP 403 error code: 1010` | Cloudflare 拦截 Python `urllib` 默认 UA | `vision_api.py` 改用浏览器 UA |
| Harness 工作流里指定 `provider: <本地 provider 名>` 的子代理报 `Stream ended without finish_reason` | 该网关的流式响应与 pi-ai 适配器不兼容 | 不走工作流，改用自带 `vision_api.py` 直连同一端点与同一凭据（本项目 harness 的一部分，随仓库开源）；带磁盘缓存与并发 |
| 大图（40 KB，内嵌 base64 位图）批次里缺结果 | 后台 `nohup` 进程随父 bash 任务结束被回收 | 重试时改用独立后台任务，并把结果按 `id` 落盘 `figures.out.jsonl`，缺哪张补哪张 |
| 模型偶发空回复 | reasoning token 吃满 `max_tokens` | 空回复时把上限翻倍重试；HTTP 400（超上限）时自动降档重试 |
| 26 张纯图形插图无需译字 | 图中没有可译文字 | 仍经模型处理并生成中文图注；`manifest.json` 标注「无可译文字，按原样保留」，图注进入 Markdown 的 `alt`（无障碍） |

## 4. 环境与工具

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| Chrome headless 截图后不退出 | macOS 版 `--headless=new` 写完文件会挂住 | `render_previews.py` 用 `Popen` + 轮询产物文件 + 超时 `killpg` |
| 无法用当前模型直接看渲染结果 | 主模型未声明图像输入 | 视觉复核交给声明支持图像的子代理（`minimax-cn / MiniMax-M3`），用 `read_image` 看「原图 \| 中文版」并排预览 |
| 并行 workflow 16 个 agent 全部失败 | 触发上游速率限制 | 改为每批 8 个、串行提交；失败的批次原样重跑即可 |
| 子代理启动报 `subagent limit reached (active child limit: 8)` | harness 并发上限 | 分批派发，等通知再补；长任务用 `send_message` 续跑而不是重开 |
| 并行改稿与规范化脚本互相覆盖文件 | 多个 subagent 同时写不同译文，规范化脚本又全量重写 | 规范化只在没有改稿任务运行时执行；每次写盘前用「按 id 替换 + 立即自检」的方式，避免整文件重写 |

## 5. 流程经验

- **结构与文字分离**是整条流水线能自动校验的前提：翻译只改 `segments[].text`，标签序列由脚本逐条比对，任何结构漂移都会在 `validate_translation.py` 暴露。
- **复核与改稿分离**：复核者只写 `reviews/*.json`，改稿者负责采纳/驳回并写 `applied*.json`，主进程只处理跨章与术语表层的问题。这样每一处改动都可追溯（谁提的、谁改的、理由是什么）。
- **多视角复核**（忠实度 / 中文语感 / 一致性）比让一个 agent「通读一遍」有效得多：本轮共 96 份复核报告、约 700 条意见，其中一致性视角几乎全部是跨章对照才能发现的（术语、编号、量词、称谓）。
- 复核意见也会错：改稿者驳回了约 5% 的条目（多为风格偏好、理解偏差、或落实对象其实是术语表而非译文），每条都写明理由。
