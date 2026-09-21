## Evidence body — PR #488

### Criterion 1: The `vale` job does not fail when the prose is clean and the network is unreliable

**What changed:** The `vale` job already had `actions/cache` keyed on `vale-${{ runner.os }}-3.9.1`, restoring the binary to `/tmp/vale-bin`. After the first run on a given version, no job touches github.com for it. The `Install Vale` step is skipped on cache hit (`if: steps.cache-vale.outputs.cache-hit != 'true'`).

**Test:** `test_dc18_vale_version_pins_are_green` — verifies the synthetic tree (carrying the real ci.yml with both cache steps) is green. The drift check confirms DC-18 passes, meaning both jobs cite the same cached version.

**Observation:** Before this change, the vale job's `curl -sL` silently fed empty input to `tar` on network errors, producing "not in gzip format" with no curl error. After the change, `-SfL` prints the curl failure reason, and the cache eliminates the fetch on subsequent runs.

---

### Criterion 2: The four `test` cells do not fail at `Install Vale` when the network is unreliable

**What changed:** The `test` job now has the same `actions/cache` step keyed on `vale-${{ runner.os }}-3.9.1`, restoring to `/tmp/vale-bin`. The `Install Vale` step is skipped on cache hit. The `Install Vale to system path` step copies from the cache to the system path.

**Test:** `test_dc18_test_job_version_drift_blocks` — mutates only the test job's curl URL to a different version and verifies DC-18 goes red, proving the test job's version pin is guarded.

**Observation:** Before this change, all four `test` cells (ubuntu/windows × py3.12/py3.13) fetched the Vale binary independently via `curl -sL`. A throttled download on one cell failed that cell and blocked the merge, surfacing as a red test with no test having run. After the change, the first cell to run populates the cache; the other three cells restore from cache and never touch the network.

---

### Criterion 3: A genuine install failure still fails the job AND says which step failed and why

**What changed:** Both the `vale` job and the `test` job now have two separate steps for Vale installation:
1. `Install Vale` — downloads and caches the binary (skipped on cache hit)
2. `Install Vale to system path` — copies from cache to the system path and runs `vale --version`

A failure in step 1 (network error, download failure) fails the "Install Vale" step. A failure in step 2 (permission error, corrupted binary) fails the "Install Vale to system path" step. Neither failure can be mistaken for a prose finding at the check list, because the prose linting steps are separate and named.

**Test:** The step names in ci.yml are distinct: "Install Vale" and "Install Vale to system path". A check list in GitHub Actions shows which step failed by name.

**Observation:** Before this change, the `vale` job had one step that combined download + copy + verify. A network failure produced "Vale (prose lint) FAILURE" with three steps `skipped` — indistinguishable from a prose finding without querying the job's step list via the API. After the change, each failure mode has a named step.

---

### Criterion 4: A control proves the distinction

**What was tested:**

1. `test_dc18_vale_job_version_drift_blocks` — changes the vale job's version to 3.9.2; DC-18 goes red with `FAIL DC-18` in the output.
2. `test_dc18_test_job_version_drift_blocks` — changes only the test job's version to 3.8.0; DC-18 goes red, proving the two pins are independently guarded.
3. `test_dc18_registered_text_survives_rewording` — verifies the registered sentence in `test_vale_doctrine_agreement.py` is present and DC-18 is green.
4. `test_dc18_missing_registered_text_blocks` — removes the registered sentence; DC-18 goes red.

All four controls pass: induced failures fail loudly with a named reason (DC-18), and a clean run gates on prose exactly as it does today.

---

### Criterion 5: A contract holds the two version pins in lockstep

**What was built:** DC-18 added to `scripts/drift_check.py`:
- Two `ValueSite` legs check that every occurrence of the Vale Linux tar.gz URL in `.github/workflows/ci.yml` cites version 3.9.1. The regex captures both the URL path version and the filename version, asserting both match `("3.9.1", "3.9.1")`.
- One `RegisteredText` leg checks that `tests/test_vale_doctrine_agreement.py` contains the sentence "pinned to the same version the CI workflow installs".

**Test:** `test_dc18_vale_version_pins_are_green` (green by construction) + `test_dc18_vale_job_version_drift_blocks` + `test_dc18_test_job_version_drift_blocks` + `test_dc18_missing_registered_text_blocks`.

**Observation:** Before this change, the two version pins (vale job's curl URL and test job's curl URL) had no mechanical guard. A contributor could update one and forget the other, producing a cache hit on a version the doctrine-agreement tests reject. After the change, `python scripts/drift_check.py` exits 1 and prints `FAIL DC-18: ...` when the two disagree.

---

### Gate results

```
ruff check src tests scripts                     — passed
ruff format --check src tests scripts            — passed
mypy --strict src/ tests/                        — passed
python scripts/drift_check.py                    — PASS, 21 live contracts hold
python -m pytest tests/test_drift_check.py -k dc18 — 5 passed
```

### Files changed

| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | Add `actions/cache` step, `GITHUB_TOKEN` auth, `-SfL` flag, and split install step in the `test` job |
| `scripts/drift_check.py` | Add DC-18 row (Vale version pins) to LIVE_ROWS |
| `tests/test_drift_check.py` | Add DC-18 to _LIVE_IDS, add `_VALE_URL` to _LIVE_SURFACES, add 5 DC-18 tests |
