# Reproduction evidence

The original `examples/invalid-exclusion/pyproject.toml` and `uv.lock` are the TOML blocks from [astral-sh/uv issue 12276](https://github.com/astral-sh/uv/issues/12276), reported by `rg936672`. The report describes a manual merge leaving a selected version incompatible with the recorded constraint. These are public reporter inputs, not a claim of execution on the reporter's computer.

`examples/valid-exclusion` is an explicitly derived control: both declaration metadata exclusions become `!=2.2.5`, selected NumPy remains `2.2.4`. Other adversarial test inputs are engineering fixtures.

On 2026-10-20 the original input was tested with uv **0.13.1** and Python **3.12.13**. Native lock checks and default sync succeeded despite the exclusion; a local default execution of the unchanged [uv-lock-check verifier](https://github.com/hbelmiro/uv-lock-check) also succeeded. Its subprocess installed NumPy **2.2.4**. This was a local invocation, not a hosted Actions run. A reproducible [scope report](https://github.com/hbelmiro/uv-lock-check/issues/109) discloses automated assistance. The report is our own contribution, not independent adoption or endorsement.

The successful repair baseline, `uv lock --refresh`, selected **2.5.4** and changed the lockfile. Refresh is a useful resolution alternative; it is distinct from auditing the existing input without mutation or network access. `--refresh --offline` was rejected as incompatible options.

The separate public [kingjin94/workspace-conflicts](https://github.com/kingjin94/workspace-conflicts) checkout was used as a valid workspace control: all four direct workspace member requirements were consistent for the supplied Python3.12 Linux environment. Its mutually exclusive optional extras remain outside this checker's production scope. This does not validate that report's optional-extra behavior.

The test suite covers the public contradiction, derived valid control, exact pins, active/inactive markers, ambiguous/disambiguated versions, workspace members, source overrides, dynamic declarations, malformed inputs, path escapes and input immutability. Socket and subprocess creation are blocked during an audit test; project setup code is deliberately invalid and never executed. Installation is a separate operation.

No human adoption, GitHub star outcome, universal cross-platform result, dependency artifact authenticity or complete dependency resolution is established by these tests.
