#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""用 headless Chrome 的 `--dump-dom` 给阅读站点做**几何探针**：不需要看图，直接读布局数值。

在临时副本里注入一段探针脚本（测得结果写进 `<pre id="probe-json">`），
再按预设逐项断言：双语是分栏还是标签页、隐藏栏是否真的不占位、投票刻度行是否按 flex 分位、
分页模式页数与位移、进度与「继续阅读」是否生效等。

用法: python3 pipeline/probe_site.py
"""
from __future__ import annotations

import html as htmlmod
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_site_previews import (ACTIONS, CHROME, FRAMED, PRESETS, stage,  # noqa: E402
                                  window_args)

PROBE = """
<script>
window.addEventListener('load', function(){
  setTimeout(function(){
    // headless 的 --dump-dom 模式下 ResizeObserver 首次回调不保证送达，
    // 这里制造一次真实尺寸变化（改一下再改回来）把它逼出来，让分栏判定确定性地跑一遍。
    try {
      window.dispatchEvent(new Event('resize'));
      var __m = document.getElementById('reader-main');
      if (__m) {
        var __w = __m.style.width;
        __m.style.width = 'calc(100% - 81px)';
        void __m.getBoundingClientRect();
        __m.style.width = __w;
      }
    } catch (error) {}
    try { __ACTION__ } catch (error) { window.__actionError = String(error); }
    var __ready = function () {
    function box(sel){var e=document.querySelector(sel); if(!e) return null;
      var r=e.getBoundingClientRect(), c=getComputedStyle(e);
      return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height),
              display:c.display, visibility:c.visibility, opacity:c.opacity};}
    // 按钮排布体检：是否被裁切、文字换行/溢出、互相重叠，以及相邻间距
    function fit(bar, selector) {
      if (!bar) return null;
      var br = bar.getBoundingClientRect();
      if (!br.width) return null;
      var els = Array.prototype.filter.call(bar.querySelectorAll(selector), function (e) {
        var r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
      var rects = els.map(function (e) { return e.getBoundingClientRect(); });
      // 只在「同一行」（纵向有重叠）的相邻控件之间比较重叠与间距，换行的不算
      var gaps = [], overlaps = 0;
      for (var i = 1; i < rects.length; i++) {
        var a = rects[i - 1], b = rects[i];
        if (b.top >= a.bottom - 1 || a.top >= b.bottom - 1) continue;
        if (b.left < a.right - 1) overlaps++;
        gaps.push(Math.round(b.left - a.right));
      }
      return {
        count: els.length,
        clipped: rects.filter(function (r) { return r.left < br.left - 1 || r.right > br.right + 1; }).length,
        wrapped: els.filter(function (e) {
          return e.scrollWidth > e.clientWidth + 2 || e.scrollHeight > e.clientHeight + 2;
        }).length,
        overlaps: overlaps,
        minGap: gaps.length ? Math.min.apply(null, gaps) : null
      };
    }
    function vis(sel){return Array.prototype.filter.call(document.querySelectorAll(sel), function(e){
      var r=e.getBoundingClientRect(); return r.width>1 && r.height>1;}).map(function(e){
      var r=e.getBoundingClientRect(); return [Math.round(r.x),Math.round(r.y),Math.round(r.width)];});}
    var f=document.getElementById('flow-zh'), fe=document.getElementById('flow-en');
    function flow(el){return el?{sw:el.scrollWidth, cw:el.clientWidth, sh:el.scrollHeight, ch:el.clientHeight,
                                 tf:getComputedStyle(el).transform}:null;}
    var out={
      page: document.body.dataset.page || '', chapter: document.body.dataset.chapter || '',
      theme: document.documentElement.dataset.theme, lang: document.documentElement.dataset.langMode,
      dual: document.documentElement.dataset.dualLayout, activePane: document.documentElement.dataset.activePane,
      mode: document.documentElement.dataset.pageMode, ui: document.documentElement.dataset.ui,
      js: document.documentElement.dataset.js || '', font: document.documentElement.dataset.font,
      paneZh: box('#pane-zh'), paneEn: box('#pane-en'), langTabs: box('#lang-tabs'),
      main: box('#reader-main'), topbar: box('#topbar'),
      progress: (document.getElementById('progress-bar')||{}).style ? document.getElementById('progress-bar').style.width : '',
      indicator: (document.getElementById('page-indicator')||{}).textContent || '',
      flowZh: flow(f), flowEn: flow(fe),
      voteSpans: vis('div[style*="justify-content"] > span'),
      voteRows: vis('div[style*="justify-content"]'),
      figures: vis('figure.fig img'), ranges: vis('input[type=range]'),
      panels: vis('.device-view'),
      continueEl: (function(){var a=document.getElementById('continue-reading');
        return a?{hidden:a.hidden, href:a.getAttribute('href'), text:a.textContent.trim()}:null;})(),
      tocCurrent: document.querySelectorAll('#toc-list .is-current').length,
      tocRead: document.querySelectorAll('#toc-list .is-read').length,
      tocProgress: (document.getElementById('toc-progress')||{}).textContent || '',
      docW: document.documentElement.scrollWidth, clientW: document.documentElement.clientWidth,
      viewH: document.documentElement.clientHeight,
      viewHNominal: __VIEW_H__,
      bodyOverflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
      actionError: window.__actionError || '',
      scrollY: Math.round(window.scrollY || document.documentElement.scrollTop || 0),
      settingsBox: box('#settings-panel'), drawerBox: box('#drawer'),
      settingsLast: box('#settings-panel .setting-group:last-of-type'),
      btnSettingsExpanded: (document.getElementById('btn-settings')||{}).getAttribute
        ? document.getElementById('btn-settings').getAttribute('aria-expanded') : null,
      readerSize: getComputedStyle(document.documentElement).getPropertyValue('--reader-size').trim(),
      syncZh: Math.round((document.getElementById('pane-zh')||{scrollTop:0}).scrollTop),
      syncEn: Math.round((document.getElementById('pane-en')||{scrollTop:0}).scrollTop),
      stored: (function(){try{var s=JSON.parse(localStorage.getItem('snowmoon.reader.v1')||'{}');
        return s.chapters||{};}catch(e){return null;}})(),
      syncAttr: document.documentElement.getAttribute('data-sync'),
      topbarOverflow: (function () {
        var w = document.documentElement.clientWidth;
        return Array.prototype.filter.call(
          document.querySelectorAll('#topbar a, #topbar button, #topbar span'),
          function (e) { var r = e.getBoundingClientRect(); return r.width > 0 && (r.right > w + 1 || r.left < -1); }
        ).map(function (e) {
          var r = e.getBoundingClientRect();
          return (e.textContent || '').trim().slice(0, 6) + '@' + Math.round(r.right) + '/' + w;
        });
      })(),
      heading: box('.chapter-heading'),
      navZh: box('#chapter-nav'), flowZhBox: box('#flow-zh'),
      bottomBarTop: (function () {
        var b = document.getElementById('bottombar');
        return b ? Math.round(b.getBoundingClientRect().top) : null;
      })(),
      lastContentBottom: (function () {
        var els = document.querySelectorAll('#pane-zh .chapter-content > *');
        if (!els.length) return null;
        return Math.round(els[els.length - 1].getBoundingClientRect().bottom);
      })(),
      siteHeader: (function () {
        var a = document.querySelector('.site-header .back-link') ||
                document.querySelector('.site-header .site-brand');
        if (!a) return null;
        var r = a.getBoundingClientRect(), c = getComputedStyle(a);
        return { w: Math.round(r.width), h: Math.round(r.height), y: Math.round(r.y),
                 color: c.color, bg: getComputedStyle(document.body).backgroundColor,
                 text: (a.textContent || '').trim().slice(0, 12) };
      })(),
      cssOverridesLoaded: Array.prototype.some.call(document.styleSheets, function (sheet) {
        return (sheet.href || '').indexOf('overrides.css') >= 0;
      }),
      // ---- 「网文分行」段式 ----
      gaps: document.querySelectorAll('#pane-zh .sentence-gap').length,
      gapDisplay: (function () {
        var g = document.querySelector('#pane-zh .sentence-gap');
        return g ? getComputedStyle(g).display : null;
      })(),
      paragraphIndent: (function () {
        var p = document.querySelector('#pane-zh .chapter-content p');
        return p ? getComputedStyle(p).textIndent : null;
      })(),
      paragraphAttr: document.documentElement.dataset.paragraph,
      // ---- 分栏时「正文内滚动先滚整页、章标题区随之隐藏」----
      docScrollTop: Math.round((document.scrollingElement || document.documentElement).scrollTop),
      docScrollMax: (function () {
        var d = document.scrollingElement || document.documentElement;
        return d.scrollHeight - d.clientHeight;
      })(),
      headingTop: (function () {
        var h = document.querySelector('.chapter-heading');
        return h ? Math.round(h.getBoundingClientRect().top) : null;
      })(),
      // ---- 底栏上一章 / 下一章 ----
      prevChapter: (function () {
        var a = document.getElementById('btn-prev-chapter');
        return a ? { hidden: a.hidden, href: a.getAttribute('href'), text: (a.textContent || '').trim(),
                     w: Math.round(a.getBoundingClientRect().width) } : null;
      })(),
      nextChapter: (function () {
        var a = document.getElementById('btn-next-chapter');
        return a ? { hidden: a.hidden, href: a.getAttribute('href'), text: (a.textContent || '').trim(),
                     w: Math.round(a.getBoundingClientRect().width) } : null;
      })(),
      barButtons: vis('#bottombar .reader-bar-button'),
      // 底栏中段应落在视口正中（某一侧章节按钮被 hidden 时也不能偏）
      barCenter: (function () {
        var g = document.querySelector('.reader-bottombar__group--flip');
        if (!g || !g.getBoundingClientRect().width) return null;
        var r = g.getBoundingClientRect();
        return Math.round((r.left + r.right) / 2 - document.documentElement.clientWidth / 2);
      })(),
      // 字号 5 档必须排在同一行
      sizeRows: (function () {
        var tops = {};
        Array.prototype.forEach.call(document.querySelectorAll('#settings-panel [data-set="size"]'), function (e) {
          tops[Math.round(e.getBoundingClientRect().top)] = 1;
        });
        return Object.keys(tops).length;
      })(),
      // 主页主 CTA 必须是实心强调色胶囊（不能被 `.reading-actions > a` 盖掉）
      ctaPrimary: (function () {
        var e = document.querySelector('.reading-actions .button-primary');
        if (!e) return null;
        var c = getComputedStyle(e);
        return { bg: c.backgroundColor, radius: c.borderRadius, color: c.color };
      })(),
      // 目录卡片标题的左缘：同一列里「当前章」不能因为强调条而错位
      tocTitleLefts: Array.prototype.map.call(
        document.querySelectorAll('#toc-list .chapter-title-zh'),
        function (e) { return Math.round(e.getBoundingClientRect().left); }),
      // 已读 / 当前章的状态标记仍要出现，其余卡片的空状态行不占位
      tocStatus: (function () {
        function s(n) {
          var el = document.querySelector('#toc-list li[data-chapter="' + n + '"] .chapter-status');
          if (!el) return null;
          var c = getComputedStyle(el);
          return { display: c.display, after: getComputedStyle(el, '::after').content };
        }
        return { read: s(1), normal: s(2), current: s(7) };
      })(),
      topbarFit: fit(document.getElementById('topbar'),
        '.reader-brand, .reader-control, #btn-lang, .reader-topbar__chapter'),
      barFit: fit(document.getElementById('bottombar'), '.reader-bar-button, #page-indicator'),
      settingsFit: fit(document.getElementById('settings-panel'), '.setting-options button'),
      // ---- 滚轮接管（由动作脚本写入）----
      wheel: window.__wheel || null
    };
    var pre=document.createElement('pre'); pre.id='probe-json';
    pre.textContent=JSON.stringify(out); document.body.appendChild(pre);
    try { if (window.parent && window.parent !== window) window.parent.postMessage({snowmoonProbe: out}, '*'); } catch (e) {}
    };
    var __tries = 0;
    (function __wait() {
      if (__tries++ < 30 && !(__WAIT_FOR__)) { setTimeout(__wait, 100); return; }
      setTimeout(__ready, __ACTION_WAIT__);
    })();
  }, 600);
});
</script>
"""


# 测量前的额外等待（毫秒）：图多的章节、需要等 rAF 的动作用更长的等待
ACTIONS_WAIT = {"read-sync-scroll": 1500, "read-progress-save": 1400,
                "read-wide-paged": 900, "read-paged-figures": 900,
                "read-wide-paged-next": 900, "read-narrow-tab-en": 600}


# 测量前轮询的「就绪条件」（按预设 id）：等异步结果（如进度落盘）出现再测量
WAIT_FOR = {
    "read-progress-save": (
        "(function () { try { var s = JSON.parse(localStorage.getItem('snowmoon.reader.v1') || '{}');"
        "var c = (s.chapters || {})[document.body.dataset.chapter] || {};"
        "return !!(c.zh && c.zh.y > 100); } catch (e) { return false; } })()"),
    # 手机框先 390px 再拉宽到 1600px：等它自己恢复分栏
    "read-dual-recover": "document.documentElement.dataset.dualLayout === 'columns'",
}

# 需要「先窄后宽」的预设：pid -> 拉宽后的 iframe 宽度（回归测试「窄屏样式卡住回不去分栏」）
FRAME_GROW = {"read-dual-recover": 1600}


FRAME_PROBE_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#20242b}
.phone{width:%dpx;height:%dpx;margin:20px auto;border:10px solid #11141a;border-radius:22px;
       overflow:hidden;background:#fff}
iframe{width:100%%;height:100%%;border:0;display:block}
pre{color:#9ab;font:12px/1.4 monospace;padding:8px}
</style></head><body><div class="phone"><iframe src="%s"></iframe></div>
<script>
window.addEventListener('message', function (event) {
  var data = event.data && event.data.snowmoonProbe;
  if (!data) return;
  var pre = document.getElementById('probe-json') || document.createElement('pre');
  pre.id = 'probe-json';
  pre.textContent = JSON.stringify(data);
  document.body.appendChild(pre);
});
</script></body></html>
"""


