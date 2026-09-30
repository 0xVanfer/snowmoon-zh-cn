# 修复记录：逻辑审计发现的缺陷与修法

本文记录一轮完整代码逻辑审计（2026-09-30）中**实际修复**的缺陷：每一处都写明现象、错误的
逻辑（位置与机制）、以及修法。通用性经验另见 [lessons.md](lessons.md) §6。

- 范围：`pipeline/*.py`、`pipeline/site/*`、`.github/workflows/pages.yml`、`docs/`
- 原则：不改变译文内容。仅两处译文数据为修复所必需（见 §0.2）
- 验证：`validate_translation.py` / `validate_svg.py` / `verify_extract.py` / `qa_book.py` /
  `qa_site.py` 全部通过，并做了反向验证（注入缺陷确认闸门会失败），见 §9

## 0. 两处译文数据迁移

修抽取层必然改动 `sources/work/`，其中两章会连带影响 `translations/zh/`：

| 章 | 改动 | 为什么必须改 |
| --- | --- | --- |
| 18 | `c18-s0097`（locked 泽国语字符画）同步为保留空白的新原文 | `locked` 片段要求与原文逐字一致 |
| 26 | 新增 `c26-s0092 = "3724年霜期6日"`；其后 111 条 id 整体 +1 | 补回被丢弃的日期片段会占用一个 id |

ch26 已核对：除新增日期外**无增删、顺序保持**。日期写法依 `glossary.json` 的
`date_format = {year}年{month}{day}日` 与同章既有日期（`3724年霜期5日`）。

---

## 1. 抽取层

### 1.1 `<pre>` 的空白被折叠（第 18 章字符画压成一行）

- 错在哪：`extract.py` 的 `inline_markup()` 末尾对所有叶子统一 `re.sub(r"\s+", " ", s)`；
  `<pre>` 的缩进与换行是**内容**，被当排版空白抹掉。片段又是 `locked`，损坏被逐字带进成品。
- 修法：`inline_markup(node, preserve_ws=False)`，`render()`/`simple_block()` 对 `pre` 传
  `preserve_ws=True`：只裁掉首尾换行，内部原样保留。

### 1.2 卷首／场景分隔的日期丢失（第 26 章）

- 错在哪：`dateline_block()` 的裸文本回退条件是
  `if txt_direct and date is None and place is None`。「有 `<span class="place">` + 裸文本日期」
  的写法里 `place` 已赋值，条件不成立，日期既不转片段也无处补救。
- 修法：条件改为 `if txt_direct and date is None`（缺什么补什么，而不是「两个都缺才补」）。

### 1.3 空表格单元格被丢弃，整行列数变少（第 15 章 17 个空 `<th>`）

- 错在哪：`render()` 对「内容为空」的叶子一律 `return ""`。空 `<td>`/`<th>` 是**占位槽**，
  丢掉会让该行少一列，后续单元格整体左移。
- 修法：新增 `EMPTY_KEEP = {td, th, li, a, button}`，这些标签即使为空也输出骨架。
  （`render_layout_items()` 里「空项也要保留」是同一类问题，此前只覆盖了布局容器。）

### 1.4 未加标记的泽国语没有 `locked`

- 错在哪：`is_locked()` 只看叶子自身的 tag 与 class（`pre`、`dz-line`）。
  直接写在 `<p>`/`<td>` 里的泽国语罗马字完全不可见，会被当普通散文送翻译；
  而 `validate_translation.py` 的豁免规则**恰好放行**泽国语，译错了也不会报错。
- 修法：新增 `looks_like_conlang()`，用 `sources/work/conlang_vocab.json` 词表识别：
  含汉字排除、至少两词、除句首外无大写、不含与英语常用词同形的音节（`ten`/`min` 等
  `ENGLISH_LOOKALIKE`）、且所有词都在词表内。实测新锁 8 段、与既有译文 **0 冲突**。

### 1.5 未闭合的 `<svg>` 把后续正文吞进插图

- 错在哪：`HTMLParser` 不会弹出未闭合的 `<svg>`，其后的兄弟节点会成为 svg 的子节点；
  `device_block()` 只收集直接子 svg，被吞掉的正文拿不到片段 id，既不翻译也不渲染，
  却仍然写进插图文件。
- 修法：`device_block()` 检查 svg 后代里是否出现 `HTML_ONLY_TAGS`（p/div/table…），
  出现即 `SystemExit` 报出章节与标签，宁可失败也不静默吞内容。

### 1.6 `<script>`/`<style>` 漏进可译文本

