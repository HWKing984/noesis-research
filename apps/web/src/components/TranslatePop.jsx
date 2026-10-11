/**
 * 点击翻译 / 点击解释 —— NOESIS「钉住」交互（D:\a-Soft Term.jsx）的双 tab 承载。
 *
 * 交互契约与 Term.jsx 逐条对齐（这条契约是有测试守着的，别改）：
 *   hover 140ms 预览 → click 钉住（tooltip 升格 dialog）→
 *   Esc / 点外部 / 再点一次锚点 关闭 → 钉住后 hover 别的锚点不抢 →
 *   CLOSE_DELAY 220ms（让鼠标能移进浮层）→ mousemove 滚轮守卫（Chrome 滚动
 *   不补发 mouseout）→ placeNear 定位（优先下方，空间不够翻上方）→ portal 到 body。
 *
 * 两个 tab，两种内容、同一条边界：
 *   翻译 tab —— hover 预览就是它（快）；钉住后可对照原文/复制/重译。
 *   解释 tab —— NOESIS 概念卡的移植（类别/一句话定义/详解/为什么重要/例子 +
 *   「更简单一点」重问）。解释生成慢，只在钉住态可达；样式 simple 是缓存键
 *   的一部分，「更简单一点」必然真的再问一次模型。
 *
 * 点击用 **capture 阶段** 委托（NOESIS TermPopoverHost 同款）：锚点常嵌在
 * 自己有点击行为的卡片里（rail 论文卡），stopPropagation 必须发生在
 * React 的委托 root 之前才拦得住。
 *
 * 硬边界：**译文与解释都不是证据** —— 不产生 EvidenceRef、不进引用核查；
 * 浮层里常驻这句声明。失败如实显示（503/502 各自有文案），原文绝不会被
 * 冒充成译文，模型失败也绝不会被一段编出来的解释掩盖。
 */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import {
  describeExplainError,
  describeTranslateError,
  glossLabel,
  parseExplainResponse,
  parseTranslateResponse,
} from '../lib/translate.js';

const HOVER_DELAY = 140; // 防误触：鼠标划过不要立刻弹
const CLOSE_DELAY = 220; // 移出后留点时间，让鼠标能移到浮层里

/** 定位：优先贴锚点下方，空间不够翻到上方；左右夹在视口内（照 Term.jsx placeNear）。 */
export function placeNear(anchorEl, popEl) {
  if (!anchorEl || !popEl) return null;
  const a = anchorEl.getBoundingClientRect();
  const pw = popEl.offsetWidth;
  const ph = popEl.offsetHeight;
  const gap = 8;

  let top = a.bottom + gap;
  if (top + ph > window.innerHeight - 12) {
    const above = a.top - gap - ph;
    top = above >= 12 ? above : Math.max(12, window.innerHeight - ph - 12);
  }
  let left = a.left + a.width / 2 - pw / 2;
  left = Math.max(12, Math.min(left, window.innerWidth - pw - 12));
  return { top, left };
}

/** 本会话的翻译结果缓存：同一段文字只翻一次（后端还有磁盘缓存兜底）。 */
function createTranslateCache(api) {
  const byKey = new Map();
  const inflight = new Map();
  const keyOf = (text, kind) => `${kind}|${text}`;
  return {
    get: (text, kind) => byKey.get(keyOf(text, kind)),
    drop: (text, kind) => byKey.delete(keyOf(text, kind)),
    load(text, kind) {
      const key = keyOf(text, kind);
      if (byKey.has(key)) return Promise.resolve(byKey.get(key));
      if (inflight.has(key)) return inflight.get(key);
      const pending = api
        .translate(text, kind)
        .then((payload) => {
          const value = parseTranslateResponse(payload, { originalText: text });
          byKey.set(key, value);
          return value;
        })
        .finally(() => inflight.delete(key));
      inflight.set(key, pending);
      return pending;
    },
  };
}

