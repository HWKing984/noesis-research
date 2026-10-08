import React, { useMemo, useState } from 'react';

const LEVEL_LABEL = { title: '题名级', abstract: '摘要级', fulltext: '全文级' };
const VERIFY_LABEL = { unverified: '未核验', id_valid: 'id 可解析', evidence_supports: '引文支持', semantic_verified: '语义已核' };

const SORTS = [
  { key: 'hit', label: '命中顺序' },
  { key: 'year', label: '年份新→旧' },
];

/**
 * 证据链右栏（A+B 融合里的 B）：默认收起，由顶栏开关控制。
 * 数据来自运行事件里的 paperItems —— 与给模型的视图同源，同一篇论文只出现一次。
 */
export default function EvidenceRail({ papers, onInspect, busy }) {
  const [sort, setSort] = useState('hit');

  const sorted = useMemo(() => {
    const list = [...papers];
    if (sort === 'year') {
      list.sort((a, b) => (Number(b.year) || 0) - (Number(a.year) || 0));
    }
    return list;
  }, [papers, sort]);

  return (
    <aside className="rail" aria-label="证据链" data-testid="rail">
      <div className="rail-inner">
        <div className="rail-h" data-testid="rail-header">
          证据链 <span className="n">{papers.length} 条 · {sort === 'hit' ? '按命中顺序' : '按年份'}</span>
        </div>
        <div className="rail-f" data-testid="rail-filters">
          {SORTS.map((item) => (
            <button
              key={item.key}
              type="button"
              disabled={busy}
              data-testid="rail-sort"
              data-sort={item.key}
              data-active={sort === item.key ? 'true' : 'false'}
              className={sort === item.key ? 'is-on' : ''}
              onClick={() => setSort(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="rail-body" data-testid="rail-body">
          {papers.length === 0 ? (
            <div className="rail-empty" data-testid="rail-empty">
              还没有命中的论文。
              <br />
              发起一次检索后，命中的记录会按顺序落到这里。
            </div>
          ) : (
            sorted.map((paper) => {
              const level = LEVEL_LABEL[paper.evidenceLevel] || paper.evidenceLevel || '未知深度';
              const verify = VERIFY_LABEL[paper.verificationStatus] || paper.verificationStatus || '未核验';
              return (
                <div
                  key={paper.publicationId}
                  className="pcard"
                  data-testid="rail-card"
                  data-publication-id={paper.publicationId}
                  onClick={() =>
                    onInspect({
                      reference: {
                        sourceType: 'kg_bibliography',
                        sourceId: paper.publicationId,
                        publicationId: paper.publicationId,
                        graphId: null,
                        evidenceLevel: paper.evidenceLevel || 'title',
                        assertionStatus: 'none',
                        verificationStatus: paper.verificationStatus || 'unverified',
                      },
                      context: { title: paper.title, publicationId: paper.publicationId },
                    })
                  }
                >
                  <div className="t">{paper.title || paper.publicationId}</div>
                  <div className="m">
                    {paper.year ? <span>{paper.year}</span> : null}
                    <span className="lv">{level}</span>
                    <span>{verify}</span>
                  </div>
                  <div className="ev">{paper.publicationId}</div>
                </div>
              );
            })
          )}
          {papers.length > 0 ? (
            <div className="rail-empty" style={{ padding: '10px 6px' }}>
              同一篇论文只出现一次；证据深度与核验状态原样展示，不做修饰。
            </div>
          ) : null}
        </div>
      </div>
    </aside>
  );
}