- 错在哪：`script/style/nav` 过滤只在**结构**路径生效；叶子容器直接走 `inline_markup()`，
  而它没有这三个分支，落到「兜底：丢掉标签保留内容」，CSS/JS 源码被当散文送翻译。
- 修法：`inline_markup()` 增加 `script/style/nav` 分支直接 `continue`。

### 1.7 空值属性被丢弃

- 错在哪：`attr_str()` 过滤 `if v != ""`，于是 `checked`/`disabled`/`class=""` 等全部消失。
- 修法：取消该过滤（语料中 0 处空值属性，输出不变）。

### 1.8 属性顺序会导致页面切片错位

- 错在哪：`parse_chapter()` 用字面量 `find('<div class="document-page">')`，
  `class` 必须是第一个属性；顺序一变就 `i = -1`，切出整份文件。
- 修法：抽出 `slice_document_page()`，改用正则
  `<div[^>]*\bclass="[^"]*\bdocument-page\b[^"]*"`；找不到即报错，不再静默切错。

### 1.9 死分支与两处遗漏

- 错在哪：`render()` 里 `if node.tag in ("input",)` 与 `if node.tag == "br"` 都不可达
  （`VOID` 分支已经处理）；`simple_block()` 丢掉了元素的 class/style，且不设
  `note="conlang"`，与另两条路径产出的记录形状不一致。
- 修法：删除死分支；`simple_block()` 改用 `attr_str(self.out_attrs(node))` 并补 `note`。

### 1.10 陈旧的本章插图不清理

- 错在哪：`process()` 只写新图，上游删图后旧 SVG 仍留在 `sources/work/figures/`；
  `make_figures.build()` 是 `glob("*.svg")`，会为不存在的图白跑一次模型调用。
- 修法：写完新图后删除本章 `chapter-NN-fig-*.svg` 中不在本次结果里的文件。

### 1.11 还原比对失效（`verify_extract.py`）

- 错在哪：三个问题叠加——① `norm()` 删掉全部空白，**结构上不可能**发现 1.1 的空白丢失；
  ② 三处常驻误报（dateline 的 `·` 分隔号、实体只在原文侧解码、ch30 的未闭合 `<svg>`
  让 svg 剥离整段失效）导致 32/32 章全红，真缺陷被噪声淹没；③ 全文无 `sys.exit`，
  也从不接入 CI —— 它只是日志，不是闸门。此外它与 `parse_chapter()` 各写了一份切片逻辑。
- 修法：改用共享的 `slice_document_page()`；两侧都做实体解码；`·` 分隔号两侧一起排除；
  `<svg>` 改成「只剥离标签配平的元素」，未配平则打印 WARN 并跳过该章（该章插图由
  `validate_svg.py` 单独校验）；命中区间合并后再计数（不再 `i += 40` 跳过窗口）；
  加上 `sys.exit(1 if bad else 0)`；上游原文不存在时提示并跳过。

---

## 2. mini-markup 渲染

### 2.1 `<a>` 渲染成畸形 HTML

- 错在哪：`render_html.mini_to_html()` 开标签只输出到 `'<a href='`，闭标签才补
  `'"' + URL + '">'`，链接文字被夹在 `href=` 与引号之间：
  `<a href=点我"https://…">` —— 文字消失、地址失效。
  `docs/style-guide.md` 与 `prompts/translate.md` 都**要求**译者写 `<a href>`，属规范主动招致的坑。
- 修法：开标签输出 `'<a href="URL">'`、闭标签输出 `'</a>'`。

### 2.2 实体二次转义（第 19 章 `>` 显示成 `&gt;`）

- 错在哪：片段文本在抽取时已由 `esc_text` 转义（`>` → `&gt;`），
  `mini_to_html()` 又 `html.escape(..., quote=False)` 一遍，得到 `&amp;gt;`。
- 修法：改为 `esc_visible()`：只转义游离的 `&`（非 `&name;`/`&#n;` 形式）与意外的 `<`、`>`，
  已存在的实体原样通过。

### 2.3 未知标签被静默丢弃

- 错在哪：`TAG_RE` 匹配任意小写标签，但分发只处理白名单，其余**开闭标签一并丢弃**，
  例如译者写了 `<em>` 会凭空消失。
- 修法：定义 `KNOWN_TAGS`，遇到名单外的标签直接 `SystemExit` 报出标签名与片段前缀
  （`validate_translation.py` 的白名单会先一步拦住，这里是构建期的第二道）。

### 2.4 `expand()` 失败放行

- 错在哪：`segs.get(id, "")` 对未知片段静默替换成空串——这是全流水线唯一把结构与文字
  汇合的地方，正文会整段凭空消失而无人发现。
