import React, { useEffect } from 'react';

import { DetailPanel, GraphPanel } from './InspectorPanel.jsx';
import { Loading } from './StatusPieces.jsx';

/**
 * 论文抽屉（检索优先布局）：选中论文后从右侧滑出，承载「论文详情 / 局部图谱」两个 tab。
 * 层级约定：论文抽屉 z-45，证据抽屉 z-49/50 —— 从详情里点证据 chip 时证据抽屉叠上来，
 * 关掉后论文抽屉还在。
 */
export default function PaperDrawer({
  open,
  onClose,
  tab,
  onTab,
  selectedId,
  detail,
  detailBusy,
  slice,
  graphBusy,
  graphMode,
  onModeChange,
  onRefresh,
  onInspect,
  onOpenPaper,
  appearance = 'light',
}) {
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    document.body.classList.add('is-paper-drawer');
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.classList.remove('is-paper-drawer');
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="lib-mask" data-testid="paper-drawer-backdrop" onClick={onClose} />
      <aside className="lib-drawer" data-testid="paper-drawer" role="dialog" aria-label="论文详情与局部图谱">
        <div className="dw-tabs">
          <button
            type="button"
            className={tab === 'detail' ? 'is-on' : ''}
            data-testid="tab"
            data-tab="detail"
            data-active={tab === 'detail' ? 'true' : 'false'}
            onClick={() => onTab('detail')}
          >
            论文详情
          </button>
          <button
            type="button"
            className={tab === 'graph' ? 'is-on' : ''}
            data-testid="tab"
            data-tab="graph"
            data-active={tab === 'graph' ? 'true' : 'false'}
            onClick={() => onTab('graph')}
          >
            局部图谱
          </button>
          <span className="mono" style={{ marginLeft: 'auto', paddingBottom: 6, fontSize: 10, color: 'var(--text-muted)' }}>
            {selectedId}
          </span>
          <button
            type="button"
            className="lib-icon-btn"
            data-testid="paper-drawer-close"
            aria-label="关闭"
            style={{ marginLeft: 8, marginBottom: 4 }}
            onClick={onClose}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="dw-body">
          {tab === 'detail' ? (
            detailBusy ? (
              <Loading label="正在读取论文详情…" />
            ) : (
              <DetailPanel detail={detail} onInspect={onInspect} onOpenPaper={onOpenPaper} />
            )
          ) : (
            <GraphPanel
              slice={slice}
              busy={graphBusy}
              mode={graphMode}
              onModeChange={onModeChange}
              onRefresh={onRefresh}
              appearance={appearance}
            />
          )}
        </div>
      </aside>
    </>
  );
}
