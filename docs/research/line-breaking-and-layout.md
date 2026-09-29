# 中文换行方式与版面/阅读体验调研（小说正文）

- 范围：英文长篇《Snowmoon》中译本的**正文阅读版面**（Markdown 主成品 + 由同一份结构渲染的 HTML 单页）。
- 方法与约束：本文所有结论均以可核实的公开来源支撑（W3C clreq / clreq-gap、MDN 及其 browser-compat-data、CSS 规范原文、CommonMark 规范、WCAG 2.2、开源阅读器与中文排版库的实现）。**凡未能取到一手证据的判断，均显式标注「未核实」。**
- 检索工具说明：本环境的 `web_search` 不可用（返回 401），全部资料通过 `curl` 直接抓取页面与规范原文获得。


## 0. 结论速览

| 议题 | 本项目结论 | 依据强度 |
| --- | --- | --- |
| 段首 | **首行缩进 2em**，段间**不加**间距（`margin: 0`） | clreq 6.2.1.1 明确「中文出版品上，段首缩排以两个汉字的空间为标准」 |
| 段落映射 | 与英文源 **1:1 对应**，一段一个 `<p>` / Markdown 一个块 | 项目源文件结构 + clreq 段落定义 |
| 对话 | 对话留在所属段落内，用中文引号；一段内含多句对话不拆段 | 与英文源一一对应，避免改写结构 |
| 避头尾 | `line-break: strict`（等价 clreq 的「严格处理」） | CSS Text 3 + clreq 6.1.1 |
| 标点挤压 | `text-spacing-trim: trim-start`（渐进增强，回退 `normal`） | CSS Text 4 §8.5 |
| 悬挂标点 | **不用**（中文横排传统不悬挂，且 Chrome/Firefox 不实现） | clreq 6.1.3 + BCD |
| 中西混排 | `word-break: normal` + `overflow-wrap: break-word`；不自动插 `&nbsp;` | clreq 6.1.4 / 6.3.3 |
| 行长 | 约 **30–38 字/行**（clreq 建议 17–40，横排上限 48） | clreq 7.1.1 |
| 行高 | **1.75**（≈75% 行距，落在 clreq 建议的 50%–100%） | clreq 6.4 |
| 交付 | Markdown 用「段间空行 + 段内软换行」；HTML 为推荐阅读成品；EPUB 可行但优先级低于前两者 | CommonMark + EPUB 3.3 |


## 1. 项目现状（决定规则的前提）

对 `sources/en/html/chapter-1.html` 的结构统计：128 个 `<p>`、7 个 `<table>`、4 个 `<blockquote>`、5 个 `<ul>`、6 个 `<hr>`、3 个内联 `<svg>` 插图、21 个 `<br>`（几乎都出现在表格单元格里）。

由此得到三条硬约束：

1. **英文每段就是一个 `<p>`**，且对话不单独成段（例：`"Five points for me!", the boy shouted excitedly.` 整句在同一个 `<p>` 内）。
2. 存在**非正文块**：表格（书中「手环/界面的面板」，含滑杆与表单控件）、`blockquote`（大写体的战歌/咒语）、`ul`、`hr`（场景切换符）、SVG 插图。
3. 原文有**章节内的 `<hr>` 分隔符**，在中文版里应当保持为一个视觉分隔符，而不是靠空行堆叠。

因此中文版的换行规则必须同时覆盖：正文段落、引文块、清单、表格、插图、长英文串。


## 2. 中文段落惯例：首行缩进 2em vs 西式段间距

### 2.1 权威规定

W3C《中文排版需求》（clreq）6.2.1.1「段首缩排」给出四种做法，并给出取舍：

- 所有段落首行皆缩排 —— 「几乎所有的书籍与杂志皆使用此方法」；
- 篇章最初段落首行不缩排、其余缩排 —— 「多见于西文书籍」；
- 所有段落首行皆不缩排，改用段间距区隔 —— 「部分书籍与杂志使用这种方式」；
- 缩排量：「**中文出版品上，段首缩排以两个汉字的空间为标准**」；仅在多栏杂志、每栏字数很少时，才改用缩排一字。

