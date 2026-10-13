"""Compact English Markdown; full comparisons remain in HTML and JSON."""


def markdown_report(report):
    counts = report['counts']
    lines = ['# Citation Audit', '',
        '**'+report['verdict']+'** · '+str(len(report['references']))+' references · '+
        str(counts['VERIFIED'])+' verified · '+str(counts['REJECTED'])+' rejected · '+
        str(counts['UNVERIFIED'])+' unverified', '',
        'Scope: reference metadata only. [Interactive report](report.html) · [Full evidence](report.json)', '']
    reviewed = report.get('coverage',{}).get('reviewed') and not any(
        b.get('code')=='coverage_not_confirmed' for b in report['blockers'])
    lines.append('Bibliography coverage: '+('reviewed.' if reviewed else 'not confirmed.'))
    if report.get('execution',{}).get('mode')=='captured_evidence_replay':
        lines.append('Execution: fresh extraction with saved evidence; no full online recheck.')
    elif report.get('execution',{}).get('refinement'):
        lines.append('Execution: captured evidence reused for refinement, with live official-source fallbacks.')
    else:
        lines.append('Execution: source capture timestamps are recorded in the evidence.')
    if report['blockers']:
        lines.extend(['','Blockers: '+str(report['blockers'])])
    attention = [r for r in report['references'] if r['status']!='VERIFIED']
    if attention:
        lines.extend(['','## Findings',''])
    for ref in attention:
        lines.extend(['### '+ref['id']+' · '+ref['status'], '', ref['fields'].get('title',''), ''])
        locations = ', '.join('PDF p. '+str(l['page']) for l in ref.get('locations',[]) if 'page' in l)
        if locations:
            lines.append('Location: '+locations+'.')
        note = report.get('validation_notes',{}).get(ref['id'])
        if note:
            lines.append(str(note))
        for conflict in ref['conflicts']:
            lines.append('- '+conflict['field']+': '+str(conflict['input'])+' → '+str(conflict['source']))
        if ref['problems']:
            lines.append('Unresolved: '+', '.join(ref['problems'])+'.')
        for source in ref['evidence']:
            lines.append('- [Source]('+source['source_url']+')')
        for candidate in ref.get('discovery_candidates',[]):
            lines.append('- [Candidate source]('+candidate['source_url']+
                         '): identity is incomplete; differences are not confirmed errors.')
            for row in candidate['comparisons']:
                if row['result'] in {'CONFLICT','AMBIGUOUS_FORMAT'}:
                    lines.append('  - '+row['field']+': '+str(row['input'])+' → '+str(row['source']))
        lines.append('')
    lines.extend(['## All References','','| ID | Result | Title |','| --- | --- | --- |'])
    for ref in report['references']:
        title = ref['fields'].get('title','').replace('|','&#124;').replace('\n',' ')
        lines.append('| '+ref['id']+' | '+ref['status']+' | '+title+' |')
    unchecked = [r for r in report['references'] if r['unchecked_optional_fields']]
    if unchecked:
        lines.extend(['','## Unchecked Optional Fields','',
            'These fields are absent or incomplete in the trusted source and permitted by the configured policy.',''])
        for ref in unchecked:
            lines.append('- '+ref['id']+': '+', '.join(ref['unchecked_optional_fields']))
    lines.extend(['','Unresolved entries block a pass. Unavailable evidence does not prove nonexistence.',''])
    return '\n'.join(lines)
