# Snowmoon 中译 · GitHub Pages 阅读站点前端设计任务书（视觉模型）

你是资深前端工程师 + 中文阅读产品设计师。请为一个**已经完成的中文译作**重新设计整套阅读前端。
这是一次**完全重新设计**：视觉语言、信息架构、页面布局、交互、响应式策略全部由你决定；
唯一不可更改的是下面「硬约束」和「集成契约」（因为它们由构建脚本负责填充）。

## 作品背景

- 原作 **Snowmoon /《雪月》**，作者 Vitalik Buterin，英文科幻（太阳朋克色彩：城邦 Veridia、
  密码学投票、手表终端、虚构语言 Dzegoban），公开发布于 GPL-3.0-only。
- 本项目是非官方**中译本**：32 章、约 14.6 万汉字、内嵌 56 幅 SVG 插图（图中文字已中文化），
  另有大量「模拟手表／终端界面」面板（深色底、等宽字体、表格布局）。
- 成品是**纯静态站点**，直接托管在 GitHub Pages，不使用任何后端、构建期以外的依赖。

## 硬约束（必须遵守）

1. **零外部依赖**：不得引用 CDN、npm 包、webfont、图标库、追踪脚本。只能用系统字体栈 + 原生
   HTML/CSS/JS（ES2017 以内，无模块打包）。所有资源都在仓库内。
2. **必须能从 `file://` 直接打开**：不得 fetch/XHR 任何数据文件，正文必须直接内联在 HTML 里。
3. **不是单页滚动小说**：必须有彼此独立的「主页」「目录（章节选择）」「正文」页面，且正文页面之间
   是真实的不同 URL（利于分享、SEO、书签、GitHub Pages 无路由问题）。
4. **无 JS 也要能读**：默认（中文单栏）内容在禁用 JS 时依然完整可读，控制条可缺失但正文不可缺失。
5. **目标读者是中文读者**：默认语言中文；中文排版必须遵守：正文首行缩进 2em、中文标点挤压
   （`text-spacing-trim`）、`line-break: strict`、行高 1.7~1.9、段间距 0、两端对齐（`text-align: justify`）。
6. 不得出现广告、登录、弹窗、自动播放、无限滚动。

## 必须实现的功能

**三个页面**
- 主页 `index.html`：书名/副题、作品与译本简介、开始阅读（跳第 1 章）、继续阅读（有进度时跳上次位置）、
  进入目录、阅读设置简介、**GitHub 仓库地址**、**bug report / 建议的联系方式**、许可与免责声明。
- 目录 `toc.html`：32 章列表（中文「第X章」+ 英文「Chapter N」+ 该章地点/日期），带已读/当前章标记；
  窄屏单列、宽屏多列；顶部有返回主页。
- 正文 `read/chapter-NN.html`：阅读页。必须有：返回主页、返回目录、上一章、下一章、
  章节标题、阅读进度、设置面板、目录抽屉（快速跳到任意章）。

**阅读页交互**
- 顶栏 / 底栏：可点击中部或按 Esc 显示/隐藏；隐藏后全屏沉浸阅读（底栏保留极简进度）。
- 点击区域：正文区左 1/3 = 上一屏/上一页，右 1/3 = 下一屏/下一页，中间 1/3 = 显隐菜单。
- 翻页模式两种，可切换并记忆：①上下滚动（默认）②左右翻页（分页，CSS 多列或分屏实现，
  到本章末页再按下一页自动进入下一章）。分页模式要处理「高于一页的图片/表格」不炸版。
- 上/下一章按钮在滚动到章末时也要自然出现（章末导航块，含「返回目录」）。
- 键盘：`←/→` 翻页或翻章、`↑/↓` 滚动、`Esc` 关菜单/抽屉、`t` 切主题、`d` 切语言模式。
- 进度记忆（localStorage）：记录 章号、滚动位置/页码、字号、主题、语言模式、翻页模式；
  再次进入该章恢复位置，主页显示「继续阅读 第X章」。
- 底栏三段式：左「上一章」、中「上一屏 · 进度 · 下一屏」、右「下一章」。两侧是真实章链接
  （首章没有上一章、末章没有下一章时用 `hidden` 收起），中间的翻屏按钮保留；
  窄屏要收紧内边距与字号，保证这些元素不挤压、不横向溢出。