同节还明确了一条常被网页排版忽略的规则：**中文书籍中段落之间不使用间距**，前段末行、后段首行与段内行距一致；而且「若段落间加入空白行，则表示一节的结束」——也就是说，**空行在中式排版里是有语义的（分节）**，不该拿来当段落分隔符。原文见 [clreq §6.2.1.1](https://www.w3.org/TR/clreq/#line_head_indent_at_the_beginning_of_paragraphs)。

### 2.2 网页/阅读器主流做法

- 中文网页排版库 [typo.css](https://github.com/sofish/typo.css)（`sofish/typo.css`）在 `.typo` 中同时使用 `line-height: 1.75`、`line-break: strict`、`hanging-punctuation: allow-end`、`text-autospace: ideograph-alpha ideograph-numeric`、`text-spacing-trim: normal`，并以 `.typo-readable` 把行长限制在 `48em`；其设计文档明确把 clreq 的「多数书籍 17–40 字、横排不超过 48 字」和「行距为字号的 50%–100%」作为依据（见 [docs/modern-chinese-typography.md](https://github.com/sofish/typo.css/blob/master/docs/modern-chinese-typography.md)）。
- 开源中文电子书阅读器 [Koodo Reader](https://github.com/koodo-reader/koodo-reader) 的界面语言包中，正文排版可调项为：`Line height`（行高）、`Letter spacing`（字距）、`Text indentation`（首行缩进）、`Paragraph spacing`（段间距）、`Paragraph spacing threshold`（段间距阈值）、`Margin`（页边距）。可见**缩进与段间距在阅读器里是「二选一」的两个独立开关**（见 [src/assets/locales/en.json](https://github.com/koodo-reader/koodo-reader/blob/master/src/assets/locales/en.json)）。
- 网文平台阅读器（起点中文网 / 番茄小说 / 微信读书）的**具体线上 CSS 未取到**（站点为鉴权 + JS 渲染，`curl` 只能拿到外壳与懒加载资源清单，未能定位正文样式表）——**未核实**。因此本文对它们只做「不冲突」的设计，不宣称它们的确切取值。

### 2.3 结论与落地对比

**采用：首行缩进 2em + 段间零间距**（clreq 的中国大陆书籍惯例）。

| 落地方式 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- |
| `text-indent: 2em`（CSS，作用于渲染层） | 语义干净、可被阅读器覆写、符合 clreq、导出的纯文本不被污染 | 纯文本/Markdown 预览（GitHub 等）看不到缩进 | **采用**（HTML 主路径） |
| 全角空格 `　　` 开头 | 任何渲染器都可见 | 污染文本、无法复制干净、检索与 diff 变脏、AI/工具链易误判 | **禁用** |
| 内联 HTML `<p style="text-indent:2em">` | 强制生效 | Markdown 可读性差、样式与内容耦合、导出 EPUB 时重复 | **禁用**（仅在极端场景允许一次性 `<div class="indent">`） |
| 段间空行代替缩进 | Markdown 原生好看 | 违反 clreq「中文书籍段间不加间距/空行表示分节」，且与源 `<hr>` 分节语义冲突 | **不用作主方案**，仅作 HTML 的可选「西式模式」开关 |


## 3. 对话与换行

### 3.1 源文到译文的对应关系

英文源把一句对话与其提示语写在同一个 `<p>` 内。中文若把提示语拆到新段落，就会破坏与源文的 1:1 结构（也会让后续任何对齐/双语校对失效）。

**规则：**

1. **对话不额外拆段**。英文一个 `<p>` ↔ 中文一个 `<p>`（Markdown 里一个块）。
2. 段落**以对话开头**时，用中文引号 `“……”` 起句；提示语按中文习惯灵活处理：
   - 英文 `"Five points for me!", the boy shouted excitedly.` → 中文可作 `“我拿五分！”男孩兴奋地喊道。`（提示语在后，不换段）
   - 英文 `He said, "…"` → 中文宜前置：`他说：“……”`
3. **连续的多句对话**：中文习惯是「一人一段」——同一说话人的连续话语若在英文里已分成多段，则逐段对应；若在英文里同段，则**不主动拆分**（保持 1:1）。这样既不违反中文观感，也不引入结构性改写。
4. **语气未完的段落**：clreq 6.2.1.1 规定「部分语气未完的段落予以断行、而**不缩排**」（典型是引语接续，如段末 `……` 或引号未闭合）。实现方式：该段落加 `class="cont"`，CSS 里 `text-indent: 0`（见 §9）。中文里更常见的做法是让引号在段末不闭合（`“……`），下一段继续用 `……`）。
5. **内心独白**：不与普通对话区分字号或缩进，统一用引号（中文出版惯例）；若原文用斜体表内心独白，中文改用引号或「心想」类提示语，**不要**用斜体（CJK 斜体是伪斜体，可读性差）。
6. **引文 / 战歌（源 `<blockquote>`）**：居中或左侧缩进皆可，但**不首行缩进**，行高可略紧（1.6）；**清单（`<ul>`）** 同理 `text-indent: 0`，层级由 `padding-inline-start` 负责。见 §9 CSS。

### 3.2 关于「凸排」（对话人名顶格）

clreq 6.2.1.2 描述了剧本式凸排：人名 + 冒号共占四字宽，次行起缩排四字。**本项目不采用**——原书是叙述体小说而非剧本，且源文没有说话人标签结构。


## 4. 标点避头尾（禁则）与相关 CSS

### 4.1 clreq 的四级禁则

clreq 6.1.1 把行首行尾禁则分为四级（原文：<https://www.w3.org/TR/clreq/#prohibition_rules_for_line_start_end>）：

| 级别 | 内容 |
| --- | --- |
| 不处理 | 完全不处理禁则（台港部分报刊） |
| **基本处理（最推荐）** | 点号（顿号、逗号、句号、冒号、分号、叹号、问号）、结束引号、结束括号、结束书名号、连接号、间隔号、分隔号**不能出现在行首**；开始引号、开始括号、开始书名号**不能出现在行尾** |
| GB 法 | 基本处理 + 分隔号不得出现在行尾 |
| 严格处理 | GB 法 + **破折号、省略号不得出现在行首** |

另有 6.1.2「符号分离禁则」：破折号（乙式）与省略号各占 2em，**视为一体不可拆行**；阿拉伯数字整体不可拆；百分号/千分号/度数符号与其前数字不可拆；正负号与其后数字不可拆；货币符号与数字不可拆；上下标与被标记文字不可拆（<https://www.w3.org/TR/clreq/#prohibition_rules_for_unbreakable_marks>）。

处理次序也很关键：clreq 规定**先做标点挤压（6.3.2），再做禁则**，并遵守「先挤进，后推出」——先尝试把标点挤进前一行，挤不进才从前行取一字下移。

### 4.2 挤压与悬挂

- 标点挤压（clreq 6.3.2 / 6.3.2.2 / 6.3.2.3，<https://www.w3.org/TR/clreq/#punctuation_width_adjustment>）：中日韩大陆/香港出版物**多数**做挤压，台湾很多出版物不做。原则：两个相邻标点占 2 字宽时缩为 1.5 字宽（可进一步缩到 1 字宽）；**行首出现开始括号可缩其始侧半个汉字**；并引 GB/T 15834—2011 第 5.1.10 条——**行尾全角标点应缩去末侧半字宽**。
- 行尾悬挂（clreq 6.1.3，<https://www.w3.org/TR/clreq/#hanging_punctuation_marks_at_line_end>）：**绝大多数中文出版物不悬挂行尾点号**；且港台横排不做悬挂，仅直排可用。因此本项目**不启用** `hanging-punctuation`（也正好规避其浏览器支持问题，见 §4.4）。

### 4.3 CSS 属性设置（本项目取值）

| 属性 | 取值 | 理由 |
| --- | --- | --- |
| `line-break` | `strict` | 对应 clreq「严格处理」；MDN 定义 `normal` 为最常见规则、`strict` 为最严格（<https://developer.mozilla.org/en-US/docs/Web/CSS/line-break>） |
| `word-break` | `normal` | 保持 CJK 默认逐字断行、西文按词断行；**绝不用 `break-all`**（会拆断英文单词） |
| `overflow-wrap` | `break-word` | 仅在单个超长串（URL、无空格代码）无法放入一行时才断 |
| `hyphens` | `manual`（或 `none`） | 中文里不做英文音节断词；clreq 6.1.4 规定混排西文单词不得拆行（连字符处除外） |
| `text-spacing-trim` | `trim-start`（回退 `normal`） | 实现「行首开始括号缩半字」；`normal` 只处理相邻标点与行尾，是安全默认 |
| `text-autospace` | `ideograph-alpha ideograph-numeric` | 自动产生中西文之间的 1/4 em 级间距（clreq 6.3.3 要求），替代手工空格 |
| `text-wrap` | `pretty`（正文）+ `balance`（标题/图注） | `pretty` 改善末行过短与整段均衡；`balance` 仅适合短文本 |
| `hanging-punctuation` | 不设置 | 见 §4.2 |

### 4.4 浏览器实际支持（数据来源：MDN browser-compat-data，抓取于调研当日）

| 特性 | Chrome | Firefox | Safari |
| --- | --- | --- | --- |
| `line-break`（含 `strict`/`loose`） | 58（`strict` 25） | 69 | 11（`strict` 8） |
| `word-break`（含 `keep-all`） | 1（`keep-all` 44） | 15 | 3（`keep-all` 9） |
| `word-break: auto-phrase` | 119 | 否 | preview |
| `overflow-wrap`：`break-word` / `anywhere` | 1 / 80 | 3.5 / 65 | 1 / 15.4 |
| `hyphens`（含 `auto`） | 88 | 43（`auto` 6） | 17 |
| `hanging-punctuation` | **否** | **否** | 26.5（10 起为部分实现） |
| `text-spacing-trim` | 123 | **否** | **否** |
| `text-autospace` | 140 | 145 | 18.4 |
| `text-wrap: balance` | 114 | 121 | 17.5 |
| `text-wrap: pretty` | 117 | **否** | 26 |
| `text-justify`（含 `inter-character`） | 145 | 55 | **否** |
| `text-align-last` | 47 | 49 | 16 |

BCD 文件地址示例：<https://github.com/mdn/browser-compat-data/blob/main/css/properties/text-spacing-trim.json>、<https://github.com/mdn/browser-compat-data/blob/main/css/properties/hanging-punctuation.json>。

规范侧定义：`hanging-punctuation` 取值与「每端最多一个标点悬挂」（[CSS Text 3 §7](https://www.w3.org/TR/css-text-3/#hanging-punctuation-property)）；`text-spacing-trim` 各值的行列裁剪语义见 [CSS Text 4 §8.5](https://www.w3.org/TR/css-text-4/#text-spacing-trim-property)。

> **未核实**：Safari 的 `hanging-punctuation: allow-end` 对中文全角句读（`。`、`，`）的实际悬挂像素行为（本环境无 Safari 可实测）；Chrome/Firefox 的 `line-break: strict` 在「省略号/破折号不得行首」这一条上是否与 clreq 完全一致，亦未实测。

### 4.5 `text-wrap: pretty` / `balance` 的边界

CSS Text 4 规定：`balance` 在行数 ≤ 5 时**不得**改变行盒数量，超过 10 行 UA 可退化为 `auto`；`pretty` 允许 UA 考虑多行，可能包含「避免末行过短」「避免排版河流」等，且计算可能昂贵（<https://www.w3.org/TR/css-text-4/#text-wrap-style-property>）。因此：**正文用 `pretty`，标题/图注用 `balance`，绝不把 `balance` 用在长段落上。**


## 5. 中西混排的换行

1. **英文单词与数字不被拆断**：clreq 6.1.4 规定「横排中混排的西文单词……在可使用连字符处之外，不得分隔为两行」（<https://www.w3.org/TR/clreq/#prohibition_rules_for_unbreakable_marks> 同节体系）。CSS 默认行为已满足，**不要**用 `word-break: break-all`。
2. **中英之间的间距**：clreq 6.3.3 规定汉字与西文字母、数字间使用**不多于 1/4 汉字宽**的字距或空白，且**行首行尾不加**、中文点号前后不加（<https://www.w3.org/TR/clreq/#mixed_text_composition_in_horizontal_writing_mode>）。落地方式优先 `text-autospace`；在不支持的浏览器里，**宁可不加空格，也不要手工插 `&nbsp;`**——手工空格会污染文本、且在行首行尾产生不合规的间隙。
3. **`&nbsp;` / `word-joiner` 的正确用法**：只在**语义上绝不可分**且 CSS 无法表达时才用：
   - `&nbsp;`（U+00A0）：数字与单位（`25&nbsp;kg`、`第&nbsp;3&nbsp;章`）、姓名与称谓；
   - `&#8288;`（U+2060 WORD JOINER）：需要在**不允许任何断行**处粘连，且不希望产生可见宽度时（`&nbsp;` 会占一个西文空格宽）。
   - **不要**用 `&nbsp;` 做中英混排的通用间距。
4. **URL / 长代码串**：单独用 `overflow-wrap: anywhere`（或在 `code`/`a[href^="http"]` 上），这样它只影响这些元素，且不影响正文的 min-content 计算逻辑（`break-word` 与 `anywhere` 的区别见 [MDN `overflow-wrap`](https://developer.mozilla.org/en-US/docs/Web/CSS/overflow-wrap)）。
5. **公式 / 不可断的短串**：用 `.nowrap { white-space: nowrap }` 包住，外层给 `overflow-x: auto`，避免撑破版心。
6. **`<wbr>`**：在特别长的英文串里显式指定断行机会（MDN 指南 <https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_text/Wrapping_breaking_text>）。
7. **已知浏览器差异**：clreq-gap 记录了 #244「浏览器对表意空格 U+3000 的断行处理不一致」与 #245「UAX #14 对引号的断行规则过严——中文里 `“` 前允许断行，Gecko/Blink/WebKit 均已正确处理」（<https://www.w3.org/TR/clreq-gap/>）。结论：**不要手工插入 U+3000 当排版间距**。


## 6. 行距、字号、字距、行宽、响应式、插图与表格

### 6.1 数值依据

clreq 6.4（<https://www.w3.org/TR/clreq/#h_baselines>）：**行距（line gap）通常为字号的 50%–100%**，行长较短或字号较小时取小值；行距一般不超过字号，「就算超过也不会因而增加易读性」。换算关系为 `行高 = 字号 + 行距`，故 `line-height` 取值区间为 **1.5 – 2.0**，本项目取 **1.75**。

clreq 7.1.1（<https://www.w3.org/TR/clreq/#page_design>）：**大多数书籍正文行长设在 17–40 字**；最小不宜少于 10 字；**横排最大不宜长于 48 字**。中文里 `1em` 恰好等于一个汉字宽，因此可以用 `em` 精确控制「每行字数」。

clreq 7.1.2「孤字不成行、孤行不成页」（<https://www.w3.org/TR/clreq/#adjustments_of_orphans_and_widows>）在网页上无法完全实现，可用 `text-wrap: pretty` / `avoid-short-last-line` 近似。

### 6.2 推荐值

| 项目 | 手机（<480px） | 平板 | 桌面 |
| --- | --- | --- | --- |
| 正文 `font-size` | 17px（不要 <16px） | 17–18px | 18–19px |
| `line-height` | 1.75 | 1.75 | 1.75 |
| 行长 `max-inline-size` | 容器满宽 − 2×1rem | ≈ 30em | ≈ 32–38em（→30–38 字/行） |
| `letter-spacing` / 段间距 | 0 / 0（靠 2em 缩进） | 0 / 0 | 0（可 0.01em 微调）/ 0 |
| 左右页边距 | 16px | 24px | 自动居中 + 32px |

**可访问性硬约束**：WCAG 2.2 SC 1.4.12（AA）要求用户把行高改到 ≥1.5、段间距 ≥2em、字距 ≥0.12em、词距 ≥0.16em 时**内容不丢失、功能不失效**（<https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html>）。因此：**不要给正文容器设固定高度**，间距一律用 `margin` / `line-height`，`text-indent` 不要用像素绝对值锁死（`2em` 天然跟随字号缩放）。

### 6.3 插图与表格

- **插图**：`figure` 居中，`img { max-inline-size: 100%; height: auto; display: block; margin-inline: auto }`。原书插图是内联 SVG，建议在中文版中改为独立文件并放入 `assets/zh-images/`（本项目已存在该目录），以便 Markdown 与 HTML 共用一份资源。
- **图注**：放在图下方，`figcaption` 必须 `text-indent: 0`（因为 `text-indent` 是**继承属性**，不重置会导致图注首行也缩进 2em），字号 0.9em、行高 1.5、颜色次要、居中。
- **表格**：源文表格是「设备界面面板」，窄屏必须**横向滚动**而不是压缩换行：外层 `.table-wrap { overflow-x: auto }`，表格设 `min-inline-size`，单元格 `text-indent: 0`。
- **`<hr>` 场景分隔**：渲染为居中分隔符（`＊　＊　＊`）而非靠左直线；`margin: 1.8em 0`，`text-indent: 0`。


## 7. 交付形态建议

### 7.1 Markdown 的换行策略

CommonMark 规范（<https://spec.commonmark.org/0.31.2/#hard-line-breaks>）规定：

- **硬换行** = 行尾两个及以上空格，或行尾反斜杠 `\`，渲染为 `<br />`；
- **软换行** = 普通换行，合规解析器可渲染为换行或空格；解析器也可以选择把软换行渲染为硬换行。

**本项目结论：**

1. **段落之间用一个空行**（这是 Markdown 的段落语义，不是 clreq 意义上的「分节空行」；Markdown 里没有别的选择）。
2. **段内一律不换行**（写成长行），不要用「行尾两空格」或 `\` 造硬换行——`<br>` 会破坏 CSS 整齐排版（首行缩进只管第一行），也让 diff 变脆。
3. 场景分隔用 `---`（`<hr>` 的 Markdown 等价物），**不要**用多个空行表示；对话段落照常用空行分隔。
4. 中文正文**不使用硬换行**做「每行 40 字」的人工断行：行长由 CSS 决定，人工断行在不同屏宽下会崩坏。
5. 不需要任何 `<p>` 级内联 HTML 标签：首行缩进完全由渲染层 CSS 承担。

### 7.2 HTML 单页

**建议同时产出**，且是「主阅读体验」的承载者：

- 一份结构相同、样式内联（`<style>`）的单文件 HTML，可离线打开；
- 样式层复用 §9 的 CSS；
- 优点：`text-indent`、`line-break: strict`、`text-spacing-trim`、`text-autospace` 这些中文排版能力只有 CSS 能提供；Markdown 原生渲染器（GitHub 等）无法表达首行缩进。
- 注意：内联 `<style>` 与 Markdown 内容需从同一份结构生成，避免两处维护规则漂移。

### 7.3 EPUB（简要）

- EPUB 3.3 的内容文档基于 Open Web Platform（XHTML/SVG），样式表可随包分发，阅读系统允许覆写作者样式；`rendition:flow` 可声明 `paginated` 或 `scroll`（<https://www.w3.org/TR/epub-33/>）。
- **可行性：高**——把 HTML 单页按章拆分为 `chapter-N.xhtml`，加 `package.opf` 与 `nav.xhtml` 即可。CSS 可原样复用，但要注意：
  - 阅读器常自带「首行缩进/段间距」开关（见 §2.2 的 Koodo Reader 证据），作者样式可能被用户设置覆盖，这是预期行为；
  - `line-break`/`hyphens` 在 EPUB 3.3 附录 E 中还有历史 `-epub-` 前缀，**现代阅读器已改用无前缀标准属性**（前缀的现行必要性未核实）；长篇 EPUB 的兼容性风险高于 HTML 单页，故**优先级排在 Markdown 与 HTML 之后**。


## 8. 本项目换行与版面规则清单（Checklist）

**内容层（Markdown / 结构）**

- [ ] 1. 英文一个 `<p>` ↔ 中文一个 Markdown 段落，**1:1 对应**，不合并、不拆分。
- [ ] 2. 段落之间**恰好一个空行**；段内长行不换行，**不用**行尾两空格或 `\` 造硬换行。
- [ ] 3. 章节内场景分隔用 `---`，不用连续空行。
- [ ] 4. 对话不独立成段；对话与其提示语留在同一段落内。
- [ ] 5. 引号统一使用中文弯引号 `“”‘’`；引号不跨越段落时保持成对；跨段接续时**后段不缩进**（加 `cont` 标记）。
- [ ] 6. 中西混排**手工不插空格、不插 `&nbsp;`**（交给 `text-autospace`）。
- [ ] 7. `&nbsp;` 仅用于数字+单位、姓名+称谓等语义不可分处；需要零宽粘连时用 U+2060 WORD JOINER。
- [ ] 8. 数字、英文单词、`%`、`°C`、`¥` 与其数字、上下标与其基字，保持在同一行内。
- [ ] 9. 长 URL / 代码串用反引号包裹，交由 CSS 断行；不在其中手工断行。
- [ ] 10. 表格保留为 Markdown 表格；单元格内容不手工折行。

**样式层（HTML/CSS）**

- [ ] 11. 正文 `text-indent: 2em`，`margin: 0`（段间零间距）。
- [ ] 12. `text-indent: 0` 必须显式重置于：`blockquote`、`li`、`td`/`th`、`figcaption`、`.cont`、标题。
- [ ] 13. `line-break: strict`；`word-break: normal`；`overflow-wrap: break-word`。
- [ ] 14. **不**设置 `hanging-punctuation`；**不**使用 `word-break: break-all`；**不**在同一文档混用禁则级别。
- [ ] 15. `text-spacing-trim: trim-start`（渐进增强，回退 `normal`）；`text-autospace: ideograph-alpha ideograph-numeric`。
- [ ] 16. `line-height: 1.75`；正文 `font-size` ≥ 17px。
- [ ] 17. 行长 `max-inline-size: 32em`（≈32 字/行），落在 clreq 的 17–40 字区间且小于横排 48 字上限。
- [ ] 18. `letter-spacing: 0`（正文密排）。
- [ ] 19. 正文 `text-wrap: pretty`；标题/图注 `text-wrap: balance`（且标题行数 ≤5）。
- [ ] 20. 正文容器**不设固定高度**，满足 WCAG 2.2 SC 1.4.12。
- [ ] 21. 插图 `figure` 居中、`img { max-inline-size: 100%; height: auto }`；插图资源放 `assets/zh-images/`。
- [ ] 22. 表格外包 `.table-wrap { overflow-x: auto }`，窄屏横向滚动。
- [ ] 23. 提供深色模式（`prefers-color-scheme: dark`），深色下把字重提到 400 以抵消反白变细。
- [ ] 24. 移动端断点：<480px 时页边距收到 1rem、行长 100%；≥1024px 时字号上调到 18–19px、行长放宽到 34–38em。
- [ ] 25. Markdown 与 HTML 由**同一份结构**生成；CSS 只有一份事实源。


## 9. 建议 CSS 片段（可直接使用）

```css
/* 中文里 1em = 1 个汉字宽，所以行长可以直接用 em 指定「每行几个字」 */
:root {
  --novel-font-size: 1.0625rem;   /* 17px（根字号 16px） */
  --novel-line-height: 1.75;      /* 行距 ≈ 字号 75%，落在 clreq 的 50%–100% */
  --novel-measure: 32em;          /* ≈ 每行 32 字（clreq 建议 17–40） */
  --novel-ink: #1f1f1f;
  --novel-bg: #fbfaf7;
}
/* 正文容器：中文排版能力集中声明于此 */
.novel {
  font-family: "Songti SC", "Noto Serif CJK SC", "Source Han Serif SC",
               "Noto Serif SC", SimSun, STSong, Georgia, ui-serif, serif;
  font-size: var(--novel-font-size);
  line-height: var(--novel-line-height);
  color: var(--novel-ink);
  background: var(--novel-bg);
  font-kerning: normal;
  font-optical-sizing: auto;
  -webkit-text-size-adjust: 100%;
  max-inline-size: var(--novel-measure);
  margin-inline: auto;
  padding: 1.25rem 1rem 4rem;
  line-break: strict;             /* = clreq「严格处理」：省略号/破折号不上行首 */
  word-break: normal;             /* CJK 逐字断行，西文按词断行 */
  overflow-wrap: break-word;      /* 仅超长不可断串才强制断开 */
  text-spacing-trim: trim-start;  /* 行首开始括号缩半字；回退值为 normal */
  text-autospace: ideograph-alpha ideograph-numeric; /* 中西文自动间距 */
  text-wrap: pretty;
  text-align: justify;            /* 字距不均时改 start */
}
/* 段落：首行缩进 2em + 段间零间距（clreq 中国大陆书籍惯例） */
.novel p { margin: 0; text-indent: 2em; }
.novel p.cont { text-indent: 0; }   /* 语气未完的接续段 / 未闭合引语 */
/* text-indent 是继承属性，以下块必须显式归零 */
.novel :is(h1,h2,h3,h4,li,td,th,figcaption,blockquote,hr,.table-wrap) { text-indent: 0; }
.novel blockquote p { text-indent: 0; margin: 0.2em 0; }
/* 标题与图注：短文本用 balance（行数 ≤5 时 UA 不得改变行盒数） */
.novel :is(h1,h2,h3) { line-height: 1.35; margin-block: 1.6em 0.7em; text-wrap: balance; }
.novel figcaption { font-size: .9em; line-height: 1.5; color: #6b6b6b;
                    margin-block-start: .5em; text-align: center; }
/* 插图居中、不超出版心 */
.novel figure { margin: 1.6em 0; text-align: center; }
.novel :is(figure img, figure svg) { display: block; max-inline-size: 100%; height: auto; margin-inline: auto; }
/* 引文（原书战歌/咒语）：不缩进首行 */
.novel blockquote { margin: 1.4em 0; border: 0; text-align: center; line-height: 1.6; }
/* 场景分隔符：渲染为居中符号而非靠左直线 */
.novel hr { border: 0; margin: 1.8em 0; text-align: center; line-height: 1; }
.novel hr::before { content: "＊　＊　＊"; letter-spacing: .2em; color: #9a9a9a; }
/* 清单 */
.novel :is(ul,ol) { padding-inline-start: 1.6em; }
.novel li { margin-block: .2em; }
/* 表格：窄屏横向滚动，不压缩不折行 */
.table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 1.4em 0; }
.table-wrap table { border-collapse: collapse; min-inline-size: 28em; width: 100%; }
.table-wrap :is(th,td) { border: 1px solid #d8d4cc; padding: .4em .7em; text-indent: 0; }
/* 长英文串 / URL / 公式 */
.novel :is(code,kbd,samp,a[href^="http"]) {
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  overflow-wrap: anywhere;        /* 只在此处生效，不影响正文 min-content 计算 */
  word-break: normal;
}
.nowrap { white-space: nowrap; }
.formula { overflow-x: auto; text-indent: 0; padding-block: .3em; }
/* 响应式 */
@media (max-width: 480px) {
  :root { --novel-font-size: 1.0625rem; --novel-measure: 100%; }
  .novel { padding-inline: 1rem; padding-block-start: 1rem; }
}
@media (min-width: 1024px) {
  :root { --novel-font-size: 1.1875rem; --novel-measure: 36em; } /* ≈19px / 36 字 */
  .novel { padding-inline: 2rem; }
}
/* 深色模式 */
@media (prefers-color-scheme: dark) {
  :root { --novel-ink: #e2ded6; --novel-bg: #1b1a18; }
  .novel { font-weight: 400; }    /* 反白字视觉变细，锁定常规字重 */
  .novel figcaption { color: #a5a096; }
  .table-wrap :is(th,td) { border-color: #3a3833; }
}
/* 可选：西式「段间距代替缩进」模式 */
.novel--gap p { text-indent: 0; margin-block: 0 .85em; }
```
**使用要点**

1. `text-spacing-trim` / `text-autospace` 目前仅部分引擎支持，写法上**直接写、不包 `@supports`**——不支持的引擎会忽略整条声明，不影响回退（回退行为即各浏览器默认的标点宽度与无自动间距）。
2. 若正文出现「字距被 `text-align: justify` 拉得过开」，把 `.novel` 的 `text-align` 改为 `start`；clreq 6.2.2 要求优先拉伸西文词距与标点空隙，浏览器实现**未核实**是否完全遵守。目标阅读器若自带「首行缩进」开关（Koodo Reader 等），本 CSS 会被用户设置覆盖，属预期行为，不要用 `!important` 对抗。


## 10. 资料来源

**规范与权威文档**

- W3C，《中文排版需求》(clreq)：<https://www.w3.org/TR/clreq/> ｜本文引用的节：
  6.1.1 行首行尾禁则 <https://www.w3.org/TR/clreq/#prohibition_rules_for_line_start_end>｜
  6.1.2 符号分离禁则 <https://www.w3.org/TR/clreq/#prohibition_rules_for_unbreakable_marks>｜
  6.1.3 行尾点号悬挂 <https://www.w3.org/TR/clreq/#hanging_punctuation_marks_at_line_end>
  6.2.1.1 段首缩排 <https://www.w3.org/TR/clreq/#line_head_indent_at_the_beginning_of_paragraphs>｜
  6.2.2 行内调整 <https://www.w3.org/TR/clreq/#line_adjustment>｜
  6.3.2 标点宽度调整 <https://www.w3.org/TR/clreq/#punctuation_width_adjustment>｜
  6.3.2.3 行首行尾标点挤压 <https://www.w3.org/TR/clreq/#h-compression_of_punctuation_marks_at_line_start>
  6.3.3 横排中西文混排 <https://www.w3.org/TR/clreq/#mixed_text_composition_in_horizontal_writing_mode>｜
  6.4 基线、行高 <https://www.w3.org/TR/clreq/#h_baselines>｜
  7.1.1 页面设计（行长 17–40 字 / 上限 48 字）<https://www.w3.org/TR/clreq/#page_design>｜
  7.1.2 孤行与孤字 <https://www.w3.org/TR/clreq/#adjustments_of_orphans_and_widows>
- W3C，《Chinese Layout Gap Analysis》(clreq-gap)：<https://www.w3.org/TR/clreq-gap/>（#244 表意空格断行差异、#245 引号断行规则）
- W3C，CSS Text Module Level 3（`hanging-punctuation`、`line-break`）：<https://www.w3.org/TR/css-text-3/>
- W3C，CSS Text Module Level 4（`text-wrap`、`text-spacing-trim`、`text-autospace`、`hyphenate-limit-chars`）：<https://www.w3.org/TR/css-text-4/>
- CommonMark Spec 0.31.2，Hard line breaks / Soft line breaks：<https://spec.commonmark.org/0.31.2/#hard-line-breaks>
- W3C，EPUB 3.3：<https://www.w3.org/TR/epub-33/>
- W3C WAI，WCAG 2.2 Understanding SC 1.4.12 Text Spacing：<https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html>

**MDN 与浏览器兼容数据**

- MDN 属性页：`line-break` <https://developer.mozilla.org/en-US/docs/Web/CSS/line-break>｜
  `word-break` <https://developer.mozilla.org/en-US/docs/Web/CSS/word-break>｜
  `overflow-wrap` <https://developer.mozilla.org/en-US/docs/Web/CSS/overflow-wrap>｜
  `hanging-punctuation` <https://developer.mozilla.org/en-US/docs/Web/CSS/hanging-punctuation>｜
  `text-wrap` <https://developer.mozilla.org/en-US/docs/Web/CSS/text-wrap>
- MDN 指南《Wrapping and breaking text》：<https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_text/Wrapping_breaking_text>
- MDN browser-compat-data（§4.4 支持度表格的数据源）：<https://github.com/mdn/browser-compat-data>

**中文排版实践与阅读器实现**

- typo.css（中文网页重设与排版，含 `.typo` 现代中文排版规则）：<https://github.com/sofish/typo.css> ｜设计依据文档：<https://github.com/sofish/typo.css/blob/master/docs/modern-chinese-typography.md>
- Koodo Reader（开源中文电子书阅读器，正文排版可调项：行高 / 字距 / 首行缩进 / 段间距 / 页边距）：<https://github.com/koodo-reader/koodo-reader> ｜语言包：<https://github.com/koodo-reader/koodo-reader/blob/master/src/assets/locales/en.json>


## 11. 未核实事项（明确声明）

1. **网文平台阅读器的确切排版参数**：起点中文网、番茄小说、微信读书的正文样式表均为鉴权 + 懒加载，`curl` 只能取得外壳 HTML 与资源清单，未能定位实际生效的正文 CSS。本文因此不引用其具体取值，只采用与「缩进 or 段间距二选一」这一通用模型兼容的方案。
2. **GB/T 15834—2011《标点符号用法》原文**：未找到可免费访问的一手副本；本文关于「行尾全角标点缩半字（第 5.1.10 条）」的表述转引自 W3C clreq 6.3.2.3。
3. **渲染观感未实测**：Safari 的 `hanging-punctuation: allow-end` 对中文全角句读的实际悬挂行为（无 Safari 可测）；各浏览器 `text-spacing-trim` / `text-autospace` 的挤压量与自动间距像素值（规范允许 UA 自行裁剪，`auto` 为 platform dependent）。
4. **EPUB 3.3 附录 E 中 `-epub-line-break` / `-epub-hyphens` 前缀在现代阅读器中的必要性**：未核实；本文建议统一使用无前缀标准属性。
