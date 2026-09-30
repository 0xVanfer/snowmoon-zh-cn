# Snowmoon / 雪月 · 中文版

本项目为 [Vitalik 的小说 Snowmoon](https://vitalik.eth.limo/snowmoon/) 的非官方中译版本，
目标是译制成更适合中文读者阅读习惯的形式：中文正文 + 中文化插图 + 中文排版。

原著共 32 章、约 10.2 万英文词，正文内嵌 56 幅 SVG 插图（另有 85 个模拟手表／终端界面的面板）。
中译本约 146 千汉字（含标点约 19 万字符）。

## 依赖

| 用途 | 依赖 |
| --- | --- |
| 阅读成品 | 现代浏览器，无需构建（Markdown 与单页 HTML 均可直接打开） |
| 译制流水线 | Python 3.11+（仅标准库）；`python3 pipeline/*.py` |
| 文字翻译 | DeepSeek Harness + DeepSeek V4.1 Flash（subagent 逐章翻译） |
| 插图重绘 |视觉模型（`pipeline/vision_api.py` 直连 harness 配置的端点） |
| 插图渲染校验 | Google Chrome（headless，把 SVG 渲染成 PNG 供视觉复核） |

## 运行方式

```bash
# 1) 结构抽取（需要先自备上游英文原文到 sources/en/html/chapter-N.html，见 docs/licensing.md）
python3 pipeline/extract.py

# 2) 逐章翻译：按 pipeline/prompts/translate.md 派 subagent，
#    每章产出 translations/zh/chapter-NN.zh.json 后自检
python3 pipeline/validate_translation.py

# 3) 术语合并、体例统一
python3 pipeline/merge_terms.py && python3 pipeline/normalize_zh.py

# 4) 插图中文化（需要 harness 环境中的视觉模型凭据）
python3 pipeline/build_conlang_vocab.py
python3 pipeline/make_figures.py build
python3 pipeline/vision_api.py --batch sources/work/jobs/figures.jsonl \
    --out sources/work/jobs/figures.out.jsonl --concurrency 6
python3 pipeline/make_figures.py apply

# 5) 组装阅读成品
python3 pipeline/build_markdown.py     # → book/snowmoon-zh.md, book/chapters/
python3 pipeline/build_html.py         # → book/snowmoon-zh.html
```

流水线细节、踩坑记录与复现步骤见 [docs/pipeline.md](docs/pipeline.md)。

## 阅读入口

| 文件 | 说明 |
| --- | --- |
| [book/snowmoon-zh.html](book/snowmoon-zh.html) | 推荐：单页 HTML，含中文排版（首行缩进、避头尾、深色模式） |
| [book/snowmoon-zh.md](book/snowmoon-zh.md) | 全书 Markdown（插图以相对路径引用 `book/images/`） |
| [book/chapters/](book/chapters/) | 逐章 Markdown |

## 质量保证

- 逐章结构校验：译文只改文字，标签/样式/表格/颜色由脚本逐条比对（`pipeline/validate_translation.py`）。
- 插图逐张校验：根属性、元素序列、`<text>` 数量与位置、数字与虚构语言原样；另有「英文原版 | 中文版」
  并排渲染 +视觉模型复核（56/56 通过）。
- 读者视角复核：32 章 × 3 个视角（忠实度 / 中文语感与本土化 / 一致性）共 96 份报告，
  经改稿者逐条采纳或驳回，过程记录保留在 [reviews/](reviews/)。
- 成品书级体检：`pipeline/qa_book.py`（章节数、插图引用、占位符、中文标点与空格体例、HTML 标签配对）。

## 文档

- [docs/style-guide.md](docs/style-guide.md)：文体、标点、数字、排版规范（事实源）
- [docs/glossary.md](docs/glossary.md)：术语表（由 `pipeline/glossary.json` 生成）
- [docs/pipeline.md](docs/pipeline.md)：流水线、复核改稿流程与复现说明
- [docs/lessons.md](docs/lessons.md)：踩坑与经验记录
- [docs/research/](docs/research/)：中国小说市场、中文排版、换行与版面的调研
- [reviews/](reviews/)：读者复核报告与各章落实记录
- [docs/licensing.md](docs/licensing.md)：上游许可与合规做法

## 许可与声明

本项目（中文译文、中文化插图及自产脚本与提示词）以 **GPL v3** 发布，完整条款见 [LICENSE](LICENSE)。
上游 Snowmoon 亦为 GPL-3.0-only，按上游要求，本项目的译制流水线（提示词、脚本、harness）一并开源。

本项目为粉丝译制，与原作者无关联；译文与重绘插图均未经原作者审定。
