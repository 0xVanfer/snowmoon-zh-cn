# 译制流水线说明

本项目按 GPL-3.0-only 发布，上游许可要求「开源制作流水线（AI 提示词、脚本、任务专用 harness 等）」
以便他人复用，因此这里完整记录每一步。

## 0. 总览

```
sources/en/html/chapter-N.html       上游英文原文（1.6 MB，32 章，**不入库**：.gitignore 已忽略 sources/en/）
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
book/snowmoon-zh.md          全书单文件 Markdown（插图引用 images/）
book/site/                   多页阅读站点（含中英对照，见 §5）
book/images/*.svg            中文插图（视觉模型重绘）
book/site/assets/images/     站点中文栏插图（= book/images/ 的副本）
book/site/assets/images-en/  站点**英文栏**插图（= sources/work/figures/ 的上游原图）
```

设计要点：**结构与文字彻底分离**。抽取阶段把 HTML 拆成「骨架 + 片段」两层，翻译只改片段文字，
标签种类/顺序/属性由校验脚本逐条比对，杜绝翻译过程中结构漂移（表格塌陷、颜色丢失、插图位置错乱）。

## 1. 结构抽取 `extract.py`

- 用标准库 `html.parser` 建 DOM；`<nav>`、`<script>`、`<style>`、装饰性 `<br>` 丢弃。
- 不可译的虚构语言（泽国语 `dz-line`、`<pre>`）标记 `locked: true`。
- 内联文字转成受限 mini-markup（`<c st="…">` 颜色、`<e>`、`<b>`、`<sup>`、`<a>`、`<br/>`、`<f>` 等）。
  其中 `<e>`（原文着重）只存在于**原文侧**骨架：中文译文不用斜体，一律取消或改写为 `<b>`
  （见 [style-guide.md](style-guide.md) §2），`validate_translation.py` 会拒绝译文里的 `<e>`/`<i>`。
- **布局容器单独处理**：`style` 里带 `display:flex|grid`／`justify-content` 的容器，其直接子元素各自是
  独立布局项（`space-between` 靠项数分位），因此不拍平成一条文本，而是逐个保留元素、各自成一条片段。
  容器内第一条片段占用正常自增编号，其余用 `基准id#2`、`#3`…，所以容器外的片段编号与既有译文 id 完全不动。
- SVG 是 XML：HTMLParser 会把 `viewBox`/`clipPath` 等转小写，脚本按映射表还原大小写。
- **上游有未闭合标签，按浏览器的规则补关**（`IMPLIED_END` + foreign content breakout）：
  - 第 3 章的投票表少一个 `</td>`，按钮格被嵌进上一格、整行少一列——`<td>` 开始标签会补关上一格；
    不补，重跑抽取就会让「不可变骨架」与既有译文对不上。
  - 第 30 章两个 `<svg>` 没有 `</svg>`。此前之所以没出事，纯属运气：栈弹到**下一个同名结束标签**时
    顺带把 `svg` 弹掉，而那两处后面恰好跟的是 `</div>`。顺序一变（下一段是 `<p>`），整段正文会
    变成图里的内容并丢掉全部片段 id，而抽取照常 exit 0。现在 HTML-only 标签在 `<svg>` 外一律触发
    breakout，显式收口；`<foreignObject>` 内的 HTML 仍属合法，不受影响。
- `verify_extract.py` 做还原比对：把抽取值回填成纯文本，与原文纯文本逐章 diff（排除 SVG 内部文字），
  两类有意差异（dateline 的 `·` 分隔号、字符实体归一化）已在两侧对齐，**32 章全部 OK**。
  剥离 `<svg>` 时未闭合的那个也按同一条 breakout 规则收尾（**在文本层独立实现**，不与 `extract.py`
  共用代码，否则共同错误会互相抵消）。第 30 章的未闭合是**上游缺陷**，会打 WARN 留痕，但该章
  **照常参与比对**——判据是「比对结果有没有差异」而不是「有没有比对过」。
  `verify_extract.py` 有退出码：有差异即 exit 1，可以当闸门用。