- 修法：`expand()` 缺片段即 `SystemExit`（`render_html.py` 与 `build_markdown.py` 各一份）。
  另外在两个构建器增加**全量同步预检**：章标题、卷首日期这类块不走 `expand`，
  只靠 `expand` 兜底会让它们的 id 失配静默留空。

### 2.5 Markdown 转义用在 raw HTML 块里

- 错在哪：`mini_to_md()` 无条件转义 `[]*_\`` 等，但 `panel`/`center` 等块的骨架本身就是
  原始 HTML，Markdown 转义在其中不被解释，成品出现字面 `\[`。
- 修法：`mini_to_md(text, escape=True)` / `expand(..., escape=...)`；`p` 块（纯 Markdown）
  用 `escape=True`，其余块与 dateline 行用 `escape=False`。

### 2.6 全书单文件 Markdown 的插图链接全部失效

- 错在哪：逐章文件与全书文件共用 `../images/` 前缀，但两者目录深度不同；
  全书在 `book/snowmoon-zh.md`，正确前缀应是 `images/`。`qa_book.py` 又同时接受两种写法，
  把这个 bug 写进了验收标准。
- 修法：`build_chapter(ch, segs, img_prefix)`；逐章传 `../images/`、全书传 `images/`。
  校验改为**按文件各自目录解析路径**（见 4.7）。

---

## 3. 组装

### 3.1 对话色条正则永不匹配（功能整条链路失效）

- 错在哪：`build_site.render_blocks()` 用
  `re.fullmatch(r'<span style="(#[0-9a-f]{6})">…')` 判断「整段被彩色 span 包裹」，
  但 `oklch_to_hex()` 保留 `color:` 前缀，产出的是 `style="color:#ed756b"`，`group(1)` 永不匹配。
  实测 2 111 段对话应命中，命中 0；而 `style.css` 与 `overrides.css` 都在维护 `.dialog.railed`。
- 修法：正则改为 `<span style="(?:color:)?(#[0-9a-f]{6})">`。

### 3.2 「全书 N 章」与目录取自常量而非实际产物

- 错在哪：`CHAPTER_COUNT=str(len(CHAPTERS))`、`toc_items(..., CHAPTERS, ...)` 都用模板常量
  `CHAPTERS`，与本次实际发布（`todos` / `built`）无关；`qa_site.py` 还断言目录条目 ≥32，
  于是**永远无法发现**下架章节的站点。
- 修法：先求出 `chapters = [有译文的章]`，目录、章数、上/下章导航全部以它为准；
  `qa_site` 改为断言「目录条目数 == 已发布章数」。

### 3.3 未参与构建的章节缺译文会让整轮中断

- 错在哪：`for ch in CHAPTERS: segs_of(ZH_DIR/…)` 无存在性判断，且发生在 `OUT.mkdir` 之前；
  `build_markdown.load_segs()` 有保护，两个构建器行为不一致。
- 修法：`segs_of(p, required=True)` 对必需文件给出明确报错；构建循环改为遍历 `requested`
  并与 `chapters` 求交，缺译文的章只 skip 不中断。

### 3.4 定向重建把整本单文件书截断

- 错在哪：`build_markdown.py 1 2 3` 会把 `book/snowmoon-zh.md` 重写成 3 章；参数还重复成章。
- 修法：参数只影响逐章文件；全书单文件**始终由全部可用译文重建**；参数 `sorted(set(...))` 去重。

### 3.5 组装器从不删除产物

- 错在哪：`book/site/` 与 `book/chapters/` 只写不删，撤下的章节继续被提交、被 CI 部署。
- 修法：`build_site` 清理不在 `chapters` 内的 `read/chapter-*.html` 与 `assets/images/*.svg`。

### 3.6 占位符取值不转义

- 错在哪：`toc_items()` 对 dateline 做了 `html.escape`，而章节页把同一个值原样写进
  `<title>`、`<meta content>` 与正文属性，转义口径不一致。
- 修法：`CHAPTER_TITLE_*` / `CHAPTER_DATELINE_*` 一律 `html.escape(..., quote=True)`。

### 3.7 卷首日期硬编码 `s0002`/`s0003`

- 错在哪：英文 dateline 直接拼 `c{ch}-s0002 · s0003`，依赖「每章都有 h1、日期紧跟其后」的假设。
- 修法：新增 `chapter_meta(ch)` / `block_ids(blk)`，从骨架的 `title` 与 `dateline-open` 块里
  取真实片段 id；中英两侧共用同一组 id。

### 3.8 `inject_overrides()` 静默 no-op

