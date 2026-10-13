"""Resolve PDF formatting only from actual line breaks and validated evidence."""
from copy import deepcopy
from itertools import product
from .automatic import parse_reference
from .audit import compare, same
from .io import fingerprint


HYPHEN_ISSUE = 'line_break_hyphen_reconstruction_requires_review'


def reference_variants(ref):
    if ref.get('extraction',{}).get('method') != 'numbered_author_year':
        return [deepcopy(ref)]
    rows = ref['extraction']['original_rows']
    breaks = [i for i in range(1,len(rows))
              if rows[i-1]['text'].rstrip().endswith('-')
              and rows[i]['text'].lstrip() and rows[i]['text'].lstrip()[0].islower()]
    if len(breaks) > 12:
        return [deepcopy(ref)]
    variants = []
    for decisions in product((False, True),repeat=len(breaks)):
        choices = dict(zip(breaks,decisions))
        content = ''
        for i,row in enumerate(rows):
            line = row['text'].strip()
            if i in choices:
                content = content[:-1] + ('-' if choices[i] else '') + line
            else:
                content += (' ' if content else '') + line
        candidate = parse_reference(rows,int(ref['id'].split('-')[-1]), reconstructed=content)
        candidate['id'] = ref['id']
        candidate['extraction']['break_choices'] = [
            {'after_line':rows[i-1]['line_number'],'keep_hyphen':choices[i]} for i in breaks]
        # Never drop manually reviewed or unsupported supplied fields.
        if set(candidate['fields']) == set(ref['fields']):
            variants.append(candidate)
    return variants or [deepcopy(ref)]


def resolve_reference(ref, records):
    if HYPHEN_ISSUE not in ref.get('issues',[]):
        return ref
    variants = reference_variants(ref)
    varied_fields = {field for field in ref['fields']
                     if len({fingerprint([v['fields'][field]]) for v in variants}) > 1}
    choices = []
    for record in records:
        if record.get('role') != 'primary':
            continue
        for variant in variants:
            if any(not record['fields'].get(f) or
                   not same(f,variant['fields'].get(f),record['fields'][f],variant,record)
                   for f in ('title','authors')):
                continue
            rows = compare(variant,record)
            matching = {row['field'] for row in rows if row['result']=='MATCH'}
            # Every field affected by a break must be supported by this one source.
            # Unaffected page/venue mismatches remain real comparison results.
            if varied_fields <= matching:
                choices.append((variant,record))
    identities = {fingerprint([v['fields']]) for v,_ in choices}
    if len(identities) != 1:
        return ref
    chosen,record = choices[0]
    result = deepcopy(ref)
    result['fields'] = chosen['fields']
    result['issues'] = [i for i in ref['issues'] if i != HYPHEN_ISSUE]
    result['format_resolutions'] = [{
        'method':'original_line_break_variants_matched_to_single_trusted_record',
        'original_fields':ref['fields'],'resolved_fields':chosen['fields'],
        'break_choices':chosen['extraction'].get('break_choices',[]),
        'source_url':record['source_url'],'source_sha256':record['sha256'],
        'note':'Only observed line-end hyphens may be kept or removed. No fuzzy edits.'}]
    return result