## 2. 翻译

- 翻译单位是「片段」：一个 `<p>`／表格单元格／按钮／列表项 = 一条，全章 96–218 条（全书 4 808 条）。
- 由 DeepSeek Harness 的 subagent 逐章执行，任务书是 [prompts/translate.md](../pipeline/prompts/translate.md)，
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
  提示词见 [prompts/svg-zh.md](../pipeline/prompts/svg-zh.md)；要求模型输出「CAPTION 行 + 完整 SVG」。
- 调用器 `vision_api.py`：端点、模型名、凭据一律由环境变量注入（`VISION_API_URL` /
  `VISION_MODEL` / `VISION_API_KEY`（或 `VISION_API_KEY_FILE` + `VISION_API_KEY_NAME`），
  或本地 gitignored 的 `.vision.env`；详见该脚本 docstring），
  **仓库里不保存任何网关地址与 provider 命名**；带磁盘缓存（可断点续跑）、并发、失败重试、
  `max_tokens` 自适应降档，报错文本落盘前会先抹掉端点 URL。
  `python3 pipeline/vision_api.py --check` 是**预检**：只验端点/模型/凭据是否齐备与 URL 形态，
  不发任何模型请求（免费、可当闸门用），缺项时一次列全。缺配置时批处理要跑到一半才抛错，
  预检把这件事提前到一条命令。注意它**不验连通性**，端点路径写错只有真调用才会暴露。
- `validate_svg.py` 校验等价性：根属性、元素标签序列、`<text>` 数量与位置/锚点/颜色、
  font-size ±20%、数字与虚构语言必须原样、其余文字必须含中文且不残留英文单词。
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
- **落实**：改稿者按 [prompts/apply-review.md](../pipeline/prompts/apply-review.md) 逐条判断，采纳的用脚本按 `id` 改
  `segments[].text`，驳回的写明理由（风格偏好、理解偏差、或落实对象其实是术语表），
  分别记入 `reviews/chapter-NN.applied.json`（第一轮）与 `applied2.json`（第二轮）。
- **分工**：跨章与术语表层的问题由主进程处理——`glossary.json` 的 `aliases`（异体译名统一）+
  `fixups.json`（需要上下文的定点正则，如「载符飞船」里的「符」不能动），改完再全量 `normalize_zh.py`。
- 每轮结束都必须 `validate_translation.py` 全绿：结构、`locked`、标签序列一条都不能漂。

## 5. 组装与阅读

- `build_markdown.py`：把骨架里的占位符替换成译文，并做 mini-markup → Markdown 转换
  （颜色 span 的 `oklch()` 会换算成 `#rrggbb` 以兼容旧渲染器）。
- `build_site.py`：把同一份骨架渲染成**多页阅读站点**（主页 `index.html`、目录 `toc.html`、
  逐章 `read/chapter-NN.html`，产物在 `book/site/`）。每一章同时注入中文与英文两份正文，
  分别放在 `data-lang="zh"` / `data-lang="en"` 的正文栏里，由前端决定分栏还是标签页。
- **插图按语言分流**（`render_blocks` 的 `figdir` / `figalt` 参数）：
  中文栏 `assets/images/`（重绘版 + 中文图注），英文栏 `assets/images-en/`（**上游原图**）。
  此前两栏共用 `images/` 与同一份中文图注，于是英文原文那栏里，英文正文旁边配的是中文重绘图——
  56 张里 30 张含英文标注，对照模式读者看到的是与周围英文正文对不上的中文标签。
  两份同名成对，缺任一张即 `SystemExit`，绝不让英文栏退回中文图。
  英文栏的 `alt` 只陈述事实（`Chapter N, figure M (original English illustration)`）——
  英文原图没有配套英文图注（`manifest.json` 的 `CAPTION` 是重绘时产出的中文图注），
  凭空补一句英文描述就是自撰内容（见 §7「自拟标题即增译内容」）。要可用的英文图注，
  应让视觉模型在重绘时一并产出（manifest 增加 `caption_en` 字段）。
