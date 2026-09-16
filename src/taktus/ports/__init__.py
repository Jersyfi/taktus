"""Cross-cutting ports: designed for what the core needs, never mirroring a tool (ADR-0016).

A port is a Python protocol. The core calls it; a driven adapter implements it. Nothing here
imports a technology, and nothing here imports a component: the types a port carries are its
own or the shared kernel's.
"""
