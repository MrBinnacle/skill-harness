"""Evidence-side repository modules.

Per A24: functional API only. No classes. No update_*/delete_*/set_*/
patch_*/modify_*/remove_* symbols. The AST-walker test enforces this.

These repos take a sqlite3.Connection parameter — they do NOT construct one.
Connections come from open_evidence() in storage.migrations.
"""
