"""A30 — discover() must raise BootstrapError on duplicate version numbers.

The check runs BEFORE filename-validation so a duplicate-version error is
distinguishable from a malformed-filename error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skill_harness.storage.errors import BootstrapError
from skill_harness.storage.migrations import discover


class TestDiscoverRejectsDuplicateVersions:
    def test_duplicate_version_raises_bootstrap_error(self, tmp_path: Path) -> None:
        """Two files with the same NNNN prefix in the same directory → BootstrapError."""
        d = tmp_path
        (d / "0001_one.sql").write_text("SELECT 1;", encoding="utf-8")
        (d / "0001_two.sql").write_text("SELECT 2;", encoding="utf-8")
        with pytest.raises(BootstrapError) as exc_info:
            discover(d)
        msg = str(exc_info.value)
        # Must name the version number
        assert "0001" in msg
        # Must name both conflicting filenames
        assert "0001_one.sql" in msg
        assert "0001_two.sql" in msg

    def test_single_version_per_file_does_not_raise(self, tmp_path: Path) -> None:
        """Each version appears exactly once → no error."""
        d = tmp_path
        (d / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
        (d / "0002_second.sql").write_text("SELECT 2;", encoding="utf-8")
        result = discover(d)
        assert len(result) == 2

    def test_duplicate_version_message_names_directory(self, tmp_path: Path) -> None:
        """BootstrapError message must also include the directory path."""
        d = tmp_path
        (d / "0003_alpha.sql").write_text("SELECT 1;", encoding="utf-8")
        (d / "0003_beta.sql").write_text("SELECT 2;", encoding="utf-8")
        with pytest.raises(BootstrapError) as exc_info:
            discover(d)
        # The directory path (or at least its name) is in the message
        assert str(d) in str(exc_info.value)

    def test_duplicate_check_fires_before_filename_validation(self, tmp_path: Path) -> None:
        """Even if one duplicate file has a well-formed name, the BootstrapError fires
        before any ValueError from filename validation."""
        d = tmp_path
        (d / "0001_valid.sql").write_text("SELECT 1;", encoding="utf-8")
        (d / "0001_also_valid.sql").write_text("SELECT 2;", encoding="utf-8")
        # Must raise BootstrapError, NOT ValueError
        with pytest.raises(BootstrapError):
            discover(d)
