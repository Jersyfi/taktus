"""Owns process, version, step, method, exactness class, bundle.

The domain model is the process graph of docs/architecture/control-plane.md §4: a directed
graph of steps, each carrying its method, the reason, the alternatives rejected, a fallback where
the method can vary, and an exactness class where it produces a result. The step itself is the
shared kernel's `Step`; this component owns the graph around it — versions, edges, triggers,
service levels — and the rules that make a graph valid (`domain.service.validation`).
"""
