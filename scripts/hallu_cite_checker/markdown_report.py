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
    review = report.get('final_review', {})
    lines.append('Model review: complete; '+str(review.get('reviewed_count', 0))+' flagged entries reviewed.'
                 if review.get('completed') else 'PRELIMINARY — final model review is pending.')
    rejected = [r for r in report['references'] if r['status'] == 'REJECTED']
    conflicts_pending = [r for r in report['references'] if r['status'] == 'UNVERIFIED'
                         and r.get('conflicts') and not r.get('identity_finding')]
    if rejected:
        lines.extend(['', '## Confirmed Errors', ''])
        for ref in rejected:
            fields = sorted({c['field'] for c in ref.get('confirmed_conflicts', ref['conflicts'])})
            lines.append('- **'+ref['id']+'** · '+ref['fields'].get('title', '')+' · '+', '.join(fields))
    risks = [r for r in report['references'] if r.get('identity_finding')]
    if risks:
        lines.extend(['', '## Suspected Fabrication', '',
            str(len(risks))+' high-risk citation(s), included in the unverified total. Evidence suggests metadata conflation; global nonexistence is not established.', ''])
        for ref in risks:
            finding = ref['identity_finding']
            related, catalogue = finding['related_work'], finding['catalogue']
            lines.extend(['- **'+ref['id']+' · '+ref['fields'].get('title', '')+'**: '+finding['reason'],
                '  Related work: ['+related['fields']['title']+']('+related['source_url']+').',
                '  [Official catalogue]('+catalogue['source_url']+'): '+str(catalogue['entries_inspected'])+
                ' entries inspected; no matching or closely similar title.', ''])
    if conflicts_pending:
        lines.extend(['', '## Field Conflicts Requiring Review', '',
            'Prioritize these unresolved differences. They are not all confirmed errors; source, version or formatting ambiguity remains.', ''])
        for ref in conflicts_pending:
            fields = sorted({c['field'] for c in ref['conflicts']})
            lines.append('- **'+ref['id']+'** · '+ref['fields'].get('title', '')+' · '+', '.join(fields))
    if report.get('execution',{}).get('mode')=='captured_evidence_replay':
        lines.append('Execution: fresh extraction with saved evidence; no full online recheck.')
    elif report.get('execution',{}).get('mode')=='reviewed_inventory_reuse_with_live_supplement':
        lines.append('Execution: reviewed inventory and saved evidence reused; official sources supplemented online. No full online recheck.')
    elif report.get('execution',{}).get('refinement'):
        lines.append('Execution: captured evidence reused for refinement, with live official-source fallbacks.')
    else:
        lines.append('Execution: source capture timestamps are recorded in the evidence.')
    if report['blockers']:
        lines.extend(['','Blockers: '+str(report['blockers'])])
    if review.get('completed') and review.get('decisions'):
        lines.extend(['', '## Model Review', '',
            'Detailed reasoning is in the HTML and JSON reports.', '',
            '| Reference | Decision |', '| --- | --- |'])
        for decision in review['decisions']:
            lines.append('| '+decision['ref_id']+' | '+decision['outcome']+' |')
    attention = sorted((r for r in report['references'] if r['status']!='VERIFIED'),
        key=lambda r: 0 if r['status']=='REJECTED' else 1 if r.get('identity_finding') else 2 if r['conflicts'] else 3)
    if attention:
        lines.extend(['','## Findings',''])
    for ref in attention:
        label = 'SUSPECTED FABRICATION' if ref.get('identity_finding') else ref['status']
        lines.extend(['### '+ref['id']+' · '+label, '', ref['fields'].get('title',''), ''])
        locations = ', '.join('PDF p. '+str(l['page']) for l in ref.get('locations',[]) if 'page' in l)
        if locations:
            lines.append('Location: '+locations+'.')
        note = report.get('validation_notes',{}).get(ref['id'])
        if note:
            lines.append(str(note))
        if ref['conflicts']:
            lines.append('')
        seen_conflicts = set()
        for conflict in ref['conflicts']:
            key = (conflict['field'], str(conflict['input']), str(conflict['source']))
            if key in seen_conflicts:
                continue
            seen_conflicts.add(key)
            lines.append('- '+conflict['field']+': '+str(conflict['input'])+' → '+str(conflict['source']))
        if ref['problems']:
            lines.append('')
            lines.append('Unresolved: '+', '.join(ref['problems'])+'.')
        if ref['evidence']:
            lines.append('')
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
        label = 'SUSPECTED FABRICATION' if ref.get('identity_finding') else ref['status']
        lines.append('| '+ref['id']+' | '+label+' | '+title+' |')
    unchecked = [r for r in report['references'] if r['unchecked_optional_fields']]
    if unchecked:
        lines.extend(['','## Unchecked Optional Fields','',
            'These fields are absent or incomplete in the trusted source and permitted by the configured policy.',''])
        for ref in unchecked:
            lines.append('- '+ref['id']+': '+', '.join(ref['unchecked_optional_fields']))
    lines.extend(['','Unresolved entries block a pass. Unavailable evidence does not prove nonexistence.',''])
    return '\n'.join(lines)
