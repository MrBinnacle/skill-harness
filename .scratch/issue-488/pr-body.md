## Evidence body — PR #488

### Criterion 1: The `vale` job does not fail when the prose is clean and the network is unreliable

**What changed:** The `vale` job caches the binary under `${{ runner.temp }}/vale-bin` with key `vale-${{ runner.os }}-3.9.1`. On cache hit the download step is skipped. Curl uses `-SfL` so a failed fetch prints its reason instead of feeding tar empty input.

**Test:** `test_dc18_vale_version_pins_are_green` (DC-18 green on the real pins) and `test_dc18_install_steps_are_split_and_named` (cache step present on the vale job).

---

### Criterion 2: The four `test` cells do not fail at `Install Vale` when the network is unreliable

**What changed:** The `test` job uses the same cache key and path. Windows install writes `vale.exe` via Windows Python and `cygpath -w` (the pre-cache traps), not an MSYS `/tmp` path Windows Python cannot open. `chmod +x` is Linux-only.

**Test:** `test_dc18_single_linux_url_drift_blocks`, `test_dc18_windows_url_drift_blocks`, `test_dc18_cache_key_drift_blocks`, `test_dc18_install_steps_are_split_and_named`.

---

### Criterion 3: A genuine install failure still fails the job AND says which step failed and why

**What changed:** Both jobs split install into `Install Vale` (download, skipped on cache hit) and `Install Vale to system path` (copy + `vale --version`).

**Test:** `test_dc18_install_steps_are_split_and_named` — both job bodies carry both step names and the cache id.

---

### Criterion 4: A control proves the distinction

**Controls:**

1. `test_dc18_linux_url_drift_blocks` — all Linux URLs drifted → DC-18 red.
2. `test_dc18_single_linux_url_drift_blocks` — only the first Linux URL drifted → DC-18 red.
3. `test_dc18_windows_url_drift_blocks` — Windows zip URL drifted → DC-18 red.
4. `test_dc18_cache_key_drift_blocks` — cache key drifted → DC-18 red.
5. `test_dc18_missing_registered_text_blocks` — registered sentence removed → DC-18 red.
6. `test_dc18_install_steps_are_split_and_named` — step split and `runner.temp` cache path present on both jobs.

---

### Criterion 5: A contract holds the version pins in lockstep

**What was built:** DC-18 in `scripts/drift_check.py`:

- Linux tar.gz URL groups must be `("3.9.1", "3.9.1")` on every match.
- Windows zip URL groups must be `("3.9.1", "3.9.1")`.
- Cache keys `vale-${{ runner.os }}-N` must capture `3.9.1` on every match.
- Registered text in `tests/test_vale_doctrine_agreement.py`: "pinned to the same version the CI workflow installs".

---

### Review fixes on this branch

The implementer diff broke Windows on every cache miss: `chmod +x /tmp/vale-bin/vale` ran after extracting `vale.exe`, and Windows Python opened an MSYS `/tmp/...` zip path. Cache path `/tmp/vale-bin` is not a path `actions/cache` restores on Windows. DC-18 duplicated one Linux ValueSite and left the Windows URL and cache keys unguarded. The "test job only" mutation control mutated the second Linux URL (vale job). Those are corrected here.

### Gate results

```
ruff check src tests scripts                     — passed
ruff format --check src tests scripts            — passed
mypy --strict src/ tests/                        — passed
python -m pytest tests/test_drift_check.py -k dc18 — 8 passed
```
