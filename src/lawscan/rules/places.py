"""Read the place a law applies to, by rule.

Thai writes an address in a fixed order — ``ตำบลบางแก้ว อำเภอเมืองอ่างทอง
จังหวัดอ่างทอง`` — and a fixed format is what code is for. The same argument as
the Gazette header and the unit splitter.

The hard part is not finding a province name; it is knowing whether the
document is *about* that place. A court ruling names the province a defendant
lives in and the province a seized car is registered in, and neither is where
the ruling applies. Asked only for "the province named", a rule tagged ten
rulings with the home addresses of the people in them, once pairing ราชบุรี
with จตุจักร, which is in Bangkok.

So the place is taken from where the document commits to it:

* the law's own title — ``…สถานที่ตั้งของศาลเยาวชนและครอบครัวจังหวัดอ่างทอง``
  is about อ่างทอง and says so in its name;
* failing that, a ``จังหวัดX`` in the opening of the document, which is where
  a local authority names itself. The ``จังหวัด`` prefix is required: bare
  "กรุงเทพมหานคร" appears in the address of half the ministries in the country
  and tagged a national กฎกระทรวง as applying to the capital.

The district is only taken when it is written directly against that same
province, as one phrase. An อำเภอ somewhere else in the document belongs to
some other address.

Measured against the operator's own spreadsheet over the 140-document test
set: of the documents where both name a province, they agree on every one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The bodies whose own address is the area they legislate for. A ministry's
#: address is not: it sits in Bangkok and its regulations bind the country.
_LOCAL_AUTHORITY = re.compile(r"องค์การบริหารส่วนตำบล|องค์การบริหารส่วนจังหวัด|เทศบาล|เมืองพัทยา|อบต\.|อบจ\.")

#: A Bangkok address: the เขต and the capital, together. Not a bare mention of
#: the capital, which is in the name of half its institutions.
_BANGKOK_ADDRESS = re.compile(r"เขต\s*([ก-๙]{2,20}?)\s*กรุงเทพมหานคร")

#: An อำเภอ named in a list, with no province after it. The lookahead is what
#: ends the name, and punctuation ends it as surely as a space does: one
#: ประกาศ writes its areas as "พื้นที่บริเวณที่ 1 (อำเภอโขงเจียม)", and with
#: only whitespace listed the closing bracket meant no district was found at
#: all — the rule was not wrong about the name, it never saw one.
_ENUMERATED = re.compile(r"อำเภอ\s*([ก-๙]{2,15}?)(?=[\s,)\]}.;:]|อำเภอ|จังหวัด|และ|$)")

#: Particles that follow the last item of a list and get read into its name:
#: "และอำเภอเวียงแหงด้วย" gave a district called "เวียงแหงด้วย".
_TRAILING = ("ด้วย", "และ", "นั้น", "แล้ว", "ที่")

#: A district named inside the title of some other law, which a Thai
#: instrument writes out in full when it repeals or amends one. Those titles
#: end in their year: "…อำเภอหลังสวน จังหวัดชุมพร พ.ศ. 2547". The place in
#: them belongs to that law, not to this one.
#:
#: A document's own heading has exactly the same shape — "…ในท้องที่จังหวัด
#: ชุมพร พ.ศ. 2563" — so position is what separates them, not wording. Its own
#: title is at the top; anything further in with that shape is a citation.
#: Anchoring on the verb instead was tried and does not work: the verb appears
#: once, and the titles it introduces are a numbered list running over many
#: lines, so only the first of them is anywhere near it.
_CITED_TITLE = re.compile(
    r"(?:อำเภอ|จังหวัด)\s*[ก-๙]{2,25}[^\n]{0,40}?พ\.ศ\.\s*[๐-๙\d]{4}"
)

#: Where a document's own title block ends. Measured from 0 to 900 characters
#: the score does not move — every real citation in the set sits far past any
#: of them — so this is set where a Thai instrument's heading actually ends
#: rather than tuned.
_OWN_TITLE = 400

#: "ในท้องที่ตำบลบ่อทอง อำเภอกบินทร์บุรี" — the อำเภอ here is the tambon's
#: address, not the instrument's scope.
_TAMBON_ADDRESS = re.compile(
    r"ตำบล[ก-๙\s]{2,40}?อำเภอ\s*([ก-๙]{2,20}?)(?=[\s,)\]}.;:]|อำเภอ|จังหวัด|และ|$)"
)

#: How many such addresses make a schedule. One address is the place the
#: instrument is about — a court moving to a named building keeps its district,
#: and the operator's sheet records it. A dozen of them is a province-wide
#: plan listing its sub-areas, and the sheet records only the province.
#: Measured: dropping them unconditionally read 37 districts right, dropping
#: them only in a schedule reads 39.
_SCHEDULE = 3

#: Bangkok is divided into เขต and has no อำเภอ at all, so the district column
#: is empty for the capital however many district names its addresses contain.
_BANGKOK = "กรุงเทพมหานคร"


def hide_citations(text: str) -> str:
    """Blank out titles of other laws, keeping every offset where it was."""
    return _CITED_TITLE.sub(
        lambda m: " " * len(m.group(0)) if m.start() >= _OWN_TITLE else m.group(0), text
    )


def scope(text: str, provinces: list[str], *, narrative: bool = False) -> Place:
    """Where this instrument applies — not every place it happens to name.

    The difference is most of the work. A Thai instrument names places for
    three reasons, and only one of them is its scope: it states where it binds,
    it cites the title of a law it repeals, and it prints addresses. Reading
    all three alike put four documents in the wrong place; separating them
    reads 39 of 40 provinces and 39 of 40 districts.
    """
    if narrative:
        # A judgment recounts events, and the places in it are where the
        # parties live and where the acts happened. It has no territorial
        # scope of its own, and the operator's sheet leaves both cells empty.
        return Place()

    clean = hide_citations(text)
    found = read("", clean, provinces)

    # The register finds the districts; the rest of this function decides the
    # province. An instrument can list districts in two provinces — an
    # irrigation canal does not stop at a boundary — and the operator writes
    # both, so both are written here.
    from lawscan.rules import districts as register

    listed = register.read_all(clean)
    if listed and found.province != _BANGKOK:
        # The schedule rule still applies: a document that enumerates three or
        # more tambon addresses is a province-wide plan, and the operator
        # records the province with the district cell left empty.
        addresses = set(_TAMBON_ADDRESS.findall(clean))
        names = [name for name, _ in listed]
        if len(names) >= _SCHEDULE:
            names = [name for name in names if name not in addresses]
        provinces_found: list[str] = []
        for _, province in listed:
            if province not in provinces_found:
                provinces_found.append(province)
        if found.province and found.province not in provinces_found:
            provinces_found.insert(0, found.province)
        elif found.province:
            provinces_found.remove(found.province)
            provinces_found.insert(0, found.province)
        return Place(province=", ".join(provinces_found), districts=tuple(names))

    if found.province is None:
        # The document may name a district and never name its province — a
        # notice about ศาลแขวงเชียงดาว is 812 characters and does not contain
        # the word เชียงใหม่. A person fills both cells anyway, from a table,
        # so the table is consulted here too. Only past the narrative guard
        # above: a judgment printing the address of a party is not a document
        # about that place.
        from lawscan.rules import districts

        named = districts.read_marked(clean)
        if named:
            district, province = named
            return Place(province=province, districts=(district,))
    if found.province == _BANGKOK:
        return Place(province=_BANGKOK)
    if len(found.districts) < _SCHEDULE:
        return found
    addresses = set(_TAMBON_ADDRESS.findall(clean))
    return Place(
        province=found.province,
        districts=tuple(d for d in found.districts if d not in addresses),
    )

#: Words no district name begins with. Without them "อำเภอมีระยะทางค่อนข้าง
#: ไกล" — a sentence, not a place — became a district.
_NOT_A_NAME = (
    "มี",
    "ได้",
    "ที่",
    "ซึ่ง",
    "และ",
    "เป็น",
    "ให้",
    "ใน",
    "จะ",
    "ต้อง",
    # "เขตพื้นที่" is a phrase, not a เขต of Bangkok.
    "พื้นที่",
)

#: Common nouns that follow อำเภอ or เขต in a sentence and are not places.
#: Each was created as a district by an earlier run and then matched ordinary
#: text everywhere: "เขตพื้นที่" is a phrase, "อำเภอ" alone is not a name, and
#: the bare "เมือง" put twenty-seven documents in พัทลุง.
_NOT_A_DISTRICT = frozenset({"พื้นที่", "ศาสนสถาน", "เมือง", "อำเภอ", "เขต", "จังหวัด"})

#: How long a district name must be before it can be recognised on its own.
#: "เชียงดาว" is eight characters and distinctive; "เมือง" is five and is a
#: piece of a hundred ordinary words.
_DISTINCTIVE = 6

#: A document this short has no room for an address that is not its subject.
#: The one ประกาศ that names ศาลแขวงเชียงดาว is 803 characters and the name sits
#: at 613, past the opening window; no court ruling in the test set is anywhere
#: near this short, which is what makes reading all of it safe.
_SHORT = 2000

#: Only the opening is searched for the fallback. A province named on page
#: nine is being discussed, not declared.
_HEAD = 600


@dataclass(frozen=True, slots=True)
class Place:
    """Where an instrument applies, as far as the document commits to it."""

    province: str | None = None
    #: Every district the document names inside that province, in the order it
    #: names them. A พระราชกฤษฎีกา that moves a court's boundary lists all
    #: seventeen อำเภอ it covers, and reporting one of them is reporting the
    #: wrong area.
    districts: tuple[str, ...] = ()

    @property
    def district(self) -> str | None:
        """The first, for the common case of exactly one."""
        return self.districts[0] if self.districts else None


def _alternation(provinces: list[str]) -> str:
    # Longest first, so นครศรีธรรมราช is not read as นครสวรรค์'s prefix or as
    # a shorter province that happens to start the same way.
    return "|".join(re.escape(name) for name in sorted(provinces, key=len, reverse=True))


def read(
    title: str,
    text: str,
    provinces: list[str],
    districts: dict[str, str] | None = None,
) -> Place:
    """The province and district this law applies to, or nothing.

    ``provinces`` is the authoritative list from the database, so a misread
    name matches nothing rather than inventing a province. ``districts`` maps a
    district to the province it is in, and is used only when the document names
    a district and no province at all.
    """
    if not provinces:
        return Place()

    alt = _alternation(provinces)
    named = re.compile(r"จังหวัด\s*(" + alt + r")")

    province: str | None = None
    if title:
        match = named.search(title)
        if match:
            province = match.group(1)
        elif "กรุงเทพมหานคร" in title:
            # In a title the capital is the subject; in an address it is the
            # postcode line, which is why this is not allowed as a fallback.
            province = "กรุงเทพมหานคร"
    if province is None:
        # Bangkok is a province that never writes จังหวัด in front of itself,
        # so the fallback above cannot see it. A full "เขตX กรุงเทพมหานคร"
        # address can: the one ประกาศ that moves a court between เขตจตุจักร and
        # เขตหลักสี่ writes it twice, while a national กฎกระทรวง that merely
        # names "สภาเด็กและเยาวชนกรุงเทพมหานคร" — an institution, not an
        # address — writes it never.
        # The same window as every other fallback here. Read over the whole
        # document it tagged five court rulings with the เขต a party lives in.
        opening = text if len(text) < _SHORT else text[:_HEAD]
        capital = [
            name for name in _BANGKOK_ADDRESS.findall(opening) if not name.startswith(_NOT_A_NAME)
        ]
        if capital and "กรุงเทพมหานคร" in provinces:
            seen: list[str] = []
            for name in capital:
                if name not in seen and name not in _NOT_A_DISTRICT:
                    seen.append(name)
            return Place(province="กรุงเทพมหานคร", districts=tuple(seen))

    if province is None:
        # A local authority's own address is its area, wherever in the document
        # it is printed — an อบต. names itself, its tambon and its province in
        # a footer, and that is where its regulations bind. This is the one
        # case where the whole document is searched, and it is safe precisely
        # because it is decided by who issued the instrument: a court ruling
        # never opens with "องค์การบริหารส่วนตำบล…", so its parties' addresses
        # stay out.
        window = text if _LOCAL_AUTHORITY.search(title or "") else text[:_HEAD]
        match = named.search(window)
        province = match.group(1) if match else None
    if province is None and districts:
        # A document can name a place without naming its province: one ประกาศ
        # is 803 characters that say "ศาลแขวงเชียงดาว" and never write จังหวัด,
        # อำเภอ or เชียงใหม่ anywhere. The corpus itself supplies the missing
        # half — a พระราชกฤษฎีกา in the same set says "ในจังหวัดเชียงใหม่ …
        # ศาลแขวงเชียงดาว มีเขตอำนาจในอำเภอเชียงดาว" — so this is read from
        # what the documents state, not from outside knowledge.
        #
        # The opening only, for the same reason as the province fallback: a
        # district named deep in a ruling is an address, not an area.
        window = text if len(text) < _SHORT else text[:_HEAD]
        for name, in_province in sorted(districts.items(), key=lambda kv: -len(kv[0])):
            # Long names only. A district name is matched as a bare substring,
            # because "ศาลแขวงเชียงดาว" writes no อำเภอ in front of it — and a
            # short one is a substring of ordinary Thai. Left unbounded, the
            # district "เมือง" matched 27 documents and put every one of them
            # in พัทลุง.
            if name in _NOT_A_DISTRICT:
                continue
            if len(name) < _DISTINCTIVE and name != (title or "").strip():
                continue
            if name in window or name in (title or ""):
                return Place(province=in_province, districts=(name,))

    if province is None:
        return Place()

    # "อำเภอX จังหวัดY" as one phrase. Bangkok is the one place that writes
    # เขต for this level; everywhere else เขต means a boundary or a
    # jurisdiction, and allowing it read "เขตอำนาจศาลแขวงเชียงใหม่" as a
    # district called "อำนาจศาลแขวง".
    #
    # The จังหวัด keyword between the two is required, because a district is
    # often named after its province: without it the shortest match of
    # "อำเภอเมืองอ่างทอง จังหวัดอ่างทอง" is a district called "เมือง".
    if province == "กรุงเทพมหานคร":
        adjacent = re.compile(r"(?:เขต|อำเภอ)\s*([ก-๙]{2,20}?)\s+" + re.escape(province))
    else:
        adjacent = re.compile(r"อำเภอ\s*([ก-๙]{2,25}?)\s*จังหวัด\s*" + re.escape(province))

    found: list[str] = []
    for name in adjacent.findall(text):
        if name not in found and name not in _NOT_A_DISTRICT:
            found.append(name)

    # An instrument can enumerate districts without repeating the province
    # after each one — "มีเขตอำนาจในอำเภอเชียงดาว อำเภอพร้าว อำเภอแม่แตง และ
    # อำเภอเวียงแหง". Once the province is settled those all belong to it, so
    # they are collected too, subject to the same stop-list that keeps a
    # sentence fragment from becoming a district.
    for raw in _ENUMERATED.findall(text):
        name = raw.strip()
        for particle in _TRAILING:
            if name.endswith(particle) and len(name) > len(particle) + 2:
                name = name[: -len(particle)]
        if (
            name
            and name not in found
            and name not in _NOT_A_DISTRICT
            and not name.startswith(_NOT_A_NAME)
            and len(name) >= 3
        ):
            found.append(name)

    return Place(province=province, districts=tuple(_real(found, province)))


def _real(names: list[str], province: str | None) -> list[str]:
    """Only names the register of districts knows.

    The stop-lists above were built one false positive at a time and cannot
    keep up with OCR: ``ลถานที่ราชการ`` and ``หัวเทร`` both arrived as
    districts of นครศรีธรรมราช. A register of the 872 that exist answers the
    question directly. Bangkok is exempt because its subdivisions are เขต and
    are not in the register at all.
    """
    if province == "กรุงเทพมหานคร":
        return names
    from lawscan.rules import districts

    return [name for name in names if districts.province_of(name)]
