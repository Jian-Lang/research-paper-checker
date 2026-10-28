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
    if report.get('execution', {}).get('mode') == 'reviewed_inventory_reuse_with_live_supplement':
        execution_note = '复用同一 PDF 的已审核引用清单和保存证据，并补查官方来源；不是一次新的全量联网核验。'
    coverage_note = ('已记录参考文献清单覆盖审核。' if report.get('coverage', {}).get('reviewed') and
                     not any(b.get('code') == 'coverage_not_confirmed' for b in report['blockers'])
                     else '参考文献清单覆盖尚未确认，结果不能通过。')
    final_review = report.get('final_review', {})
    stage_note = ('模型最终复核已完成：' + str(final_review.get('reviewed_count', 0)) + ' 条初筛问题已逐条复查。'
                  if final_review.get('completed') else '初步结果：尚未完成模型最终复核，不能作为最终核验报告。')
    execution_note += ' ' + stage_note
    lines.extend([execution_note, '', coverage_note, ''])
    refinement = report.get('execution', {}).get('refinement')
    if refinement:
        execution_note += ' 已复用保存的证据进行格式复核，并联网补查官方来源；不是重新获取全部来源。'
        lines.extend(['Refinement: ' + str(refinement), ''])
    ordered = sorted(report['references'], key=lambda r: 0 if r['status']=='REJECTED' else
                     1 if r.get('identity_finding') else 2 if r['conflicts'] else 3 if r['status']=='UNVERIFIED' else 4)
    for ref in ordered:
        lines.extend([f"## {ref['id']}: {ref['status']}", "", "Input: " + str(ref["fields"]), ""])
        note = report.get('validation_notes', {}).get(ref['id'], '')
        if ref.get('model_review'):
            note = (str(note) + ' 模型复核：' + ref['model_review']['reason']).strip()
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
        risk = ref.get('identity_finding')
        if risk:
            related, catalogue = risk['related_work'], risk['catalogue']
            unchecked += ('<p><strong>疑似伪造／元数据拼接：</strong>' + esc(risk['reason']) +
                '</p><p>相关真实论文：<a href="' + esc(related['source_url']) + '">' +
                esc(related['fields']['title']) + '</a> · ' + esc(related['fields'].get('authors', [])) +
                ' · ' + esc(related['fields'].get('venue', '')) + ' · ' + esc(related['fields'].get('year', '')) +
                '</p><blockquote>' + esc(related['quote']) + '</blockquote><p><a href="' +
                esc(catalogue['source_url']) + '">所称会议官方公开目录</a>：检查 ' +
                str(catalogue['entries_inspected']) + ' 个题名，没有匹配或高度相似题名。' +
                '这是疑似拼接证据，不证明所有地方都不存在该论文。</p>')
        opened = ' open' if ref['status'] != 'VERIFIED' else ''
        badge = 'REJECTED' if risk else ref['status']
        label = ('疑似伪造／拼接' if risk else '待核实：字段冲突'
                 if ref['status']=='UNVERIFIED' and ref['conflicts'] else labels[ref['status']])
        cards.append(f'<article data-status="{esc(ref["status"])}" data-risk="{str(bool(risk)).lower()}"><details{opened}><summary><span class="badge {esc(badge)}">{label}</span> {esc(ref["fields"].get("title", ""))}</summary><p class="meta">{esc(where)} · {esc(ref["id"])}</p><p class="raw">{esc(ref.get("raw", ""))}</p><p>{links}</p><p>{esc(ref["problems"])}</p>{unchecked}<div class="scroll"><table><thead><tr><th>字段</th><th>比对结果</th><th>论文原值</th><th>来源原值</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details></article>')
        lines.append("")
    lines.extend(["## Limits", ""] + ["- " + x for x in report["limits"]])
    from .markdown_report import markdown_report
    Path(run, 'report.md').write_text(markdown_report(report), encoding='utf-8')
    rejected = [r for r in report['references'] if r['status']=='REJECTED']
    findings = ''.join('<li><strong>' + esc(r['id']) + ' · ' + esc(r['fields'].get('title',r['id'])) + '</strong><ul>' + ''.join('<li>' + esc(c['field']) + '：' + esc(c['input']) + ' → 来源：' + esc(c['source']) + '</li>' for c in r.get('confirmed_conflicts', r['conflicts'])) + '</ul></li>' for r in rejected)
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
    pending = [r for r in report['references'] if r['status']=='UNVERIFIED'
               and r['conflicts'] and not r.get('identity_finding')]
    if pending:
        pending_list = ''.join('<li><strong>' + esc(r['id']) + ' · ' +
            esc(r['fields'].get('title', '')) + '</strong> · ' +
            esc(', '.join(sorted({c['field'] for c in r['conflicts']}))) +
            '<p>' + esc(r.get('model_review', {}).get('reason', '; '.join(r['problems']))) + '</p></li>' for r in pending)
        document = document.replace('<section class="panel"><h2>阅读说明</h2>',
            '<section class="panel"><h2>待核实的字段冲突：优先复查 (' + str(len(pending)) +
            ')</h2><p>以下引用存在具体字段差异，单独置前。来源冲突、版本或格式歧义尚未消除，不能全部按错误处理；' +
            '一旦任何字段的错误被独立证实，该引用即列入确认错误，不受其他字段待核实的影响。</p><ol>' +
            pending_list + '</ol></section><section class="panel"><h2>阅读说明</h2>', 1)
    risks = [r for r in report['references'] if r.get('identity_finding')]
    if risks:
        risk_list = ''.join('<li><strong>' + esc(r['id']) + ' · ' + esc(r['fields'].get('title', '')) +
            '</strong><p>' + esc(r['identity_finding']['reason']) + '</p></li>' for r in risks)
        panel = ('<section class="panel"><h2>高风险：疑似伪造／元数据拼接 (' + str(len(risks)) +
            ')</h2><p>以下引用有具体身份拼接证据，单独突出展示；数量包含在待核实总数内。' +
            '这不是仅因搜索无结果作出的判断，也不是对全球不存在的证明。</p><ol>' + risk_list + '</ol></section>')
        confirmed_panel = '<section class="panel"><h2>确认错误</h2><ol>' + (findings or '<li>暂无确认错误。</li>') + '</ol></section>'
        document = document.replace(confirmed_panel, confirmed_panel + panel, 1)
        document = document.replace('<button data-value="all">',
            '<button data-value="suspected">疑似伪造 (' + str(len(risks)) + ')</button><button data-value="all">', 1)
        document = document.replace("mode===s;", "mode===s||mode==='suspected'&&a.dataset.risk==='true';")
    Path(run, "report.html").write_text(document, encoding="utf-8")
