"""Preserve malformed PDF text without dropping unknown characters."""
import re


def pdf_text(value):
    display, events = [], []
    i = 0
    while i < len(value):
        c = ord(value[i])
        if 0xD800 <= c <= 0xDBFF and i + 1 < len(value) and 0xDC00 <= ord(value[i + 1]) <= 0xDFFF:
            display.append(chr(0x10000 + ((c-0xD800)<<10) + ord(value[i+1])-0xDC00))
            events.append({'offset':i,'codepoints':[f'U+{c:04X}',f'U+{ord(value[i+1]):04X}'],'action':'paired_surrogates_decoded'})
            i += 2
            continue
        if 0xD800 <= c <= 0xDFFF:
            display.append(f'[UNRESOLVED U+{c:04X}]')
            events.append({'offset':i,'codepoints':[f'U+{c:04X}'],'action':'unresolved_surrogate',
                           'context':ascii(value[max(0,i-24):i+25])})
        else:
            display.append(value[i])
        i += 1
    return ''.join(display), events
