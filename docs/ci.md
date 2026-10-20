# GitHub Actions recipe

Install the checker separately from the project dependencies, then audit without calling the project build backend. Replace `REVIEWED_COMMIT` below with a reviewed full public commit after release. This is a template, not a published marketplace action or an already-tested hosted workflow.

```yaml
name: Direct lock constraint audit
on: [push, pull_request]
permissions:
  contents: read
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: python -m venv "$RUNNER_TEMP/lock-audit"
      - run: >-
          "$RUNNER_TEMP/lock-audit/bin/python" -m pip install
          'uv-lock-integrity @ git+https://github.com/GwangHoonYoo/uv-lock-integrity@REVIEWED_COMMIT'
      - run: >-
          "$RUNNER_TEMP/lock-audit/bin/python" -m uv_lock_integrity . --format json
```

The default target is this runner's interpreter/platform. A target JSON can select another marker environment, but it does not emulate it. Exit2 requires investigation just as exit1 does. Direct production scope is intentionally narrower than resolver or security validation.
