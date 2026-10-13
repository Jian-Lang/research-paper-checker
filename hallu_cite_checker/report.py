import html
from pathlib import Path


def render(report, run):
    esc = lambda v: html.escape(str(v), quote=True)
    labels = {"VERIFIED": "通过", "REJECTED": "确认错误", "UNVERIFIED": "待核实"}
    lines = [f"# Citation audit: {report['verdict']}", "", "Scope: citation metadata only.", "",
             "Counts: " + str(report["counts"]), "", "Blockers: " + str(report["blockers"]), ""]
    cards = []
    replay = report.get('execution', {}).get('mode') == 'captured_evidence_replay'
    execution_note = ('独立环境证据复跑：重新提取 PDF，逐条核对原文并重新计算结果；复用此前保存的来源证据及提取审核，不是一次新的全量联网核验。'
                      if replay else '根据本次保存的来源证据核验；获取时间见证据记录。')
    coverage_note = ('已记录参考文献清单覆盖审核。' if report.get('coverage', {}).get('reviewed') and
                     not any(b.get('code') == 'coverage_not_confirmed' for b in report['blockers'])
                     else '参考文献清单覆盖尚未确认，结果不能通过。')
    lines.extend([execution_note, '', coverage_note, ''])
    refinement = report.get('execution', {}).get('refinement')
    if refinement:
        execution_note += ' 已复用保存的证据进行格式复核，并联网补查官方来源；不是重新获取全部来源。'
        lines.extend(['Refinement: ' + str(refinement), ''])
    for ref in report["references"]:
        lines.extend([f"## {ref['id']}: {ref['status']}", "", "Input: " + str(ref["fields"]), ""])
        note = report.get('validation_notes', {}).get(ref['id'], '')
        if note:
            lines.extend(['说明：' + str(note), ''])
        lines.extend(["- " + p for p in ref["problems"]])
        rows = []
        for ev in ref["evidence"]:
            lines.extend(["", "Source: " + ev["source_url"], ""])
            for diff in ev["comparisons"]:
                lines.append(f"- {diff['field']}: {diff['result']} | input={diff['input']} | source={diff['source']}")
                rows.append("<tr>" + "".join(f"<td>{esc(diff[k])}</td>" for k in ("field", "result", "input", "source")) + "</tr>")
        if ref["unchecked_optional_fields"]:
            lines.extend(["", "Absent from source, permitted but unchecked: " + ", ".join(ref["unchecked_optional_fields"])])
        links = " ".join(f'<a href="{esc(ev["source_url"])}">{esc(ev["kind"])}</a>' for ev in ref["evidence"])
        unchecked = '<p>Permitted but unchecked: ' + esc(', '.join(ref['unchecked_optional_fields'])) + '</p>' if ref['unchecked_optional_fields'] else ''
        if note:
            unchecked += '<p class="note">' + esc(note) + '</p>'
        if ref.get('format_resolutions'):
            lines.extend(['PDF formatting resolution: ' + str(ref['format_resolutions']), ''])
            unchecked += '<p>已依据原始断行位置及同一来源记录还原 PDF 排版；原始文字保留在上方，完整还原记录见 JSON / Markdown。</p>'
        for candidate in ref.get('discovery_candidates', []):
            differences = '; '.join(c['field'] + ': ' + str(c['input']) + ' → ' + str(c['source'])
                for c in candidate['comparisons'] if c['result'] in {'CONFLICT', 'AMBIGUOUS_FORMAT'})
            unchecked += '<p>候选来源（身份尚未完整确认，以下差异尚非确认错误）：<a href="' + esc(candidate['source_url']) + '">Crossref</a> · ' + esc(differences) + '</p>'
        if ref.get('acceptance_policy') == 'matching_google_scholar_export':
            unchecked += '<p>通过依据：Google Scholar citation 导出完整匹配。其他来源的差异保留为提示，不推翻该通过结果。</p>'
        where = ', '.join('PDF 第 ' + str(l['page']) + ' 页 · 第 ' + str(l.get('entry_index', '?')) + ' 条' if 'page' in l else str(l) for l in ref['locations'])
        opened = ' open' if ref['status'] != 'VERIFIED' else ''
        cards.append(f'<article data-status="{esc(ref["status"])}"><details{opened}><summary><span class="badge {esc(ref["status"])}">{labels[ref["status"]]}</span> {esc(ref["fields"].get("title", ""))}</summary><p class="meta">{esc(where)} · {esc(ref["id"])}</p><p class="raw">{esc(ref.get("raw", ""))}</p><p>{links}</p><p>{esc(ref["problems"])}</p>{unchecked}<div class="scroll"><table><thead><tr><th>字段</th><th>比对结果</th><th>论文原值</th><th>来源原值</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details></article>')
        lines.append("")
    lines.extend(["## Limits", ""] + ["- " + x for x in report["limits"]])
    from .markdown_report import markdown_report
    Path(run, 'report.md').write_text(markdown_report(report), encoding='utf-8')
    rejected = [r for r in report['references'] if r['status']=='REJECTED']
    findings = ''.join('<li><strong>' + esc(r['fields'].get('title',r['id'])) + '</strong><ul>' + ''.join('<li>' + esc(c['field']) + '：' + esc(c['input']) + ' → 来源：' + esc(c['source']) + '</li>' for c in r['conflicts']) + '</ul></li>' for r in rejected)
    counts = report['counts']
    document = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>参考文献核验报告 — {esc(report['verdict'])}</title>
