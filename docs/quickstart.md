# Quick start

Get a task proven end to end. The walkthrough below uses the same command sequence
as the README quickstart. `tests/test_readme_quickstart.py` executes that sequence
in a clean temporary workspace, proves that a pre-integrity audit fails closed,
and proves that the authenticated final audit exits `0`. It also compares the
documented transcript with real output. `tests/test_doc_transcripts.py` checks the
failing-run transcript on this page, and `tests/test_docs_metadata.py` checks that
every `plan-auditor` command on this page is a real subcommand.

## Install

```bash
pipx install plan-auditor
```

Prefer an isolated environment. If you must install into the current one:

```bash
pip install plan-auditor
```

Python 3.11 or newer. No third-party runtime dependencies.

The commands and transcripts on this page were written against a checkout of
`main` and re-checked against the published `2.4.2` release. See the
release-status section of the README for what each published version contains.

The examples invoke the interpreter as `python`. On a system that only provides
`python3`, activate a virtualenv that has `python` or change the `cmd` in the
plan to `python3`.

```bash
plan-auditor --help
```

If you would rather not install anything, the deterministic core runs straight from
a checkout:

```bash
python scripts/audit_check.py --help
```

## Your first verified task

The walkthrough uses a throwaway directory so nothing else on your machine is
touched. It uses the same command sequence as the README quickstart; CI executes
that sequence and compares the transcript against real output.

**1. Create the project and the plan.**

```bash
mkdir plan-auditor-demo && cd plan-auditor-demo
mkdir .plan-auditor
```

`.plan-auditor/plan.json`, and `request-source.json` beside it — the host-owned
statement of what you asked for, sealed on activation so the agent cannot restate it:

```json
{
  "task": "Prove README.md exists and prints its first line",
  "created": "2026-07-24T00:00:00",
  "requirements": [{ "id": "REQ-001", "description": "README.md must exist in the project root and print its first line.", "priority": "must" }],
  "steps": [{
    "id": 1, "title": "README.md exists and is readable", "covers": ["REQ-001"], "status": "pending",
    "verify": [
      { "type": "file_exists", "path": "README.md" },
      { "type": "run", "cmd": "python -c \"print(open('README.md', encoding='utf-8').read().strip())\"", "expect_exit": 0 }
    ]
  }]
}
```

```json
{
  "format_version": 1,
  "task": "Prove README.md exists and prints its first line",
  "requirements": [{
    "id": "REQ-001", "description": "README.md must exist in the project root and print its first line.", "priority": "must",
    "acceptance_checks": [
      { "type": "file_exists", "path": "README.md" },
      { "type": "run", "cmd": "python -c \"print(open('README.md', encoding='utf-8').read().strip())\"", "expect_exit": 0 }
    ]
  }]
}
```

**2. Run the gate.**

```bash
plan-auditor request init . --file request-source.json
plan-auditor plan verify .
plan-auditor run . 1

# Before claiming completion, authenticate the evidence chain. A keyless chain
# is only tamper-evident — anyone with write access can rebuild it — so the
# gate never treats it as proof. Generate the key OUTSIDE the workspace and
# point the environment at it:
python -c "import os, pathlib; d = pathlib.Path.home()/'.plan-auditor'; d.mkdir(exist_ok=True); (d/'plan-auditor-hmac.key').write_bytes(b'plan-auditor: ' + os.urandom(48))"
export PLAN_AUDITOR_HMAC_KEY_FILE="$HOME/.plan-auditor/plan-auditor-hmac.key"
plan-auditor integrity init .
plan-auditor audit .
```

On Windows PowerShell, use the same Python key-generation command, then set the
environment variable with:

```powershell
$env:PLAN_AUDITOR_HMAC_KEY_FILE = "$HOME\.plan-auditor\plan-auditor-hmac.key"
```

Use either the Bash `export` or the PowerShell assignment, not both. In both cases
the key file is outside the workspace; do not commit or copy it into the project.

Real output. A lone `...` marks fields omitted for length; every other line is verbatim,
and every JSON level that is not elided lists exactly the keys the tool emits.

