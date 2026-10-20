# uv-lock-integrity

Find declared version contradictions in `uv.lock`, offline and without changing project files.

A manually merged lockfile can select `numpy==2.2.4` while `pyproject.toml` says `numpy!=2.2.4`. On the [public reporter's input](https://github.com/astral-sh/uv/issues/12276), uv **0.13.1** accepts that lock with `uv lock --check`, `uv lock --offline`, and `uv sync`. This checker reports the contradiction and exits **1**.

```text
VIOLATIONS: 1 contradiction(s), 0 unresolved condition(s)
Target: Python 3.12.13, linux, x86_64
pyproject.toml: numpy!=2.2.4 rejects locked 2.2.4
Scope: direct production version constraints. Use --format json for checks and unexamined scope.
```

## Try the public reproduction

Requires **Python 3.11+**. From this source checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m uv_lock_integrity examples/invalid-exclusion --environment examples/linux-python312.json
```

The last command intentionally exits **1**. The bundled target JSON describes the environment to evaluate; it does not run Linux or install NumPy. A derived control changes the exclusion to `!=2.2.5` while retaining locked `2.2.4`:

```sh
.venv/bin/python -m uv_lock_integrity examples/valid-exclusion --environment examples/linux-python312.json
```

Expected: `CONSISTENT: 0 contradiction(s), 0 unresolved condition(s)`, exit **0**.

## Check a project

```sh
.venv/bin/python -m uv_lock_integrity /path/to/project --format json
```

Reads that directory's `pyproject.toml`, `uv.lock`, and declared workspace member manifests. The target defaults to the Python interpreter running this checker. All target fields are included in JSON.

For a different target, export a complete PEP 508 environment, edit the related fields together, then supply it with `--environment`:

```sh
.venv/bin/python -m uv_lock_integrity --show-environment > target.json
.venv/bin/python -m uv_lock_integrity /path/to/project --environment target.json --format json
```

`python_version` must match `python_full_version`; platform and implementation fields must describe the intended target. Results apply only to those supplied values. CLI entrypoint `uv-lock-integrity` has the same arguments.

## Agent and CI interface

| Exit | `status` | Meaning |
| --- | --- | --- |
| 0 | `consistent` | Examined direct production version constraints are consistent for the reported target. |
| 1 | `violations` | At least one declared constraint rejects its locked version. |
| 2 | `inconclusive` | Invalid, unsupported, missing, or ambiguous input prevents a complete scoped verdict. |

JSON schema version **1** includes `target_environment`, `scope`, `checks`, `findings`, `errors`, and `unexamined`. Each contradiction identifies the manifest, original requirement, dependency, and selected version. If an unresolved condition accompanies a proven contradiction, exit **2** takes precedence and the finding remains in JSON. Compare exit codes before interpreting an empty findings array as success.

The audit itself performs file reads and packaging-specifier evaluation. Installation of this tool may need a package index; auditing performs no network requests, dependency installation, subprocess invocation, project import, or file writes.

For GitHub Actions, install a reviewed pinned version of this checker into a separate environment and invoke it against the checked-out project. See [the CI recipe](docs/ci.md). Treat contributed lockfiles as untrusted data. Apply normal runner resource and permission limits.

## Scope and alternatives

Supported: uv lock format **version 1, revisions 0 through 3**; static root and workspace direct production requirements; registry packages and declared workspace sources; PEP 440 versions and target-specific PEP 508 markers. Same-name variants must resolve unambiguously through dependency edge version/source and applicable resolution markers.

Explicitly unexamined: transitive constraints, optional extras, dependency groups, wheel availability, artifact hashes/authenticity, vulnerabilities, build/runtime compatibility, and other environments. A consistent result describes this narrow audit. Empty production scope is inconclusive.

Dynamic dependencies, dependency overrides/constraints, non-workspace source overrides, direct URLs, extra/group-specific lock markers, newer lock formats and ambiguous/missing targets produce exit **2**. These conditions need resolver semantics or further implementation.

| Task on the original public fixture | Observed result |
| --- | --- |
| uv 0.13.1 `lock --check`, `lock --offline`, default `sync` | Exit 0; contradictory locked version remains. |
| uv-align 0.2.1 `--check` | Exit 0 on this exclusion case. |
| uv-lock-check unchanged default verifier with uv 0.13.1 | Local execution exits 0 and installs 2.2.4. |
| uv 0.13.1 `lock --refresh` | Re-resolves to compatible 2.5.4; uses network and changes the lock. |
| This checker | Read-only audit exits 1 with the declaring constraint and rejected version. |

Use uv for resolution, installation and repair. This checker adds a separate static check. The comparison is one public reproduction, not a benchmark across arbitrary locks. [Evidence and fixture provenance](docs/evidence.md) distinguish the original case, derived controls, and actual user adoption. This is an independent project, with no claimed Astral or third-party affiliation.

## Development and contributing

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Report a minimal manifest/lock pair, target environment JSON, command, exit code and output. Remove credentials and private package URLs before posting. Contributions should include a failing reproduction, a scoped fix, and tests for valid and unsupported inputs. AI-assisted contributions must disclose assistance; contributors remain responsible for execution evidence and accuracy.

MIT license. Public reproduction attribution and limits: [docs/evidence.md](docs/evidence.md).