- 错在哪：`page.replace("</head>", …)` 缺少锚点时什么都不做。
- 修法：`if "</head>" not in page: raise SystemExit(…)`。

---

## 4. 校验器

### 4.1 强调标签不参与结构比对，且未配对不报错

- 错在哪：`tag_seq(..., drop_emphasis=True)` 在**两侧同时**剔除 `<b>/<e>/<i>/<em>/<strong>`，
  丢标签、改属性都不会报错；未配对的 `</b>` 会穿透并闭合外层 `<c>` 生成的 `<span>`。
- 修法：新增 `unbalanced_tags()`，逐标签核对开闭数量并报错；`bold_count ≤ emphasis_count`
  的上限检查保留。文件头「标签序列（含属性）完全一致」的描述已与实际口径对齐。

### 4.2 `TAG_RE` 只匹配小写标签

- 错在哪：`<SPAN>`/`<C>` 逃过白名单与结构比对，只以「残留未转义尖括号」的形式误报。
- 修法：正则改 `[A-Za-z]+` 并统一 `lower()`。

### 4.3 「疑似未翻译」可被短词英文通过

- 错在哪：`all(len(w) <= 4 or …)` 让任何由短词组成的英文句子被判为「泽国语」而豁免，
  这是防止整段未翻译的最后一道防线。
- 修法：引入 `COMMON_ENGLISH` 功能词表（运行时扣除泽国语词表，避免误伤 `no`/`go`/`du`）；
  仅当**出现 ≥3 字母的英语功能词**时才收紧；单词片段与哈希／十六进制串按数据放行。
  反向验证：`he was in the car`、`They can not see me` 均被拦下，泽国语与界面标签照常通过。

### 4.4 `validate_svg.py` 的「残留英文」检查不可达

- 错在哪：进入该分支的前提是 `has_cjk(tb)` 为真，而 `re.sub` 只删 ASCII 字母，
  删完中文必然还在，`not has_cjk(...)` 恒为假——**这条检查从来没生效过**。
- 修法：改为只要出现白名单外的 ≥3 字母拉丁词就报错（中英混排同样拦截）。修好后 56/56 张图通过。

### 4.5 `validate_svg.py` 的真空通过与静默跳过

- 错在哪：`book/images` 为空或改名时打印「0 对图，失败 0」并退出 0；源图缺对应中文图时
  静默跳过；docstring 宣传的 `--pair-dir` 根本没实现。
- 修法：无参模式下逐张源图必须有中文版，缺一张即计入失败；无任何可校验对象则退出 1；
  删除不存在的 `--pair-dir` 说明；未知参数直接报错。

### 4.6 `qa_book.py` 的 HTML 段是死代码

- 错在哪：`book/snowmoon-zh.html` 没有任何脚本生产，`if html:` 让占位符、`<p>`/`<div>`
  配对、插图引用四项检查永远不执行，却看起来像主要防线。
- 修法：删除该段；`docs/pipeline.md` 与 `docs/style-guide.md` 中把它列为产物的说法一并删除。

### 4.7 `qa_book.py` 的计数、路径与遗漏

- 错在哪：`re.search` 只取每段首个命中，「N 处」少算；插图只比对**文件名**，
  不验证路径可解析（正是 2.6 被掩盖的原因）；没有任何检查针对游离的 Markdown 转义符。
- 修法：改用 `finditer` 计数；按每个 md 文件所在目录解析引用路径；新增「游离反斜杠」检查。

### 4.8 `qa_site.py` 的招牌检查覆盖 3/166 且能看漏空正文

- 错在哪：`FLEX_RE` 要求 `<div … style="…display:flex…">`（只认内联样式 + 只认 div），
  非贪婪 `(.*?)</div>` 在嵌套时取错内容；子元素还必须是九种内联标签。
  全书 166 处布局声明只有 3 处能被它看到；双语页面下英文栏就能满足 `got >= want`，
  把中文栏整段清空也照样通过。
- 修法：改为「任意标签 + 内联 flex/grid 样式 + `balanced_element()` 配平取内容 +
  `direct_children()` 取直接子元素」；新增**结构元素计数**（`table/tr/td/th/blockquote/li`、
  终端面板、插图数量不得减少）与**中文栏长度下限**（相对英文栏）两项真正有覆盖面的检查。

### 4.9 `qa_site.py` 的页面大小门槛形同虚设

- 错在哪：`len(text) < 20000` 比真实最小章节页（49 001 字节）低约 2.4 倍，
  且中文栏被清空后仍有 66 356 字节，唯一的内容存在性检查实际上不会触发。
- 修法：改为对中文栏文本本身设下限（绝对下限 + 相对英文栏比例）。

