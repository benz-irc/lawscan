"""Two corrections to กลุ่มเป้าหมาย that the answer is not trusted to make.

Both were found by the operator reading finished rows, and both were applied
to the CSV by hand — which meant they vanished on the next rebuild. Asking the
prompt for them is worth doing and is done, but a prompt is a request. This is
the part that holds regardless of which model answered, or whether it complied
that particular time.

The two are opposite in shape. One splits: a group distinguished only by which
section it is cited in is two groups, because a reader checks one section and
needs to find themselves under it. One removes: a word broad enough to cover
anyone puts no one on notice, and the document usually meant itself by it.
"""

import re

#: Words that name no group. Each appeared alone in a finished row, next to
#: items that did name someone, and each is a word the document uses for the
#: office writing it or for the public at large. They are removed only in that
#: company — see ``tidy``. This is a closed list rather than a rule about
#: length or structure, because the difference between ``เจ้าหน้าที่`` and
#: ``เจ้าหน้าที่ผู้รับผิดชอบงานทะเบียน`` is not structural, it is whether the
#: words draw a line, and that has to be read rather than computed.
#:
#: ``หน่วยงานของรัฐ`` is deliberately absent. It is broad, but state bodies are
#: in and private ones are out, which is a line a reader can stand on.
NAMES_NOBODY = frozenset({
    "นิติบุคคล",
    "ประชาชน",
    "พนักงานเจ้าหน้าที่",
    "ส่วนราชการ",
    "สำนักงาน",
    "เจ้าหน้าที่",
})

#: A citation is a place in a law, not a property of a person — so the words
#: around it are the same words twice, and repeating them costs nothing while
#: leaving them joined costs a reader the ability to search for their section.
_CITED = r"(?:มาตรา|ข้อ|วรรค|หมวด)"
_JOINED = re.compile(
    rf"^(?P<prefix>.*?)(?P<first>{_CITED}\s*[\d๐-๙]+(?:\s*\([^)]*\))?)"
    rf"(?:\s*และ\s*(?P<more>{_CITED}\s*[\d๐-๙]+(?:\s*\([^)]*\))?))+$"
)
_TAIL = re.compile(rf"\s*และ\s*({_CITED}\s*[\d๐-๙]+(?:\s*\([^)]*\))?)")


def _split_citations(group: str) -> list[str]:
    """``ผู้แจ้งตามมาตรา 13 และมาตรา 16`` as two groups, or the group as it is.

    The prefix is repeated onto each citation rather than dropped, because
    ``มาตรา 16`` on its own is a section number, not a group of people.
    """
    match = _JOINED.match(group.strip())
    if not match:
        return [group]
    prefix = match.group("prefix")
    citations = [match.group("first")] + _TAIL.findall(group)
    return [f"{prefix}{citation}".strip() for citation in citations]


def tidy(groups: list[str]) -> list[str]:
    """The audience list as it should reach the column.

    Splitting runs first: a bare word can only be judged against the company
    it keeps, and splitting is what decides how much company there is.
    """
    split = [part for group in groups for part in _split_citations(group)]

    seen: set[str] = set()
    unique = []
    for group in split:
        if group and group not in seen:
            seen.add(group)
            unique.append(group)

    kept = [g for g in unique if g.strip() not in NAMES_NOBODY]
    # Everything named nobody, so nobody is what the document said. An empty
    # column reads as "this law binds no one", which is never true and which
    # nobody would think to go and check.
    return kept or unique