def probe(page: Path, w: int, h: int, action: str = "", wait: int = 250,
          frame: tuple[int, int] | None = None, wait_for: str = "true",
          grow: int | None = None) -> dict:
    raw = page.read_text(encoding="utf-8")
    script = (PROBE.replace("<script>", '<script id="probe-script">', 1)
              .replace("__ACTION__", action).replace("__ACTION_WAIT__", str(wait))
              .replace("__WAIT_FOR__", wait_for).replace("__VIEW_H__", str(h)))
    raw = re.sub(r'<script id="probe-script">.*?</script>', '', raw, flags=re.S)
    page.write_text(raw.replace("</body>", script + "</body>"), encoding="utf-8")
    target = page
    if frame:
        fw, fh = frame
        rel = page.relative_to(page.parents[len(page.parents) - 1]).as_posix()
        # 站点根目录下的相对路径（read/chapter-01.html 等）
        site_root = page.parent
        while site_root.name != "site":
            site_root = site_root.parent
        rel = page.relative_to(site_root).as_posix()
        target = site_root / "_probe_frame.html"
        html = FRAME_PROBE_HTML % (fw, fh, rel)
        if grow:
            # 「先窄后宽」：把手机框里的 iframe 拉宽，逼页面走一次 标签页 → 分栏 的判定
            html = html.replace("</body>", (
                "<script>setTimeout(function(){var f=document.querySelector('iframe');"
                "if(f)f.style.width='%dpx';},500);</script></body>" % grow))
        target.write_text(html, encoding="utf-8")
        w, h = 500, fh + 60
    # Chrome 打印完 DOM 后不会自己退出（和截图一样会挂住），所以把 stdout 写到文件里轮询。
    with tempfile.TemporaryDirectory() as prof:
        dom_p = Path(prof) / "dom.html"
        cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
               "--no-default-browser-check", "--disable-extensions", "--hide-scrollbars",
               f"--user-data-dir={prof}/p", *window_args(w, h),
               "--virtual-time-budget=9000", "--dump-dom", f"file://{target}"]
        with dom_p.open("wb") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.DEVNULL, start_new_session=True)
            deadline = time.time() + 45
            try:
                while time.time() < deadline:
                    if dom_p.exists() and b"probe-json" in dom_p.read_bytes()[-400000:]:
                        time.sleep(0.2)
                        break
                    if proc.poll() is not None:
                        break
                    time.sleep(0.2)
            finally:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                proc.wait(timeout=5)
        dom = dom_p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'<pre id="probe-json">(.*?)</pre>', dom, re.S)
    if not m:
        raise RuntimeError(f"探针没跑出来（DOM {len(dom)} 字节）")
    return json.loads(htmlmod.unescape(m.group(1)).replace("&nbsp;", " "))