- 前端（HTML 模板 + `style.css` + `reader.js`）由 **视觉模型** 设计，源文件在 `pipeline/site/`，
  任务书见 `pipeline/prompts/design-reader-site.md`；`build_site.py` 只做占位符替换，
  不参与视觉设计。占位符契约（`{{CONTENT_ZH}}`、`{{TOC_ITEMS}}`、`{{REPO_URL}}`、
  `{{PREV_CH_HREF}}` 等）写在该任务书里，模板与构建脚本必须保持一致。
-视觉模型的产出是五份文件（index/toc/chapter.html + style.css + reader.js）、多次调用生成的，段落之间存在接口不一致；视觉模型之后的修补统一放在
  `pipeline/site/overrides.css`（由 `build_site.py` 注入到每个页面 `<head>` 末尾），分
  「接口对齐 / 视觉复核修补 / 用户请求的界面调整」三类；视觉模型的原始产出只做最小改动，
  便于将来用同一份任务书重新生成后做 diff。逐条记录见
  [reader-site-design.md](reader-site-design.md) §5 与 §6。
- 色彩可用性：原文用颜色区分说话人。阅读页除了保留颜色，还给纯对话段落加了同色左侧色条作为
  非颜色线索，并在主页说明「颜色仅作辅助」。
- `qa_book.py`：书级体检（章节数、插图引用与存在性、占位符残留、中文标点/空格体例）。
- `qa_site.py`：站点结构体检（页面齐全、占位符清空、双语两栏在位、站内链接与插图可解析、
  **英文栏必须真的引用 `images-en/` 且原图与中文版一一对应**、
  以及**布局容器（flex/grid）子项与原文逐项一致**、**结构元素计数（table/tr/td/th/
  blockquote/li、终端面板、插图）不得减少**、**中文栏长度不得塌陷**、**assets 与
  pipeline/site 同步**——见 [lessons.md](lessons.md) 第 6 节。上游原文不入库时，
  依赖它的三项检查会自动跳过并提示。
  图注对账只对**中文栏**做：`manifest.json` 是中文图注的事实源，英文栏用的是原图 + 英文 alt，
  拿 manifest 去比英文 alt 会永远报「不符」。
- `validate_terms.py`：术语卡片闸门（43 个概念 ↔ 43 篇科普 ↔ 构建产物三向对账）。
  **必须排在 `build_site.py` 与 `qa_site.py` 之后**——它校验的是最终产物：正文里有没有真的标出术语、
  卡片里的章号链接能不能落到真实段落、触发点与卡片是否逐页一一对应。
  只查 `terms.json` 自洽是不够的，数据自洽但产物里什么都没标出来，是最容易漏过的一种状态。
  三条无头环境跑不到的行为（深链跳过进度恢复、`applyDeepLink()` 的调用点、断句跳过 `.term`）
  改用静态守卫检查。详见 [reader-site-design.md](reader-site-design.md) §7.6。

## 5.1 部署

站点是纯静态的，构建期唯一的“后端”就是这一串 Python 脚本。仓库用
`.github/workflows/pages.yml` 在 `main` 分支推送时重新组装 `book/site/` 并用
GitHub Actions 发布到 Pages（仓库 Settings → Pages → Source 选 “GitHub Actions”）。
`book/site/` 同时提交进仓库，因此本地 `file://` 直接打开 `book/site/index.html`
也能完整阅读（站点不 fetch 任何数据文件）。

## 6. 复现步骤

