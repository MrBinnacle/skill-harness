"""Runtime-side repository modules.

Per A24 + A2: runtime tables are MUTABLE by design. update_*/delete_* functions
are PERMITTED here (unlike evidence repos). The AST-walker test only scans
repositories/evidence/, not repositories/runtime/.

These repos take a sqlite3.Connection parameter — they do NOT construct one.
Connections come from open_runtime() in storage.migrations.
"""
