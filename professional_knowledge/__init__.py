"""Portable entry points for the professional knowledge recognition module."""

from .catalog import list_rag_knowledge_bases


def render_professional_knowledge_system(*args, **kwargs):
    from .ui import render_professional_knowledge_system as _render

    return _render(*args, **kwargs)


__all__ = ["render_professional_knowledge_system", "list_rag_knowledge_bases"]
