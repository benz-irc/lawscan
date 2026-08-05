"""Who a judgment binds, read from which court decided it.

This is the smallest rule in the project and one of the clearest. The Supreme
Court's Criminal Division for Persons Holding Political Positions tries, by the
statute that creates it, persons holding political positions. So the class its
judgments bind is not something to work out from the text — it is the name of
the court.

The model does not work it out either. Given a judgment it reads the parties,
and the parties are one deputy mayor of a named tambon, one secretary to one
minister, one member of one provincial council. Every one of those is true
about the document and none of them is a group. Measured over the six
judgments and rulings in the reference set, the model's answers sat at 38%
similarity to the operator's; the court's own jurisdiction sits at 76%.

Nothing else in the audience column is decided here. A law that regulates
something has to be read to know who it regulates, and that is the model's job.
"""

from __future__ import annotations

from lawscan.rules import kind

#: What the operator writes for every one of these, without exception: six
#: judgments and rulings, six answers that open with this phrase.
POLITICAL_OFFICE = "ผู้ดำรงตำแหน่งทางการเมือง"


def read(text: str) -> str:
    """The class a judgment binds, or nothing if this is not a judgment."""
    return POLITICAL_OFFICE if kind.read(text) in kind.NARRATIVE else ""
