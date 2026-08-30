"""The runtime-package installer: a planning engine (core), a CLI, and an optional GUI.

Every filesystem decision lives in core. The CLI and the GUI choose only what to print and
what to ask; if either one ever needs its own copy or delete, that is the bug, because the
two front ends would then be able to disagree about what is safe.
"""
