"""Owns knowledge sources, embeddings, citations.

What exists today: the guides beyond the repository (UC-13.6, ADR-0065). The repository declares
an administration guide and a guide for the people who use Taktus (`docs/guides/guides.yaml`).
A rule renders their pages from the repository at one commit, each naming the files and the
commit it came from (`domain/service/render.py`). A rule measures each page against what the
organisation's knowledge system holds, and a page a person edited there is never overwritten:
its difference from the repository is reported (`domain/service/pages.py`). The pages are put
into the knowledge system through the capability `knowledge.pages`
(`application/service/publish_guides.py`).
"""