```console
$ plan-auditor request init . --file request-source.json
{
  "activated": true,
  "valid": true,
  "reason": "request contract active",
  "request_sha256": "d39e577eb0577d8c0c81231fdd7fc559d1c6045ecc5e5bd3a00e7e8f2f49197b",
  "authenticated": false
}
$ plan-auditor plan verify .
{
  "plans": {
    ...
  },
  "outcome": "PASS"
}
$ plan-auditor run . 1
[OK ] step 1: README.md exists and is readable (attempt 1/3)
       - passed | README.md EXISTS
       - passed | exit=0 (expected 0)
$ plan-auditor integrity init .
{
  "authenticated": true,
  ...
}
$ plan-auditor audit .
{
  "outcome": "PASS",
  "plans": {
    "default": "PASS"
  },
  "deterministic_core": "fresh audit PASS for every active plan under workspace-wide freeze",
  "gate": {
    "outcome": "PASS",
    ...
  }
}
```

Scoped omission: the elided fields are the plan-inspection block and `seal`, the per-step
progress lines and verdict table, and the gate's remaining fields including
`policy_findings`, `verdict` and `seal_ok`. [docs/cli.md](https://github.com/Furox-Art/plan-auditor/blob/main/docs/cli.md)
shows each command's full output.

`audit` re-runs every check in a fresh subprocess, and only exit code `0` means the work is
proven. Progress lines are English human-readable output; the JSON verdict
is the stable machine interface, so parse `"outcome"`.

## What "verified" actually means

| It does prove | It does not prove |
|---|---|
| The named command exited `0` in a fresh subprocess | That the command tested the right thing |
| The file or regex matched at audit time | That your product code is correct |
| The plan still matches the sealed contract | That your requirements were complete |
| The evidence chain is unbroken | That a same-user hostile process could not interfere |
| Every active plan passed | That natural-language meaning was formalized perfectly |

The right column is not a disclaimer to ignore; it is why the acceptance checks are
yours to write. See [Threat model](threat-model.md).

## Adding a real project

For a repository you already have:

1. Write `.plan-auditor/plan.json` with one requirement per thing you asked for,
   and a step per deliverable.
2. Write `request-source.json` with the same requirement IDs, descriptions and
   priorities, plus the deterministic acceptance checks.
3. Activate the contract **yourself**, before handing the task to the agent.
4. Seal with `plan-auditor plan verify .`.
5. Let the agent implement and run `plan-auditor run . <step-id>` after each step.
6. Configure the workspace-external HMAC key, run `plan-auditor integrity init .`,
   and only then require `plan-auditor audit .` to exit `0` before merge.

Useful conventions:

- Prefer `{"type": "pytest", "args": "tests/ -q"}` over a hand-written shell
  command; it is portable and its output is captured automatically.
- Set `"timeout"` on a `run` check that can hang. Output is bounded; overflow fails
  the check rather than truncating silently.
- Add a named `output` to a step when a later step must consume its artifact, and
  bind it with `requires_outputs`. See
  [Dependency graph](dependency-graph.md).
- For non-trivial multi-step plans, run `plan-auditor-formalize compile .` **before**
  sealing. The compiler refuses to mutate a sealed plan.

## Troubleshooting

Start here, always:

```bash
plan-auditor doctor .
```

It emits JSON with a top-level `assessment.outcome` and an `integrity` block. A
workspace with no plan reports `NO_PLAN`; that is healthy.

### `audit` reports `"request contract is not activated"`

You skipped the host-side approval. The agent must not be able to invent your
requirements, so this gate has no bypass:

```bash
plan-auditor request init . --file request-source.json
```

Check `plan-auditor request status .` for the current activation state.

### `request init` reports `"... is not a safe regular file"`

`--file` is resolved against your current working directory, not against the
workspace argument. From the workspace root use a bare filename, or pass an
absolute path:

```bash
plan-auditor request init . --file request-source.json
plan-auditor request init . --file "$PWD/request-source.json"
```

### `request init` reports `"invalid request contract: ... at least one BEHAVIORAL control"`

Your `acceptance_checks` are all `file_exists`/`regex`. Add at least one `run`,
`pytest`, or `exec` check per requirement. (`exec` is an accepted alias for
`run`.)

### `request init` reports `"requirement REQ-001 is missing from every active plan"`

The request contract is authoritative. Every requirement in it must also appear
in a plan's `requirements` with the **same** description and priority, and must be
named by at least one step's `covers`. If the text drifts you get
`"was modified in plan requirements"` instead — keep the two strings identical.

### `plan verify` reports `"seal.json already exists"` / refuses to change

Once a plan is sealed, criteria may only be **strengthened**. To genuinely change
the scope you need a new host-approved request generation. See
[Threat model](threat-model.md) and the `plan-auditor-migrate-seal` command for
the representation-only migration path.

### A step fails three times and then refuses to run

```console
$ plan-auditor run . 1
[FAIL] step 1: the sentinel script exits nonzero (attempt 1/3)
       - FAILED | exit=3 (expected 0)
$ plan-auditor run . 1
[FAIL] step 1: the sentinel script exits nonzero (attempt 2/3)
       - FAILED | exit=3 (expected 0)
$ plan-auditor run . 1
[FAIL] step 1: the sentinel script exits nonzero (attempt 3/3)
       - FAILED | exit=3 (expected 0)
$ plan-auditor run . 1
[SKIPPED] step 1: the sentinel script exits nonzero previous genuine failed attempts — 3 limit exceeded.
```

Nothing is elided and every invocation exits `1`. The check here is
`python -c "import sys; sys.exit(3)"` against `expect_exit: 0`; a failing command
that writes to stderr additionally gets a `output:` line, joined with `" | "`.

Fix the underlying problem. Re-arm deliberately with `plan-auditor run . 1 --force`
only when you are certain the check is correct and the implementation is wrong.

### `audit` fails with `"workspace content/type/mode changed during the full final-audit session"`

The final audit is **observational**: it fingerprints the workspace, runs the
checks, and fails if anything changed underneath it. The usual causes are yours,
not the agent's:

- A background process, formatter, watcher, or build writing into the workspace
  during the audit.
- Redirecting the audit's own output into a file inside the workspace.
- Another agent or terminal running a generator concurrently.

Quiesce those writers and re-run. If a *verification command itself* creates the
artifact it asserts, move creation into an earlier step and have the check only
read it.

### `audit` fails with `"no fresh deterministic full-audit proof for the current plan"`

The workspace fingerprint changed since the last successful audit. Re-run
`plan-auditor audit .` with nothing else touching the tree.

### `evidence verify` reports a broken chain

Records in `.plan-auditor/evidence.jsonl` (or an archive) were edited or reordered.
Every record carries the SHA-256 of the previous one, so tampering is detected.
`doctor` explains where the chain breaks; you will have to re-establish the plan
rather than repair the log by hand.

### The npm launcher always exits 0

It should not. The published bin (`bin/plan-auditor.js`, which `npx` and the
package's `bin` field resolve to) exits with the child verifier's code, so a
nonzero result reaches your shell:

```bash
npx plan-auditor audit .
echo $?
```

If that prints `0` while the JSON verdict says `FAIL`, you are running npm
`2.4.0`, which shipped a syntax error in the launcher so the `bin` entry point
could not run at all. Update the package:

```bash
npm i plan-auditor@latest
```

or use the console script, which does not go through the launcher:

```bash
pipx install --force plan-auditor
plan-auditor audit .
```

### The npm launcher audits the wrong directory

npm `2.4.1` is affected by this and must not be used: it ran the CLI with the
*installed package directory* as its working directory, so a relative workspace
path such as `.` resolved against the package instead of the directory you ran
the command from. The output looks authoritative and refers to a tree you did not
ask about.

`2.4.2` is fixed and is the release to use. If you are pinned to an older build,
pass an absolute path or use the console script instead:

```bash
npx plan-auditor audit "$(pwd)"
```

For comparison, `plan-auditor audit .` from the same shell reports the workspace
you are standing in, because the console script does not change directory.

### The agent keeps "fixing" the test instead of the code

That is a policy problem, not a bug. Add a check that asserts the *product*
behavior independently — for example a `run` check that imports your package and
calls the API — so editing the test cannot produce a green result.

## Next steps

- [CLI reference](cli.md) for every command and exit code.
- [Integrations](integrations.md) for skill hosts, blocking hooks, and CI.
- [Architecture](architecture.md) for the layer model.
- [Formal planning](formal-planning.md) for LLM-free STRIPS reachability.
- [What is measurable](benchmark.md) for claims this project does and does not make.