def check(pid: str, d: dict) -> list[str]:
    """按预设断言；返回问题列表。"""
    bad: list[str] = []
    zh, en = d["paneZh"], d["paneEn"]
    vis_zh = bool(zh and zh["w"] > 1)
    vis_en = bool(en and en["w"] > 1)

    def need(cond, msg):
        if not cond:
            bad.append(msg)

    need(d["js"] == "1", "JS 没跑起来（html 上没有 data-js）")
    if pid.startswith("home"):
        need(d["page"] == "home", f"data-page 应为 home，实际 {d['page']}")
        c = d["continueEl"] or {}
        need(c.get("hidden") is False and str(c.get("href", "")).endswith("chapter-01.html"),
             f"「继续阅读」未按进度填充：{c}")
        cta = d.get("ctaPrimary") or {}
        need(cta.get("radius") == "999px",
             f"主页主 CTA 没并入胶囊圆角（.reading-actions > a 盖掉了 .button）：{cta}")
        need(cta.get("bg") == "rgb(128, 96, 45)",
             f"主页主 CTA 应为实心强调色（纸色主题 #80602d）：{cta}")
    if pid.startswith("toc"):
        need(d["page"] == "toc", f"data-page 应为 toc，实际 {d['page']}")
        h = d.get("siteHeader") or {}
        need(h.get("w", 0) > 20 and h.get("h", 0) > 8,
             f"目录页顶部导航没有渲染出内容：{h}")
        need(h.get("color") != h.get("bg"), f"目录页顶部导航文字与背景同色：{h}")
        need(d["tocCurrent"] == 1, f"目录页当前章标记数应为 1，实际 {d['tocCurrent']}")
        need("第7章" in d["tocProgress"] or "7" in d["tocProgress"],
             f"目录页进度文案未填充：{d['tocProgress']!r}")
        columns = 1 if pid.endswith("narrow") else 3
        need(len(set(d.get("tocTitleLefts") or [])) <= columns,
             f"目录卡片左对齐线不齐（当前章的强调条挤掉了内边距）：{sorted(set(d.get('tocTitleLefts') or []))}")
        st = d.get("tocStatus") or {}
        read, normal, current = st.get("read") or {}, st.get("normal") or {}, st.get("current") or {}
        need(read.get("display") == "block" and "已读" in str(read.get("after")),
             f"已读章的状态标记没显示：{read}")
        need(normal.get("display") == "none", f"未读且非当前章的卡片仍留着空状态行：{normal}")
        need(current.get("display") == "block" and "正在阅读" in str(current.get("after")),
             f"当前章的状态标记没显示：{current}")
    if pid.startswith("read"):
        need(d["page"] == "read", f"data-page 应为 read，实际 {d['page']}")
        if d["lang"] == "zh":
            need(vis_zh and not vis_en, f"中文模式应只显示中文栏（zh={vis_zh}, en={vis_en}）")
        if d["lang"] == "dual":
            need(d["dual"] in ("columns", "tabs"), f"data-dual-layout 未设置：{d['dual']}")
            if d["dual"] == "columns":
                need(vis_zh and vis_en, f"分栏时两栏都应可见（zh={vis_zh}, en={vis_en}）")
            else:
                need(vis_zh != vis_en, f"标签页模式只应显示一栏（zh={vis_zh}, en={vis_en}）")
                need(d["langTabs"]["w"] > 1, "标签页模式标签条应可见")
        if d["mode"] == "paged":
            need(vis_zh, "分页模式中文栏不可见")
            f = d["flowZh"] or {}
            cols = f.get("sw", 0) / max(1, f.get("cw", 1))
            need(cols > 1.4, f"分页模式没有分列（scrollWidth/clientWidth={cols:.2f}）")
            need("页" in d["indicator"], f"页码指示未更新：{d['indicator']!r}")
    if pid == "read-wide-dual":
        need(d["dual"] == "columns", f"1600x900 应为分栏，实际 {d['dual']}")
        need(en["x"] < zh["x"], "分栏时英文应在左、中文在右")
        need(abs(en["w"] - zh["w"]) <= 4 or abs(en["w"] - zh["w"]) <= 0.05 * max(en["w"], zh["w"]),
             f"两栏宽度不一致：{en['w']} vs {zh['w']}")
        need(d["langTabs"]["display"] == "none" or d["langTabs"]["w"] < 2, "分栏时应隐藏标签条")
    if pid in ("read-narrow-dual", "read-tablet-dual"):
        need(d["dual"] == "tabs", f"{pid} 应为标签页，实际 {d['dual']}")
        need(d["langTabs"]["w"] > 1, "标签条应可见")
    if pid == "read-longwide":
        need(d["dual"] == "columns", f"2200x780（宽扁）也应为分栏，实际 {d['dual']}")
    if pid == "vote-row":
        rows = d["voteRows"]
        need(len(rows) == 2, f"第 1 章应有 2 个投票刻度行可见，实际 {len(rows)}")
        spans = d["voteSpans"]
        need(len(spans) == 6, f"应有 6 个刻度项（2 行 × 3），实际 {len(spans)}")
        for i in range(0, len(spans) - 2, 3):
            left, mid, right = spans[i], spans[i + 1], spans[i + 2]
            row = rows[i // 3]
            need(left[0] - row[0] <= 8, f"最左刻度没贴左边：{left} vs 行 {row}")
            need(abs((right[0] + right[2]) - (row[0] + row[2])) <= 8,
                 f"最右刻度没贴右边：{right} vs 行 {row}")
            need(left[0] < mid[0] < right[0] and abs((mid[0] + mid[2] / 2) - (row[0] + row[2] / 2)) <= 12,
                 f"中间刻度不在正中：{mid} vs 行 {row}")
    if pid == "emoji-row":
        spans = d["voteSpans"]
        need(len(spans) == 5, f"第 7 章表情刻度应有 5 项，实际 {len(spans)}")
        if len(spans) == 5:
            xs = [s[0] for s in spans]
            need(xs == sorted(xs) and len(set(xs)) == 5, f"表情刻度位置异常：{xs}")
    if d.get("actionError"):
        bad.append(f"交互动作抛错：{d['actionError']}")
    if pid == "read-narrow-tab-en":
        need(d["activePane"] == "en", f"点 English 标签后 activePane 应为 en，实际 {d['activePane']}")
        need(vis_en and not vis_zh, f"切到 English 后只应显示英文栏（zh={vis_zh}, en={vis_en}）")
    if pid == "read-wide-paged-next":
        m = re.search(r"第\s*(\d+)\s*/\s*(\d+)", d["indicator"])
        need(bool(m) and int(m.group(1)) >= 2, f"翻页后页码指示应前进：{d['indicator']!r}")
        f = d["flowZh"] or {}
        need(f.get("tf", "none") not in ("none", ""), f"翻页后应有位移：transform={f.get('tf')!r}")
    if pid == "read-wide-settings":
        need(d["settingsBox"] and d["settingsBox"]["w"] > 100,
             f"点「阅读设置」后面板未显示：{d['settingsBox']}")
        need(d["btnSettingsExpanded"] == "true", f"aria-expanded 未置 true：{d['btnSettingsExpanded']}")
        last = d.get("settingsLast") or {}
        need(last.get("y", 0) + last.get("h", 0) <= d["viewHNominal"] - 2,
             f"设置面板最后一组控件超出首屏（底 {last.get('y', 0) + last.get('h', 0)}"
             f" > 视口高 {d['viewHNominal']}）")
    if pid in ("read-paged-figures", "read-wide-paged"):
        f = d["flowZh"] or {}
        need(f.get("sh", 0) <= f.get("ch", 0) + 12,
             f"分页模式下正文纵向溢出（scrollHeight {f.get('sh')} > clientHeight {f.get('ch')}）")
        # 章末导航必须落在最后一列（分页模式），不能出现在正文中间
        m = re.search(r"第\s*(\d+)\s*/\s*(\d+)", d["indicator"])
        nav, flow = d.get("navZh"), d.get("flowZhBox")
        if m and nav and flow and int(m.group(2)) > 2:
            step = flow["w"] + 32
            col = round((nav["x"] - flow["x"]) / step)
            need(col >= int(m.group(2)) - 2,
                 f"章末导航没在最后一页：在第 {col + 1} 列 / 共 {m.group(2)} 页（nav x={nav['x']}, flow x={flow['x']}）")
    if pid == "read-sync-scroll":
        need(d["syncEn"] > 100, f"开启同步滚动后英文栏未跟随（en.scrollTop={d['syncEn']}）")
        a, b = d["syncZh"], d["syncEn"]
        need(abs(a - b) < max(200, 0.35 * max(a, b)),
             f"同步滚动比例偏差过大：zh={a} en={b}")
    need(d.get("cssOverridesLoaded"), "overrides.css 没被加载（集成修正未生效）")
    # 按钮排布体检：不裁切、不换行、不重叠、相邻间距不小于 3px
    for label, key in (("顶栏", "topbarFit"), ("底栏", "barFit"), ("设置面板", "settingsFit")):
        f = d.get(key)
        if not f or not f.get("count"):
            continue
        need(not f.get("clipped"), f"{label}有控件超出容器边界：{f}")
        need(not f.get("wrapped"), f"{label}有控件文字被裁切或换行：{f}")
        need(not f.get("overlaps"), f"{label}控件互相重叠：{f}")
        need(f.get("minGap") is None or f["minGap"] >= 3, f"{label}控件间距过小（{f.get('minGap')}px）：{f}")
    if d["topbarOverflow"]:
        bad.append(f"顶栏在 {d['clientW']}px 下横向溢出：{d['topbarOverflow']}")
    if pid == "read-bottom":
        need(d["lastContentBottom"] is not None and d["bottomBarTop"] is not None
             and d["lastContentBottom"] <= d["bottomBarTop"] + 2,
             f"滚到文档末尾后正文最后一块被底栏压住：正文底 {d['lastContentBottom']} > 底栏顶 {d['bottomBarTop']}")
    if pid == "read-wide-zh":
        need(d["gaps"] == 0, f"默认段式不应出现断句标记，实际 {d['gaps']} 个")
    if pid == "read-webnovel-zh":
        need(d["paragraphAttr"] == "webnovel", f"段式属性未生效：{d['paragraphAttr']!r}")
        need(d["gaps"] > 20, f"「一句一行」没有断句：.sentence-gap={d['gaps']}")
        need(d["gapDisplay"] == "block", f"断句标记没有换行：display={d['gapDisplay']!r}")
        need(d["paragraphIndent"] in ("0px", "0"), f"「一句一行」应取消首行缩进，实际 {d['paragraphIndent']!r}")
    if pid in ("read-wide-zh", "read-wide-dual", "read-last-chapter"):
        p, n = d.get("prevChapter") or {}, d.get("nextChapter") or {}
        if pid == "read-last-chapter":
            need(p.get("hidden") is False and str(p.get("href", "")).endswith("chapter-31.html"),
                 f"末章应有指向第 31 章的上一章按钮：{p}")
            need(n.get("hidden") is True, f"末章不应有下一章按钮：{n}")
        else:
            need(p.get("hidden") is True, f"第 1 章不应有上一章按钮：{p}")
            need(n.get("hidden") is False and str(n.get("href", "")).endswith("chapter-02.html"),
                 f"第 1 章下一章按钮应指向第 2 章：{n}")
        need(len(d.get("barButtons") or []) >= 3, f"底栏按钮没排出来：{d.get('barButtons')}")
    if pid == "read-wheel-chain":
        w = d.get("wheel") or {}
        need(w.get("innerPrevented") is False,
             f"指针下的滚动区还有余量时不应由页面接管滚轮：{w}")
        need(not w.get("innerPaneDelta") and not w.get("innerDocDelta"),
             f"指针下的滚动区还有余量时不该带动正文：{w}")
        need(w.get("edgeDocDelta", 0) > 100 and not w.get("edgePaneDelta"),
             f"内层到边且整页在顶部时，应先滚整页（隐藏章标题区）：{w}")
        need(w.get("deepPaneDelta", 0) > 100,
             f"整页到底后，内层到边应接续滚动正文栏：{w}")
    if pid == "read-wide-settings":
        need(d.get("sizeRows") == 1, f"字号 5 档应排在同一行，实际占 {d.get('sizeRows')} 行")
    if pid in ("read-narrow-zh", "read-narrow-dual", "read-tablet-dual", "read-last-chapter"):
        need(d.get("barCenter") is not None and abs(d["barCenter"]) <= 3,
             f"底栏中段未落在视口正中（偏差 {d.get('barCenter')}px）")
    if pid == "read-dual-recover":
        need(d["dual"] == "columns",
             f"窗口由窄变宽后没有恢复分栏（旧实现会卡在标签页样式）：dual={d['dual']}")
        need(vis_zh and vis_en, f"恢复分栏后两栏都应可见（zh={vis_zh}, en={vis_en}）")
    if pid == "read-wide-dual":
        h = d["heading"] or {}
        f = d["flowZh"] or {}
        need(h.get("w", 0) >= 0.8 * (d["main"]["w"] if d["main"] else 0),
             f"分栏时章标题区未与两栏同宽：heading {h.get('w')} vs main {d['main'] and d['main']['w']}")
    if pid == "read-keyboard":
        need(d["theme"] != "paper", f"按 t 后主题应切换，实际仍为 {d['theme']}")
    if pid == "read-clickzone":
        need(d["scrollY"] > 50, f"点击正文右侧 1/3 后未翻屏：scrollY={d['scrollY']}")
    if pid == "read-progress-save":
        rec = (d.get("stored") or {}).get(d.get("chapter") or "1") or {}
        zh = rec.get("zh") or {}
        need(d["scrollY"] > 100, f"整页没有滚动：scrollY={d['scrollY']}")
        need((zh.get("y") or 0) > 100,
             f"滚动后没有把位置写进 localStorage：{rec}（进度条 {d['progress']}，指示 {d['indicator']}）")
    if pid == "read-scroll-next":
        need(d["scrollY"] > 50, f"滚动模式点「下一屏」后没有滚动：scrollY={d['scrollY']}")
    if not pid.startswith("home"):
        need(not d["bodyOverflowX"], f"页面出现横向溢出（scrollWidth {d['docW']} > clientWidth {d['clientW']}）")
    return bad


def main() -> None:
    only = sys.argv[1:]
    todo = {k: v for k, v in PRESETS.items() if not only or k in only}
    failed = 0
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for pid, (rel, w, h, preset, _wait) in todo.items():
            # 探针自己会执行动作（与测量同一轮），这里不要再注入动作脚本，否则动作会执行两次
            page = stage(tmp, rel, preset)
            try:
                d = probe(page, w, h, ACTIONS.get(pid, ""), ACTIONS_WAIT.get(pid, 500),
                          FRAMED.get(pid), WAIT_FOR.get(pid, "true"), FRAME_GROW.get(pid))
            except Exception as e:  # noqa: BLE001
                print(f"FAIL {pid}: {e}")
                failed += 1
                continue
            bad = check(pid, d)
            retried = False
            if bad:
                # headless 环境偶发（ResizeObserver/虚拟时间抖动）：同一预设重跑一次再判
                page2 = stage(tmp, rel, preset)
                try:
                    d2 = probe(page2, w, h, ACTIONS.get(pid, ""), ACTIONS_WAIT.get(pid, 500),
                               FRAMED.get(pid), WAIT_FOR.get(pid, "true"), FRAME_GROW.get(pid))
                    bad2 = check(pid, d2)
                except Exception:  # noqa: BLE001
                    bad2 = bad
                if not bad2:
                    d, bad, retried = d2, [], True
                else:
                    bad = bad2
            if bad:
                failed += 1
                print(f"FAIL {pid}")
                for b in bad:
                    print("   -", b)
            else:
                print(f"OK{'（重跑）' if retried else '   '} {pid}  lang={d['lang']} dual={d['dual']} "
                      f"theme={d['theme']} zh={d['paneZh'] and d['paneZh']['w']}px "
                      f"en={d['paneEn'] and d['paneEn']['w']}px")
    print(f"探针通过 {len(todo) - failed}/{len(todo)}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
