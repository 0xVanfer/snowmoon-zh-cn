# 译制流水线说明

本项目按 GPL-3.0-only 发布，上游许可要求「开源制作流水线（AI 提示词、脚本、任务专用 harness 等）」
以便他人复用，因此这里完整记录每一步。

## 0. 总览

```
sources/en/html/chapter-N.html       上游英文原文（1.6 MB，32 章，仅本地保留，不随仓库分发）
        │  pipeline/extract.py
        ▼
sources/work/chapters/chapter-NN.json     结构骨架（块 + {{S:id}} 占位，不可变）
sources/work/segments/chapter-NN.src.json 可译片段（英文，含 role/locked 标记）
sources/work/figures/chapter-NN-fig-MM.svg 插图原始 SVG（56 张）
        │  subagent 逐章翻译（prompt: pipeline/prompts/translate.md）
        ▼
translations/zh/chapter-NN.zh.json   中文片段（只改文字，不改结构）
        │  pipeline/normalize_zh.py   术语与空格/标点体例统一
        │  pipeline/build_markdown.py
        ▼
book/chapters/chapter-NN.md  逐章 Markdown
book/snowmoon-zh.md          全书单文件 Markdown
book/snowmoon-zh.html        单页 HTML（含中文排版 CSS）
book/images/*.svg            中文插图（视觉模型重绘）
```

设计要点：**结构与文字彻底分离**。抽取阶段把 HTML 拆成「骨架 + 片段」两层，翻译只改片段文字，
标签种类/顺序/属性由校验脚本逐条比对，杜绝翻译过程中结构漂移（表格塌陷、颜色丢失、插图位置错乱）。

## 1. 结构抽取 `extract.py`

- 用标准库 `html.parser` 建 DOM；`<nav>`、`<script>`、`<style>`、装饰性 `<br>` 丢弃。
- 不可译的虚构语言（泽国语 `dz-line`、`<pre>`）标记 `locked: true`。
- 内联文字转成受限 mini-markup（`<c st="…">` 颜色、`<e>`、`<b>`、`<sup>`、`<a>`、`<br/>`、`<f>` 等）。
- SVG 是 XML：HTMLParser 会把 `viewBox`/`clipPath` 等转小写，脚本按映射表还原大小写。
- `verify_extract.py` 做还原比对：把抽取值回填成纯文本，与原文纯文本逐章 diff（排除 SVG 内部文字），
  当前 32 章仅剩 `·`（分隔号）与 entity 归一化差异。

## 2. 翻译

- 翻译单位是「片段」：一个 `<p>`／表格单元格／按钮／列表项 = 一条，全章约 100–210 条。
- 由 DeepSeek Harness 的 subagent 逐章执行，任务书是 [prompts/translate.md](prompts/translate.md)，
  术语以 [glossary.json](../pipeline/glossary.json) 为唯一事实源。
- 译文只允许出现白名单标签；`locked` 片段必须逐字照抄。
- `validate_translation.py` 校验：id 序列、locked 完整性、标签序列（含属性）、残留占位符/英文/尖括号。
- 各章译者在 `new_terms` 里登记新术语，`merge_terms.py` 合并回术语表；
  已出现的异体译名登记在术语表的 `aliases` 里，由 `normalize_zh.py` 全书统一替换。
- `normalize_zh.py` 另外统一：连续空格、中西文之间一个半角空格、中文与西文标点之间不留空格、
  中文语境半角标点转全角、`...` → `……`。

## 3. 插图中文化（视觉模型）

插图共 56 张，其中 30 张含英文标注、26 张为纯图形。全部经视觉模型重绘：

- `make_figures.py build` 为每张图生成任务：术语表子集 + 该图前后段落的原文/译文 + 原始 SVG 源码，
  提示词见 [prompts/svg-zh.md](prompts/svg-zh.md)；要求模型输出「CAPTION 行 + 完整 SVG」。
- 调用器 `vision_api.py` 走 harness 环境里配置的 harness 里配置的 provider（视觉模型，端点与凭据取自
  `<harness 本地 provider 配置>` 与 `<本地凭据文件>`），带磁盘缓存（可断点续跑）、
  并发、失败重试、`max_tokens` 自适应降档。
- `validate_svg.py` 校验等价性：根属性、元素标签序列、`<text>` 数量与位置/锚点/颜色、
  font-size ±20%、数字与虚构语言必须原样、其余文字必须含中文且不残留英文标点。
- 泽国语罗马字靠 `build_conlang_vocab.py` 自动建表（locked 片段 + Chorus 字体 span + 纯小写短词），
  避免把 `fai hie` 这类虚构语言误判为「未翻译」。
- 结果落 `book/images/`，图注（`CAPTION`）写入 `manifest.json`，Markdown 的 `alt` 直接用它（无障碍）。

## 4. 复核与改稿（读者视角，两轮）

翻译初稿完成后进入独立复核，复核者与译者不是同一批 subagent：

