"""Temporary seed-reproducibility probe for #561. Not committed to the pull request."""

STATE = {"poisoned": False}


def test_probe_deterministic_failure() -> None:
    raise AssertionError("seed probe 561: deterministic failure")


def test_probe_poisoner() -> None:
    STATE["poisoned"] = True


def test_probe_victim() -> None:
    assert not STATE["poisoned"], "seed probe 561: ran after test_probe_poisoner in this process"