/** 解释缓存。key 含 kind + style（「更简单一点」= 换一个缓存条目，真再问一次）。 */
function createExplainCache(api) {
  const byKey = new Map();
  const inflight = new Map();
  const keyOf = (text, kind, style) => `${kind}|${style}|${text}`;
  return {
    drop: (text, kind, style) => byKey.delete(keyOf(text, kind, style)),
    load(text, kind, style, context) {
      const key = keyOf(text, kind, style);
      if (byKey.has(key)) return Promise.resolve(byKey.get(key));
      if (inflight.has(key)) return inflight.get(key);
      const pending = api
        .explain(text, kind, { style, context })
        .then((payload) => {
          const value = parseExplainResponse(payload);
          byKey.set(key, value);
          return value;
        })
        .finally(() => inflight.delete(key));
      inflight.set(key, pending);
      return pending;
    },
  };
}

/** 解释 tab 的正文（只在钉住态渲染——解释慢，hover 预览保持是翻译）。 */
export function ExplainBody({ style, value, onSimpler }) {
  const detailParts = String(value.detail).split(/\n+/).filter(Boolean);
  const copyText = [value.brief, value.detail, `为什么重要：${value.whyItMatters}`, `例子：${value.example}`].join('\n');
  return (
    <>
      <span className="tr-pop-cat" data-testid="explain-category">{value.category}</span>
      <p className="tr-pop-brief" data-testid="explain-brief">{value.brief}</p>
      <div className="tr-pop-sec">
        <div className="k">是什么</div>
        <div className="v" data-testid="explain-detail">
          {detailParts.map((part, i) => <p key={i}>{part}</p>)}
        </div>
      </div>
      <div className="tr-pop-sec">
        <div className="k">为什么重要</div>
        <div className="v" data-testid="explain-why">{value.whyItMatters}</div>
      </div>
      <div className="tr-pop-sec">
        <div className="k">例子</div>
        <div className="v" data-testid="explain-example">{value.example}</div>
      </div>
      <div className="tr-pop-note">
        AI 生成的解释，<b>不是证据</b>——引用仍指向原文来源 id，解释不进引用核查。
      </div>
      <div className="tr-pop-acts">
        <button type="button" data-testid="explain-copy" onClick={() => navigator.clipboard?.writeText(copyText)}>
          复制解释
        </button>
        {style === 'simple' ? (
          <span className="tr-pop-hint">已是简化版</span>
        ) : (
          <button type="button" data-testid="explain-simpler" onClick={onSimpler}>更简单一点</button>
        )}
      </div>
      {value.cached ? <div className="tr-pop-hint">来自缓存</div> : null}
    </>
  );
}

