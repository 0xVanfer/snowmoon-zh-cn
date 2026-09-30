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
| 无法用当前模型直接看渲染结果 | 主模型未声明图像输入 | 视觉复核交给声明支持图像的子代理（`minimax-cn / MiniMax-M3.1-Flash-Preview`），用 `read_image` 看「原图 \| 中文版」并排预览 |
| 并行 workflow 16 个 agent 全部失败 | 触发上游速率限制 | 改为每批 8 个、串行提交；失败的批次原样重跑即可 |
| 子代理启动报 `subagent limit reached (active child limit: 8)` | harness 并发上限 | 分批派发，等通知再补；长任务用 `send_message` 续跑而不是重开 |
| 并行改稿与规范化脚本互相覆盖文件 | 多个 subagent 同时写不同译文，规范化脚本又全量重写 | 规范化只在没有改稿任务运行时执行；每次写盘前用「按 id 替换 + 立即自检」的方式，避免整文件重写 |
| 投票/拖动条的刻度 `-5 / 0 / 5` 全挤在左边，位置与数字对不上 | 刻度行是 `display:flex; justify-content:space-between`，三个 `<span>` 没有内联样式；抽取时把无样式 `span` 拍平，整个容器压成一条文本节点，flex 只剩一个项，分位与「按项分布」全部失效 | `extract.py` 对带 `display:flex\|grid`／`justify-content` 的容器改走 `render_layout_items()`：每个直接子元素各自保留标签、各自成一条片段，空元素也保留（否则项数不对）。同类问题用 `qa_site.py` 的「布局容器子项与原文逐项比对」兜底 |
| 修结构会牵连全部译文 id | 片段编号按章连续自增，中间插入片段会让后续 id 全部位移 | 容器内第一条片段占用那个自增号，其余用 `基准id#2`、`#3`…；容器外编号完全不变。对无文字的刻度/表情，拆出来的片段按「旧译文与旧原文同形」自动沿用原文，无需重译，日志会逐条打印便于核对 |
| 让模型设计前端却拼不起来 | 模型各自产出 HTML/CSS/JS，互相不知道对方的 id 与 class | 在任务书里先钉死「集成契约」：占位符表、`id`/`data-*` 接口、`localStorage` 键名与结构；构建脚本只做占位符替换。三份产物按同一契约生成，落盘后即可组装 |
| 契约钉死后仍然拼不上 | 契约只写了「有哪些 id」，没写「同一个函数/属性的语义」：`qs()` 一边按裸 id 实现、一边按选择器调用；`sync` 一边存布尔、一边只认 `'on'`；CSS 一边用 `html.js`、一边用 `data-js`；两栏外多套了一层 `<div class="reader">` 让 grid 落空 | 契约里补上「函数签名/取值类型/DOM 层级」；分多次生成的成品必须逐条对接口，`probe_site.py` 的交互断言就是为这类「不报错但不生效」准备的（第 2 段整段空转时页面既不报错也看不出异常） |
| 分页模式下「章末导航跑到正文中间」 | 定高多列容器里给正文块写了 `height: 100%`，正好等于「一列高」，正文只占第 1 列、其余溢出到后续列，紧跟其后的导航被挤到第 2 列 | 探针加一条断言：章末导航的列号必须 ≥ 总页数 − 1；修法是把正文块改回 `height: auto` |
| 视觉复核报的「问题」有一半是采集假象 | headless 的 `--screenshot` 拍「滚动后的页面」会输出空白/错位的图；`--window-size` 在 macOS 上最小宽度约 500px，窄屏截图其实是 500px 版面被裁 | 截图脚本改成「要露出某元素就把视口开高」而不是滚动；窄屏改用「手机框 iframe」（iframe 内是独立 CSS 视口）拿到真 390px；交互态先注入动作脚本再截图；滚动类状态只跑几何探针、不出截图 |
| 几何探针偶发假失败 | headless 的 `--dump-dom` 下 `ResizeObserver` 首次回调不保证送达，虚拟时间与图片解码也有抖动 | 探针先制造一次尺寸变化逼出 RO，再按「就绪条件」轮询（如等进度落盘），最后对失败预设重跑一次；失败信息里带上进度条/指示器便于判断是真 bug 还是抖动 |
| 有图注的 flex 刻度行在被拍平时会「粘」成一个数 | 元素之间原有的空白文本节点被当成纯排版空白丢掉 | 布局容器的元素间空白保留一个空格：flex 会忽略它，Markdown 等非 flex 场景却需要它分隔（否则 `-5 0 5` 会变成 `-505`） |
| 无头环境里「栏内滚动」的 scroll 事件常常收不到 | 嵌套滚动容器（正文栏）的 scroll 事件由渲染帧派发，`--virtual-time-budget` 下帧可能一直不产生，事件留在队列里；页面的滚动逻辑看着像没生效（同步滚动探针改前 5 次里假失败 3 次） | 动作脚本在设置 `scrollTop` 后补派发一次 `scroll` 事件；页面侧把栏内 scroll 监听集中到 `document` 捕获阶段，并把「同步对栏」从 `requestAnimationFrame` 改成同步写入 |
| 分段生成的前端脚本里用了「上一段的作用域」 | 第 1 段自定义了局部 `qs()` / `qsa()`，第 2、3 段只有 `S.qs` / `S.qsa`；新加的代码照抄裸调用，整个第 2 段（分栏判定、点击翻页、同步滚动）当场抛 `ReferenceError`，而页面不报错、只是静默失效 | 跨段一律用 `S.qs` / `S.qsa`；这类「静默失效」只能靠探针的交互断言发现，`--dump-dom` 里看不到异常时改用「本地 HTTP 服务 + `window.onerror`」把真实错误打出来 |
| 用 `#reader-main` 的实测尺寸判断「能不能分栏」 | 该元素在标签页/单栏下被 `max-width: 38em` 限宽，量到的是当前布局而不是可用空间，于是窗口一旦变窄掉进标签页就再也回不到分栏 | 分栏/标签页这类「响应式状态机」必须用**与当前状态无关**的输入（视口可用宽高），两个方向用同一套输入，否则迟滞会退化成单向棘轮；判据重算也别只挂在 `ResizeObserver` 上，`window.resize` 一起接（缩放/iframe 变宽/一次 RO 回调丢失都可能漏掉），并补一条「先窄后宽必须恢复分栏」的回归预设 |
| 已提交的产物比规则更早存在 | `.gitignore` 里写着 `__pycache__/`、`*.pyc`，但两个 `.pyc` 和 172 个可再生的中间产物（模型缓存、译文备份、截图预览）早已被提交，规则对它们完全无效 | 补规则的同时用 `git rm -r --cached` 把已跟踪的可再生产物移出索引（本地文件保留）；「改了 .gitignore 却还一直有脏文件」先怀疑「是不是早就跟踪了」 |
| 子代理/工作流的 `provider` / `model` 覆盖在本环境不生效 | 用 workflow 的 `agent(..., {provider, model})` 指定视觉模型时全部返回 `null`（失败被吞掉），看着像「模型不可用」；旧记录里的 `MiniMax-M3` 也不是当前模型 id | 需要图像复核时直接依赖运行时的默认子代理模型（本环境为 `minimax-cn / MiniMax-M3.1-Flash-Preview`），不要依赖覆盖参数；`null` 先归因到「覆盖失效」而不是「模型不行」 |

