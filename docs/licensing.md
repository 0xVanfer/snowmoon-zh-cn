# 许可与来源说明

## 上游声明

原著 Snowmoon 由 Vitalik Buterin 发布于 <https://vitalik.eth.limo/snowmoon/>。
该站点 License 栏目原文（2026-09-29 抓取）：

> Snowmoon is released under the [GPL v3](https://www.gnu.org/licenses/gpl-3.0.html)
>
> Yes, I said GPL v3, not CC-BY-SA. My legal theory, which Kimi K3 says is plausible, is that you
> are free to go turn it into a movie or a vibe-coded anime or whatever, but if you do that, you are
> required to open-source the pipeline (AI prompts, scripts, task-specific harness, etc) and other
> non-commodity materials that you used to make it so that other people can build on top of your work.

同一页面的 AI 使用声明（与署名相关）：

> All words were written directly by me.
>
> Spelling, grammar and style checking, verifying consistency of the rules of Minpentai and Dzegoban,
> the HTML and CSS format and style, and the SVGs were done with assistance from Kimi K3 and
> Qwen 3.8 Flash Next.

上游未声明 “or any later version”，故上游作品为 **GPL-3.0-only**。

## 对本项目的要求

中文译文属于 GPL v3 意义上的演绎作品，因此本项目：

- 整体（译文、重绘插图、脚本、提示词等非通用材料）同样以 GPL v3 发布，不附加额外限制；
- 必须开源制作流水线——翻译提示词、术语表与格式规范、校验与组装脚本、任务专用 harness 等，
  全部随仓库提供，使他人可在此基础上继续工作；
- 必须保留原作者署名与许可声明，并标明本项目所作的修改（中译、插图重绘）。

## 本项目做法

- 根目录 [LICENSE](../LICENSE) 为 GPL v3 完整原文，未作改动。
- 制作流水线随仓库提交，不另设限制，包括：
  - 全部脚本（`pipeline/*.py`）：结构抽取、译文/插图自检、术语合并与体例统一、插图重绘、
    Markdown/HTML 组装、成品书级体检；
  - 全部提示词（`pipeline/prompts/`：逐章翻译、插图中文化、读者复核、复核落实）；
  - 术语表与规范（`pipeline/glossary.json`、`docs/glossary.md`、`docs/style-guide.md`）；
  - 任务专用 harness（`pipeline/vision_api.py`：视觉模型调用器，含缓存、并发、重试）；
  - 过程记录（`reviews/`：96 份读者复核报告 + 各章落实记录，含采纳/驳回理由）。
- 成品中标注原著来源与本项目的修改事实（见全书开篇声明与 [README](../README.md)）。
- 源码文件在文件头标注 `SPDX-License-Identifier: GPL-3.0-only`（Python 脚本已标注）。
- 上游英文原文快照 `sources/en/html/` 仅本地保留，未随仓库分发：`.gitignore` 已忽略 `sources/en/`
  （`git ls-files sources/en` 为空），复现时按上表来源自行获取。

## 来源与取得日期

| 材料 | 来源 | 取得日期 | 许可 |
| --- | --- | --- | --- |
| 英文原文（32 章） | `https://vitalik.eth.limo/snowmoon/html/chapter-N.html` | 2026-09-29 | GPL-3.0-only |
| 站点首页（目录与声明） | `https://vitalik.eth.limo/snowmoon/` | 2026-09-29 | GPL-3.0-only |
| GPL v3 许可原文 | `https://www.gnu.org/licenses/gpl-3.0.txt` | 2026-09-29 | FSF 允许逐字复制 |

英文原文快照位于 `sources/en/html/`，仅本地保留，不随仓库分发。