### 4.10 `qa_site.py` 的其他补充

- 新增「`assets` 与 `pipeline/site` 是否一致」，防止提交陈旧的构建产物；
- 新增「页面是否真的引用了 `overrides.css`」（`inject_overrides` 曾经会静默 no-op）；
- 上游原文不入库时，依赖它的三项检查打印提示后跳过，不再因缺文件抛栈。

### 4.11 `merge_terms.py`

- 错在哪：术语冲突只打印，仍照常改写 `glossary.json` 与 `docs/glossary.md` 并退出 0；
  `is_conlang_entry()` 把「全大写」也当虚构语言（CPU/GUI 中招）；重分类只对**含空格**的
  既有条目生效，与新增路径口径不一致。
- 修法：两处口径统一为「**至少两词**且全部在词表内」，去掉 `isupper` 判断；
  冲突时 `sys.exit(1)`（含 `--check`）。逐条核对确认 `No→反对`、`TEI`、`pin→球瓶`、`To→收件人`
  这类英文形近词不会再被误判，术语表内容不变。

---

## 5. 插图与模型调用

### 5.1 插图任务的「图前正文」上下文恒为空（56/56）

- 错在哪：`prev_ids = [s for s in blk.get("segs", []) if s in src_segs]` —— 骨架的
  `block["segs"]` 存的是 `{{S:c01-s0004}}` **占位符**，而 `src_segs` 的键是裸 id，
  交集恒为空集，`ctx_lines` 永远为空。
- 修法：新增 `block_seg_ids(blk)` 先解析占位符；重建任务后 56/56 均带上
  「[前文英] … / [前文中] …」。

### 5.2 先落盘后校验

- 错在哪：`apply_results()` 先把模型产出的 SVG 写进 `book/images/`，**之后**才校验；
  校验失败只在 manifest 记 `invalid`，而两个构建器都是无条件 `glob("*.svg")` 全量采用，
  于是一张未通过等价性校验的图会被发布。
- 修法：先写临时文件 → 校验 → 通过才 `replace()` 到正式产物；失败则删除临时文件并记
  `published: false`，旧图保持不动。

### 5.3 贪婪正则把多张 SVG 拼成一个文件

- 错在哪：`re.search(r"<svg\b.*</svg>", text, re.S)` 会从第一个 `<svg` 一路吃到**最后一个**
  `</svg>`；模型若同时给出示例与正稿，产物是两个根元素的非法 XML。
- 修法：新增 `extract_svg()`，逐个数标签配平，取**最后一个自身配平**的 `<svg>…</svg>`。

### 5.4 结果 JSONL 末行损坏会让整批作废

- 错在哪：逐行 `json.loads` 无保护，而 `vision_api.py` 的写入是「写 + flush」，进程被杀会留下半行；
  异常从循环里抛出去，后面的结果全部跳过，`manifest.json` 也不会重写。
- 修法：逐行 `try/except`，坏行打印行号后跳过；新增结果覆盖率提示（缺少哪些任务）；
  `extract_design_files.py` 同样逐行保护。

### 5.5 `vision_api.py --batch` 启动即清空结果文件

- 错在哪：`out.open("w")` 在启动那一刻毁掉上一轮结果，没有续跑路径（缓存只省调用、不存结果）。
- 修法：先读回已有成功结果，重写一份干净的结果文件（顺带丢掉半行损坏），只跑未成功的任务；
  有失败任务时 `sys.exit(1)`。

### 5.6 被 `max_tokens` 截断的回复被当成成功并永久缓存

- 错在哪：成功路径只判 `content.strip()`，`finish_reason` 仅用于拼错误信息；
  截断的 SVG/CSS/JS 是废文件，而且一旦进缓存就永久复用——缓存键还**不含** `max_tokens`，
  调大上限重跑也命中旧缓存。
- 修法：`finish_reason == "length"` 视为失败，抬高上限重试（仍失败则报错）；
  缓存键加入 `max_tokens` 与 `temperature`。

### 5.7 `vision_api.py` 的凭据与重试细节

- 错在哪：凭据文件里若写成 `NAME: "sk-…"`，`\S+` 会把引号一起塞进 Authorization 头；
  端点与模型名硬编码在脚本里；429/5xx 忽略 `Retry-After`；最后一次尝试后仍 `time.sleep`；
  错误信息里的重试次数与实际不符。
- 修法：凭据剥引号；端点/凭据/模型名全部改为 `VISION_API_URL`、`VISION_API_KEY`、`VISION_MODEL`
  环境变量（或本地 gitignored 的 `.vision.env`）注入，脚本内不留任何默认端点；尊重 `Retry-After`；
  仅在还有下一次尝试时 sleep；错误信息不再虚报次数。