## 4.5 移动端触摸

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 手机上「拖拽极其僵硬，无法正常滚动」 | 终端面板 `.device-view` 带 `overscroll-behavior: contain`（当初是为了让桌面滚轮由脚本接管），而面板竖向上没有溢出：触摸拖拽落在面板上时既不滚面板、也不会接续滚正文，**手势被整段吃掉**；这片区域点按又被 `excluded()` 排除，等于死区 | 面板改回 `overscroll-behavior: auto`，把 scroll chaining 交还浏览器，滚轮接管逻辑照旧。教训：`overscroll-behavior: contain` 同时作用于滚轮与触摸，只为其中一种输入加的限制必须把另一种也验一遍；「桌面能滚」不等于「手机能滚」 |
| 翻页模式在手机上完全拖不动 | 分页模式只有「点左/右三分之一」与键盘 `←/→` 两种入口，移动端本能的横向滑动没有任何处理器 | 补 `touchstart`/`touchend` 横向滑动翻页（阈值 48px，且横向位移须大于纵向 1.2 倍才判定），落在面板／链接／按钮等交互区时不接管 |
| 无头环境里怎么验证「手机能不能拖」 | `--dump-dom` 的几何探针测不到浏览器自己怎么处理手势 | 用 CDP（`--remote-debugging-port` + 手写 WebSocket 客户端）设 `Emulation.setDeviceMetricsOverride(mobile)` 后发 `Input.dispatchTouchEvent`，直接量 `window.scrollY` 位移；`Input.synthesizeScrollGesture` 在 headless 里没有惯性，测不出 momentum 相关现象 |
| 在受沙箱约束的 harness 里启动 CDP 版 Chrome | `--headless=new` 起完就 `GPU process exited unexpectedly: exit_code=6` → `GPU process isn't usable. Goodbye.`，`/json/version` 短暂可用后进程消失 | 加 `--no-sandbox --in-process-gpu --disable-crash-reporter` 即可；`probe_site.py` / `render_site_previews.py` 用的 `--dump-dom` / `--screenshot` 模式不受影响，无需改动 |

## 5. 流程经验

- **结构与文字分离**是整条流水线能自动校验的前提：翻译只改 `segments[].text`，标签序列由脚本逐条比对，任何结构漂移都会在 `validate_translation.py` 暴露。
- **复核与改稿分离**：复核者只写 `reviews/*.json`，改稿者负责采纳/驳回并写 `applied*.json`，主进程只处理跨章与术语表层的问题。这样每一处改动都可追溯（谁提的、谁改的、理由是什么）。
- **多视角复核**（忠实度 / 中文语感 / 一致性）比让一个 agent「通读一遍」有效得多：本轮共 96 份复核报告、约 700 条意见，其中一致性视角几乎全部是跨章对照才能发现的（术语、编号、量词、称谓）。
- 复核意见也会错：改稿者驳回了约 5% 的条目（多为风格偏好、理解偏差、或落实对象其实是术语表而非译文），每条都写明理由。
- **视觉类改动先落几何断言再谈截图**：按钮是不是被挤压/换行/重叠，可以用探针量（容器内不裁切、文字不换行、相邻间距 ≥3px），比人眼扫截图更稳定；截图留给「观感」，探针留给「回归」。