- 指针在插图/终端面板这类**内部可滚动区块**上滚动时先滚它自己，到顶或到底后再接续滚正文栏；
  宽屏分栏且整页还在顶部时，正文内向下滚要**先把整页滚下去**，让章标题区随滚动隐藏。
- 正文栏的 `scroll` 事件请在 `document` 捕获阶段集中接收（无头/无帧环境里挂在栏元素上偶发收不到）。

**双语对照（本项目重点）**
- 三种语言模式：`中文`（默认）、`English`、`对照`。
- 对照模式：**宽屏左右分栏**（左＝英文原文，右＝中文译文，两栏各自独立滚动，「同步滚动」开关默认开启）；
  **窄屏分为两个标签页**（中文 / English 切换，标签条固定在正文上方）。
- 分栏/标签页的切换必须**按可用空间动态判断**，而不是简单按某个固定像素断点死切：
  以「每栏至少能放 ≈30 个中文字」为判据（可用 `ResizeObserver` + CSS 容器查询/媒体查询、
  同时考虑视口宽高比），窗口从宽变窄时平滑降级为标签页，变宽时自动恢复分栏。
  **判据要用页面可用空间（视口宽 − 页边距、再夹到分栏容器最大宽；视口高 − 顶栏 − 底栏），
  不要用正文容器当下的实测尺寸**——它在标签页/单栏下被 `max-width` 限宽，会让状态卡在窄屏一侧。
- 中英段落**不做逐段对齐**（原文与译文段落结构一致但长度差异大，不做强制对齐），
  同步滚动按「滚动百分比」即可；对栏写入请同步完成，不要推迟到 `requestAnimationFrame`
  （无帧环境里 rAF 可能迟迟不执行）。

**中文段式**：阅读设置里给中文栏两档段式——`常规段落`（首行缩进 2em、段间距 0）与
`一句一行`（按句断开、一句一行、取消首行缩进、句间留白，接近中文网文阅读习惯）。
这档必须保留原有的内联样式（说话人颜色、加粗、虚构语言字体），并且可逆（切回常规即还原）。

**阅读设置面板**：字号（5 档）、行距（3 档）、中文段式（2 档）、主题（羊皮纸 / 浅色 / 深色 / 夜间护眼，至少 3 种）、
字体（宋体/黑体两套系统字体栈）、翻页模式、语言模式、同步滚动开关（默认开启）。
各控件用统一的胶囊按钮与等距排布，避免堆叠挤压；面板要在 1440×900 的窗口里尽量一屏放完
（最后一组控件不能落到首屏之外）。

**无障碍与健壮性**：键盘可达（focus 可见）、`prefers-reduced-motion`、`prefers-color-scheme`、
打印样式（打印时隐藏所有控件、只打印当前显示的语言、去底纹）、章节标题用正确的标题层级、
`aria-label`/`aria-expanded`/`role` 到位、图片有 alt。

## 视觉语言参考（不强制，可自行提升）

现有单页版的基调：《雪月》是暖色纸张 + 深蓝终端面板的太阳朋克。可用：
米白/羊皮纸底（#f6f4ef）、墨色正文、暖金强调（#8a6d3b）、终端面板深蓝（#0a0e27 / #9cc2ff）。
插图 SVG 自带深色底色，容器请给深色底与圆角，避免在浅色页面上出现刺眼白边。
虚构语言（Dzegoban）用衬线/手写感字体栈单独排版（`.dz-script`）。

## 集成契约（构建脚本按此填充，必须原样保留占位符）

构建产物目录结构：

```
index.html
toc.html
read/chapter-01.html …… read/chapter-32.html
assets/style.css
assets/reader.js
assets/images/*.svg
```

构建脚本会对模板做**纯字符串替换**，把 `{{NAME}}` 换成实际内容。模板里必须原样保留下列占位符
（同一占位符可以在模板中出现多次；大小写、花括号数量必须完全一致）：

