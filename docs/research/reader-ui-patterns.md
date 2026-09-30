# 小说阅读器界面与交互布局调研（阅读页 / 目录 / 设置 / 双语对照）

- 范围：主流小说阅读 App 与在线阅读站点的**阅读界面与交互布局**——首页/书架/详情页分工、目录形态、阅读页布局、翻页模式、设置项、宽窄屏适配、双语对照、可访问性与反例。内容与市场见 `china-novel-market.md`，正文排版数值见 `line-breaking-and-layout.md`，本文不重复。
- 方法：本环境 `web_search` 不可用（401），全部资料用 `curl` / `web_fetch` 直接抓取。Bing 中文结果失真、搜狗/百度/DDG 反爬，因此**不做泛搜索**，改为按已知 URL 抓官方页面、App Store 描述（iTunes Lookup API）、前端 JS bundle 文案与开源仓库源码。
- 证据等级：**一手** = 产品页面 / 官方帮助 / 开发者自述的商店描述 / 开源源码与语言包；截图推断会写明；**未核实**表示未取得一手来源。
- 网络限制：AO3、Wattpad、Webnovel、Google Play 帮助站、知乎在本网络不可达（超时/403）。AO3 改用官方开源代码 [otwcode/otwarchive](https://github.com/otwcode/otwarchive) 取证；Wattpad / Webnovel 只用官方商店描述。

## 0. 结论摘要

1. 中文平台的**目录多数不是独立页面**，而是「详情页内嵌目录 + 阅读器内目录面板」；番茄详情页目录默认折叠（1496 章只显示约 50 条 + 「查看更多」）。
2. 目录信息量最大的是**表格式目录**：晋江网页版六列「章节 / 标题 / 内容提要 / 字数 / 点击 / 更新时间」；QQ阅读网页版只有「章节名 + 倒序 + 最新章节更新时间」。
3. 网页阅读器顶栏趋向**极简**（Standard Ebooks 只有「返回书籍 / 目录」），章节导航放在正文下方，并带 `rel="prev"/"next"`。
4. 「点击区域」确有产品做成**可配置项**（「阅读」App），但主流商业 App 的左/中/右映射**未取到一手来源**，不应照抄传说。
5. 翻页动画的主流枚举是**覆盖 / 滑动 / 仿真 / 滚动 / 无动画**；Apple Books 与 Kindle 官方只承诺「翻页 ↔ 连续滚动」二选一——**滚动是必须支持的降级路径**。
6. 设置项最全的是桌面开源阅读器（行距、字距、段距、页边距、首行缩进、背景虚化与透明度、E-Ink、简繁、自动翻页、朗读）；商业网页版通常只给「字号 + 背景/主题」。
7. 宽屏的核心手段是**限制行宽 + 居中留白**：SE 正文 `max-width: 55ch`，Royal Road 让用户选 50%–100%/Max；**没有一家正文做多栏**。
8. 双语对照有两条成熟路线：**并列（parallel text）** 与 **覆盖/点击切换（overlay / tap-to-toggle）**；Beelinguapp 用「同段高亮 + 同步滚动」。
9. 双语排版已知坑：段落粒度不一致、两栏行高不一致导致错位、图片/表格只在一侧、超长段落时列模式出错。
10. 合规会**直接改变产品形态**：开源「阅读」App 的原仓库 README 已被替换为侵权公告，代码与发行物整体撤下。

## 1. 首页 / 书架 / 详情页的职责与「进入阅读」的步数

| 产品 | 首页 | 书架 | 详情页 | 进入正文 | 来源 |
| --- | --- | --- | --- | --- | --- |
| 番茄小说（网页） | 书城/推荐 | 独立页，官方描述支持添加/隐藏/移除/排序/分组 | 简介 + 标签 + 字数 + 状态 + **内嵌目录** + 「开始阅读」 | 详情 → 章（每章 `/reader/<id>`） | [详情](https://fanqienovel.com/page/7143038691944959011)、[书架](https://fanqienovel.com/bookshelf) |
| QQ阅读（网页） | 书城/分类/排行 | 「书架」入口 | `/book-detail/<id>`：简介、评分、加书架、章节列表 | 详情 → `/book-read/<bid>/<cid>`；目录在 `/book-chapter/<bid>` | [详情](https://book.qq.com/book-detail/173741)、[目录](https://book.qq.com/book-chapter/173741) |
| 微信读书（网页） | 书城/推荐 | **网页端不可管理书架**，需 App | 书籍详情 | 详情 → 阅读页；工具栏含「下载 App 继续阅读」 | [web 阅读器](https://weread.qq.com/web/)及其 [bundle](https://cdn.weread.qq.com/web/wrwebnjlogic/js/app.88f998b2.js) |
| 起点读书（App） | 书城/推荐 | 书架 | 详情 | 官方描述强调**书架、阅读进度、书签、笔记云端同步** | [App Store](https://apps.apple.com/cn/app/id534174796) |
| Standard Ebooks | 书目 | —（无账号） | 详情页：Read free / **Read online：目录 或 单页整本** | 详情 → 目录 → 章（2 跳） | [详情](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice)、[目录](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/text) |
| Royal Road | 榜单/最新更新 | Follow / Favorites | 简介、**章节表**、「Start Reading」 | 作品页 → 章（1 跳） | [作品页](https://www.royalroad.com/fiction/21220/mother-of-learning) |
| AO3 | 作品列表 | Bookmarks / Marked for Later | 作品页**即阅读页** | 0 跳；正文上方有 Entire Work / Chapter by Chapter | [源码](https://github.com/otwcode/otwarchive/blob/master/app/views/works/show.html.erb) |

要点：

- 中文平台把「选书 → 看书」压到最短：番茄详情页内即可读目录并一键「开始阅读」；代价是**目录默认折叠**，1496 章要先「查看更多」。
- 微信读书网页版是明确的**功能阉割 + 引流 App**：书架管理、私密阅读、无限卡购买都要求下载 App；其内置帮助原文列出阅读器右下角竖排工具栏「上一章 / 目录 / 下一章 / 深色模式 / 浅色模式 / 下载 App 继续阅读」（[bundle](https://cdn.weread.qq.com/web/wrwebnjlogic/js/app.88f998b2.js)）。
- 起点读书 App 的具体版式**未取到一手来源**，只引用官方商店描述能证实的部分。

## 2. 目录（章节列表）的呈现方式与信息量

| 形态 | 产品 | 目录项信息 | 来源 |
| --- | --- | --- | --- |
| 独立目录页 + 表格 | 晋江文学城（网页） | **章节 / 标题 / 内容提要 / 字数 / 点击 / 更新时间**（六列，抓取时观察到的表头） | [onebook.php](http://www.jjwxc.net/onebook.php?novelid=1140079) |
| 独立目录页 | QQ阅读（网页） | 「目录(56章)」、倒序开关、章节名、最新章节的更新时间、书籍更新时间 | [book-chapter](https://book.qq.com/book-chapter/173741) |
| 详情页内嵌区块 | 番茄小说 | 「目录 1496 章」、倒序、分卷标题（如「第十卷：这一切的终焉」）、默认约 50 条 + 「查看更多」 | [详情页](https://fanqienovel.com/page/7143038691944959011) |
| 阅读器内面板/抽屉 | 「阅读」App、Koodo Reader | 面板内含目录、书签、笔记、高亮；细节项有「目录（%d）」「反转目录」「更新目录」「移除重复标题」 | [阅读 App 中文文案](https://raw.githubusercontent.com/Jer-Chao/legado/master/app/src/main/res/values-zh/strings.xml)、[Koodo 语言包](https://raw.githubusercontent.com/koodo-reader/koodo-reader/master/src/assets/locales/zh-CN.json) |
| 下拉 select + 独立兜底页 | AO3 | 章节索引用可展开的 `<select>` 提交跳转，另有「full page」链接；**`<noscript>` 下直接给独立导航页** | [源码](https://github.com/otwcode/otwarchive/blob/master/app/views/works/_work_header_navigation.html.erb) |
| 独立目录页（无标题） | Standard Ebooks | 仅罗马数字章序；另有「单页整本」模式，用 `#chapter-N` 锚点 | [目录](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/text)、[单页](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/text/single-page) |
| 作品页章节表 | Royal Road | 两列：**Chapter Name / Release Date**；正文页内没有目录，需退回作品页 | [作品页](https://www.royalroad.com/fiction/21220/mother-of-learning) |

- **已读标记**：上述产品的公开页面/源码中均未取到「目录项显示已读/未读」的直接证据（Koodo 的「标记为未读」是图书级）；**未找到一手来源**。
- 「阅读」App 支持「目录（%d）」计数与「更新目录」，说明目录与正文缓存分离、可刷新。
- 起点、七猫、掌阅、晋江 **App 内**的目录是抽屉还是独立页，**未取到一手来源**。

## 3. 阅读页面布局：顶栏/底栏、点击区域与进度

**工具栏内容**

- 微信读书（网页）：右下角竖排按钮，自上而下「上一章 / 目录 / 下一章 / 深色模式 / 浅色模式 / 下载 App 继续阅读」，默认深色（同上 bundle）。
- QQ阅读（网页）：底部工具栏「加入书架 / 字号 / 背景」，弹层标题为「调整字号」「阅读背景」；正文区有 `< 上一章`、`下一章 >` 与「目录」；「更多设置」含**听书、自动阅读、举报、摸鱼模式、手机阅读（扫码下载 App）**；章末显示**本章字数、更新时间、自动购买下一章**（[阅读页](https://book.qq.com/book-read/173741/1)及其前端 bundle）。
- Standard Ebooks：顶栏只有「Standard Ebooks / Back to ebook / Table of contents」；正文底部是 `rel="prev"`/`rel="next"` 的上一章/下一章，直接显示目标章名（[示例章](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/text/chapter-1)）。
- Royal Road：正文上方是 `Reader Preferences`、`Previous Chapter`、`Next Chapter` 与一个**广告位（带 Remove 按钮）**；正文标题形如「Chapter 001 / Good Morning Brother」（[章节页](https://www.royalroad.com/fiction/21220/mother-of-learning/chapter/301778/1-good-morning-brother)）。
- AO3（源码）：action nav 含 Entire Work、← Previous Chapter、Next Chapter →、Chapter Index、Bookmark / Mark for Later、Comments，跳转锚点 `#workskin`，页首 `#top`。

**进度指示**

- Kindle App 官方描述：显示「阅读百分比、真实页码（多数畅销书）、按阅读速度估算的本章/全书剩余时间」（[App Store](https://apps.apple.com/us/app/id302584613)）。
- 「阅读」App：`进度 %1$s 进度 %2$d/%3$d`（章内/全书），并有「进度条行为」设置项；QQ阅读在章末给「本章字数 + 更新时间」。

**点击区域**

- 有明确一手证据的是开源侧：「阅读」App 的中文文案包含「点击翻页」「点击区域设置」「滑动翻页阈值」「音量键翻页」「鼠标滚轮翻页」「自定义翻页按键」。
- 起点/番茄/微信读书/七猫/掌阅/晋江 App 的左/中/右点击映射**未找到一手来源**，本文不做断言。

## 4. 翻页模式：可选集合与取舍

| 模式 | 有据可查的产品 | 优点 | 缺点 |
| --- | --- | --- | --- |
| 上下连续滚动 | Kindle（官方描述：可「left to right 翻页」或「continuously scroll」）、Apple Books（可开启 vertical scrolling） | 手机操作成本最低、长章连贯、实现最简单 | 长内容定位与回看困难；进度条与内容长度脱钩（[NN/g](https://www.nngroup.com/articles/infinite-scrolling/) 对无限滚动的批评同理） |
| 左右平移滑动 | 「阅读」App（`滑动`） | 方向感明确、性能好 | 需自实现分页与手势，锚点/选词易冲突 |
| 覆盖 | 「阅读」App（`覆盖`） | 接近纸感的轻量替代，性能优于仿真 | 视觉层级稍突兀 |
| 仿真翻页 | 「阅读」App（`仿真`）、Koodo「仿真」 | 拟真、老用户偏好 | 渲染成本高，与点击区域/长按选词易冲突 |
| 无动画 | 「阅读」App（`无动画`）、Koodo「禁用水平滚动动画」 | 最快、省电 | 缺少翻页反馈，易误触 |
| 自动翻页/滚动 | 「阅读」App（间隔/速度）、QQ阅读（自动阅读 + 速度上限）、Koodo（可**禁用**章末自动跳章） | 解放双手 | 争议集中在「跨章自动跳转」 |

Koodo 的 `Disable auto scroll to next or previous chapter`（当到达本章末尾时禁用自动滚动到下一章）说明：**跨章自动滚动是需要显式开关的行为**，默认边界应保守。

## 5. 阅读设置项清单（跨产品对照）

| 设置项 | Royal Road（网页，实测弹层） | Apple Books / Kindle（官方描述） | 「阅读」App（中文文案） | Koodo Reader | 微信读书/QQ阅读（网页） |
| --- | --- | --- | --- | --- | --- |
| 字号 | 10–32 逐档 | 可调文字大小 | 字号、字体大小 | 字体大小 | 字号（QQ阅读「调整字号」） |
| 行距 / 字距 / 段距 | —（无） | **行高、字距**（Apple Books） | 行距、字距、段距 | 行间距、字间距、段落间距 | —（未取到） |
| 首行缩进 | — | — | —（由字体/样式决定） | **首行缩进** | — |
| 页边距 / 行宽 | **Reader Width：Max/90/80/70/60/50%** | 边距（Kindle）、文本对齐 | 页边距 | 页边距、页面宽度 | — |
| 字体 | 17 种，含 **Open Dyslexic、Atkinson Hyperlegible** | 字体类型（Kindle） | 字体、系统内置字体 | 字体、CJK 字体、导入本地字体 | 掌阅官方描述称可「自定义阅读背景和字体」 |
| 主题 / 背景 / 亮度 | Theme（Dark/Light）+ **Dim background 0–100%（20% 步进）** | 多套主题（字体+底色）、夜间自动主题、背景色、亮度 | 主题模式、夜间模式、**E-Ink 模式**、背景颜色/图片、背景透明度、虚化、亮度 | 主题、背景颜色/图片、颜色反转、覆盖原书背景 | 微信读书：深色/浅色；QQ阅读：「阅读背景」多色 |
| 翻页/滚动 | —（网页原生滚动） | 翻页 ↔ 连续滚动切换 | 翻页动画（覆盖/滑动/仿真/滚动/无动画）、自动翻页 | 翻页动画（滑动/仿真） | QQ阅读：自动阅读（含速度） |
| 简繁 | — | — | 简繁转换 | — | — |
| 其它 | 主题作用于整站 | Page Flip、X-Ray、词典、生词/即时翻译、跨设备同步 | 朗读、音量键翻页、进度条行为、点击区域 | 阅读标尺、速读模式、摸鱼模式（老板键）、孤行寡行 | QQ阅读：摸鱼模式、「自动购买下一章」 |

（Royal Road 来自其阅读页 `#settings` 弹层实测 HTML；Apple Books / Kindle 来自官方商店描述；「阅读」App 与 Koodo 来自各自语言包；微信读书/QQ阅读来自其网页阅读器前端资源。）

## 6. 响应式 / 宽屏

- **固定度量 + 居中留白**：Standard Ebooks 网页阅读器 `main { max-width: 55ch; margin: 5rem auto 3rem; padding: 0 3rem }`，`font-size: 18px`、`line-height: 1.5`；窄屏（`≤65ch`）内边距降为 2rem，`≤450px` 换小 logo；`@media(pointer: coarse)` 时头部 `position: fixed`，并给 `*:target` 加 `scroll-margin-top: 4em` 以免锚点被固定头部遮挡（[web.css](https://standardebooks.org/css/web.css)）。这是「宽屏利用空间 = 控制行宽而非塞更多内容」的教科书实现。
- **把宽度交给用户**：Royal Road 提供 50%–100%/Max 的 Reader Width；Koodo 提供「页面宽度」与「页边距」。
- **窄屏降级 = 删功能 + 引流**：微信读书网页版在窄屏仍是一个竖排工具栏，但书架管理、私密阅读、无限卡购买等入口直接引导下载 App（内置帮助文案）；QQ阅读网页版同样在阅读器里放了「手机阅读」「扫码下载 App」。（反例，见 §9）
- **没有任何产品在正文层做多栏**；`columns` 只出现在双语对照/印刷排版场景。

## 7. 中英对照 / 双语阅读

**有产品在做，且有两套成熟布局**

| 路线 | 代表 | 做法（来源原话） |
| --- | --- | --- |
| 并列（parallel text） | Beelinguapp | 官方描述：*parallel-text method*，两种语言 **side by side**；「Karaoke-Style Scrolling Text：跟随同步文本滚动」（[App Store](https://apps.apple.com/us/app/id1225056371)、[官网](https://beelinguapp.com/)） |
| 并列（沉浸式译文排版） | 欧路「每日英语阅读」 | 官方页：「采用**沉浸式翻译排版，原文、译文对照呈现**」「可灵活设置翻译字体、颜色等样式」「一键导出双语对照翻译文档」（[产品页](https://www.eudic.net/v4/en/app/eudic)） |
| 并列（导入式） | kerivin/bilingual-book-builder | 「Builds a parallel text ePub with **sentences aligned side-by-side**」——用 bertalign 做**句级对齐**后生成平行 EPUB（[repo](https://github.com/kerivin/bilingual-book-builder)） |
| 分栏 / 交替行（印刷） | bilinguator/print-bilingual-pdf | `mode='cols'`（平行分栏）或 `mode='rows'`（交替行），支持统一插图目录（[repo](https://github.com/bilinguator/print-bilingual-pdf)） |
| 点击切换 | Ovid | 「**Click-to-toggle** — Tap any paragraph to switch between original and translated text instantly」；另有 CJK 排版、PWA（[repo](https://github.com/GabrielDrapor/ovid)） |
| 覆盖层（不改原书） | dualtranslate.koplugin | 用 CSS `::after` 注入译文，译文有**独立的字号(8–40)/字体/颜色**设置（[repo](https://github.com/enneaa/dualtranslate.koplugin)） |

另有一类**单词级辅助**而非对照：LingQ 的 Reader 追踪每个遇到的词、点词即时释义（[App Store](https://apps.apple.com/us/app/id379385811)）。

**同步滚动怎么做**

- Beelinguapp 的官方说法是「**同一段文本同步高亮**」（karaoke-style），即两侧共享同一份定位，而非两个独立滚动容器互推位置。
- 未找到任何产品级文档描述「双栏独立滚动 + 实时同步」的实现（**该部分未找到一手来源**）。工程上更稳的是**按段落配对渲染成同一个网格行**，滚动天然同步。

**已知排版问题（均有可核实来源）**

1. 段落粒度不一致：`Kpeved/LanguageLearner` 自述用「**proportionally-mapped** native translation」（按比例映射），`bilingual-book-builder` 必须引入句级对齐模型，说明段级 1:1 并非默认成立（[repo1](https://github.com/Kpeved/LanguageLearner)、[repo2](https://github.com/kerivin/bilingual-book-builder)）。
2. 分栏模式在长段落时出错：`print-bilingual-pdf` README 原文「These codes are browser and texts dependent. **In case of big texts with big paragraphs, bugs may occur.**」
3. 两栏行高/字体度量不一致会造成段落错位——这是「按段配对成网格行」要规避的问题；未找到专门论述，标注为**由布局机制推导**。
4. 插图只能出现一次：`print-bilingual-pdf` 用统一插图目录让插图独立于两侧文本，避免「图只在一栏」。

**中国 App 的中英对照**：微信读书、起点、掌阅是否提供「对照翻译」阅读模式，**未找到一手来源**（站点鉴权，且无官方帮助文档可取）。

## 8. 可访问性 / 合规经验

**可访问性（有据可查的做法）**

- Standard Ebooks 官方声明：语义 XHTML、非文字内容全部有替代文本、**符合 WCAG 2.2 AA 与 EPUB Accessibility 1.1**、**永不使用 DRM**（[Accessibility](https://standardebooks.org/about/accessibility)）；站点设置提供 `Automatic / Light / Dark` 三选一并保存（[Settings](https://standardebooks.org/settings)），CSS 内有 `@media(prefers-reduced-motion)`。
- 字体层面的可访问性：Royal Road 把 **Open Dyslexic** 与 **Atkinson Hyperlegible** 排在字体列表最前，并提供 Dim background 0–100% 降低眩光。
- **无 JS 降级**：AO3 的章节索引用 `<noscript>` 回退到独立导航页，脚本关闭也能换章。
- **深链接**已是标配：SE `/text/chapter-1`（带 `rel="prev"/"next"`）、Royal Road `/fiction/<id>/<slug>/chapter/<cid>/<slug>`、QQ阅读 `/book-read/<bid>/<cid>`、番茄 `/reader/<chapterId>`、AO3 `/works/<id>/chapters/<id>`。
- **键盘**：Koodo 键位最全（上下页/上下章、四个阅读面板、老板键）；「阅读」App 有音量键翻页、滚轮翻页、自定义按键；SE 与 AO3 的快捷键文档**未找到一手来源**。
- **打印**：SE 的 `web.css`/`core.css` 中**未发现 `@media print`**（抓取当日）；双语侧有 `print-bilingual-pdf` 专做打印版，说明「双语 + 打印」是真实需求。

**合规改变设计的公开案例**

- 开源「阅读」（Legado）项目：原仓库 [gedoor/legado](https://github.com/gedoor/legado) 的 README 已被替换为一则中文公告，称「本项目涉及侵权行为的违法……在此郑重发布公告，**删除项目内容**」，并链接《阅文知识产权保护公告》；仓库根目录只剩 `README.md` 与公告图片，源码与发行物已撤下（[README](https://github.com/gedoor/legado)、[公告链接](https://mp.weixin.qq.com/s/bcTbqBQA1T0YoRwq76xcWQ)，后者在本环境被微信验证页拦截，未取到正文）。与之相对，第三方镜像 fork 仍保留完整文案（本文用它取证 UI 文案，**不涉及任何内容获取方式**）。
- 免费模式的界面取舍公开写在官方描述里：番茄与七猫均自称「**【广告+免费】的阅读模式**（读者免费看书，广告商买单）」；Wattpad 把「**uninterrupted ads-free reading**」列为 Premium 卖点（[番茄](https://apps.apple.com/cn/app/id1468454200)、[七猫](https://apps.apple.com/cn/app/id1387717110)、[Wattpad](https://apps.apple.com/us/app/id306310789)）。
- 起点/晋江等因版权或内容合规被下架、整改并具体改版的**公开一手通报未找到**（本环境无法用中文搜索引擎核实）。

## 9. 反例（不要这样做）

| 反例 | 证据 | 来源 |
| --- | --- | --- |
| 阅读页插广告 | Royal Road 章节页正文上方即广告位，并引导点「Remove」（付费去广告） | [章节页](https://www.royalroad.com/fiction/21220/mother-of-learning/chapter/301778/1-good-morning-brother) |
| 网页端阉割、逼装 App | 微信读书网页阅读器工具栏直接放「下载 App 继续阅读」，书架管理/私密阅读/无限卡购买均不可用 | [bundle 帮助文案](https://cdn.weread.qq.com/web/wrwebnjlogic/js/app.88f998b2.js) |
| 目录塞进详情页且默认折叠 | 番茄 1496 章默认只显示约 50 条 + 「查看更多」，长书要多次点击才能定位 | [详情页](https://fanqienovel.com/page/7143038691944959011) |
| 无限滚动承载「找」的任务 | NN/g：无限滚动不适合目标导向的查找，长页回找已读条目效率低，还破坏滚动条的长度语义 | [NN/g](https://www.nngroup.com/articles/infinite-scrolling/) |
| 跨章自动滚动无开关 | Koodo 专门提供「到达章末/章首时禁用自动滚动到下一章/上一章」 | [Koodo 语言包](https://raw.githubusercontent.com/koodo-reader/koodo-reader/master/src/assets/locales/zh-CN.json) |
| 单一底色、无深色模式 | SE 与 Royal Road 都把深色模式做成显式选项（后者还有 0–100% 减光） | [SE Settings](https://standardebooks.org/settings)、[RR 阅读页](https://www.royalroad.com/fiction/21220/mother-of-learning/chapter/301778/1-good-morning-brother) |
| 强制登录 / 注册墙 | **未找到一手来源**（Wattpad、Webnovel、知乎在本网络不可达） | — |
| 阅读进度丢失 | **未找到一手来源**；可核实的只有起点宣称「书架、阅读进度、书签、笔记自动云同步」与「阅读」App 的进度冲突确认逻辑 | [起点](https://apps.apple.com/cn/app/id534174796)、[阅读 App 文案](https://raw.githubusercontent.com/Jer-Chao/legado/master/app/src/main/res/values-zh/strings.xml) |

## 10. 对本项目的设计建议

本项目约束：GitHub Pages 静态站点、无后端、中英双语、32 章、含 SVG 插图、纯前端。

1. **信息架构**：`index.html`（详情 + 目录合一）+ `chapters/NN.html`（每章独立 URL）。取番茄「详情页内嵌目录」与 Standard Ebooks「独立目录页」的折中，兼顾 SEO 与「1 跳进正文」；32 章目录**全部展开**，不要学 1496 章产品的「查看更多」。
2. **双端导航**：章页顶部「← 目录」，底部「上一章 / 下一章」，用 `rel="prev"/"next"` 并显示目标章标题（照抄 SE，兼顾 SEO 与可用性）；目录页用 `#chapter-N` 锚点，另提供可选单页版。
3. **顶栏 2–3 项**：目录 / 语言模式 / 设置，默认隐藏、点正文中部切换；底部只放「百分比 + 章号」，不伪造页码。
4. **点击区域**：左/中/右三分是常见方案，但**本次未取得主流 App 一手证据**，建议默认「仅滚动」，翻页作为设置项开启（参照「阅读」App 把点击区域做成可配置项）。
5. **设置项最小集**（对齐 Royal Road / Apple Books 可核实项）：字号 3–5 档、行高 1.5/1.75/2.0、行宽 60%/75%/Max、主题（自动/浅/深/羊皮纸），存 `localStorage`；默认跟随 `prefers-color-scheme`，并像 SE 一样给 Automatic/Light/Dark 三选一。
6. **双语布局分档**：≥1024px 用**按段落配对的单网格双栏**（每段一个 `grid-row`，不是两个独立滚动容器）——本项目源↔译段落已 1:1（见 `line-breaking-and-layout.md`），无需句级对齐模型；<1024px 降级为**同段点击切换**（Ovid 式）；始终保留「仅中 / 仅英 / 对照」三档并记忆。
7. **双语排版防护**：两栏共用同一 `line-height`，英文侧只调字号与 `hyphens: auto`；`<hr>`、表格、SVG 用 `grid-column: 1 / -1` 跨栏**只出现一次**。
8. **无 JS 降级**：目录与上下章用纯 `<a href>`；设置与对照模式用 CSS 类渐进增强（同 AO3 的 `noscript` 思路）；SVG 给 `<title>`/`aria-label`。
9. **键盘与打印**：←/→ 翻章、`[`/`]` 切章、`s` 开关设置；补 `@media print`（隐藏工具栏、对照模式转单栏或交替行）——SE 没做，双语场景需要。
10. **反例规避**：不做无限滚动、不折叠目录、不插广告、不引导下载 App、不强制登录；进度同时写 `localStorage` 与 `#p3` 锚点。

## 11. 来源清单

**中国大陆产品（官方页面 / 商店描述 / 前端资源）**

- App Store（数据经 iTunes Lookup API）：[起点读书](https://apps.apple.com/cn/app/id534174796)、[番茄小说](https://apps.apple.com/cn/app/id1468454200)、[微信读书](https://apps.apple.com/cn/app/id952059546)、[七猫小说](https://apps.apple.com/cn/app/id1387717110)、[掌阅](https://apps.apple.com/cn/app/id463150061)、[晋江小说阅读](https://apps.apple.com/cn/app/id966807283)、[QQ阅读](https://apps.apple.com/cn/app/id487608658)
- 番茄：[书籍详情页](https://fanqienovel.com/page/7143038691944959011)、[书架页](https://fanqienovel.com/bookshelf)
- QQ阅读：[目录页](https://book.qq.com/book-chapter/173741)、[阅读页](https://book.qq.com/book-read/173741/1)
- 微信读书 web 阅读器 — <https://weread.qq.com/web/>；内置帮助文案 bundle — <https://cdn.weread.qq.com/web/wrwebnjlogic/js/app.88f998b2.js>
- 晋江文学城 文章页（目录表） — <http://www.jjwxc.net/onebook.php?novelid=1140079>

**书源/开源阅读器**

- 阅读（Legado）原仓库（现为侵权公告） — <https://github.com/gedoor/legado>；公告引用链接 — <https://mp.weixin.qq.com/s/bcTbqBQA1T0YoRwq76xcWQ>
- 阅读 App 中文文案（镜像 fork，仅用于 UI 取证） — <https://raw.githubusercontent.com/Jer-Chao/legado/master/app/src/main/res/values-zh/strings.xml>
- Koodo Reader 中文语言包 — <https://raw.githubusercontent.com/koodo-reader/koodo-reader/master/src/assets/locales/zh-CN.json>

**海外 / 网页端**

- Royal Road [作品页](https://www.royalroad.com/fiction/21220/mother-of-learning)、[章节页](https://www.royalroad.com/fiction/21220/mother-of-learning/chapter/301778/1-good-morning-brother)、[知识库](https://www.royalroad.com/support/faq)
- AO3 官方开源代码 — <https://github.com/otwcode/otwarchive>（[章节导航模板](https://github.com/otwcode/otwarchive/blob/master/app/views/works/_work_header_navigation.html.erb)、[章节页模板](https://github.com/otwcode/otwarchive/blob/master/app/views/chapters/show.html.erb)）
- [Kindle App 描述](https://apps.apple.com/us/app/id302584613)、[Apple Books 描述](https://apps.apple.com/us/app/apple-books/id364709193)
- Standard Ebooks：[阅读入口](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice)、[目录页](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/text)、[单页版](https://standardebooks.org/ebooks/jane-austen/pride-and-prejudice/text/single-page)、[阅读器 CSS](https://standardebooks.org/css/web.css)、[Accessibility](https://standardebooks.org/about/accessibility)、[Settings](https://standardebooks.org/settings)
- [Wattpad 描述](https://apps.apple.com/us/app/id306310789)、[Webnovel 描述](https://apps.apple.com/us/app/id1234939196)（站点本体不可达）
- NN/g《Infinite Scrolling Is Not for Every Website》 — <https://www.nngroup.com/articles/infinite-scrolling/>

**双语对照**

- [Beelinguapp 官网](https://beelinguapp.com/)、[App Store 描述](https://apps.apple.com/us/app/id1225056371)；[欧路「每日英语阅读」](https://www.eudic.net/v4/en/app/eudic)；[LingQ](https://apps.apple.com/us/app/id379385811)
- [Ovid（点击切换式双语读者）](https://github.com/GabrielDrapor/ovid)、[bilingual-book-builder（句级对齐 + 平行 EPUB）](https://github.com/kerivin/bilingual-book-builder)、[print-bilingual-pdf（分栏/交替行 + 打印）](https://github.com/bilinguator/print-bilingual-pdf)、[dualtranslate.koplugin（覆盖层式双语）](https://github.com/enneaa/dualtranslate.koplugin)、[LanguageLearner（按比例映射译文）](https://github.com/Kpeved/LanguageLearner)

**未核实项汇总**

- 起点/番茄/微信读书/七猫/掌阅/晋江 **App 内**的阅读页细节：点击区域映射、顶底栏自动隐藏策略、翻页动画选项、目录是抽屉还是独立页。
- 各产品的**章级已读/未读标记**与**字数/更新时间**在目录中的展示规则（晋江六列表格除外）。
- 微信读书/起点/掌阅是否提供「中英对照」阅读模式。
- 强制登录/注册墙、阅读进度丢失的**用户吐槽一手来源**（社区站点不可达）。
- SE / AO3 的键盘快捷键文档；SE 的打印样式（当前未发现）。
