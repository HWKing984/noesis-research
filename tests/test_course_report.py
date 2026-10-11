import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from build_course_report import inline, render


def test_report_subset_preserves_text_and_escapes_markup():
    text = '# 报告\n\n<script>x</script>\n\n| 项 | 值 |\n|---|---:|\n| F1 | 60.07% |\n\n```cypher\nMATCH (a)<-[:R]-(b)\n```'
    rendered = render(text)
    assert '<h1>报告</h1>' in rendered and '<script>' not in rendered
    assert '&lt;script&gt;' in rendered and '<td>60.07%</td>' in rendered
    assert 'MATCH (a)&lt;-[:R]-(b)' in rendered and '<thead>' in rendered
    assert 'javascript:' not in inline('[bad](javascript:alert)')
    with pytest.raises(ValueError): render('```\nmissing end')
    with pytest.raises(ValueError): render('![missing](../not_real.png)')
