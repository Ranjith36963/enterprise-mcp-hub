"""ARQ worker tasks (Batch 2 Phase 5).

Tasks are written as plain async functions that take an ARQ-shaped ``ctx``
dict (``ctx['db']`` for the aiosqlite connection, ``ctx['enqueue']`` for
fan-out into other tasks). This keeps the module importable without the
``arq`` package installed — pytest never touches Redis.

Runtime wiring (settings + Redis pool) lives in ``workers/settings.py`` and
is only imported by the ``arq`` CLI.
"""