### 5.8 前端重生成：缺文件留旧版 / 无围栏写散文

- 错在哪：`extract_design_files.py` 对缺失或失败的产物 `continue`，磁盘上的旧文件原样保留，
  于是可能发布「新模板 + 旧 CSS/JS」的混合前端；模型回复没有围栏时代码把整段说明文字
  写进 `style.css` / `reader.js`。
- 修法：改为**全有或全无**——只要有一个文件缺失就一个都不写并退出 1；无围栏直接报错；
  取最后一个围栏块（正稿通常在最后，取最长会命中示例）。

### 5.9 预览渲染器

- 错在哪：`CHROME` 硬编码 macOS 路径且不做存在性检查（非 macOS 直接 `FileNotFoundError`）；
  两个脚本都不 `sys.exit`，0/N 张成功也算通过；宽高正则扫描整份 SVG（根元素无尺寸时会取到
  子元素的值）；预设注入在没有 `<script src=` 时静默 no-op。
- 修法：新增 `chrome_path()`（`CHROME` 环境变量 → macOS 默认位置 → 常见 Linux 路径 → `which`），
  找不到即给出明确指引；成功数不足即退出 1；宽高正则限定在根标签内；
  预设注入增加 `</head>` 回退并在地锚缺失时报错。

### 5.10 `normalize_zh.py`

- 错在哪：① 术语别名替换按 `glossary.json` 键序执行，短键先替换会吃掉长键
  （「掌舵团」被「掌舵」抢先），一次无害的键序调整就会静默改动正文；
  ② 备份用扁平文件名，第二次运行会覆盖掉真正的原始文本；③ 写入非原子，中途崩溃毁章节文件；
  ④ 规则会钻进 `<code>`/`<f>` 内部（`...` → `……`、别名替换命中 URL）。
- 修法：别名按**长度降序**排序后再替换；备份仅在不存在时创建（保留最早版本）；
  写入改为临时文件 + `replace()`；`<code>`/`<f>` 内部跳过规则处理（`protected` 计数）。
  逐章核对：全文改动 0 处，原有不动点保持。

---

## 6. 前端

### 6.1 设置面板宣传的方向键快捷键没有实现

- 错在哪：`chapter.html` 的快捷键表（随每一章发布）与 `docs/reader-site-design.md:39` 都写明
  「`←/→` 上一屏/下一屏；`↑/↓` 滚动当前阅读栏」，而全局 `keydown` 只处理 `Tab`/`Esc`/`t`/`d`。
- 修法：在 `reader.js` 第 2 段补方向键处理：`←/→` 调 `S.step()`（到章首/章末继续切章）；
  `↑/↓` 在滚动模式滚动当前栏、在翻页模式翻页；输入控件与标签页内不接管。

### 6.2 翻页模式的页高随滚动位置变化，每页顶部被顶栏压住

- 错在哪：`layoutPages()` 用 `rect.top`（视口相对坐标，随文档滚动变化）计算可用高度，
  于是「先滚动再切翻页」会少算一屏，首行被固定顶栏遮住且没有滚动余量可以救回来。
- 修法：页高只由 `window.innerHeight −（顶栏 + 底栏）− 16` 决定；新增
  「新高度生效后再量一次并把正文盒顶端对齐到顶栏下沿」的步骤。

### 6.3 `S.step()` 缺「该栏是否可见」判断

- 错在哪：不可见的栏 `clientHeight = 0`、`scrollHeight = 0`，于是 `max = 0`、`y = 0`，
  「到章首/章末」两个边界条件同时成立，「下一屏」会直接跳一整章。
  `remember()`/`writePosition()` 都有可见性守卫，唯独这里没有。
- 修法：`S.step()` 先 `if (!visible(lang)) return;`。

### 6.4 两套互不同步的阅读位置存储

- 错在哪：第 2 段的 `positions`（百分比，初始 0）与第 3 段的 `snapshots`（含 `y/p/page`，
  从 localStorage 恢复）各自为政；`restoreVisible()` 对两栏都写，而 `remember()` 对隐藏的栏
  直接返回，于是布局切换时**刚显露的那一栏**会被写入陈旧值 0，跳到章首。
- 修法：新增 `captured[lang]` 标记「是否真的量到过位置」；`restoreVisible()` 只写量到过的栏，
  没量到过的对齐到已知栏的位置；`writePosition()` 在容器不可滚动时不再留下
  `expected` 闩锁（该闩锁曾吞掉之后 1-2px 的真实滚动）。

### 6.5 抽屉/设置面板的关闭动画是死 CSS

