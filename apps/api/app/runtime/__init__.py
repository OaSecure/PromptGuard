"""Runtime package namespace.

Submodules intentionally stay lazy so split worker environments can import one
runtime probe without loading unrelated parser, OCR, or ML dependencies.
"""
