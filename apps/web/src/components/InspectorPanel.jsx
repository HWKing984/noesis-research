import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';

import { EvidenceChip, EvidenceGate } from './StatusPieces.jsx';
import { countCandidates } from '../lib/evidence.js';

/** 论文详情。作者身份状态、候选断言、引文草稿都原样展示，不加工成"结论"。 */
export function DetailPanel({ detail, onInspect, onOpenPaper }) {
  if (!detail) return null;
  const { publication, authors, venues, mentions, assertions, citationDraft, notice } = detail;
  const candidates = countCandidates(assertions);
  const publicationContext = {
    title: publication.title,
    publicationId: publication.publicationId,
  };

  return (
    <div className="space-y-4 px-5 py-4" data-testid="detail-panel">
      <div>
        <h2 className="text-[15px] font-semibold leading-snug" data-testid="detail-title">
          {publication.title}
        </h2>
        <div className="mono mt-1 text-[11px] text-[var(--ink-muted)]" data-testid="detail-id">
          {publication.publicationId}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <EvidenceChip
            reference={publication.evidence}
            context={publicationContext}
            onInspect={onInspect}
          />
          {publication.doi ? (
            <a
              className="text-[11px] text-[var(--accent)] underline"
              href={`https://doi.org/${publication.doi}`}
              target="_blank"
              rel="noreferrer noopener"
            >
              DOI
            </a>
          ) : null}
          {publication.dblpUrl ? (
            <a
              className="text-[11px] text-[var(--accent)] underline"
              href={publication.dblpUrl}
              target="_blank"
              rel="noreferrer noopener"
            >
              DBLP
            </a>
          ) : null}
          {publication.urls?.map((url) => (
            <a
              key={url}
              className="text-[11px] text-[var(--accent)] underline"
              href={url}
              target="_blank"
              rel="noreferrer noopener"
            >
              外链
            </a>
          ))}
        </div>
      </div>

      <Section title={`作者（${authors.length}）`}>
        <ul className="space-y-1" data-testid="author-list">
          {authors.map((author) => (
            <li key={`${author.name}-${author.position}`} className="flex flex-wrap items-center gap-2 text-[12px]">
              <span className="text-[var(--ink-muted)]">{author.position}.</span>
              <span>{author.signatureName || author.name}</span>
              {author.identityStatus ? (
                <span className="rounded bg-[var(--bg)] px-1.5 py-0.5 text-[10px] text-[var(--ink-muted)]">
                  {author.identityStatus}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`会议 / 期刊（${venues.length}）`}>
        <div className="flex flex-wrap gap-1.5 text-[12px]">
          {venues.map((venue) => (
            <span key={venue.name} className="rounded border border-[var(--line)] px-1.5 py-0.5">
              {venue.name}
            </span>
          ))}
        </div>
      </Section>

      <Section title={`实体提及（${mentions.length}）`}>
        <div className="flex flex-wrap gap-1.5" data-testid="mention-list">
          {mentions.map((mention, index) => (
            <span
              key={`${mention.text}-${index}`}
              className="rounded border border-[var(--line)] bg-[var(--panel)] px-1.5 py-0.5 text-[11px]"
            >
              {mention.text}
              <span className="ml-1 text-[10px] text-[var(--ink-muted)]">{mention.label}</span>
            </span>
          ))}
        </div>
      </Section>

      <Section
        title={`候选断言（${assertions.length}${candidates ? ` · 其中候选 ${candidates}` : ''}）`}
        hint="方法—任务 / 方法—数据集关系由模型从题名抽取，状态恒为 candidate，不是已核实事实。"
      >
        {assertions.length === 0 ? (
          <p className="text-[12px] text-[var(--ink-muted)]">本篇没有抽取到候选断言。</p>
        ) : (
          <ul className="space-y-2" data-testid="assertion-list">
            {assertions.map((assertion) => (
              <li
                key={assertion.id}
                className="rounded-lg border border-[var(--line)] bg-[var(--panel)] px-3 py-2"
                data-testid="assertion-item"
                data-status={assertion.status}
              >
                <div className="flex flex-wrap items-center gap-2 text-[12px]">
                  <span className="rounded bg-[var(--candidate-soft)] px-1.5 py-0.5 text-[11px] text-[var(--candidate)]">
                    候选
                  </span>
                  <code className="mono">{assertion.predicate}</code>
                  <span className="text-[var(--ink-muted)]">
                    {assertion.head?.text} → {assertion.tail?.text}
                  </span>
                  {assertion.confidence != null ? (
                    <span className="text-[11px] text-[var(--ink-muted)]">
                      分数 {assertion.confidence.toFixed(4)}
                      {assertion.confidenceCalibrated ? '' : '（未校准）'}
                    </span>
                  ) : null}
                </div>
                <div className="mt-1.5">
                  <EvidenceChip
                    reference={assertion.evidence}
                    context={{
                      title: assertion.evidenceText || publication.title,
                      publicationId: publication.publicationId,
                      predicate: assertion.predicate,
                      head: assertion.head?.text,
                      tail: assertion.tail?.text,
                    }}
                    onInspect={onInspect}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {citationDraft ? (
        <Section title="引文草稿" hint="这是草稿，引用前须核对原文与书目信息。">
          <p className="mono text-[11px] leading-relaxed text-[var(--ink-muted)]" data-testid="citation-draft">
            {citationDraft}
          </p>
        </Section>
      ) : null}

      {notice ? (
        <p className="rounded border border-[var(--line)] bg-[var(--bg)] px-3 py-2 text-[11px] text-[var(--ink-muted)]">
          {notice}
        </p>
      ) : null}
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <section>
      <h3 className="mb-1.5 text-[12px] font-medium">{title}</h3>
      {hint ? <p className="mb-2 text-[11px] text-[var(--ink-muted)]">{hint}</p> : null}
      {children}
    </section>
  );
}

const MODE_LABELS = {
  paper: '本篇关系',
  coauthors: '共同作者',
  methods: '共享方法',
};

const KIND_ZH = {
  Publication: '论文', Person: '作者', Venue: '会议', Concept: '概念',
  Task: '任务', Dataset: '数据集', Mention: '提及', Assertion: '断言',
};

/**
 * 局部知识图谱 —— force-graph 内核（canvas）。
 *
 * 移植自 NOESIS `KnowledgeForceGraph`（同栈 react-force-graph-2d + d3-force）：
 * 节点可拖拽（松手后回力场）、滚轮缩放、空白平移；hover 高亮邻接；点击节点看属性。
 * 渲染走 canvas，交互不在 DOM 里 —— 因此同时渲染一份 `.sr-only` 节点/边清单：
 * e2e 与读屏都通过它核对数据侧，canvas 只负责视觉。
 */
export function GraphPanel({ slice, busy, mode, onModeChange, onRefresh, appearance = 'light' }) {
  const graphRef = useRef(null);
  // callback ref：GraphPanel 有 `if (!slice) return` 早退分支 —— 挂载 ref 的元素会随分支切换重建。
  // 常规 useRef 在早退态拿到 null 且 effect 不重跑，RO 就永远挂不上（canvas 停在 1x1）。
  // callback ref + 依赖 [containerEl]：每次节点重建都重新 observe。
  const [containerEl, setContainerEl] = useState(null);
  const [size, setSize] = useState({ w: 1, h: 1 });
  const [hoverId, setHoverId] = useState(null);
  const [nodeInfo, setNodeInfo] = useState(null);

  useEffect(() => {
    if (!containerEl) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      setSize({
        w: Math.max(1, Math.floor(entry.contentRect.width)),
        h: Math.max(1, Math.floor(entry.contentRect.height)),
      });
    });
    observer.observe(containerEl);
    return () => observer.disconnect();
  }, [containerEl]);

  const graphData = useMemo(() => {
    if (!slice) return null;
    const nodes = slice.nodes.map((node) => ({
      id: node.id,
      kind: node.kind,
      label: node.props?.title || node.props?.name || node.props?.text || KIND_ZH[node.kind] || node.kind,
      isRoot: node.id === slice.rootId,
      raw: node,
    }));
    const index = new Map(nodes.map((n) => [n.id, n]));
    const links = slice.edges
      .filter((e) => index.has(e.source) && index.has(e.target))
      .map((e) => ({ id: e.id, source: e.source, target: e.target, kind: e.kind }));
    return { nodes, links };
  }, [slice]);

  const neighbors = useMemo(() => {
    const next = new Map();
    if (!graphData) return next;
    const linkId = (v) => (typeof v === 'string' ? v : v?.id);
    graphData.links.forEach((link) => {
      const s = linkId(link.source);
      const t = linkId(link.target);
      if (!s || !t) return;
      if (!next.has(s)) next.set(s, new Set());
      if (!next.has(t)) next.set(t, new Set());
      next.get(s).add(t);
      next.get(t).add(s);
    });
    return next;
  }, [graphData]);

  // canvas 颜色不能在 render 阶段读 getComputedStyle：data-theme 由 App 的 effect 写入，
  // 子组件 render 时 dataset 还是旧值（竞态）。直接按 appearance 映射 index.css 的 token 值。
  const colors = useMemo(() => (appearance === 'dark'
    ? { ink: '#ececf1', line: 'rgba(255,255,255,0.15)', sub: '#71717a', node: '#a1a1aa' }
    : { ink: '#1a1a1c', line: 'rgba(0,0,0,0.16)', sub: '#8b8b92', node: '#525257' }), [appearance]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph || !graphData) return;
    graph.d3Force('charge')?.strength(-320);
    graph.d3Force('link')?.distance(110).strength(0.35);
    graph.d3ReheatSimulation();
  }, [graphData, size.w, size.h]);

  const fitView = useCallback(() => graphRef.current?.zoomToFit(400, 46), []);
  useEffect(() => {
    if (!slice) return undefined;
    const timer = window.setTimeout(fitView, 900);
    return () => window.clearTimeout(timer);
  }, [slice, fitView]);

  const resetLayout = useCallback(() => {
    if (!graphData) return;
    graphData.nodes.forEach((node) => { node.vx = 0; node.vy = 0; });
    graphRef.current?.d3ReheatSimulation();
    window.setTimeout(fitView, 900);
  }, [graphData, fitView]);

  const paintLink = useCallback((link, ctx, globalScale) => {
    const source = typeof link.source === 'string' ? null : link.source;
    const target = typeof link.target === 'string' ? null : link.target;
    if (!source || !target) return;
    const focus = hoverId && (source.id === hoverId || target.id === hoverId);
    ctx.save();
    ctx.globalAlpha = focus ? 0.95 : 0.5;
    ctx.strokeStyle = focus ? colors.ink : colors.line;
    ctx.lineWidth = (focus ? 1.6 : 1) / globalScale;
    ctx.beginPath();
    ctx.moveTo(source.x, source.y);
    ctx.lineTo(target.x, target.y);
    ctx.stroke();
    if (focus && link.kind) {
      ctx.globalAlpha = 0.95;
      ctx.fillStyle = colors.sub;
      ctx.font = `${10 / globalScale}px system-ui, sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText(link.kind, (source.x + target.x) / 2, (source.y + target.y) / 2 - 4 / globalScale);
    }
    ctx.restore();
  }, [colors, hoverId]);

  const paintNode = useCallback((node, ctx, globalScale) => {
    const x = node.x || 0;
    const y = node.y || 0;
    const isRoot = node.isRoot;
    const radius = isRoot ? 15 : 7;
    const hovered = hoverId === node.id;
    const related = !hoverId || hovered || (neighbors.get(hoverId) || new Set()).has(node.id);
    ctx.save();
    ctx.globalAlpha = related ? 1 : 0.3;
    ctx.fillStyle = isRoot ? colors.ink : colors.node;
    ctx.beginPath();
    ctx.arc(x, y, hovered ? radius * 1.2 : radius, 0, Math.PI * 2);
    ctx.fill();
    if (hovered) {
      ctx.strokeStyle = colors.ink;
      ctx.lineWidth = 1.6 / globalScale;
      ctx.beginPath();
      ctx.arc(x, y, radius * 1.2 + 3 / globalScale, 0, Math.PI * 2);
      ctx.stroke();
    }
    const label = (isRoot ? '' : `${KIND_ZH[node.kind] || node.kind} · `) + node.label;
    ctx.globalAlpha = related ? 0.92 : 0.3;
    ctx.fillStyle = colors.sub;
    ctx.font = `${10.5 / globalScale}px system-ui, sans-serif`;
    ctx.textAlign = 'center';
    ctx.fillText(label, x, y - radius - 5 / globalScale);
    ctx.restore();
  }, [colors, hoverId, neighbors]);

  const paintNodePointerArea = useCallback((node, color, ctx, globalScale) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(node.x || 0, node.y || 0, (node.isRoot ? 15 : 7) + 8 / globalScale, 0, Math.PI * 2);
    ctx.fill();
  }, []);

  if (!slice) {
    return (
      <div className="graph-panel" data-testid="graph-panel">
        <p className="text-[12px] text-[var(--ink-muted)]">选择一篇论文后载入局部图谱。</p>
      </div>
    );
  }

  return (
    <div className="graph-panel" data-testid="graph-panel">
      <div className="gp-toolbar">
        <div className="seg">
          {Object.keys(MODE_LABELS).map((key) => (
            <button
              key={key}
              type="button"
              disabled={busy}
              onClick={() => onModeChange(key)}
              data-testid="graph-mode"
              data-mode={key}
              data-active={mode === key ? 'true' : 'false'}
              className={mode === key ? 'is-on' : ''}
            >
              {MODE_LABELS[key]}
            </button>
          ))}
        </div>
        <button type="button" onClick={onRefresh} disabled={busy} className="gp-btn">
          重新载入
        </button>
        <button type="button" onClick={fitView} className="gp-btn" data-testid="graph-fit">
          适应窗口
        </button>
        <button type="button" onClick={resetLayout} className="gp-btn" data-testid="graph-reset">
          重置布局
        </button>
        {busy ? <span className="text-[11px] text-[var(--ink-muted)]">加载中…</span> : null}
      </div>

      <div className="gp-canvas" ref={setContainerEl}>
        {graphData ? (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={size.w}
            height={size.h}
            backgroundColor="rgba(0,0,0,0)"
            nodeRelSize={5}
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => 'replace'}
            nodePointerAreaPaint={paintNodePointerArea}
            linkCanvasObject={paintLink}
            linkCanvasObjectMode={() => 'replace'}
            enableNodeDrag
            onNodeHover={(node) => setHoverId(node ? node.id : null)}
            onNodeClick={(node) => setNodeInfo(node)}
            onBackgroundClick={() => setNodeInfo(null)}
            onNodeDragEnd={(node) => {
              window.setTimeout(() => { node.fx = undefined; node.fy = undefined; }, 120);
            }}
            warmupTicks={60}
            cooldownTicks={140}
          />
        ) : null}
        <div className="gp-info" data-testid="graph-nodeinfo">
          {nodeInfo
            ? `${KIND_ZH[nodeInfo.kind] || nodeInfo.kind}：${nodeInfo.label} · 属性来自真实 Neo4j（identityStatus / 候选标记）`
            : '拖动节点重排 · 滚轮缩放 · 拖空白平移 · 点击节点看属性'}
        </div>
        <ul className="sr-only" data-testid="graph-node-list">
          {graphData?.nodes.map((node) => (
            <li key={node.id} data-testid="graph-node" data-kind={node.kind} data-root={String(node.isRoot)}>
              {node.label}
            </li>
          ))}
        </ul>
        <ul className="sr-only" data-testid="graph-edge-list">
          {graphData?.links.map((link) => {
            const s = typeof link.source === 'string' ? link.source : link.source?.id;
            const t = typeof link.target === 'string' ? link.target : link.target?.id;
            return <li key={link.id} data-testid="graph-edge" data-source={s} data-target={t}>{link.kind}</li>;
          })}
        </ul>
      </div>

      <dl className="gp-stats">
        <div>
          节点 <b className="text-[var(--ink)]">{slice.nodes.length}</b> · 关系{' '}
          <b className="text-[var(--ink)]">{slice.edges.length}</b> · 路径{' '}
          <b className="text-[var(--ink)]">{slice.paths.length}</b>
        </div>
        <div>
          graphId <code className="mono text-[var(--ink)]">{slice.graphId}</code>
        </div>
        <div>
          还有更多路径：{slice.hasMorePaths ? '是（已截断）' : '否'} · 极局部：
          {slice.notice?.includes('局部') ? '是' : '否'}
        </div>
      </dl>
      <p className="gp-notice">{slice.notice}</p>
    </div>
  );
}

export { EvidenceGate };