- **视角**：`fidelity`（忠实度：误译/漏译/增译/因果/比喻/说话人）· `fluency`（中文语感与本土化：
  翻译腔、断句、对话是否说人话、语气与笑点、称谓与度量）· `consistency`（术语、编号、人称、
  数字与单位体例、标点、面板文案、locked 虚构语言）。
- **规模**：3 视角 × 32 章 = 96 份报告（`reviews/chapter-NN.<lens>.<reviewer>.json`），
  共 987 条意见（high 49 / medium 436 / low 502）；提出者不修稿，只写报告。
- **落实**：改稿者按 [prompts/apply-review.md](prompts/apply-review.md) 逐条判断，采纳的用脚本按 `id` 改
  `segments[].text`，驳回的写明理由（风格偏好、理解偏差、或落实对象其实是术语表），
  分别记入 `reviews/chapter-NN.applied.json`（第一轮）与 `applied2.json`（第二轮）。
- **分工**：跨章与术语表层的问题由主进程处理——`glossary.json` 的 `aliases`（异体译名统一）+
  `fixups.json`（需要上下文的定点正则，如「载符飞船」里的「符」不能动），改完再全量 `normalize_zh.py`。
- 每轮结束都必须 `validate_translation.py` 全绿：结构、`locked`、标签序列一条都不能漂。

## 5. 组装与阅读

- `build_markdown.py`：把骨架里的占位符替换成译文，并做 mini-markup → Markdown 转换
  （颜色 span 的 `oklch()` 会换算成 `#rrggbb` 以兼容旧渲染器）。
- `build_html.py`：同一份结构渲染成单页 HTML，中文排版规则（首行缩进 2em、`line-break: strict`、
  1.75 行高、32em 行长、深色模式、设备面板样式）都在这里的 CSS 落地。
- 色彩可用性：原文用颜色区分说话人。HTML 版除了保留颜色，还给纯对话段落加了同色左侧色条作为
  非颜色线索，并在书首说明「颜色仅作辅助」。
- `qa_book.py`：书级体检（章节数、插图引用与存在性、占位符残留、中文标点/空格体例、HTML 标签配对）。

## 6. 复现步骤

```bash
python3 pipeline/extract.py                 # 32 章结构 + 片段 + 插图
python3 pipeline/verify_extract.py            # 抽取自检
#  逐章翻译（subagent，任务书见 pipeline/prompts/translate.md）
python3 pipeline/validate_translation.py      # 译文自检
python3 pipeline/merge_terms.py               # 合并新术语 + 生成 docs/glossary.md
python3 pipeline/normalize_zh.py              # 术语/空格/标点统一
#  读者复核（3 视角，任务书见 pipeline/prompts/review-reader.md）
python3 pipeline/collect_reviews.py --todo    # 汇总问题清单
#  改稿（任务书见 pipeline/prompts/apply-review.md）
python3 pipeline/build_conlang_vocab.py       # 泽国语词表
python3 pipeline/make_figures.py build        # 插图任务
python3 pipeline/vision_api.py --batch sources/work/jobs/figures.jsonl \
    --out sources/work/jobs/figures.out.jsonl --concurrency 6
python3 pipeline/make_figures.py apply        # 校验 + 落盘 book/images
python3 pipeline/render_previews.py           # 渲染「原图 | 中文版」供视觉复核
python3 pipeline/build_markdown.py            # 组装 Markdown
python3 pipeline/build_html.py                # 组装单页 HTML
python3 pipeline/qa_book.py                   # 书级体检
```

## 7. 编辑决策（与市场调研建议的差异）

调研文档 [research/china-novel-market.md](research/china-novel-market.md) 从网文市场惯例出发，建议把 32 章重切为
60–75 章（每章 2500 字）、给每章起标题、把图解集中到卷末图录。本译本**没有采纳**这些建议，理由如下：

| 决策 | 理由 |
| --- | --- |
| 章节与原文 **1:1**（仍为 32 章），不重切、不加卷 | 本项目定位是**忠实译制 + 可双语对照**：读者复核、结构校验、插图与正文的对应关系都依赖一一对应；重切属于改编，应另立项目 |
| 章节标题保持「第N章」，不自拟标题 | 原文没有标题，自拟标题即增译内容 |
| 图解**保留在正文原位**，不移到卷末图录 | 原文插图紧跟在被说明的段落之后（如第 1 章的「预测分数」图、第 4 章的棋局图），移位会切断图文指代 |
| 正文不插入译注 | 术语首现夹注原文即止；解释性内容一律不加，避免破坏原文的叙述节奏 |
| 不改背景设定、不做过度本土化 | 调研结论亦指出读者排斥的是翻译腔与阅读门槛，而非外国背景；本土化只做到称谓、度量、口语、标点的层面 |

若后续要做「网文版」，调研文档里的分卷、切章、章末钩子、图录等建议可直接作为改编输入，与本研究版的
`translations/zh/` 片段级译文并行，不需要重新翻译。

## 8. 踩坑记录

关键错误与经验单独记在 [lessons.md](lessons.md)（抽取的 SVG 大小写、字符实体比对、术语别名自替换、
Chrome headless 不退出、网关 UA 拦截、子代理并发上限等），此处不再重复。