```bash
python3 pipeline/extract.py                 # 32 章结构 + 片段 + 插图
python3 pipeline/verify_extract.py            # 抽取自检
#  逐章翻译（subagent，任务书见 pipeline/prompts/translate.md）
python3 pipeline/build_conlang_vocab.py       # 泽国语词表（validate/merge 都依赖它，必须先跑）
python3 pipeline/validate_translation.py      # 译文自检
python3 pipeline/merge_terms.py               # 合并新术语 + 生成 docs/glossary.md（有冲突则 exit 1）
python3 pipeline/normalize_zh.py --self-check # 只跑术语表加载期自检，不改译文（可当闸门用，CI 调它）
python3 pipeline/normalize_zh.py              # 术语/空格/标点统一
#  读者复核（3 视角，任务书见 pipeline/prompts/review-reader.md）
python3 pipeline/collect_reviews.py --todo    # 汇总问题清单
#  改稿（任务书见 pipeline/prompts/apply-review.md）
python3 pipeline/make_figures.py build        # 插图任务（含图前正文上下文）
python3 pipeline/vision_api.py --check         # 预检端点/模型/凭据（不发请求；缺配置时先补 .vision.env）
python3 pipeline/vision_api.py --batch sources/work/jobs/figures.jsonl \
    --out sources/work/jobs/figures.out.jsonl --concurrency 6
python3 pipeline/make_figures.py apply        # 校验 + 落盘 book/images
python3 pipeline/render_previews.py           # 渲染「原图 | 中文版」供视觉复核
python3 pipeline/build_markdown.py            # 组装 Markdown
python3 pipeline/build_site.py                # 组装阅读站点
python3 pipeline/qa_book.py                   # 书级体检
python3 pipeline/qa_site.py                   # 站点结构体检
python3 pipeline/check_privacy.py             # 隐私闸门：端点/凭据/provider 命名不得进仓库
python3 pipeline/probe_site.py                # 站点几何/交互探针（headless Chrome，33 个预设）
python3 pipeline/render_site_previews.py      # 各视口截图，供人工/视觉模型复核（本机需有显示链路）
```

`probe_site.py` / `render_site_previews.py` / `render_previews.py` 共用 `pipeline/chrome_runtime.py`：
它**逐个候选真跑一次 `--dump-dom`** 来挑浏览器，而不是「文件存在就选」——受限沙箱里系统 Chrome
常常存在却一启动就 FATAL，按存在性挑会让整套探针 0/N 全红，而那不是页面坏了。
挑不出来就在导入期 `SystemExit` 并逐条说明原因。截图另有一道能力自检：
本机没有可用显示链路时（`CVDisplayLinkCreateWithCGDisplay failed`，`--screenshot` 返回 0 却只写
0 字节 PNG）直接说明并退出，不会逐张打出 FAIL。细节见 [lessons.md](lessons.md)
「本轮（全局审计）新增的坑」一节。

探针本身还有一条覆盖面很大的断言：**页面有任何未捕获脚本错误即判失败**。
几何断言察觉不到 `ReferenceError`——页面照样渲染、别的断言照样过，
而对应功能已经死了（本轮就靠它抓到深链入口的跨作用域调用）。
`file://` 下默认会把错误抹成一句 `Script error.`，所以探针这一条命令额外带
`--allow-file-access-from-files`，好让报告里带得上文件名与行号。

README 给读者看的两张截图（`assets/readme/reader-dual.png`、`assets/readme/reader-mobile.png`）
同样出自 `render_site_previews.py` 的 `read-wide-dual` / `read-narrow-zh` 预设，
渲染结果落在 `sources/work/site-previews/`（不入库），需要时手动拷进 `assets/readme/`。
站点改版后要重新拷一次，否则 README 里的图会与线上不一致。

前端需要重新设计时（任务书见 `pipeline/prompts/design-reader-site.md`）：

```bash
# 1) 让视觉模型产出前端文件（结果落 JSONL，带磁盘缓存）
#    注意是**两批**任务：大文件（style.css / reader.js）在 jobs2.jsonl 里分段生成，
#    只跑第一批会导致 style.css / reader.js 无法重建（extract_design_files.py 会拒绝写入）。
python3 pipeline/vision_api.py --batch sources/work/design/jobs.jsonl \
    --out sources/work/design/out.jsonl --concurrency 5
python3 pipeline/vision_api.py --batch sources/work/design/jobs2.jsonl \
    --out sources/work/design/out2.jsonl --concurrency 4
# 2) 剥掉围栏，落到 pipeline/site/（全有或全无：缺一个文件就一个都不写）
python3 pipeline/extract_design_files.py
# 3) 重新组装站点
python3 pipeline/build_site.py && python3 pipeline/qa_site.py
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