- 错在哪：CSS 用 `[data-state="closing"]` 定义退出动画，而 `reader.js` 里
  `grep data-state` 无匹配——`closePanel()` 直接 `hidden = true`。
- 修法：`closePanel()` 设置 `data-state="closing"` 并在 220ms 后收尾；
  `reflectOverlay()` 在关闭动画期间不立即隐藏；`openPanel()` 会取消待收尾状态，
  快速重开不受影响。

### 6.6 `aria-current` 取值与 CSS 不一致

- 错在哪：JS 写 `aria-current="location"`，CSS 匹配的是 `[aria-current="page"]`，
  抽屉里当前章的强调色/加粗永远不生效。
- 修法：改为 `"page"`，同时写在 `<li>` 与其 `.chapter-link` 上（两处选择器都能命中）。

### 6.7 英文栏的章末导航没有样式、也不被打印隐藏

- 错在哪：中文栏是 `<nav id="chapter-nav">`，英文栏只有 class；而样式与打印隐藏清单都锚在
  `#chapter-nav` 上，于是英文栏退化成裸行内链接，打印时还会被打出来。
- 修法：相关选择器补上 `.chapter-navigation`（保留原有 id 选择器，特异度不变）；
  打印隐藏清单加入 `.chapter-navigation`。

### 6.8 打印样式被 JS 行内样式与特异度击败

- 错在哪：`layoutPages()` 通过 `el.style` 写入 `overflow:hidden`、像素宽高、`column-width`
  等行内声明；打印块用非 `!important` 声明复位 —— 行内声明在任何媒体下都优先，复位无效。
  双语分栏规则 `html[data-lang-mode="dual"][…] #reader-main` 的 (1,2,1) 也压过打印块的 (1,0,1)。
- 修法：打印块对 `display/width/max-width/height/max-height/overflow/columns` 逐条加
  `!important`（该块是全表唯一需要 `!important` 的地方，理由已写在注释里）。

### 6.9 断点不统一与死规则

- 错在哪：外壳一律 `max-width: 767px`，内容块却用 `768px`，正好 768px 时正文按移动端、
  外壳按桌面端；`style.css` 里两条 768px 的插图规则与 `overrides.css` 中的规则特异度相同，
  后加载者胜出，那两条在所有宽度下都不生效。
- 修法：断点统一为 767px；删除两条永远不生效的插图规则。

### 6.10 死选择器与死属性

- 错在哪：`style.css` 用 `html.js`（JS 设的是 `data-js` 属性），只靠 `overrides.css` 的
  等价补丁兜着；JS 还设置了没有任何 CSS 消费的 `data-sync`、`is-selected` 与
  `--page-w`/`--page-h`；JS 的 `aria-current` 值也无人匹配（见 6.6）。
- 修法：`style.css` 改为 `html[data-js]`；移除三个无消费者的设置。
  （`overrides.css` 里的等价补丁保留，作为「视觉模型产出与集成补丁对照」的痕迹。）

### 6.11 翻页模式插入的表格包装层不回收

- 错在哪：`prepareOversize()` 给表格套 `.pagination-table-scroll`，而 `resetStyles()`
  只还原 `style` 属性、从不移除插入的元素，退出翻页模式后 DOM 与构建产物永久不一致。
- 修法：记录创建的包装层，在 `resetStyles()` 里拆掉、还原原表格。

### 6.12 探针断言抛异常会毁掉整轮结果

- 错在哪：`probe_site.py` 只把 `probe()` 包在 `try` 里，`check()` 对探针返回值做索引/属性访问，
  元素缺失时抛 `TypeError`/`IndexError`，已打印的 PASS 与退出码一起丢失。
- 修法：`check()` 也包 `try`，异常按该预设 FAIL 计入并继续。

---

## 7. 文档与仓储

