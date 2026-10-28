"""Conservative formatting normalization. No fuzzy title or venue matching."""
from __future__ import annotations
import re
import html
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from pylatexenc.latex2text import LatexNodes2Text

_LATEX = LatexNodes2Text()
# Aliases denote exactly the same venue, never workshop/main-conference variants.
_VENUES = {
    "cvpr": ["IEEE/CVF Conference on Computer Vision and Pattern Recognition",
             "IEEE Conference on Computer Vision and Pattern Recognition",
             "Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition",
             "Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition",
             "Proceedings of the Computer Vision and Pattern Recognition Conference",
             "Computer Vision and Pattern Recognition Conference"],
    "iccv": ["IEEE/CVF International Conference on Computer Vision",
             "IEEE International Conference on Computer Vision",
             "Proceedings of the IEEE/CVF International Conference on Computer Vision"],
    "eccv": ["European Conference on Computer Vision",
             "Computer Vision – ECCV", "Computer Vision - ECCV"],
    "acl": ["Annual Meeting of the Association for Computational Linguistics",
            "Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)"],
    "kdd": ["ACM SIGKDD Conference on Knowledge Discovery and Data Mining",
            "ACM SIGKDD Conference on Knowledge Discovery and Data Mining V.1"],
    "ccl": ["China national conference on Chinese computational linguistics",
            "Chinese Computational Linguistics"],
    "iclr": ["International Conference on Learning Representations"],
    "icml": ["International Conference on Machine Learning",
             "Proceedings of the International Conference on Machine Learning"],
    "aaai": ["Proceedings of the AAAI Conference on Artificial Intelligence",
             "AAAI Conference on Artificial Intelligence"],
    "miccai": ["Medical Image Computing and Computer Assisted Intervention", "Medical Image Computing and Computer-Assisted Intervention", "proceedings of Medical Image Computing and Computer Assisted Intervention"],
    "acm mm": ["ACM International Conference on Multimedia"],
    "findings of acl": ["Findings of the Association for Computational Linguistics: ACL"],
    "zenodo": ["Zenodo dataset"],
    "neurips": ["Advances in Neural Information Processing Systems", "NeurIPS", "NIPS"],
}


def text(value):
    raw = html.unescape(str(value))
    # PDF text extraction sometimes separates a prefix acute glyph from its
    # base letter within a word (Vuli ´c). Preserve the accent while composing.
    raw = re.sub(r"([A-Za-z])\s+´\s*([A-Za-z])", lambda m: m[1] + m[2] + '\u0301', raw)
    s = _LATEX.latex_to_text(raw) if "\\" in raw or "{" in raw else raw
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.casefold().split())


def words(value):
    # Keep punctuation that changes mathematical meaning (e.g. '+' vs '-').
    s = text(value).replace("–", "-").replace("—", "-").replace("’", "'")
    s = re.sub(r"[.,:;!?\"'()]", " ", s)
    return " ".join(s.split())


def doi(value):
    s = str(value).strip().casefold()
    return re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", s)


def arxiv(value):
    s = str(value).strip().casefold()
    s = re.sub(r"^(?:https?://(?:export\.)?arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", "", s)
    return re.sub(r"\.pdf$", "", s)


def venue(value):
    s = words(value)
    # Presentation type in an accepted main-conference OpenReview record
    # does not change the venue; workshop and submission labels never match.
    if re.fullmatch(r'iclr (?:19|20)\d{2} (?:poster|oral|spotlight)', s):
        return 'iclr'
    # Only expand known main-venue formats; preserve workshop/track suffixes.
    s = re.sub(r"^(?:19|20)\d{2} ", "", s)
    s = re.sub(r" (?:(?:19|20)\d{2})$", "", s)
    s = re.sub(r" (?:cvpr|iccv)$", "", s) if s.startswith(("ieee", "proceedings of the ieee")) else s
    s = re.sub(r"^proceedings of (?:the )?\d+(?:st|nd|rd|th) ", "", s)
    s = re.sub(r"^the (?:thirteenth|fourteenth) ", "", s)
    s = re.sub(r"^advances in neural information processing systems \d+$", "advances in neural information processing systems", s)
    s = re.sub(r" -+ miccai$", "", s)
    # Proceedings labels and a redundant acronym can vary, but an unknown
    # suffix (workshop, Findings, track, or a different acronym) must survive.
    s = re.sub(r"^proceedings of (?:the )?", "", s)
    s = re.sub(r"^(?:the )?\d+(?:st|nd|rd|th)\s+", "", s)
    for canonical, aliases in _VENUES.items():
        known = {words(canonical), *(words(a) for a in aliases)}
        for acronym in (canonical, "nips" if canonical == "neurips" else canonical):
            if s.endswith(" " + acronym) and s[:-len(acronym)-1] in known:
                s = s[:-len(acronym)-1]
                break
    # Embedded conference years and ordinals are independently checked in audit.compare.
    for canonical, aliases in _VENUES.items():
        if s in {words(canonical), *(words(a) for a in aliases)}:
            return canonical
    return s


