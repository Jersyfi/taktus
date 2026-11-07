"""Owns knowledge sources, embeddings, citations.

What exists today: the guides beyond the repository (UC-13.6, ADR-0065). The repository declares
an administration guide and a guide for the people who use Taktus (`docs/guides/guides.yaml`).
A rule renders their pages from the repository at one commit, each naming the files and the
commit it came from (`domain/service/render.py`). A rule measures each page against what the
organisation's knowledge system holds, and a page a person edited there is never overwritten:
its difference from the repository is reported (`domain/service/pages.py`). The pages are put
into the knowledge system through the capability `knowledge.pages`
(`application/service/publish_guides.py`).

And the knowledge layer (UC-5.5, ADR-0265): an answer drawn from a knowledge source is cited by
rule, every statement naming the documents the asker read, with their links and versions
(`domain/service/citing.py`). The index keeps a reference and a digest of every document read,
never its text, and learns from every reading whether a document changed or was removed
(`domain/model/index.py`, `domain/service/indexing.py`). The run reaches the rule through its
port `Citations`; `application/service/cite_answer.py` answers it.
"""
