/* 临时探针（验完删）：在 vite dev 下真实挂载 ReaderView，验证
   react-pdf-highlighter-extended 8.1.0 + pdfjs-dist 4.4.168 的真渲染与划词。 */
import React from 'react';
import { createRoot } from 'react-dom/client';

import ReaderView from './src/components/ReaderView.jsx';
import './src/index.css';

const SHA = 'b'.repeat(64);

const mockApi = {
  documentFileUrl: () => '/_probe.pdf',
  documentStatus: async (publicationId) => {
    if (publicationId === 'probe-no-oa') {
      return {
        documentId: 'probe-doc-2',
        publicationId,
        status: 'no_oa_found',
        detail: 'searched arXiv, OpenAlex best_oa_location, Semantic Scholar openAccessPdf: no OA copy',
      };
    }
    if (publicationId === 'probe-failed') {
      return {
        documentId: 'probe-doc-3',
        publicationId,
        status: 'fetch_failed',
        sourceUrl: 'https://arxiv.org/pdf/1706.03762',
        detail: 'download timeout after 3 attempts',
      };
    }
    return {
      documentId: 'probe-doc-1',
      publicationId,
      status: 'available',
      sourceKind: 'upload',
      sha256: SHA,
      sizeBytes: 2215244,
      detail: '',
    };
  },
  uploadDocument: async () => {
    throw new Error('probe: upload not wired');
  },
  fetchDocument: async () => {
    throw new Error('probe: fetch not wired');
  },
};

function Frame({ id, publicationId, title, hidden }) {
  return (
    <div id={id} style={{ display: hidden ? 'none' : 'flex', flex: 1, minHeight: 0, minWidth: 0 }}>
      <ReaderView api={mockApi} publicationId={publicationId} title={title} />
    </div>
  );
}

createRoot(document.getElementById('root')).render(
  <div data-testid="probe-root" style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
    <Frame id="probe-available" publicationId="probe-ok" title="Attention Is All You Need（probe）" />
    <Frame id="probe-nooa" publicationId="probe-no-oa" title="no OA probe" hidden />
    <Frame id="probe-failed" publicationId="probe-failed" title="fetch failed probe" hidden />
  </div>,
);
