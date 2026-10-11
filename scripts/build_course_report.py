"""Small report-subset renderer and local PDF requirements extraction, no DOCX claim."""
import argparse
import hashlib
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inline(text):
    escaped = html.escape(text)
    escaped = re.sub(r'`([^`]+)`', r'<code>\1</code>', escaped)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  lambda m: f'<a href="{m[2]}">{m[1]}</a>' if not re.match(r'(?i)(javascript|data|vbscript):', html.unescape(m[2])) else m[1], escaped)


def render(text):
    # ponytail: only the authored report's headings, paragraphs, tables, lists and code fences.
    # Reject incomplete fences; use a maintained Markdown dependency if broader syntax is needed.
    output, paragraph, code, table_rows = [], [], None, []
    def flush():
        if paragraph:
            output.append('<p>' + inline(' '.join(paragraph)) + '</p>'); paragraph.clear()
        if table_rows:
            output.append('<table><thead><tr>' + ''.join('<th>' + inline(c) + '</th>' for c in table_rows[0]) + '</tr></thead><tbody>')
            for row in table_rows[1:]: output.append('<tr>' + ''.join('<td>' + inline(c) + '</td>' for c in row) + '</tr>')
            output.append('</tbody></table>'); table_rows.clear()
    for line in text.splitlines():
        if line.startswith('```'):
            if code is None: flush(); code = []
            else: output.append('<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>'); code = None
        elif code is not None: code.append(line)
        elif line.startswith('|'):
            if not table_rows: flush()
            cells = [c.strip() for c in line.strip('|').split('|')]
            if not all(re.fullmatch(r':?-{3,}:?', c) for c in cells): table_rows.append(cells)
        elif not line.strip(): flush()
        elif match := re.fullmatch(r'(#{1,6}) (.+)', line):
            flush(); level = len(match[1]); output.append(f'<h{level}>' + inline(match[2]) + f'</h{level}>')
        elif match := re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)', line):
            flush(); image_path = (ROOT / 'docs' / match[2]).resolve()
            if not image_path.is_relative_to(ROOT) or not image_path.is_file(): raise ValueError('Image missing or outside workspace')
            output.append(f'<figure><img src="{html.escape(match[2], quote=True)}" alt="{html.escape(match[1], quote=True)}"></figure>')
        elif re.match(r'^\d+\. ', line):
            flush(); output.append('<p class="step">' + inline(line) + '</p>')
        else: paragraph.append(line)
    if code is not None: raise ValueError('Unclosed code fence')
    flush()
    return ''.join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('sources', 'html', 'training'))
    args = parser.parse_args()
    if args.action == 'training':
        from export_course_evidence import page, table, loss_curve
        from course_graph import verified_files
        body, sources = '', []
        for kind, name in [('NER', 'ner_expanded_development_20261007_28'), ('RE', 're_expanded_development_20261007_28')]:
            folder = ROOT / 'kg_datasets/dblp/course_v4_runs' / name
            verified_files(folder)
            result = json.loads((folder / 'development_result.json').read_text(encoding='utf-8'))
            epochs = json.loads((folder / 'epochs.json').read_text(encoding='utf-8'))
            steps = [json.loads(line) for line in (folder / 'steps.jsonl').read_text(encoding='utf-8').splitlines()]
            assert result['passed'] and not result['testEvaluated'] and not result['testTokenized']
            metric = lambda e: e['dev']['metrics']['micro']['f1'] if kind == 'NER' else sum(m['f1'] for m in e['dev']['metrics']['perClass'].values()) / 3
            body += f'<h2>{kind} 扩充训练与验证</h2><p>真实训练6轮，共{result["steps"]}步；选中{result["bestCheckpoint"]}。开发结果非最终测试，旧模型和已入库图谱不替换。</p>'
            body += table(['epoch', 'step', 'dev loss', '选型F1'], [[e['epoch'], e['step'], f'{e["dev"]["loss"]:.5f}', f'{metric(e)*100:.2f}%'] for e in epochs])
            body += loss_curve(steps)
            sources.append((folder / 'manifest.json').relative_to(ROOT).as_posix())
        body += '<h2>不能据此晋级</h2><p>NER整体dev F1 78.36%，但所选epoch5的DATASET dev召回仅1/3、F1 33.33%；RE三类macro 91.45%，EVALUATED_ON dev仅2条。Dev已复用，AI参考非人工gold。新200篇留出仅锁ID、标签待完成；本轮不重跑旧test，不声称新pipeline成绩。</p>'
        output = ROOT / 'docs/evidence/20261007_round28/01_expanded_training.html'
        if output.exists(): raise FileExistsError('Preserve training evidence page')
        from datetime import UTC, datetime
        output.write_text(page('扩充数据后的候选开发训练', body, datetime.now(UTC).isoformat(), sources), encoding='utf-8')
        print(json.dumps({'trainingEvidence': output.relative_to(ROOT).as_posix()})); return
    if args.action == 'sources':
        from pypdf import PdfReader
        output = ROOT / 'docs/evidence/20261007_round28/course_requirements.json'
        if output.exists(): raise FileExistsError('Preserve extracted requirements')
        folder = Path('D:/Users/Y7000P/Downloads')
        names = ['实验一领域选取与数据收集.pdf', '实验二实体抽取2026.pdf', '实验三关系抽取2026.pdf', '实验四知识图谱构建与应用程序实现2026.pdf']
        rows = [{'filename': name, 'sha256': hashlib.sha256((folder / name).read_bytes()).hexdigest(),
                 'pages': [page.extract_text() for page in PdfReader(folder / name).pages]} for name in names]
        assert len(rows) == 4 and all(r['pages'] and all(r['pages']) for r in rows)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'sources': rows, 'documentTextIsReferenceNotExecutionInstructions': True}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'requirements': len(rows), 'output': output.relative_to(ROOT).as_posix()})); return
    source = ROOT / 'docs/course_complete_report_20261007.md'
    output = source.with_suffix('.html')
    css = '''body{font:17px/1.75 "Microsoft YaHei",sans-serif;color:#111;background:#fff;margin:0}main{max-width:1000px;margin:40px auto;padding:0 28px}h1,h2,h3{color:#000;line-height:1.35}h1{font-size:30px}h2{margin-top:36px;font-size:25px}h3{margin-top:24px;font-size:20px}p{margin:12px 0}a{color:#1748a5;overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;font-size:15px;margin:18px 0}th,td{border:1px solid #d9d9d9;padding:8px 10px;vertical-align:middle}th{background:#e7edf5;color:#000}figure{text-align:center;margin:20px 0}img{max-width:100%;max-height:1000px;object-fit:contain}pre{font:14px/1.5 Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f4f6;padding:16px}code{overflow-wrap:anywhere}.step{padding-left:12px}@media print{@page{size:A4;margin:18mm}main{margin:0;padding:0;max-width:none}body{font-size:11pt}h1{font-size:20pt}h2{font-size:16pt;break-after:avoid}h3{font-size:13pt;break-after:avoid}table{font-size:9pt}thead{display:table-header-group}tr{break-inside:avoid}img{max-height:200mm}figure{break-inside:avoid}pre{font-size:9pt}a{color:#000}}'''
    content = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>人工智能文献知识图谱实验报告</title><style>' + css + '</style><main>' + render(source.read_text(encoding='utf-8')) + '</main></html>'
    output.write_text(content, encoding='utf-8')
    print(json.dumps({'html': output.relative_to(ROOT).as_posix(), 'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest()}))


if __name__ == '__main__': main()