/** 浮层本体：只负责展示。tab ∈ 'tr' | 'ex'。 */
export function TranslatePop({
  kind, text, pinned, tab, style, pos, popRef,
  loading, value, error,
  onClose, onTab, onRetranslate, onSimpler, onMouseEnter, onMouseLeave,
}) {
  const label = tab === 'ex'
    ? '解释'
    : kind === 'title' ? '标题翻译' : kind === 'abstract' ? '摘要翻译' : '翻译';
  const failure = error
    ? (tab === 'ex' ? describeExplainError(error) : describeTranslateError(error))
    : null;
  return (
    <div
      ref={popRef}
      className="tr-pop"
      role={pinned ? 'dialog' : 'tooltip'}
      aria-label={tab === 'ex' ? '概念解释（AI 生成）' : `${label}（机器翻译）`}
      data-testid="translate-pop"
      data-tab={tab}
      data-pinned={pinned ? 'true' : 'false'}
      style={{
        top: pos ? `${pos.top}px` : '-9999px',
        left: pos ? `${pos.left}px` : '-9999px',
        visibility: pos ? 'visible' : 'hidden',
      }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="tr-pop-head">
        {pinned ? (
          <span className="tr-pop-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'tr'}
              className={tab === 'tr' ? 'is-on' : ''}
              data-testid="pop-tab-tr"
              onClick={() => onTab('tr')}
            >
              翻译
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'ex'}
              className={tab === 'ex' ? 'is-on' : ''}
              data-testid="pop-tab-ex"
              onClick={() => onTab('ex')}
            >
              解释
            </button>
          </span>
        ) : (
          <span className="tr-pop-name">{label}</span>
        )}
        <span className={`tr-pop-tag ${tab === 'ex' ? 'is-ai' : 'is-mt'}`}>
          {tab === 'ex' ? 'AI 解释' : '机器翻译'}
        </span>
        {pinned && (
          <button type="button" className="tr-pop-close" title="关闭（Esc）" onClick={onClose} data-testid="translate-close">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {loading && (
        <p className="tr-pop-brief" data-testid="translate-loading">{tab === 'ex' ? '正在解释…' : '正在翻译…'}</p>
      )}

      {!loading && failure && (
        <div className="tr-pop-fail" data-testid={tab === 'ex' ? 'explain-error' : 'translate-error'} role="alert">
          <b>{failure.title}</b>
          <p>{failure.detail}</p>
        </div>
      )}

      {!loading && !failure && tab === 'tr' && value && (
        <>
          <p className="tr-pop-brief" data-testid="translate-zh">{value.zh}</p>
          {pinned && (
            <>
              <div className="tr-pop-sec">
                <div className="k">原文</div>
                <div className="v orig">{text}</div>
              </div>
              {glossLabel(value.keptTerms) ? (
                <div className="tr-pop-sec">
                  <div className="k">术语处理</div>
                  <div className="v">{glossLabel(value.keptTerms)}</div>
                </div>
              ) : null}
              <div className="tr-pop-note">
                译文只是阅读辅助，<b>不是证据</b>——引用仍指向原文来源 id，翻译不进引用核查。
              </div>
              <div className="tr-pop-acts">
                <button type="button" data-testid="translate-copy" onClick={() => navigator.clipboard?.writeText(value.zh)}>
                  复制译文
                </button>
                <button type="button" data-testid="translate-retry" onClick={onRetranslate}>重译</button>
              </div>
              {value.cached ? <div className="tr-pop-hint">来自缓存</div> : null}
            </>
          )}
        </>
      )}

      {!loading && !failure && tab === 'ex' && value && pinned && (
        <ExplainBody style={style} value={value} onSimpler={onSimpler} />
      )}

      {!pinned && <div className="tr-pop-hint">点击可钉住，钉住后可切换「解释」</div>}
    </div>
  );
}

/**
 * 事件委托宿主。挂在 App 根部一次，所有 `.tr-anchor[data-tr-text]` 自动可用 ——
 * 锚点散在 rail / 详情面板 / 证据抽屉三个组件里，不需要每个都接一遍。
 * 锚点可选 `data-tr-context`（如论文题名），作为解释的"结合当前内容"语境。
 */
export default function TranslateHost({ api }) {
  const [state, setState] = useState(null); // { anchor, text, kind, context, pinned, tab, style }
  const [entry, setEntry] = useState(null); // { loading, value, error }
  const [pos, setPos] = useState(null);
  const popRef = useRef(null);
  const hoverTimer = useRef(null);
  const closeTimer = useRef(null);
  const requestId = useRef(0);
  const trCache = useRef(null);
  const exCache = useRef(null);
  if (trCache.current === null) trCache.current = createTranslateCache(api);
  if (exCache.current === null) exCache.current = createExplainCache(api);

  const clearTimers = () => {
    if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null; }
    if (closeTimer.current) { clearTimeout(closeTimer.current); closeTimer.current = null; }
  };
  useEffect(() => clearTimers, []);

  const showEntry = (text, kind, tab, style, context) => {
    const id = ++requestId.current;
    if (tab === 'ex') {
      const pending = () => {
        setEntry({ loading: true, value: null, error: null });
        exCache.current
          .load(text, kind, style, context)
          .then((value) => { if (id === requestId.current) setEntry({ loading: false, value, error: null }); })
          .catch((cause) => { if (id === requestId.current) setEntry({ loading: false, value: null, error: cause }); });
      };
      pending();
      return;
    }
    const cached = trCache.current.get(text, kind);
    if (cached) {
      setEntry({ loading: false, value: cached, error: null });
      return;
    }
    setEntry({ loading: true, value: null, error: null });
    trCache.current
      .load(text, kind)
      .then((value) => { if (id === requestId.current) setEntry({ loading: false, value, error: null }); })
      .catch((cause) => { if (id === requestId.current) setEntry({ loading: false, value: null, error: cause }); });
  };

  // 锚点 / tab / style 变化 → 取结果
  useEffect(() => {
    if (!state) { setEntry(null); return undefined; }
    showEntry(state.text, state.kind, state.tab, state.style, state.context);
    return () => { requestId.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state?.anchor, state?.text, state?.kind, state?.tab, state?.style]);

  // 定位：内容（loading→结果）变了高度会变，需要重算
  useLayoutEffect(() => {
    if (!state) { setPos(null); return undefined; }
    const update = () => setPos(placeNear(state.anchor, popRef.current));
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [state, entry]);

  // hover 预览 / click 钉住（capture：锚点嵌在可点击卡片里，必须先于 React 拦下）
  useEffect(() => {
    const anchorOf = (target) => target.closest?.('.tr-anchor[data-tr-text]');
    const onOver = (e) => {
      const el = anchorOf(e.target);
      if (!el) return;
      clearTimers();
      if (state?.pinned) return; // 钉住后 hover 不抢（NOESIS 契约）
      hoverTimer.current = setTimeout(() => {
        setState({ anchor: el, text: el.dataset.trText, kind: el.dataset.trKind || 'text', context: el.dataset.trContext || '', pinned: false, tab: 'tr', style: 'normal' });
      }, HOVER_DELAY);
    };
    const onOut = (e) => {
      if (!anchorOf(e.target) || state?.pinned) return;
      if (e.relatedTarget && popRef.current?.contains(e.relatedTarget)) return;
      scheduleClose();
    };
    const onClick = (e) => {
      const el = anchorOf(e.target);
      if (!el) return;
      e.preventDefault();
      e.stopPropagation();
      clearTimers();
      setState((s) => {
        if (s?.pinned && s.anchor === el) return null; // 再点一次收起
        return { anchor: el, text: el.dataset.trText, kind: el.dataset.trKind || 'text', context: el.dataset.trContext || '', pinned: true, tab: s?.anchor === el ? s.tab : 'tr', style: 'normal' };
      });
    };
    document.addEventListener('mouseover', onOver);
    document.addEventListener('mouseout', onOut);
    document.addEventListener('click', onClick, true);
    return () => {
      document.removeEventListener('mouseover', onOver);
      document.removeEventListener('mouseout', onOut);
      document.removeEventListener('click', onClick, true);
    };
  }, [state]);

  // 钉住态才接管外部点击；hover 态由 mouseleave 自己收走
  useEffect(() => {
    if (!state?.pinned) return undefined;
    const onDown = (e) => {
      if (popRef.current?.contains(e.target)) return;
      if (state.anchor?.contains(e.target)) return;
      setState(null);
    };
    const onKey = (e) => { if (e.key === 'Escape') setState(null); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [state]);

  // 滚轮守卫：滚动不补发 mouseout，悬浮浮层会挂着不消失（照 Term 的兜底）
  useEffect(() => {
    if (!state || state.pinned) return undefined;
    const onMove = (e) => {
      const t = e.target;
      if (popRef.current?.contains(t)) return;
      if (state.anchor?.contains(t)) return;
      if (t?.closest?.('.tr-anchor[data-tr-text]')) return; // 正划向别的锚点，交给 onOver 原地切换
      scheduleClose();
    };
    document.addEventListener('mousemove', onMove);
    return () => document.removeEventListener('mousemove', onMove);
  }, [state]);

  function scheduleClose() {
    clearTimers();
    closeTimer.current = setTimeout(() => setState(null), CLOSE_DELAY);
  }

  if (!state) return null;
  return createPortal(
    <TranslatePop
      kind={state.kind}
      text={state.text}
      pinned={state.pinned}
      tab={state.tab}
      style={state.style}
      pos={pos}
      popRef={popRef}
      loading={entry?.loading}
      value={entry?.value}
      error={entry?.error}
      onClose={() => setState(null)}
      onTab={(tab) => setState((s) => (s ? { ...s, tab } : s))}
      onMouseEnter={clearTimers}
      onMouseLeave={() => { if (!state.pinned) scheduleClose(); }}
      onRetranslate={() => {
        trCache.current.drop(state.text, state.kind);
        showEntry(state.text, state.kind, 'tr', state.style, state.context);
      }}
      onSimpler={() => {
        setState((s) => (s ? { ...s, style: 'simple' } : s));
      }}
    />,
    document.body,
  );
}