<style>body{{font:16px/1.65 system-ui,-apple-system,sans-serif;max-width:1180px;margin:36px auto;padding:0 22px;background:#f7f8fb;color:#172235}}h1{{font-size:30px}}a{{color:#215ebc}}header,.panel,article{{background:white;border:1px solid #dfe5ed;border-radius:12px;padding:22px;margin:18px 0}}.metrics{{display:flex;flex-wrap:wrap;gap:18px}}.metric{{padding:12px 24px;border-radius:8px;background:#f1f4f9}}.metric strong{{font-size:30px;display:block}}.badge{{font-size:13px;white-space:nowrap;border-radius:6px;padding:4px 8px;margin-right:6px}}.VERIFIED{{color:#126446;background:#e3f4ec}}.REJECTED{{color:#ad2436;background:#fce8eb}}.UNVERIFIED{{color:#815313;background:#fff1d9}}summary{{cursor:pointer;font-weight:600}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #dfe5ed;padding:8px;text-align:left;overflow-wrap:anywhere;min-width:90px}}.scroll{{overflow:auto}}.meta{{color:#64748b;font-size:13px}}.raw{{border-left:3px solid #b8c5d7;padding-left:14px;white-space:pre-wrap}}input{{box-sizing:border-box;font:inherit;padding:10px;width:100%;border:1px solid #b8c5d7;border-radius:8px}}button{{font:inherit;padding:7px 14px;margin:8px 4px 0 0;border:1px solid #c5d0df;background:white;border-radius:7px;cursor:pointer}}button.active{{background:#172235;color:white}}[hidden]{{display:none!important}}li{{margin-bottom:8px}}footer{{font-size:13px;color:#64748b}}</style></head><body>
<header><p class="meta">research-paper-checker / hallu-cite-checker · {esc(report['created_at'])}</p><h1>参考文献核验：{'通过' if report['verdict']=='PASS' else '不通过'}</h1><p>检查范围：参考文献元数据。未检查引用是否支持正文论点。</p><div class="metrics"><div class="metric"><strong>{len(report['references'])}</strong>全部引用</div><div class="metric VERIFIED"><strong>{counts['VERIFIED']}</strong>通过</div><div class="metric REJECTED"><strong>{counts['REJECTED']}</strong>确认错误</div><div class="metric UNVERIFIED"><strong>{counts['UNVERIFIED']}</strong>待核实</div></div><p>已核对参考文献清单覆盖范围；待核实项同样阻止通过，不能按正确处理。</p></header>
<section class="panel"><h2>确认错误</h2><ol>{findings or '<li>暂无确认错误。</li>'}</ol></section>
<section class="panel"><h2>阅读说明</h2><p>确认错误表示原文与可信来源有明确字段冲突；待核实包括无法取得证据、来源之间冲突及格式歧义。MATCH 为匹配，CONFLICT 为冲突，AMBIGUOUS_FORMAT 为未消除的歧义，SOURCE_MISSING / PARTIAL_SOURCE_MATCH 为来源缺项或仅能核对一部分。</p><p>Google Scholar 的真实 citation 导出按指定政策可信。缺少页码等可选信息可以通过，但必须披露未核实字段；会议声明必须有对应版本的证据。</p></section>
<section class="panel"><h2>逐条核验与证据</h2><input id="filter" placeholder="搜索标题、作者、字段或引用编号" aria-label="搜索引用"><div id="status"><button data-value="attention" class="active">需要处理 ({counts['REJECTED']+counts['UNVERIFIED']})</button><button data-value="all">全部 ({len(report['references'])})</button><button data-value="REJECTED">确认错误</button><button data-value="UNVERIFIED">待核实</button><button data-value="VERIFIED">通过</button></div><p id="visible" class="meta"></p></section>
{''.join(cards)}<section class="panel"><h2>覆盖与结果边界</h2><p>覆盖 / 文件完整性阻断项：{esc(report['blockers'])}</p><p>缺少官方检索结果或访问被拦截，不能证明文献不存在。本次盲测不能证明工具具备百分之百准确率；通过仅表示在所记录证据和缺项政策下完成核验。</p>{''.join('<p class="meta">' + esc(x) + '</p>' for x in report['limits'])}</section><footer>原始输入未修改。证据文件、来源 URL、获取时间和哈希保存在本次报告目录内；完整数据见 <a href="report.json">report.json</a>，文本版见 <a href="report.md">report.md</a>。</footer>
<script>let mode='attention';function update(){{const q=document.getElementById('filter').value.toLowerCase();let n=0;document.querySelectorAll('article').forEach(a=>{{const s=a.dataset.status;const ok=mode==='all'||mode==='attention'&&s!=='VERIFIED'||mode===s;a.hidden=!(ok&&a.textContent.toLowerCase().includes(q));if(!a.hidden)n++}});document.getElementById('visible').textContent='当前显示 '+n+' 条引用'}}document.getElementById('filter').addEventListener('input',update);document.querySelectorAll('button[data-value]').forEach(b=>b.addEventListener('click',()=>{{mode=b.dataset.value;document.querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===b));update()}}));update();</script></body></html>"""
    document = document.replace('已核对参考文献清单覆盖范围；', esc(coverage_note))
    document = document.replace('<div class="metrics">', '<p>' + esc(execution_note) + '</p><div class="metrics">', 1)
    Path(run, "report.html").write_text(document, encoding="utf-8")
