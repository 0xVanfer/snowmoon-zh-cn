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

## 4. 组装与阅读

- `build_markdown.py`：把骨架里的占位符替换成译文，并做 mini-markup → Markdown 转换
  （颜色 span 的 `oklch()` 会换算成 `#rrggbb` 以兼容旧渲染器）。
- `build_html.py`（可选成品）：同一份结构渲染成单页 HTML，中文排版规则（首行缩进 2em、`line-break: strict`、
  1.75 行高、32em 行长、深色模式、设备面板样式）都在这里的 CSS 落地。
- 色彩可用性：原文用颜色区分说话人。HTML 版除了保留颜色，还给纯对话段落加了同色左侧色条作为
  非颜色线索，并在书首说明「颜色仅作辅助」。

## 5. 复现步骤

```bash
python3 pipeline/extract.py                 # 32 章结构 + 片段 + 插图
python3 pipeline/verify_extract.py            # 抽取自检
#  逐章翻译（subagent，任务书见 pipeline/prompts/translate.md）
python3 pipeline/validate_translation.py      # 译文自检
python3 pipeline/merge_terms.py               # 合并新术语 + 生成 docs/glossary.md
python3 pipeline/normalize_zh.py              # 术语/空格/标点统一
python3 pipeline/build_conlang_vocab.py       # 泽国语词表
python3 pipeline/make_figures.py build        # 插图任务
python3 pipeline/vision_api.py --batch sources/work/jobs/figures.jsonl \
    --out sources/work/jobs/figures.out.jsonl --concurrency 6
python3 pipeline/make_figures.py apply        # 校验 + 落盘 book/images
python3 pipeline/build_markdown.py            # 组装 Markdown
python3 pipeline/build_html.py                # 组装单页 HTML
```

## 6. 已踩过的坑

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `viewBox` 失效、渐变不显示 | HTMLParser 把 SVG 标签/属性名转小写 | `extract.py` 里维护大小写还原映射表 |
| 网关返回 `HTTP 403 error code: 1010` | Cloudflare 拦截 Python 默认 UA | `vision_api.py` 使用浏览器 UA |
| 工作流里 `provider: <本地 provider 名>` 的子代理报 `Stream ended without finish_reason` | pi-ai 适配器与该公司网关的流式响应不兼容 | 改用自带 `vision_api.py` 直连同一端点与凭据（本项目 harness 的一部分） |
| 校验把 `improvements`、`care` 判定为虚构语言 | 只按「全小写」判断泽国语 | 改为按词表 + 短词规则判断（`build_conlang_vocab.py`） |
| subagent 并发上限（8）导致启动失败 | harness 限制 | 分批启动，等通知再补 |