def authors(value):
    def name(v):
        s = text(v).replace('’', "'")
        s = re.sub(r'\b(?:[a-z]\.){2,}', lambda m: ' '.join(re.findall(r'[a-z]', m[0])), s)
        return s.replace('.', '')
    if isinstance(value, list):
        return [name(v) for v in value]
    return [name(v) for v in re.split(r"\s+and\s+", str(value)) if v.strip()]


def name_parts(name):
    if "," in name:
        family, given = name.split(",", 1)
        return family.strip(), given.split()
    pieces = name.split()
    return (pieces[-1], pieces[:-1]) if pieces else ("", [])


def same_name(a, b):
    if a == b:
        return True
    af, ag = name_parts(a)
    bf, bg = name_parts(b)
    if "," in a and "," not in b and b.endswith(" " + af):
        bf, bg = af, b[:-len(af)].strip().split()
    if "," in b and "," not in a and a.endswith(" " + bf):
        af, ag = bf, a[:-len(bf)].strip().split()
    ag = [part for token in ag for part in token.split("-")]
    bg = [part for token in bg for part in token.split("-")]
    if af != bf and bf.endswith(" " + af):
        bg += bf[:-len(af)].strip().split()
        bf = af
    elif af != bf and af.endswith(" " + bf):
        ag += af[:-len(bf)].strip().split()
        af = bf
    if af != bf or not ag or not bg:
        return False
    # Citation styles may omit middle names. Any initials actually present must
    # still agree in order; never skip a mismatching supplied initial.
    if len(ag) != len(bg):
        short, long = (ag, bg) if len(ag) < len(bg) else (bg, ag)
        return all(x == y or (len(x) == 1 and y.startswith(x)) or
                   (len(y) == 1 and x.startswith(y)) for x, y in zip(short, long))
    return all(x == y or (len(x) == 1 and y.startswith(x)) or
               (len(y) == 1 and x.startswith(y)) for x, y in zip(ag, bg))


def author_equal(a, b, input_truncated=False, source_truncated=False):
    aa, bb = authors(a), authors(b)
    if input_truncated or source_truncated:
        if input_truncated and not source_truncated and len(aa) > len(bb):
            return False
        if source_truncated and not input_truncated and len(bb) > len(aa):
            return False
        n = min(len(aa), len(bb))
        return n > 0 and all(same_name(x, y) for x, y in zip(aa[:n], bb[:n]))
    return len(aa) == len(bb) and bool(aa) and all(same_name(x, y) for x, y in zip(aa, bb))


def norm(field, value):
    if field == "doi":
        return doi(value)
    if field == "arxiv_id":
        return arxiv(value)
    if field == "venue":
        return venue(value)
    if field == "publisher" and text(value) in {"springer", "springer nature", "springer nature switzerland", "springer international publishing"}:
        return "springer"
    if field == "volume" and re.fullmatch(r"\d+,? main conference", words(value)):
        return re.match(r"\d+", words(value))[0]
    if field == "pages":
        return re.sub(r"\s+", "", text(value).replace("–", "-").replace("—", "-").replace("--", "-"))
    if field == "url":
        p = urlsplit(str(value).strip())
        return urlunsplit(("https", p.netloc.lower(), p.path.rstrip("/"), p.query, p.fragment))
    return words(value)


# Non-bibliographic BibTeX housekeeping is intentionally outside the comparison.
IGNORE = {"ID", "ENTRYTYPE", "abstract", "keywords", "file", "annotation", "annote"}
MAP = {"author": "authors", "booktitle": "venue", "journal": "venue", "eprint": "arxiv_id",
       "number": "issue", "page": "pages"}


def canonical_fields(entry):
    fields, issues = {}, []
    for key, value in entry.items():
        if key in IGNORE or not value:
            continue
        if key in {"archiveprefix", "primaryclass"}:
            if key == "archiveprefix" and text(value) != "arxiv":
                issues.append("unsupported archiveprefix: " + str(value))
            continue
        target = MAP.get(key, key)
        if target == "arxiv_id":
            value = arxiv(value)
        if target == "authors":
            value = re.split(r"\s+and\s+", str(value))
        if target in fields and norm(target, fields[target]) != norm(target, value):
            issues.append("conflicting input fields for " + target)
        fields[target] = value
    if "venue" in fields:
        v = text(fields["venue"])
        match = re.fullmatch(r"arxiv(?: preprint)?(?: arxiv:)?\s*([a-z-]+/\d{7}|\d{4}\.\d{4,5})(v\d+)?", v)
        if match:
            fields.setdefault("arxiv_id", match.group(1) + (match.group(2) or ""))
            fields["venue"] = "arXiv"
    return fields, issues