| # | 问题 | 修法 |
| --- | --- | --- |
| 7.1 | `docs/licensing.md` 与 `docs/pipeline.md` 声称上游英文原文「不随仓库分发」，实际 32 个文件（1.6 MB）已入库 | `.gitignore` 忽略 `sources/en/`，`git rm -r --cached sources/en`（磁盘文件保留）；文档补充「已由 .gitignore 忽略」的机制说明 |
| 7.2 | `book/snowmoon-zh.html` 被文档列为产物，但没有任何脚本生产它 | 从 `docs/pipeline.md`、`docs/style-guide.md` 中删除该产物条目 |
| 7.3 | 前端重生成步骤只列了第一批视觉模型任务，而 `style.css`/`reader.js` 在 `jobs2.jsonl` 里分段生成，照做会静默保留旧版 | `README.md`、`docs/pipeline.md` 补上第二批任务并说明「缺一批会拒绝写入」 |
| 7.4 | `docs/style-guide.md` §3 要求中西文之间**加**空格，§6 却写**不加**；且误引 CSS 属性（`keep-all`、`hanging-punctuation`） | §6 与 §3 对齐；CSS 属性改为实际的 `word-break: normal` + `overflow-wrap: break-word` |
| 7.5 | `docs/glossary.md` 指向不存在的 `pipeline/render_glossary.py` | 改为真实的 `python3 pipeline/merge_terms.py`（内置 `render_doc()`） |
| 7.6 | `docs/lessons.md` 的复核意见数（约 700）与实际（987）不符 | 更正为 987 条（high 49 / medium 436 / low 502） |
| 7.7 | `docs/pipeline.md` §6 的步骤顺序把词表消费者排在词表生成之前 | 把 `build_conlang_vocab.py` 提到 `validate_translation.py` / `merge_terms.py` 之前 |
| 7.8 | `verify_extract.py` 无退出码、`merge_terms.py` 冲突不反映到退出码、CI 只组装不校验 | 补退出码；`pages.yml` 增加 `validate_translation` / `validate_svg` / `verify_extract` / `qa_book` / `qa_site` 五道闸门，任一失败即中止部署 |
| 7.9 | `README.md` 的质量保证与运行步骤未反映上述变化 | 同步更新（抽取还原比对、结构计数、图片路径可解析、CI 闸门、两批前端任务） |

---

## 8. 未修复项与理由

| 项 | 为什么没修 |
| --- | --- |
| 嵌套布局容器会让该章其后所有片段 id 漂移，与 `seg_in()` 的稳定性承诺不符 | 正确修法需要改成「两遍分配 id」，会牵连重编号现有译文；当前全书只有 8 个 `#k` id（第 1、7 章）且无嵌套。已在 `extract.py` 的 docstring 保留原承诺，待真有嵌套布局时再改 |
| `normalize_zh.py` 对标签两侧文本段 `strip()`，理论上会吃掉标签边界处应有的空格 | 「正确」修法要先区分「标签边界空格」与「标点体例空格」，而 T4/T5 规则会与之互相覆盖，改动风险大于收益；当前语料 0 处命中（规则集是不动点） |
| `BUILD_DATE` 取最近提交日期却标为「构建日期」 | 值为提交的纯函数，构建可复现；改标签属措辞调整，不影响正确性 |
| `style.css` 中 `.chapter-content .chapter-title` / `.dateline` 是死选择器 | 它们被打印块引用，且 `prompts/design-reader-site.md` 仍要求视觉模型为其写样式；删除会让「重新生成前端后的 diff」失去参照 |
| `.narrow-device-view` 有 80 处使用但无对应规则 | 属视觉设计取舍（窄面板是否撑满整栏），需要真机确认观感，不宜在无浏览器验证的情况下改 |

---

## 9. 验证

**五道闸门（全部通过）**

```
validate_translation   PASS    32 章译文结构与体例
validate_svg           PASS    56 对图等价性（含此前不可达的「残留英文」检查）
verify_extract         PASS    31 章 OK + 第 30 章 WARN（上游未闭合 <svg>）
qa_book                PASS    书级体检
qa_site                PASS    站点结构与布局/结构计数保真
```

**反向验证（闸门必须能失败）**

| 注入的缺陷 | 期望 | 实测 |
| --- | --- | --- |
| 某段插入未配对 `</b>` | 失败 | `validate_translation` 退出 1，报「标签未配对 `<b>` 0/1」 |
| 片段 id 与骨架失步（原文侧 / 译文侧） | 失败 | 两个构建器均退出 1 并报出缺失 id |
| 删除 100 字符后重跑还原比对 | 失败 | `verify_extract` 报 1 处 missing |

**产物抽检**

| 检查 | 结果 |
| --- | --- |
| 全书单文件插图链接可解析 | 56/56 可解析（此前 56/56 失效） |
| 游离 Markdown 转义反斜杠 | 0 行（此前 8 行） |
| 第 26 章场景分隔日期 | 「梅尔丹，维里迪亚 · 3724年霜期6日」在位 |
| 第 18 章字符画 | 6 行缩进原样保留 |
| 第 19 章 `>` | `&amp;gt;` 0 处（此前 2 处） |
| 对话色条 | 第 1 章 28 段 `.dialog.railed`（此前 0） |
| 空表格单元格 | `<th></th>` 保留 |
| 抽取可复现性 | 重跑 `extract.py` 后 `sources/work/` 字节级不变 |