| 占位符 | 含义 |
| --- | --- |
| `{{ASSET_PREFIX}}` | 相对本页的资源前缀，如 `assets/` 或 `../assets/`。写链接时必须形如 `{{ASSET_PREFIX}}style.css` |
| `{{HOME_HREF}}` `{{TOC_HREF}}` | 主页/目录的相对链接 |
| `{{PREV_HREF}}` `{{NEXT_HREF}}` | 上一章/下一章链接（首章上一章指向 `toc.html`，末章下一章指向 `toc.html`） |
| `{{PREV_LABEL}}` `{{NEXT_LABEL}}` | 上一章/下一章的按钮文案（如「上一章 · 第X章」） |
| `{{REPO_URL}}` | `https://github.com/0xVanfer/snowmoon-zh-cn` |
| `{{SITE_URL}}` | `https://0xvanfer.github.io/snowmoon-zh-cn/` |
| `{{UPSTREAM_URL}}` | `https://vitalik.eth.limo/snowmoon/` |
| `{{CONTACT_EMAIL}}` | `vanfer@vanfer.tech` |
| `{{CHAPTER_COUNT}}` `{{TOTAL_WORDS}}` `{{BUILD_DATE}}` | 32 / 约 14.6 万 / 构建日期 |
| `{{CHAPTER_NO}}` | 章节号 1..32 |
| `{{CHAPTER_TITLE_ZH}}` `{{CHAPTER_TITLE_EN}}` | 「第一章」/「Chapter 1」 |
| `{{CHAPTER_DATELINE_ZH}}` `{{CHAPTER_DATELINE_EN}}` | 「梅尔丹，维里迪亚 · 3724年雪月3日」/ 英文 |
| `{{TOC_ITEMS}}` | 目录条目，展开为一串 `<li>…</li>`；模板必须把它放在 `<ol>`/`<ul>` 内 |
| `{{CONTENT_ZH}}` `{{CONTENT_EN}}` | 该章中文/英文正文 HTML，各出现**恰好一次** |

正文内容里，`{{CONTENT_ZH}}` 所在元素必须带 `data-lang="zh"`，`{{CONTENT_EN}}` 所在元素必须带
`data-lang="en"`（其余结构你自由发挥，两者的父/子关系由你决定，但要能被 CSS/JS 选中）。

正文里会用到的元素/类（构建脚本产出，请你给它们写样式）：

```html
<h2 class="chapter-title">第一章</h2>
<p class="dateline">梅尔丹，维里迪亚 · 3724年雪月3日</p>
<p>正文段落（首行缩进 2em）</p>
<p class="dialog railed" style="color:#e08a5a">&#8220;对白&#8221;</p>   <!-- 颜色代表说话人 -->
<hr class="rule">
<p class="scene-break">场景切换标记</p>
<blockquote>引用</blockquote>
<ul><li>列表</li></ul>
<figure class="fig"><img src="{{ASSET_PREFIX}}images/chapter-01-fig-01.svg" alt="插图标题"></figure>
<div class="device-view wide-device-view"><table>…模拟终端面板…</table></div>
<div class="device-view device-view-left">…</div>
<span class="dz-script">Dzegoban 罗马字</span>
<sup>2</sup> <sub>x</sub> <b>粗</b> <em>斜</em> <code>等宽</code>
```

面板内部还会有 `<input type="range" style="width:100%">`、`<button>`、内联 `style="display: flex;
justify-content: space-between; width:100%"` 的刻度行（**各刻度是独立 `<span>`，必须按 flex 项正确分布**）、
`<span style="color:#rrggbb">` 上色文字、以及 `<span style="font-size:200%">🙁<sup><sup>2</sup></sup></span>`
这类表情刻度。插图是外部 SVG（`<img>` 引用），宽屏下不要超过正文栏宽。

## 交付方式

- 每次只交付一个文件，用**一个** Markdown 代码块包裹文件完整内容，代码块 info string 写成语言名
  （`css` / `javascript` / `html` / `markdown`），代码块前后可以各写不超过 5 行的说明。
- 不要省略任何代码（禁止 `/* 其余同上 */`、`...`）；文件要能直接落盘使用。
- CSS 用 CSS 变量组织设计令牌；不要用 `!important` 堆砌；选择器保持可维护。

