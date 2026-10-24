# Public below-floor case: kastellan#741

[Original request](https://github.com/hherb/kastellan/issues/741) asks for a hermetic check of declared Python minimum versions after manual lock edits. This reproduction uses actual public worker files at commit `3f2ae1cfa985702f076e884fbf415272ea1a554e` and the exact historical anyio4.13.0 package block at `ef8144f8ab5764782ba2691ce972b53af9d84928`. Original files are downloaded from their source, with SHA256 checks; they are not vendored here.

The current manifest declares `anyio>=4.14.2` and four other production requirements. Its unchanged lock selects anyio4.15.1. Replacing only the anyio package block with its historical4.13.0block retains the declaring requirement and creates the issue's below-floor condition. It is a controlled mutation of public source, not evidence that the current deployed project is vulnerable.

Measured on macOS arm64, Python3.12.13 and native uv0.13.5:

| Input | `uv lock --check --offline` | This checker |
| --- | --- | --- |
| Unchanged public files | 0 | 0, five direct requirements checked |
| Historical anyio4.13.0 block under declared>=4.14.2 | 0 | 1, declaring requirement and rejected version |
| anyio package entry removed | Not tested | 2, inconclusive rather than a clean empty match |

The original issue reports uv0.11.29; that version was not executed in this reproduction. The commands install/import no worker dependencies, Torch or model weights. Auditing performs no network access or file mutation. The source-download preparation and installation of this checker are separate network-capable steps. Linux execution, vulnerability scanning, actual runtime behavior and upstream adoption are unverified.

With the checker installed in a Python3.11+ environment, run from this checkout:

```sh
python examples/reproduce_kastellan741.py /tmp/kastellan-741-new --uv /absolute/path/to/uv
```

The output directory must not exist. Omit `--uv` to run only the checker controls. Results include exact commands and output. A future native fix can change the native exit without invalidating the three checker controls.

For an agent or CI gate, require exit0 and the intended target environment, then require named `checks` entries for `anyio` and `transformers`. Keep the missing-entry control: an absent package must produce an incomplete result rather than being treated as an empty success. Results cover declared direct production constraints only, not the issue's separate advisory-coverage request. Installing an additional checker is an explicit dependency decision; a small project-specific floor assertion remains a reasonable alternative when avoiding another tool is preferable.

This checker is independently maintained by GwangHoonYoo; no affiliation with or endorsement by kastellan is claimed. Reproduction and explanation were AI-assisted and executed locally.
