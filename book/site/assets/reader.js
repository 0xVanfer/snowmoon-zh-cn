(function () {
  'use strict';

  var html = document.documentElement;
  html.setAttribute('data-js', '1');

  var KEY = 'snowmoon.reader.v1';
  var body = document.body;
  var listeners = Object.create(null);
  var themes = ['paper', 'light', 'dark', 'night'];
  var languages = ['zh', 'en', 'dual'];
  // [集成修正] 段式：standard = 首行缩进 2em 的常规中文段落；webnovel = 一句一行、
  // 段间留白的「网文」版式（用户可请求项，见 docs/reader-site-design.md）。
  var paragraphStyles = ['standard', 'webnovel'];
  var dark = false;
  var narrow = false;
  try {
    dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    narrow = window.matchMedia('(max-width: 767px)').matches;
  } catch (error) { /* 保留纸色默认值 */ }

  var DEFAULTS = Object.freeze({
    size: narrow ? 18 : 20,
    leading: 1.8,
    font: 'serif',
    theme: dark ? 'dark' : 'paper',
    mode: 'scroll',
    lang: 'zh',
    // [集成修正] 用户要求：同步滚动默认开启（只在「对照 + 宽屏分栏」下有意义）
    sync: true,
    paragraph: 'standard'
  });
  var choices = {
    size: [16, 18, 20, 22, 24],
    leading: [1.7, 1.8, 1.9],
    font: ['serif', 'sans'],
    theme: themes,
    mode: ['scroll', 'paged'],
    lang: languages,
    sync: [true, false],
    paragraph: paragraphStyles
  };

  // [集成修正] 第 2、3 段按 CSS 选择器调用 qs()（如 '#reader-main'），第 1 段内部按裸 id 调用。
  // 两种写法都要接受，否则 qs('#reader-main') 返回 null，双语布局与点击翻页会整段失效。
  function qs(id) {
    if (typeof id !== 'string') return null;
    return id.charAt(0) === '#' || id.charAt(0) === '.' || id.indexOf(' ') >= 0
      ? document.querySelector(id) : document.getElementById(id);
  }
  function qsa(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }
  function getPane(lang) {
    return lang === 'zh' || lang === 'en' ? qs('pane-' + lang) : null;
  }
  function object(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }
  function number(value, min, max, integer) {
    return typeof value === 'number' && Number.isFinite(value) &&
      value >= min && value <= max && (!integer || Number.isInteger(value));
  }
  function setting(key, value) {
    return choices[key].indexOf(value) !== -1 ? value : DEFAULTS[key];
  }
  function position(value) {
    value = object(value) ? value : {};
    return {
      y: number(value.y, 0, Number.MAX_SAFE_INTEGER, false) ? value.y : 0,
      p: number(value.p, 0, 1, false) ? value.p : 0,
      page: number(value.page, 0, Number.MAX_SAFE_INTEGER, true) ? value.page : 0
    };
  }
  function load() {
    var raw = {};
    try {
      var parsed = JSON.parse(window.localStorage.getItem(KEY));
      if (object(parsed) && parsed.v === 1) raw = parsed;
    } catch (error) { /* 存储不可用时只用内存 */ }
    var result = { v: 1, last: 1, settings: {}, chapters: {} };
    var source = object(raw.settings) ? raw.settings : {};
    Object.keys(DEFAULTS).forEach(function (key) {
      result.settings[key] = setting(key, source[key]);
    });
    // [P1] 章数上限原本写死 32：站点有第 33 章时，读档会被截断。
    // 这里不设上限，只要求是正整数；真正的合法性判断交给各页的 validChapter。
    if (number(raw.last, 1, Number.MAX_SAFE_INTEGER, true)) result.last = raw.last;
    if (object(raw.chapters)) {
      Object.keys(raw.chapters).forEach(function (key) {
        var n = Number(key);
        if (!Number.isInteger(n) || n < 1) return;
        var entry = raw.chapters[key];
        if (!object(entry)) return;
        result.chapters[key] = {
          zh: position(entry.zh),
          en: position(entry.en),
          tab: entry.tab === 'en' ? 'en' : 'zh',
          read: entry.read === true
        };
      });
    }
    return result;
  }

  var state = load();
  var page = body && body.dataset.page;
  if (['home', 'toc', 'read'].indexOf(page) === -1) page = 'home';
  var chapterValue = Number(body && body.dataset.chapter);
  // [P1] 不写死 32：第 33 章起会被判成非法章号，整页降级成非阅读页。
  var chapter = number(chapterValue, 1, Number.MAX_SAFE_INTEGER, true) ? chapterValue : null;

  function save() {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(state));
      return true;
    } catch (error) { return false; }
  }
  function on(name, fn) {
    if (typeof fn !== 'function') return function () {};
    if (!listeners[name]) listeners[name] = [];
    listeners[name].push(fn);
    return function () {
      var list = listeners[name] || [];
      var index = list.indexOf(fn);
      if (index !== -1) list.splice(index, 1);
    };
  }
  function emit(name, ev) {
    (listeners[name] || []).slice().forEach(function (fn) {
      try { fn(ev); }
      catch (error) {
        if (window.console && window.console.error) window.console.error(error);
      }
    });
  }
  function controlValue(element) {
    var key = element.getAttribute('data-set');
    var value = element.getAttribute('data-value');
    if (key === 'size' || key === 'leading') return Number(value);
    if (key === 'sync') return value === 'on' ? true : value === 'off' ? false : null;
    return value;
  }
  function applySettings() {
    var s = state.settings;
    html.setAttribute('data-theme', s.theme);
    html.setAttribute('data-font', s.font);
    html.setAttribute('data-lang-mode', s.lang);
    html.setAttribute('data-page-mode', s.mode);
    html.setAttribute('data-paragraph', s.paragraph);
    html.style.setProperty('--reader-size', s.size + 'px');
    html.style.setProperty('--reader-leading', String(s.leading));

    var saved = chapter && state.chapters[String(chapter)];
    var active = saved ? saved.tab : html.getAttribute('data-active-pane');
    if (active !== 'en') active = 'zh';
    if (s.lang !== 'dual') active = s.lang;
    html.setAttribute('data-active-pane', active);
    if (s.lang !== 'dual') html.setAttribute('data-dual-layout', 'columns');

    // 只反映现有布局；分栏判定由下一段接管。
    var tabsVisible = s.lang === 'dual' &&
      html.getAttribute('data-dual-layout') === 'tabs';
    var tabs = qs('lang-tabs');
    if (tabs) tabs.hidden = !tabsVisible;
    ['zh', 'en'].forEach(function (lang) {
      var pane = getPane(lang);
      if (pane) pane.hidden = s.lang === 'dual' ?
        tabsVisible && lang !== active : lang !== s.lang;
    });

    qsa('[data-set][data-value]').forEach(function (control) {
      var key = control.getAttribute('data-set');
      if (!Object.prototype.hasOwnProperty.call(DEFAULTS, key)) return;
      var selected = s[key] === controlValue(control);
      control.setAttribute('aria-pressed', String(selected));
    });
    var langButton = qs('btn-lang');
    if (langButton) {
      var labels = { zh: '中文', en: 'English', dual: '对照' };
      var next = languages[(languages.indexOf(s.lang) + 1) % languages.length];
      langButton.textContent = labels[s.lang];
      langButton.setAttribute('aria-label',
        '当前语言：' + labels[s.lang] + '；切换为' + labels[next]);
    }
  }
  function patch(values) {
    if (!object(values)) return;
    Object.keys(DEFAULTS).forEach(function (key) {
      if (Object.prototype.hasOwnProperty.call(values, key)) {
        state.settings[key] = setting(key, values[key]);
      }
    });
    save();
    applySettings();
    emit('settings', { settings: state.settings });
  }

  var overlay = null;
  var returnFocus = null;
  var triggers = {
    'settings-panel': ['btn-settings', 'btn-settings-inline'],
    drawer: ['btn-drawer']
  };
  function focus(element) {
    if (!element) return;
    try { element.focus({ preventScroll: true }); }
    catch (error) { element.focus(); }
  }
  function focusables(panel) {
    return qsa('a[href],button,input,select,textarea,[tabindex],[contenteditable]', panel)
      .filter(function (element) {
        return element.tabIndex >= 0 && !element.disabled &&
          !element.closest('[hidden],[inert]') && element.getClientRects().length > 0;
      });
  }
  function reflectOverlay() {
    Object.keys(triggers).forEach(function (id) {
      var panel = qs(id);
      if (panel && !closing[id]) panel.hidden = overlay !== id;
      triggers[id].forEach(function (triggerId) {
        var trigger = qs(triggerId);
        if (!trigger) return;
        trigger.setAttribute('aria-controls', id);
        trigger.setAttribute('aria-expanded', String(overlay === id));
      });
    });
    var scrim = qs('scrim');
    if (scrim && !closing.scrim) scrim.hidden = overlay === null;
    api.overlay = overlay;
  }
  var closing = Object.create(null);   // id -> true：退出动画播放期间不要立刻 hidden
  function closePanel(restore) {
    if (!overlay) return false;
    var closingId = overlay;
    overlay = null;
    var panel = qs(closingId);
    var scrimEl = qs('scrim');
    closing[closingId] = true;
    if (scrimEl) closing.scrim = true;
    if (panel) panel.setAttribute('data-state', 'closing');
    if (scrimEl) scrimEl.setAttribute('data-state', 'closing');
    setTimeout(function () {
      if (!closing[closingId]) return;
      delete closing[closingId];
      delete closing.scrim;
      if (panel) { panel.hidden = true; panel.removeAttribute('data-state'); }
      if (scrimEl) { scrimEl.hidden = true; scrimEl.removeAttribute('data-state'); }
      reflectOverlay();
    }, 220);
    reflectOverlay();
    var target = returnFocus;
    returnFocus = null;
    if (restore !== false && target && document.documentElement.contains(target)) {
      focus(target);
    }
    return true;
  }
  function toggleUI(force) {
    var visible = typeof force === 'boolean' ? force :
      html.getAttribute('data-ui') !== 'visible';
    if (overlay) visible = true;
    html.setAttribute('data-ui', visible ? 'visible' : 'hidden');
    return visible;
  }
  function openPanel(id, trigger) {
    if (!Object.prototype.hasOwnProperty.call(triggers, id) || !qs(id)) return;
    delete closing[id];
    delete closing.scrim;
    if (overlay === id) { closePanel(); return; }
    if (overlay) closePanel(false);
    overlay = id;
    returnFocus = trigger || document.activeElement;
    toggleUI(true);
    reflectOverlay();
    var panel = qs(id);
    panel.setAttribute('tabindex', '-1');
    focus(focusables(panel)[0] || panel);
  }

  var api = window.Snowmoon = {
    DEFAULTS: DEFAULTS, state: state, save: save, applySettings: applySettings,
    patch: patch, on: on, emit: emit, qs: qs, qsa: qsa, getPane: getPane,
    page: page, chapter: chapter, toggleUI: toggleUI,
    openPanel: openPanel, closePanel: closePanel, overlay: null,
    // [深链] 当前这一页是不是靠 #cNN-sNNNN 进来的。非空时整段跳过进度恢复——
    // 不只是本模块的 restoreVisible()，还包括进度/存档模块 relayout() 里那次
    // 位置写回（见 docs/reader-site-design.md §7.4）。
    deepLink: null
  };

  Object.keys(triggers).forEach(function (id) {
    triggers[id].forEach(function (triggerId) {
      var trigger = qs(triggerId);
      if (trigger) trigger.addEventListener('click', function () { openPanel(id, trigger); });
    });
  });
  ['settings-close', 'drawer-close', 'scrim'].forEach(function (id) {
    var element = qs(id);
    if (element) element.addEventListener('click', function () { closePanel(); });
  });
  document.addEventListener('click', function (event) {
    var control = event.target.closest && event.target.closest('[data-set][data-value]');
    if (!control || control.disabled) return;
    var key = control.getAttribute('data-set');
    if (!Object.prototype.hasOwnProperty.call(DEFAULTS, key)) return;
    var values = {};
    values[key] = controlValue(control);
    patch(values);
  });
  function cycle(key, list) {
    var values = {};
    values[key] = list[(list.indexOf(state.settings[key]) + 1) % list.length];
    patch(values);
  }
  var langButton = qs('btn-lang');
  if (langButton) langButton.addEventListener('click', function () { cycle('lang', languages); });

  document.addEventListener('focusin', function (event) {
    var panel = overlay && qs(overlay);
    if (panel && !panel.contains(event.target)) focus(focusables(panel)[0] || panel);
  });
  document.addEventListener('keydown', function (event) {
    var target = event.target;
    if (event.defaultPrevented || event.isComposing ||
        (target.closest && target.closest('input,textarea,select,[contenteditable]'))) return;
    if (event.key === 'Tab' && overlay) {
      var panel = qs(overlay);
      var items = focusables(panel);
      var first = items[0];
      var last = items[items.length - 1];
      if (!first || (event.shiftKey && (target === first || target === panel)) ||
          (!event.shiftKey && (target === last || target === panel))) {
        event.preventDefault();
        focus(event.shiftKey ? last || panel : first || panel);
      }
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'Escape') {
      if (event.repeat) return;
      if (overlay || page === 'read') {
        event.preventDefault();
        if (!closePanel()) toggleUI();
      }
      return;
    }
    var key = event.key.toLowerCase();
    if ((key === 't' || key === 'd') && !event.repeat) {
      event.preventDefault();
      if (key === 't') cycle('theme', themes);
      else cycle('lang', languages);
    }
  });

  reflectOverlay();
  if (!html.hasAttribute('data-ui')) html.setAttribute('data-ui', 'visible');
  applySettings();
}());
;(function () {
  'use strict';
  if (!window.Snowmoon) return;

  var S = window.Snowmoon;
  var root = document.documentElement;
  var main = S.qs('#reader-main');
  if (!main) return;

  var langs = ['zh', 'en'];
  var tabs = S.qs('#lang-tabs');
  var positions = { zh: 0, en: 0 };
  // captured：该栏是否真的量到过位置。没量到过的栏在布局切换时不能拿 0 去写，
  // 否则刚从隐藏变可见的那一栏会跳到章首（而另一栏还停在原处）。
  var captured = { zh: false, en: false };
  var expected = { zh: null, en: null };
  var active = root.getAttribute('data-active-pane') === 'en' ? 'en' : 'zh';
  var layout = root.getAttribute('data-dual-layout') === 'tabs' ? 'tabs' : 'columns';
  var lastLang = settings().lang || 'zh';
  var lastMode = settings().mode || 'scroll';
  var layoutFrame = 0;
  var resizeTimer = 0;
  var restoring = false;
  var gesture = null;
  var suppressUntil = 0;

  function settings() {
    return S.state && S.state.settings ? S.state.settings : {};
  }
  function clamp(value) {
    return Math.max(0, Math.min(1, isFinite(value) ? value : 0));
  }
  function mode() {
    return settings().mode || root.getAttribute('data-page-mode') || 'scroll';
  }
  function language() {
    return settings().lang || root.getAttribute('data-lang-mode') || 'zh';
  }
  function pane(lang) {
    return S.getPane(lang);
  }
  function visible(lang) {
    var el = pane(lang);
    return !!(el && el.getClientRects().length && el.clientWidth && el.clientHeight);
  }
  function currentLang() {
    return language() === 'dual' ? active : language() === 'en' ? 'en' : 'zh';
  }
  function setActive(lang) {
    active = lang;
    root.setAttribute('data-active-pane', lang);
  }
  function documentBox() {
    return document.scrollingElement || document.documentElement;
  }
  function scrollBox(lang) {
    var el = pane(lang);
    if (!el) return documentBox();
    var inner = el.querySelector('[data-viewport], .pane-viewport, .reader-viewport, .viewport');
    var candidates = inner ? [inner, el] : [el];
    for (var i = 0; i < candidates.length; i++) {
      if (/(auto|scroll)/.test(getComputedStyle(candidates[i]).overflowY)) {
        return candidates[i];
      }
    }
    return documentBox();
  }
  function metrics(lang) {
    var box = scrollBox(lang);
    var height = box === documentBox() ? document.documentElement.clientHeight : box.clientHeight;
    var max = Math.max(0, box.scrollHeight - height);
    return { box: box, height: height, max: max, y: Math.max(0, box.scrollTop) };
  }
  function remember(lang) {
    if (!visible(lang) || mode() !== 'scroll') return;
    var m = metrics(lang);
    positions[lang] = clamp(m.y / Math.max(1, m.max));
    captured[lang] = true;
  }
  function capture() {
    langs.forEach(remember);
  }
  function writePosition(lang, percent) {
    if (!visible(lang) || mode() !== 'scroll') return;
    var m = metrics(lang);
    positions[lang] = clamp(percent);
    captured[lang] = true;
    if (m.max <= 0) return;   // 容器不可滚动：不要留下永远清不掉的 expected 闩锁
    var y = clamp(percent) * m.max;
    expected[lang] = y;
    m.box.scrollTop = y;
  }
  /* [深链] 术语卡片的章号 chip 指向 `chapter-NN.html#cNN-sNNNN`。
     浏览器自带的 fragment 滚动会被进度记忆覆盖——restoreVisible() 一跑就把
     localStorage 里的旧位置写回去，读者点「第 6 章」结果落回上次读的地方。
     所以带锚点进来时整段跳过进度恢复，改成滚到锚点并闪一下。 */
  var deepLink = null;

  function restoreVisible() {
    if (deepLink) return;
    if (mode() !== 'scroll') return;
    var targets = (language() === 'dual' && layout === 'columns') ? langs : [currentLang()];
    var anchor = null;
    langs.forEach(function (l) { if (anchor === null && captured[l]) anchor = positions[l]; });
    targets.forEach(function (lang) {
      if (captured[lang]) writePosition(lang, positions[lang]);
      else if (anchor !== null) writePosition(lang, anchor);   // 新露出的栏对齐到已知位置
    });
  }
  function applyDeepLink() {
    var m = /^#(c\d\d-s\d+)$/.exec(window.location.hash || '');
    if (!m) return;
    deepLink = S.deepLink = m[1];
    var target = document.getElementById(deepLink);
    if (!target) return;
    // 术语与讲解都在中文栏。若当前显示的是英文或对照的英文标签页，
    // 目标段落是 display:none，scrollIntoView 不会产生任何位移。
    if (!visible('zh')) patch({ lang: 'zh' });
    var go = function () {
      target.scrollIntoView({ block: 'center' });
      target.classList.add('is-deeplink');
      window.setTimeout(function () { target.classList.remove('is-deeplink'); }, 1600);
    };
    /* 先同步落一次位，再等两帧校正。
       原来只等两帧：落点与高亮全押在 rAF 上，而 rAF 不保证及时到（无头虚拟时间下干脆
       不出帧，慢设备上也会明显滞后）——表现是「点了章号 chip，页面先在旧位置停一下才跳」。
       同步那一次在多数情况下就是最终位置（正文已排好），两帧后那次负责图片/表格
       撑开高度后的纠偏。校正时重新加上高亮：高度变了，落点会偏。 */
    go();
    requestAnimationFrame(function () { requestAnimationFrame(go); });
  }

  function updateTabs() {
    if (!tabs) return;
    var shown = language() === 'dual' && layout === 'tabs';
    tabs.hidden = !shown;
    tabs.setAttribute('aria-hidden', String(!shown));
    Array.prototype.forEach.call(tabs.querySelectorAll('[data-tab-lang]'), function (button) {
      var lang = button.getAttribute('data-tab-lang');
      button.setAttribute('aria-selected', String(lang === active));
      button.setAttribute('tabindex', shown && lang === active ? '0' : '-1');
      button.setAttribute('aria-controls', 'pane-' + lang);
    });
  }
  function selectTab(lang, focus) {
    if (langs.indexOf(lang) < 0) return;
    remember(active);
    setActive(lang);
    updateTabs();
    restoreVisible();
    if (focus && tabs) {
      var button = tabs.querySelector('[data-tab-lang="' + lang + '"]');
      if (button) button.focus();
    }
    S.emit('active-pane', { lang: lang });
  }

  if (tabs) {
    tabs.addEventListener('click', function (event) {
      var button = event.target.closest('[data-tab-lang]');
      if (button && tabs.contains(button)) selectTab(button.getAttribute('data-tab-lang'), false);
    });
    tabs.addEventListener('keydown', function (event) {
      if (!event.target.closest('[data-tab-lang]')) return;
      var lang;
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') lang = active === 'zh' ? 'en' : 'zh';
      else if (event.key === 'Home') lang = 'zh';
      else if (event.key === 'End') lang = 'en';
      else return;
      event.preventDefault();
      selectTab(lang, true);
    });
  }

  // [集成修正] 分栏判定要用「页面可用空间」，不能用 #reader-main 的实测尺寸：
  // main 在标签页/单栏下被 CSS 的 max-width:38em 限宽、高度又是整篇正文的自然高度，
  // 量到的是「当前布局」而不是「还能放多宽」。于是窗口一旦变窄（或开发工具占位、
  // 旋转屏幕、系统缩放变化）掉进标签页，就再也量不到分栏所需的宽度，卡在窄屏样式里——
  // 这就是「宽屏偶发变成窄屏」的原因。这里改为按视口宽 − 边距、并夹到分栏容器最大宽，
  // 高度按视口高 − 顶栏/底栏，两者都与当前是分栏还是标签页无关。
  var DUAL_MAX_EM = 76;       // 与 CSS 的 max-width: calc(76em + 32px) 对齐
  var DUAL_GAP_PX = 32;       // 分栏中缝 column-gap
  function measureLayout() {
    var F = parseFloat(getComputedStyle(root).getPropertyValue('--reader-size'));
    if (!(F > 0)) F = 20;
    var pageW = root.clientWidth || window.innerWidth || 0;
    var gutter = pageW <= 767 ? 40 : 80;      // 与 CSS 的 calc(100% - 40px / 80px) 对齐
    var W = Math.min(pageW - gutter, DUAL_MAX_EM * F + DUAL_GAP_PX);
    var topbar = S.qs('#topbar'), bottombar = S.qs('#bottombar');
    var reserve = (topbar && topbar.offsetHeight ? topbar.offsetHeight : 56) +
      (bottombar && bottombar.offsetHeight ? bottombar.offsetHeight : 48);
    var H = (window.innerHeight || root.clientHeight || 0) - reserve;
    if (!(W > 0 && H > 0)) return;
    var next = layout;
    // [集成修正] 原判据按「每栏 34 个汉字」折算（68F），1366/1440 宽的常见桌面窗口会被判成标签页，
    // 与「宽屏左右分栏」的要求不符。这里放宽到每栏 30 个汉字（60F）：1366px 起即可分栏，
    // 每栏约 600px（20px 字号下 30 字/行），仍在中文舒适行长内。
    if (layout === 'tabs' && W >= 60 * F + 64 && W / H >= 1.15) next = 'columns';
    if (layout === 'columns' && (W < 60 * F + 32 || W / H < 1.05)) next = 'tabs';
    // [集成修正] 第 1 段在切到「中文/English」时会把 data-dual-layout 强制写回 columns，
    // 与这里的 layout 变量可能对不上；只比 next === layout 会提前返回、把错误属性和 CSS 一起留下。
    if (next === layout && root.getAttribute('data-dual-layout') === layout) return;
    capture();
    restoring = true;
    layout = next;
    root.setAttribute('data-dual-layout', layout);
    updateTabs();
    cancelAnimationFrame(layoutFrame);
    layoutFrame = requestAnimationFrame(function () {
      restoreVisible();
      restoring = false;
      S.emit('layout', { layout: layout });
    });
  }
  function scheduleLayout() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(measureLayout, 150);
  }
  if (window.ResizeObserver) {
    var observer = new ResizeObserver(scheduleLayout);
    observer.observe(main);
  }
  // [集成修正] 除了观察正文容器，窗口自身的 resize 也照样接上：只靠 ResizeObserver 时，
  // 视口变化（缩放、iframe 被拉宽、无头环境丢掉一次 RO 回调）可能不触发重算，
  // 「由窄变宽应该恢复分栏」就会卡在标签页样式。
  window.addEventListener('resize', scheduleLayout);

  function syncEnabled() {
    // [集成修正] 第 1 段把 sync 规范化成布尔值（true/false），第 2 段原来只认字符串 'on'，
    // 导致同步滚动永远不生效（第 3 段已经两种都认，这里对齐）。
    var sync = settings().sync;
    return (sync === true || sync === 'on') && language() === 'dual' && layout === 'columns';
  }
  function handleScroll(lang, target) {
    if (mode() !== 'scroll' || !visible(lang)) return;
    var m = metrics(lang);
    if (target && target !== m.box) return;
    if (expected[lang] !== null) {
      var programmed = Math.abs(m.y - expected[lang]) <= 2;
      expected[lang] = null;
      if (programmed) return;
    }
    if (restoring) return;
    positions[lang] = clamp(m.y / Math.max(1, m.max));
    setActive(lang);
    if (!syncEnabled()) return;
    // [集成修正] 原来把对齐推迟到 requestAnimationFrame 里做：无头环境、后台标签页这类
    // 不产生新帧的场景里 rAF 可能迟迟不执行，对栏就停在原位、看起来像「同步滚动没生效」。
    // 这里直接同步写入另一栏——写入后对方产生的 scroll 事件会被上面的 expected 判定吃掉，
    // 不会形成回环，也省掉一帧延迟。
    var other = lang === 'zh' ? 'en' : 'zh';
    if (scrollBox(lang) !== scrollBox(other)) writePosition(other, positions[lang]);
  }
  // [集成修正] 正文栏的 scroll 事件改在 document 的捕获阶段集中接收，两栏共用同一条判定，
  // 不再逐栏挂监听（也不怕某一栏后来被重建而漏挂）。
  document.addEventListener('scroll', function (event) {
    var node = event.target;
    if (!node || node.nodeType !== 1) return;
    if (node.id === 'pane-zh') handleScroll('zh', node);
    else if (node.id === 'pane-en') handleScroll('en', node);
  }, true);
  window.addEventListener('scroll', function (event) {
    if (event.target !== document && event.target !== window) return;
    var lang = currentLang();
    if (scrollBox(lang) === documentBox()) handleScroll(lang, null);
  }, { passive: true });

  function navigate(direction) {
    // 章首/章末换章走 <link rel="prev|next">（首章 prev、末章 next 回落到目录页）；
    // 原来取的是章末那排已删除的 #nav-prev/#nav-next，可见入口是底栏那对按钮。
    var link = document.querySelector(direction > 0 ? 'link[rel="next"]' : 'link[rel="prev"]');
    if (link && link.getAttribute('href')) window.location.assign(link.href);
  }
  S.step = function (direction) {
    direction = Number(direction);
    if (!isFinite(direction) || direction === 0) return;
    direction = direction > 0 ? 1 : -1;
    var lang = currentLang();
    if (mode() === 'paged') {
      // 第 3 段可提供 pagedStep，或订阅 page-step（两者选一）。
      if (typeof S.pagedStep === 'function') return S.pagedStep(direction, lang);
      S.emit('page-step', { direction: direction, lang: lang });
      return;
    }
    // 不可见的栏量到的是 0/0（max=0、y=0），会把「上一屏/下一屏」误判成到章首/章末而跳章。
    if (!visible(lang)) return;
    var m = metrics(lang);
    if ((direction > 0 && m.y >= m.max - 2) || (direction < 0 && m.y <= 2)) {
      navigate(direction);
      return;
    }
    expected[lang] = null;
    m.box.scrollTop = Math.max(0, Math.min(m.max, m.y + direction * m.height * 0.85));
    remember(lang);
  };
  ['prev', 'next'].forEach(function (name) {
    var button = S.qs('#btn-' + name + '-screen');
    if (button) button.addEventListener('click', function () { S.step(name === 'prev' ? -1 : 1); });
  });

  // [用户请求] 设置面板里写着「←/→ 上一屏/下一屏；↑/↓ 滚动当前阅读栏」，
  // 但全局 keydown 只处理了 Tab/Esc/t/d，方向键此前完全没接。
  document.addEventListener('keydown', function (event) {
    if (event.defaultPrevented || event.isComposing || event.altKey ||
        event.ctrlKey || event.metaKey || event.shiftKey) return;
    var target = event.target;
    if (target && target.closest &&
        target.closest('input,textarea,select,[contenteditable],[role="tab"]')) return;
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      S.step(event.key === 'ArrowRight' ? 1 : -1);
      return;
    }
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      var lang = currentLang();
      if (mode() === 'paged') {           // 翻页模式没有可滚动容器，方向键改翻页
        event.preventDefault();
        S.step(event.key === 'ArrowDown' ? 1 : -1);
        return;
      }
      if (!visible(lang)) return;
      var m = metrics(lang);
      if (m.max <= 0) return;             // 交给浏览器原生滚动
      event.preventDefault();
      m.box.scrollTop = Math.max(0, Math.min(m.max, m.y + (event.key === 'ArrowDown' ? 48 : -48)));
      remember(lang);
    }
  });

  function excluded(target, boundary) {
    if (target.closest('a, button, input, select, textarea, label, summary, audio, video, iframe, [role="button"], [role="slider"], [data-no-flip], [contenteditable]:not([contenteditable="false"])')) return true;
    for (var node = target; node && node !== boundary; node = node.parentElement) {
      if (node.classList.contains('device-view')) return true;
      var style = getComputedStyle(node);
      if ((/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight + 1) ||
          (/(auto|scroll)/.test(style.overflowX) && node.scrollWidth > node.clientWidth + 1)) {
        if (node !== scrollBox(boundary.getAttribute('data-lang'))) return true;
      }
    }
    return false;
  }
  function startGesture(x, y) {
    gesture = { x: x, y: y, moved: false };
  }
  function moveGesture(x, y) {
    if (gesture && (Math.abs(x - gesture.x) > 8 || Math.abs(y - gesture.y) > 8)) gesture.moved = true;
  }
  function endGesture() {
    if (gesture && gesture.moved) suppressUntil = Date.now() + 500;
    gesture = null;
  }
  if (window.PointerEvent) {
    main.addEventListener('pointerdown', function (e) { startGesture(e.clientX, e.clientY); }, { passive: true });
    window.addEventListener('pointermove', function (e) { moveGesture(e.clientX, e.clientY); }, { passive: true });
    window.addEventListener('pointerup', endGesture, { passive: true });
    window.addEventListener('pointercancel', function () { suppressUntil = Date.now() + 500; endGesture(); });
  } else {
    main.addEventListener('mousedown', function (e) { startGesture(e.clientX, e.clientY); });
    window.addEventListener('mousemove', function (e) { moveGesture(e.clientX, e.clientY); });
    window.addEventListener('mouseup', endGesture);
    main.addEventListener('touchstart', function (e) {
      if (e.touches.length === 1) startGesture(e.touches[0].clientX, e.touches[0].clientY);
      else suppressUntil = Date.now() + 1000;
    }, { passive: true });
    main.addEventListener('touchmove', function (e) {
      if (e.touches.length) moveGesture(e.touches[0].clientX, e.touches[0].clientY);
    }, { passive: true });
    window.addEventListener('touchend', endGesture, { passive: true });
    window.addEventListener('touchcancel', endGesture, { passive: true });
  }
  main.addEventListener('dragstart', function () { suppressUntil = Date.now() + 1000; });
  main.addEventListener('dragend', function () { suppressUntil = Date.now() + 500; endGesture(); });
  langs.forEach(function (lang) {
    var el = pane(lang);
    if (!el) return;
    el.addEventListener('click', function (event) {
      if (event.defaultPrevented || event.button !== 0 || event.detail === 0 ||
          event.ctrlKey || event.metaKey || event.altKey || event.shiftKey ||
          Date.now() < suppressUntil || (gesture && gesture.moved)) return;
      var selection = window.getSelection();
      if (selection && !selection.isCollapsed) return;
      if (excluded(event.target, el)) return;
      var rect = el.getBoundingClientRect();
      if (!rect.width) return;
      setActive(lang);
      var fraction = (event.clientX - rect.left) / rect.width;
      if (fraction < 1 / 3) S.step(-1);
      else if (fraction > 2 / 3) S.step(1);
      else S.toggleUI();
    });
  });

  // ---- [用户请求] 移动端拖拽：翻页模式没有任何触摸手势入口，手机上只能靠「点左/右三分之一」
  //      翻页，手指一拖就毫无反应（看起来就是「拖不动、滚不了」）。这里给翻页模式补一个横向
  //      滑动翻页：横向位移过阈值且明显大于纵向才翻，且落在面板／链接／按钮等交互区时不接管。
  var swipe = null;
  main.addEventListener('touchstart', function (event) {
    if (event.touches.length !== 1) { swipe = null; return; }
    var touch = event.touches[0];
    swipe = { x: touch.clientX, y: touch.clientY, target: touch.target || event.target };
  }, { passive: true });
  main.addEventListener('touchend', function (event) {
    var start = swipe;
    swipe = null;
    if (!start || mode() !== 'paged') return;
    var touch = event.changedTouches && event.changedTouches[0];
    if (!touch) return;
    var dx = touch.clientX - start.x, dy = touch.clientY - start.y;
    if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy) * 1.2) return;
    var lang = currentLang();
    if (start.target && start.target.closest && excluded(start.target, pane(lang) || main)) return;
    setActive(lang);
    S.step(dx < 0 ? 1 : -1);
  }, { passive: true });
  main.addEventListener('touchcancel', function () { swipe = null; }, { passive: true });

  // ---- [用户请求] 段式：「网文分行」把中文正文按句断开（一句一行），更接近中文网文阅读习惯 ----
  // 断句只在文本节点上做：在每句终止符号之后插入一个 display:block 的空 span，
  // 于是同一段里的句子各占一行，颜色、加粗、虚构语言等内联样式都原样保留；
  // 切回「常规」时把这些 span 删掉即可，正文 DOM 与构建产物保持一致。
  var SENTENCE_END = /[^。！？…!?]*[。！？…!?]+[”’」』）)\]】]*/g;
  // .dateline / .chapter-title 曾在这里：章标题与卷首日期由 .chapter-heading 渲染，
  // render_blocks 不会再放进正文流（kind=title / dateline-open 被跳过），两个选择器永远匹配不到。
  var PARAGRAPH_SKIP = '.scene-break';
  var PARAGRAPH_SKIP_INSIDE = '.device-view, figure, table, .dz-card, .pagination-table-scroll';

  function addSentenceGaps(p) {
    var walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT, null);
    var texts = [], node;
    while ((node = walker.nextNode())) texts.push(node);
    texts.forEach(function (text) {
      // 术语标注把段落切成了多个文本节点。词本身是完整的概念名、不含句末标点，
      // 但仍要跳过 .term 内部：真在词里插一个 .sentence-gap 会把可点的词切成两半。
      if (text.parentElement && text.parentElement.closest('.term')) return;
      var value = text.nodeValue;
      if (!/[。！？…!?]/.test(value)) return;
      var frag = document.createDocumentFragment(), last = 0, match;
      SENTENCE_END.lastIndex = 0;
      while ((match = SENTENCE_END.exec(value)) !== null) {
        if (!match[0].length) break;
        frag.appendChild(document.createTextNode(match[0]));
        var gap = document.createElement('span');
        gap.className = 'sentence-gap';
        gap.setAttribute('aria-hidden', 'true');
        frag.appendChild(gap);
        last = SENTENCE_END.lastIndex;
      }
      if (!last) return;
      if (last < value.length) frag.appendChild(document.createTextNode(value.slice(last)));
      if (text.parentNode) text.parentNode.replaceChild(frag, text);
    });
    // 段末不留空行
    var tail = p.lastElementChild;
    while (tail && tail.classList && tail.classList.contains('sentence-gap')) {
      var previous = tail.previousSibling;
      tail.parentNode.removeChild(tail);
      tail = previous && previous.nodeType === 1 ? previous : null;
    }
  }

  function removeSentenceGaps(p) {
    if (!p.querySelector('.sentence-gap')) return;
    S.qsa('.sentence-gap', p).forEach(function (gap) {
      if (gap.parentNode) gap.parentNode.removeChild(gap);
    });
    p.normalize();
  }

  function applyParagraphStyle() {
    var el = pane('zh');
    if (!el) return;
    var on = language() !== 'en' && settings().paragraph === 'webnovel';
    S.qsa('.chapter-content p', el).forEach(function (p) {
      if (p.matches(PARAGRAPH_SKIP) || p.closest(PARAGRAPH_SKIP_INSIDE)) return;
      // 断句会插入标记元素，重复执行必须幂等（每次改设置都会重跑一遍）
      if (on) {
        if (!p.querySelector('.sentence-gap')) addSentenceGaps(p);
      } else {
        removeSentenceGaps(p);
      }
    });
  }

  // ---- [用户请求] 滚轮：指针在插图/终端面板上时先滚它们，到顶或到底再滚正文；
  //      分栏时正文向下滚先把整页滚下去，让上方的章标题区随滚动隐藏（否则栏底会被底栏挡住）。
  function langOf(node) {
    for (var el = node; el && el !== main; el = el.parentElement) {
      if (el.id === 'pane-zh') return 'zh';
      if (el.id === 'pane-en') return 'en';
    }
    return currentLang();
  }
  function wheelChain(target, lang) {
    var box = scrollBox(lang);
    var list = [];
    for (var el = target; el && el !== main.parentElement; el = el.parentElement) {
      if (el.nodeType !== 1 || el === document.documentElement || el === document.body) break;
      if (el === box) { list.push(el); break; }
      var style = getComputedStyle(el);
      if (/(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 1) list.push(el);
    }
    if (list.indexOf(box) < 0) list.push(box);
    var doc = documentBox();
    if (box !== doc && list.indexOf(doc) < 0) list.push(doc);
    return list;
  }
  function room(el, down) {
    return down ? el.scrollHeight - el.clientHeight - el.scrollTop : el.scrollTop;
  }
  function wheelPixels(event) {
    var dy = event.deltaY || 0;
    if (event.deltaMode === 1) dy *= 16;
    else if (event.deltaMode === 2) dy *= (window.innerHeight || 600);
    return dy;
  }
  main.addEventListener('wheel', function (event) {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (!event.target || !event.target.nodeType) return;
    var dy = wheelPixels(event);
    if (!dy) return;
    var down = dy > 0;
    var lang = langOf(event.target);
    var chain = wheelChain(event.target, lang);
    var doc = documentBox();
    var paneBox = scrollBox(lang);
    var index = 0;
    while (index < chain.length && room(chain[index], down) <= 1) index += 1;
    if (index >= chain.length) return;
    var box = chain[index];
    // 分栏：整页还能继续往下滚（章标题区尚未滚出视野）时，先滚整页
    if (box === paneBox && box !== doc && down &&
        index + 1 < chain.length && chain[index + 1] === doc && room(doc, true) > 1) {
      event.preventDefault();
      doc.scrollTop += dy;
      return;
    }
    if (index === 0) return;              // 指针下的容器自己还能滚：交给浏览器
    // 内层到顶/底：手动接续到外层（终端面板带 overscroll-behavior: contain，原生不会接续）
    event.preventDefault();
    box.scrollTop += dy;
  }, { passive: false });

  S.on('settings', function () {
    var nextLang = language();
    var nextMode = mode();
    root.setAttribute('data-lang-mode', nextLang);
    root.setAttribute('data-page-mode', nextMode);
    if (nextLang !== lastLang) {
      if (nextLang !== 'dual') setActive(nextLang === 'en' ? 'en' : 'zh');
      else setActive('zh');
      lastLang = nextLang;
      updateTabs();
      requestAnimationFrame(restoreVisible);
    }
    if (nextMode !== lastMode) {
      lastMode = nextMode;
      S.emit('mode', { mode: nextMode });
    }
    applyParagraphStyle();
    scheduleLayout();
  });
  setActive(active);
  updateTabs();
  applyParagraphStyle();
  capture();
  measureLayout();
  /* [深链] 入口在本 IIFE 末尾就地调用，不跨 IIFE 调：applyDeepLink 定义在这里，
     而进度/存档模块（下一个 IIFE）也要用到它设置好的 api.deepLink。
     早于它自己的 relayout() 执行，所以首次排版就不会把位置写回旧进度。 */
  applyDeepLink();
}());
(function () {
  'use strict';
  if (!window.Snowmoon) return;
  var api = window.Snowmoon;

  function enhancePages() {
    var root = document.documentElement, state = api.state;
    if (!state || !state.settings) return;
    var main = document.getElementById('reader-main');
    var chapter = Number(api.chapter || (document.body.dataset.chapter) ||
      root.dataset.chapter || ((location.pathname.match(/chapter-(\d+)\.html$/) || [])[1]));
    var reading = !!main && Number.isInteger(chapter) && chapter >= 1;
    var models = [], originals = [], wrappers = [], snapshots = {};
    var ready = false, frame = 0, saveTimer = 0, directoryFrame = 0;
    var initial = true, previousMode = state.settings.mode;
    var bar = document.getElementById('progress-bar');
    var indicator = document.getElementById('page-indicator');
    var oldStep = api.step;
    state.chapters = state.chapters || {};
    var record = reading ? state.chapters[chapter] || {} : {};
    ['zh', 'en'].forEach(function (lang) {
      var r = record[lang] || {};
      snapshots[lang] = {
        y: finite(r.y), p: clamp(finite(r.p)), page: Math.floor(finite(r.page))
      };
    });

    function finite(n) { return typeof n === 'number' && isFinite(n) ? Math.max(0, n) : 0; }
    function clamp(n) { return Math.max(0, Math.min(1, n)); }
    // [P1] 原本写死 `n >= 1 && n <= 32`：站点一旦有第 33 章，整页被判成
    // 「非阅读页」，翻页与进度条全部失效，而没有任何闸门报警。章数上限必须
    // 来自目录本身（toc.html / 页内目录都有 li[data-chapter]）。
    var chapterTotal = (function () {
      var listed = document.querySelectorAll('#toc-list li[data-chapter], #drawer-toc li[data-chapter]');
      var max = 0;
      Array.prototype.forEach.call(listed, function (li) {
        var n = Number(li.dataset.chapter);
        if (Number.isInteger(n) && n > max) max = n;
      });
      var declared = Number(document.documentElement.dataset.chaptersTotal || 0);
      return Math.max(max, Number.isInteger(declared) ? declared : 0) || 32;
    }());
    var validChapter = function (n) { return Number.isInteger(n) && n >= 1 && n <= chapterTotal; };
    function paged() { return state.settings.mode === 'paged'; }
    function visible(m) {
      return m.pane.getClientRects().length > 0 &&
        getComputedStyle(m.pane).visibility !== 'hidden';
    }
    function active() {
      var lang = root.dataset.activePane || record.tab || 'zh';
      var available = models.filter(visible);
      return available.filter(function (m) { return m.lang === lang; })[0] || available[0];
    }
    function rememberStyle(el) {
      if (!originals.some(function (r) { return r.el === el; })) {
        originals.push({ el: el, css: el.getAttribute('style') });
      }
    }
    function style(el, properties) {
      rememberStyle(el);
      Object.keys(properties).forEach(function (key) { el.style[key] = properties[key]; });
    }
    function resetStyles() {
      originals.forEach(function (r) {
        if (r.css === null) r.el.removeAttribute('style');
        else r.el.setAttribute('style', r.css);
      });
      originals = [];
      // 翻页模式给表格套的包装层要拆掉：留在 DOM 里会改变滚动模式下的包含块
      wrappers.forEach(function (w) {
        if (w.wrapper.parentNode) {
          w.wrapper.parentNode.insertBefore(w.table, w.wrapper);
          w.wrapper.parentNode.removeChild(w.wrapper);
        }
      });
      wrappers = [];
    }
    function scrollHost(m) {
      var el = m.viewport;
      while (el && el !== document.body) {
        if (/(auto|scroll)/.test(getComputedStyle(el).overflowY)) return el;
        el = el.parentElement;
      }
      return document.scrollingElement || document.documentElement;
    }
    function position(m) {
      if (paged()) return {
        y: snapshots[m.lang].y, page: m.page,
        p: m.pages > 1 ? m.page / (m.pages - 1) : 1
      };
      var host = scrollHost(m), range = host.scrollHeight - host.clientHeight;
      return { y: Math.max(0, host.scrollTop), p: range > 0 ? clamp(host.scrollTop / range) : 1,
        page: snapshots[m.lang].page };
    }
    function updateProgress() {
      if (!ready) return;
      models.filter(visible).forEach(function (m) { snapshots[m.lang] = position(m); });
      var m = active();
      if (!m) return;
      var p = snapshots[m.lang].p, percent = Math.round(p * 100);
      if (bar) {
        bar.style.width = (p * 100).toFixed(2) + '%';
        bar.setAttribute('role', 'progressbar');
        bar.setAttribute('aria-label', '本章阅读进度');
        bar.setAttribute('aria-valuemin', '0');
        bar.setAttribute('aria-valuemax', '100');
        bar.setAttribute('aria-valuenow', String(percent));
      }
      if (indicator) indicator.textContent = paged() ?
        '第 ' + (m.page + 1) + ' / ' + m.pages + ' 页' : '本章 ' + percent + '%';
      if (p >= 0.95) record.read = true;
    }
    function persist() {
      clearTimeout(saveTimer);
      saveTimer = 0;
      if (!reading || !ready) return;
      if (!frame) updateProgress();
      record.zh = Object.assign({}, snapshots.zh);
      record.en = Object.assign({}, snapshots.en);
      record.tab = root.dataset.activePane === 'en' ? 'en' : 'zh';
      record.read = !!record.read;
      state.chapters[chapter] = record;
      state.last = chapter;
      state.v = 1;
      try { localStorage.setItem('snowmoon.reader.v1', JSON.stringify(state)); } catch (error) {}
      decorateDirectories(false);
    }
    function queueSave() {
      if (!saveTimer) saveTimer = setTimeout(persist, 300);
    }
    function displayPage(m, page) {
      m.page = Math.max(0, Math.min(m.pages - 1, Math.round(page)));
      m.flow.style.transform = 'translateX(' + (-m.page * m.step) + 'px)';
      m.viewport.scrollLeft = 0;
    }
    function prepareOversize(m, height) {
      Array.prototype.forEach.call(m.flow.querySelectorAll('table'), function (table) {
        if (table.closest('.device-view, .pagination-table-scroll')) return;
        var wrapper = document.createElement('div');
        wrapper.className = 'pagination-table-scroll';
        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
        wrappers.push({ wrapper: wrapper, table: table });
      });
      Array.prototype.forEach.call(m.flow.querySelectorAll('img, svg'), function (image) {
        style(image, { maxWidth: '100%', maxHeight: height + 'px', objectFit: 'contain' });
      });
      Array.prototype.forEach.call(m.flow.querySelectorAll(
        '.device-view, .pagination-table-scroll, .fig'
      ), function (block) {
        style(block, { maxHeight: height + 'px', maxWidth: '100%', boxSizing: 'border-box',
          overflow: 'auto', breakInside: 'avoid', pageBreakInside: 'avoid' });
      });
    }
    function layoutPages(m) {
      var bottom = document.getElementById('bottombar');
      // [P0] 这里原本写 S.qs('#topbar')：S 与 documentBox() 都属于前一段 IIFE 的作用域，
      // 本段（enhancePages）不可见 → 每次 layoutPages() 抛 ReferenceError，ready 永远置不上 true，
      // 翻页模式一次都没排版成功过（m.pages 停在初值 1，next>=pages 恒真，「下一页」直接跳章）。
      var topbar = document.getElementById('topbar');
      var topH = topbar && topbar.offsetHeight ? topbar.offsetHeight : 56;
      var reserve = (bottom ? Math.max(48, bottom.offsetHeight) : 48) + topH;
      // 页高只看视口高度，不看 rect.top——rect.top 随文档滚动变化，
      // 于是「先滚动再切翻页」会少算一屏：首行被固定顶栏压住，而且没有滚动余量可以救回来。
      var available = Math.max(1, window.innerHeight - reserve - 16);
      var width = Math.max(1, m.viewport.clientWidth);
      var height = Math.max(1, available);
      style(m.viewport, { height: height + 'px', overflow: 'hidden', position: 'relative',
        padding: '0', scrollBehavior: 'auto' });
      width = Math.max(1, m.viewport.clientWidth);
      style(m.flow, { display: 'block', boxSizing: 'border-box', width: width + 'px',
        height: height + 'px', minHeight: '0', maxHeight: 'none', maxWidth: 'none',
        padding: '0', margin: '0', columnWidth: width + 'px', columnGap: '32px',
        columnCount: 'auto', columnFill: 'auto', overflow: 'visible', direction: 'ltr',
        transition: 'none', transform: 'none' });
      prepareOversize(m, height);
      m.step = width + 32;
      m.pages = Math.max(1, Math.ceil((m.flow.scrollWidth + 32) / m.step));
      // 把正文盒顶端对齐到顶栏下沿（新高度生效后再量一次）
      // 同上：documentBox() 在本段不可见，内联展开其定义。
      var doc = document.scrollingElement || document.documentElement;
      var shift = m.viewport.getBoundingClientRect().top - topH;
      if (Math.abs(shift) > 1) doc.scrollTop = Math.max(0, doc.scrollTop + shift);
      m.viewport.scrollTop = 0;
    }
    function restoreScroll(m, saved, first) {
      var host = scrollHost(m), behavior = host.style.scrollBehavior;
      host.style.scrollBehavior = 'auto';
      var range = Math.max(0, host.scrollHeight - host.clientHeight);
      host.scrollTop = Math.min(range, first ? saved.y : saved.p * range);
      host.style.scrollBehavior = behavior;
    }
    // [用户反馈] 翻页/滚动的闪烁还有一个来源：relayout() 会 resetStyles() 还原全部行内样式、
    // 再整段重新分列，而它被 MutationObserver / ResizeObserver / 多次 scheduleLayout 反复触发。
    // 几何与排版参数都没变时，重排没有任何收益，只会在屏幕上闪一下。这里用一枚「几何指纹」
    // 把无变化的重排挡掉；指纹一改（旋转、缩放、字号/行距/字体/段式、分栏可见性）照常重排。
    var layoutKey = '';
    function geometryKey() {
      var s = state.settings || {};
      var mainEl = document.getElementById('reader-main');
      return [paged(), s.size, s.leading, s.font, s.paragraph,
        window.innerWidth, window.innerHeight,
        mainEl ? mainEl.clientWidth : 0,
        models.filter(visible).map(function (m) { return m.lang; }).join(',')].join('|');
    }
    function relayout() {
      frame = 0;
      if (!reading) return;
      var first = initial, mode = state.settings.mode;
      var key = geometryKey();
      if (ready && key === layoutKey) {
        // 几何未变：保留已经应用的行内样式，只刷新进度与存档。
        updateProgress();
        queueSave();
        return;
      }
      layoutKey = key;
      if (originals.length) resetStyles();
      // [深链] 带 #cNN-sNNNN 进来时只跳过**位置写回**，不跳过排版。
      // 这一段的排版（表格分列、图片加载、字体就绪）会被反复触发，每次都
      // restoreScroll()/displayPage() 就把读者从落点拽回上次读的地方，深链等于失效。
      // 但 layoutPages() 是分页模式的排版本身，跳过它会让深链进来的翻页页正文不排版。
      // 落点滚到位后由 updateProgress() 重新取样，读者这次的落点就成了新的进度。
      // 见 docs/reader-site-design.md §7.4。
      var deep = api.deepLink;
      models.filter(visible).forEach(function (m) {
        var saved = snapshots[m.lang];
        if (paged()) {
          layoutPages(m);
          if (deep) return;
          displayPage(m, first ? saved.page : saved.p * (m.pages - 1));
        } else {
          if (deep) return;
          restoreScroll(m, saved, first && previousMode === mode);
        }
      });
      previousMode = mode;
      initial = false;
      ready = true;
      updateProgress();
      queueSave();
    }
    function scheduleLayout() {
      if (reading && !frame) frame = requestAnimationFrame(relayout);
    }
    function chapterHref(n, list) {
      var item = list && list.querySelector('li[data-chapter="' + n + '"] a[href]');
      return item ? item.getAttribute('href') :
        (reading ? '' : 'read/') + 'chapter-' + ('0' + n).slice(-2) + '.html';
    }
    function decorateDirectories(scrollCurrent) {
      var current = reading ? chapter : Number(state.last);
      ['drawer-toc', 'toc-list'].forEach(function (id) {
        var list = document.getElementById(id);
        if (!list) return;
        Array.prototype.forEach.call(list.querySelectorAll('li[data-chapter]'), function (li) {
          var n = Number(li.dataset.chapter), isCurrent = n === current;
          li.classList.toggle('is-read', !!(state.chapters[n] && state.chapters[n].read));
          li.classList.toggle('is-current', isCurrent);
          var link = li.querySelector('.chapter-link');
          if (isCurrent) {
            li.setAttribute('aria-current', 'page');
            if (link) link.setAttribute('aria-current', 'page');
          } else {
            if (li.getAttribute('aria-current') === 'page') li.removeAttribute('aria-current');
            if (link && link.getAttribute('aria-current') === 'page') link.removeAttribute('aria-current');
          }
          if (scrollCurrent && isCurrent && li.getClientRects().length) {
            var button = document.getElementById('btn-drawer');
            if (id === 'toc-list' || (button && button.getAttribute('aria-expanded') === 'true')) {
              li.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'auto' });
            }
          }
        });
      });
      var progress = document.getElementById('toc-progress');
      if (progress) {
        var count = Object.keys(state.chapters).filter(function (key) {
          return validChapter(Number(key)) && state.chapters[key] && state.chapters[key].read;
        }).length;
        progress.textContent = '已读 ' + count + ' / ' + chapterTotal + ' 章';
        if (validChapter(Number(state.last))) {
          var link = document.createElement('a');
          link.href = chapterHref(Number(state.last), document.getElementById('toc-list'));
          link.textContent = '继续阅读 第' + state.last + '章';
          progress.appendChild(document.createTextNode(' · '));
          progress.appendChild(link);
        }
      }
    }
    var continueLink = document.getElementById('continue-reading');
    if (continueLink) {
      var last = Number(state.last);
      continueLink.hidden = !validChapter(last);
      if (validChapter(last)) {
        continueLink.href = 'read/chapter-' + ('0' + last).slice(-2) + '.html';
        continueLink.textContent = '继续阅读 · 第' + last + '章（Chapter ' + last + '）';
      }
    }
    decorateDirectories(true);
    if (!reading) return;
    ['zh', 'en'].forEach(function (lang) {
      var pane = document.getElementById('pane-' + lang);
      if (!pane) return;
      var flow = pane.querySelector('.reader-flow');
      if (!flow) {
        flow = document.createElement('div');
        flow.className = 'reader-flow';
        while (pane.firstChild) flow.appendChild(pane.firstChild);
        pane.appendChild(flow);
      }
      models.push({ lang: lang, pane: pane, flow: flow,
        viewport: pane.querySelector('.reader-viewport') || flow.parentElement, page: 0, pages: 1 });
    });
    api.step = function (direction) {
      if (!paged()) return typeof oldStep === 'function' ? oldStep.apply(api, arguments) : undefined;
      // [用户反馈] 点击「下一屏」高频闪烁的根因：这里原来会同步跑一整轮 relayout()
      // （resetStyles 把所有行内样式还原 → layoutPages 再给表格套包装层、重新分列），
      // 手机上就是一次全量重排 + 重绘，紧接着 displayPage 又改一次 transform，表现为闪一下。
      // 翻页本身只需要改一个 transform：几何没有变化时不该重排。真正变了尺寸的场景
      // （旋转、窗口缩放、字号/主题/段式切换）由 scheduleLayout 负责，不会被这里吞掉。
      if (frame) {
        cancelAnimationFrame(frame);
        frame = 0;
        // [回归] 只兜「整章没排过」不够：切到某个从未分列过的栏时 ready 仍为 true，
        // 而该栏 m.pages 还是初值 1，next>=pages 恒真 → 「下一页」把读者踢到下一章。
        // paged 下视口是 overflow:hidden，未分列的栏既不能翻也不能滚，读者直接被卡死。
        // 取消 rAF 后必须无条件补排版（geometryKey 指纹会自动挡掉空转），
        // 否则会吞掉唯一一次排版机会、留下陈旧几何。
        var pending = active();
        if (!ready || !pending || pending.pages <= 1) relayout();
        else scheduleLayout();
      }
      var m = active(), delta = Number(direction) < 0 ? -1 : 1;
      if (!m) return;
      var next = m.page + delta;
      if (next < 0 || next >= m.pages) {
        persist();
        // 翻到本章第一页还想再退、或翻到最后一页还想再进：整页换章。
        // 目标取自 <link rel="prev|next">，与第 2 段 navigate 同一来源。
        var link = document.querySelector(delta < 0 ? 'link[rel="prev"]' : 'link[rel="next"]');
        if (link && link.getAttribute('href')) location.assign(link.href);
        return;
      }
      displayPage(m, next);
      if (state.settings.sync === true || state.settings.sync === 'on') {
        models.filter(visible).forEach(function (other) {
          if (other !== m) displayPage(other, (next / Math.max(1, m.pages - 1)) * (other.pages - 1));
        });
      }
      updateProgress();
      queueSave();
    };
    document.addEventListener('scroll', function () {
      if (!ready || frame || paged()) return;
      updateProgress();
      queueSave();
    }, true);
    document.addEventListener('click', function (event) {
      if (event.target.closest('[data-set]')) scheduleLayout();
    });
    new MutationObserver(function (changes) {
      // [回归] data-active-pane 原本被当成「非几何变化」，只存档不排版。
      // 但 geometryKey() 本来就包含「可见栏集合」：zh→en 换了可见栏，几何已经变了，
      // 新露出的那一栏却从未分列过。必须走 scheduleLayout()，不能只 updateProgress()。
      var geometry = changes.some(function (change) {
        return change.attributeName === 'data-active-pane';
      });
      if (geometry) scheduleLayout();
      else { updateProgress(); queueSave(); }
    }).observe(root, { attributes: true, attributeFilter: [
      'style', 'data-font', 'data-page-mode', 'data-lang-mode', 'data-dual-layout',
      'data-active-pane', 'data-paragraph'
    ] });
    var drawerButton = document.getElementById('btn-drawer');
    if (drawerButton) new MutationObserver(function () {
      cancelAnimationFrame(directoryFrame);
      directoryFrame = requestAnimationFrame(function () { decorateDirectories(true); });
    }).observe(drawerButton, { attributes: true, attributeFilter: ['aria-expanded'] });
    window.addEventListener('resize', scheduleLayout);
    if (window.ResizeObserver) {
      var observer = new ResizeObserver(scheduleLayout);
      observer.observe(main);
      models.forEach(function (m) { observer.observe(m.viewport); });
    }
    Array.prototype.forEach.call(main.querySelectorAll('img'), function (image) {
      image.addEventListener('load', scheduleLayout);
      image.addEventListener('error', scheduleLayout);
      if (image.decode) image.decode().then(scheduleLayout, function () {});
    });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(scheduleLayout);
    window.addEventListener('pagehide', persist);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') persist();
    });
    enhanceTranslatorNotes(main);
    scheduleLayout();
  }

  /* 译者注气泡。
     正文里是 <span class="tnote" note="cNN-sNNNN">被注词</span>，
     气泡内容集中挂在章尾的 .tnote-store 里，id 为 tn-<片段id>。
     悬停 / 聚焦开，点按切换（触屏与键盘走这条），Esc 与点外部关闭。
     翻页模式下正文被裁切，气泡因此挂在 body 上用 fixed 定位。 */
  /* [术语卡片] 译者注气泡与术语卡片是同一套浮层机制，共用下面这份 show/hide/
     place/reposition。两者只在三处不同：触发点选择器、卡片 id 前缀、以及卡片里
     含有链接（要允许指针从词移动到卡片上，以及点卡片内部不误判为「点外部」）。
     合成一个系统而不是各写一份，是为了让 Esc、焦点、滚动重定位这些行为只有一处实现。 */
  function enhanceTranslatorNotes(main) {
    if (!main) return;
    var triggers = Array.prototype.slice.call(main.querySelectorAll('.tnote[note]'))
      .concat(Array.prototype.slice.call(main.querySelectorAll('.term[data-term]')));
    if (!triggers.length) return;
    var bubbles = {};
    Array.prototype.forEach.call(document.querySelectorAll('.tnote-bubble'), function (node) {
      bubbles[node.id] = node;
    });
    var cards = {};
    Array.prototype.forEach.call(document.querySelectorAll('.term-card'), function (node) {
      cards[node.id] = node;
    });
    var open = null, closeTimer = 0, sticky = null;

    // 触发点 → 它对应的浮层。注走 tn-<片段id>，术语走 tc-<概念 id>。
    function bubbleOf(trigger) {
      if (!trigger) return null;
      if (trigger.classList && trigger.classList.contains('term')) {
        return cards['tc-' + trigger.getAttribute('data-term')] || null;
      }
      return bubbles['tn-' + trigger.getAttribute('note')] || null;
    }
    function isCard(node) {
      return !!(node && node.classList && node.classList.contains('term'));
    }

    // 可用竖直区间。[移动端] 不能拿 window.innerHeight 当边界：
    //  * 顶栏 #topbar 与底栏 #bottombar 都是 position: fixed，气泡若压上去会
    //    盖住「目录/设置/翻页」这些按钮（气泡 z-index 更高，会画在栏上面）。
    //  * 手机浏览器的地址栏会收缩：layout viewport 比 visual viewport 高，
    //    按 innerHeight 算「放得下」，实际有一截在地址栏底下看不见。
    // 所以先量 visualViewport，再把两条固定栏从区间里挖掉。
    // 栏高不写死：顶栏在 data-ui="hidden" 时会滑走，用测量天然跟随。
    function safeArea() {
      var vv = window.visualViewport;
      var top = vv ? vv.offsetTop : 0;
      var bottom = top + (vv ? vv.height : window.innerHeight);
      ['#topbar', '#bottombar'].forEach(function (sel) {
        var el = document.querySelector(sel);
        if (!el || !el.getClientRects().length) return;   // 隐藏 / 未渲染
        var r = el.getBoundingClientRect();
        if (r.height <= 0) return;
        if (r.top <= top + 1) top = Math.max(top, r.bottom);
        if (r.bottom >= bottom - 1) bottom = Math.min(bottom, r.top);
      });
      if (bottom - top < 80) {          // 区间被挤没了（极端窄屏），退回整屏
        top = 0; bottom = window.innerHeight;
      }
      return { top: top, bottom: bottom };
    }

    function place(trigger, bubble, minWidth) {
      var r = trigger.getBoundingClientRect();
      // 先显示再量，否则拿不到尺寸
      bubble.hidden = false;
      bubble.style.maxHeight = '';
      bubble.style.minWidth = minWidth ? minWidth + 'px' : '';
      var box = bubble.getBoundingClientRect();
      var area = safeArea();
      var gap = 8, edge = 10;
      var avail = area.bottom - area.top - 2 * edge;

      // 注比可用高度还长时，内部滚动，而不是溢出屏幕（手机上很常见）
      if (box.height > avail) {
        bubble.style.maxHeight = Math.max(120, Math.floor(avail)) + 'px';
        box = bubble.getBoundingClientRect();
      }

      var left = Math.min(
        Math.max(edge, r.left + r.width / 2 - box.width / 2),
        Math.max(edge, window.innerWidth - box.width - edge)
      );

      // 优先放在词下方；下方不够就翻到上方；两边都不够就夹回可用区间内
      var below = r.bottom + gap;
      var above = r.top - box.height - gap;
      var top;
      if (below + box.height <= area.bottom - edge) {
        top = below;
      } else if (above >= area.top + edge) {
        top = above;
      } else {
        top = Math.min(Math.max(below, area.top + edge),
                       Math.max(area.top + edge, area.bottom - box.height - edge));
      }

      bubble.style.left = Math.round(left) + 'px';
      bubble.style.top = Math.round(top) + 'px';
      return true;
    }

    function show(trigger) {
      var bubble = bubbleOf(trigger);
      if (!bubble) return;
      if (open && open !== trigger) hide();
      window.clearTimeout(closeTimer);
      open = trigger;
      trigger.setAttribute('aria-expanded', 'true');
      // 术语卡比注宽得多，给一个下限宽度；窄屏由 place 的夹取逻辑收进视口。
      place(trigger, bubble, isCard(trigger) ? 260 : 0);
    }

    function hide() {
      if (!open) return;
      var bubble = bubbleOf(open);
      open.setAttribute('aria-expanded', 'false');
      if (bubble) bubble.hidden = true;
      open = null;
    }

    // 滚动 / 改字号 / 翻页后词会移动：气泡是 fixed 定位，不重算就停在旧坐标上。
    // 这里**重新定位**而不是关闭 —— 点按一个视口外的词时，浏览器会先把它
    // 滚进视口，那一下 scroll 紧跟着 click/hover，一关就把刚打开的气泡又收走了。
    // 「词已滚出视口就收掉」的判断也放在这里（下一帧），不能放在 show 当场：
    // mouseenter 触发时浏览器可能刚开始把词滚进视口，那一刻量到的仍是屏幕外坐标。
    var repositionFrame = 0;
    function reposition() {
      cancelAnimationFrame(repositionFrame);
      repositionFrame = requestAnimationFrame(function () {
        if (!open) return;
        var bubble = bubbleOf(open);
        if (!bubble) return;
        var r = open.getBoundingClientRect();
        var area = safeArea();
        if (r.bottom < area.top || r.top > area.bottom
            || r.right < 0 || r.left > window.innerWidth) {
          hide();
          return;
        }
        place(open, bubble, isCard(open) ? 260 : 0);
      });
    }

    triggers.forEach(function (trigger) {
      var bubble = bubbleOf(trigger);
      if (!bubble) return;   // 注内容缺失：保持虚线样式但不弹空泡
      trigger.addEventListener('mouseenter', function () { show(trigger); });
      trigger.addEventListener('mouseleave', function () {
        closeTimer = window.setTimeout(hide, 160);
      });
      trigger.addEventListener('focus', function () { show(trigger); });
      trigger.addEventListener('blur', hide);
      trigger.addEventListener('click', function (event) {
        event.stopPropagation();
        // 指针本来就在词上时，click 之前必然已经先来过 mouseenter 把气泡打开了。
        // 若这里还按「切换」处理，点一下就等于「开→立刻关」，词只闪一下就没了。
        // 所以：只有当上一次是**点按**打开的（触屏没有 mouseleave 可依赖），
        // 再点一下才收起；其余情况一律显示。
        if (open === trigger && sticky === trigger) { hide(); sticky = null; }
        else { sticky = trigger; show(trigger); }
      });
      trigger.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          if (open === trigger) hide(); else show(trigger);
        }
      });
      // 术语卡里有链接，读者要把指针从词移到卡上点章号。
      // 词上 mouseleave 起了 160ms 关闭定时器，卡上的 mouseenter 把它取消掉。
      bubble.addEventListener('mouseenter', function () {
        window.clearTimeout(closeTimer);
      });
      bubble.addEventListener('mouseleave', function () {
        closeTimer = window.setTimeout(hide, 160);
      });
      // 点在卡片内部（选文字、准备点链接）不该被当成「点外部」而收起
      bubble.addEventListener('click', function (event) { event.stopPropagation(); });
    });

    document.addEventListener('click', function (event) {
      var bubble = bubbleOf(open);
      if (bubble && event.target && bubble.contains(event.target)) return;
      hide();
    });
    // 捕获阶段处理 Esc：全局那个 Esc 处理器（关面板 / 显隐菜单）注册在更早，
    // 冒泡阶段会先跑；不抢在前面的话，卡片开着时按 Esc 关掉的是菜单而不是卡片。
    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape' || !open) return;
      event.preventDefault();
      event.stopPropagation();
      hide();
    }, true);
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    window.addEventListener('orientationchange', reposition);
    // [移动端] 地址栏收缩/展开只改 visualViewport，不一定触发 window.resize；
    // 漏掉它的话气泡会停在旧坐标，看起来就是「位置不对」。
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', reposition);
      window.visualViewport.addEventListener('scroll', reposition);
    }
    new MutationObserver(reposition).observe(document.documentElement, {
      attributes: true,
      attributeFilter: [
        'style', 'data-font', 'data-page-mode', 'data-lang-mode', 'data-dual-layout',
        'data-active-pane', 'data-paragraph'
      ]
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhancePages);
  } else enhancePages();
}());