## DOM 契约（阅读页；HTML 模板与 JS 必须同时遵守这些 id/属性）

构建脚本只做占位符替换，因此 **class/id 由你设计**，但下列 **id 与 data 属性是固定接口**，
`style.css`、`reader.js`、`chapter.html` 三份产物必须一致使用：

```html
<html lang="zh-CN" data-theme="paper" data-lang-mode="zh" data-dual-layout="columns"
      data-active-pane="zh" data-page-mode="scroll" data-ui="visible" data-font="serif"
      style="--reader-size:20px; --reader-leading:1.8">
<body class="reader-page">
  <!-- 顶栏；data-ui="hidden" 时收起（但保留一条细进度线） -->
  <header id="topbar"> … 主页链接 / 章名 / 目录链接 … </header>
  <!-- 阅读百分比进度条，宽度由 JS 写 style.width -->
  <div id="progress-bar"></div>

  <main id="reader-main">
    <section data-lang="zh" id="pane-zh">{{CONTENT_ZH}}</section>
    <section data-lang="en" id="pane-en">{{CONTENT_EN}}</section>
  </main>

  <!-- 章末导航：上一章 / 目录 / 下一章 -->
  <nav id="chapter-nav">
    <a id="nav-prev" href="{{PREV_HREF}}">{{PREV_LABEL}}</a>
    <a id="nav-toc" href="{{TOC_HREF}}">目录</a>
    <a id="nav-next" href="{{NEXT_HREF}}">{{NEXT_LABEL}}</a>
  </nav>

  <!-- 底栏：三段式 —— 上一章 / 翻屏与进度 / 下一章 -->
  <footer id="bottombar">
    <a id="btn-prev-chapter" href="{{PREV_CH_HREF}}"{{PREV_CH_HIDDEN}}>上一章</a>
    <button id="btn-prev-screen" type="button">上一屏</button>
    <span id="page-indicator">1 / 1</span>
    <button id="btn-next-screen" type="button">下一屏</button>
    <a id="btn-next-chapter" href="{{NEXT_CH_HREF}}"{{NEXT_CH_HIDDEN}}>下一章</a>
  </footer>

  <!-- 窄屏双标签页用的切换条（只在 data-dual-layout="tabs" 且 data-lang-mode="dual" 时显示） -->
  <div id="lang-tabs" role="tablist">
    <button type="button" role="tab" data-tab-lang="zh">中文</button>
    <button type="button" role="tab" data-tab-lang="en">English</button>
  </div>

  <!-- 目录抽屉 -->
  <aside id="drawer" role="dialog" aria-modal="true" aria-label="目录">
    <button id="drawer-close" type="button">关闭</button>
    <ol id="drawer-toc">{{TOC_ITEMS}}</ol>
  </aside>

  <!-- 设置面板：每个控件用 data-set + data-value 标识，JS 只认这两个属性 -->
  <aside id="settings-panel" role="dialog" aria-modal="true" aria-label="阅读设置">
    <button id="settings-close" type="button">关闭</button>
    <!-- data-set="size"    data-value="16|18|20|22|24"
         data-set="leading" data-value="1.7|1.8|1.9"
         data-set="font"    data-value="serif|sans"
         data-set="theme"   data-value="paper|light|dark|night"
         data-set="mode"    data-value="scroll|paged"
         data-set="lang"    data-value="zh|en|dual"
         data-set="sync"    data-value="on|off"   -->
  </aside>
  <div id="scrim"></div>
</body>
```

- 打开顶栏控制（目录抽屉 / 设置面板）的按钮请分别给 `id="btn-drawer"`、`id="btn-settings"`、
  `id="btn-settings-inline"`（可选，首页用），并维护 `aria-expanded`。
- 语言模式按钮：`id="btn-lang"`（可选，循环 zh→en→dual，文案反映当前模式）。
- `localStorage` 键名固定为 `snowmoon.reader.v1`，结构见设计说明；
  键名之外的设置项（字号/行距/字体/主题/翻页模式/语言/同步）都必须落在这个对象里。
- 主页若有「继续阅读」，元素 id 用 `id="continue-reading"`，JS 负责填充链接与文案；
  无进度时它应隐藏而不是报错。
