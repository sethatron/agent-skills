# Sandbox verify.sh — Display Format Specification

Canonical output format for all sandbox `verify.sh` scripts. Every sandbox must follow this spec exactly.

## Symbols & Colors

| Status  | Symbol | ANSI Code    | No-Color Fallback |
|---------|--------|-------------|-------------------|
| Pass    | `✓`    | `\033[32m`  | `+`               |
| Fail    | `✗`    | `\033[31m`  | `x`               |
| Missing | `○`    | `\033[33m`  | `?`               |

Additional styling:
- **Bold** `\033[1m` — challenge title, summary line
- **Dim** `\033[2m` — separator lines, `─` between task number and label, hint arrows
- **Cyan** `\033[36m` — field names in error sub-detail lines
- **Reset** `\033[0m` — after every styled span

### Color Gating

Disable all ANSI codes (use fallback symbols, no bold/dim/cyan) when:
- `NO_COLOR` env var is set to a non-empty string, OR
- stdout is not a TTY (`not sys.stdout.isatty()`)

## Layout & Indentation

```
Col:  0    5    10
      |    |    |
  Title (bold)
 ──────────────────────────────────────── (dim, 1 space + 40 ─)

 ✗ Task N ─ Label                         (1 space + symbol)
      ✓ detail_identifier                 (6 spaces + symbol)
      ✗ detail_identifier                 (6 spaces + symbol)
           field: error text              (11 spaces)
           → hint text                    (11 spaces, dim arrow)
      ○ detail_identifier                 (6 spaces + symbol)
           no answer provided             (11 spaces)

 ──────────────────────────────────────── (separator)
 ✗ N of M tasks passed                    (summary, bold)
```

- Title: 2-space indent, bold
- Separator: 1-space indent + 40 `─` characters, dim
- Task header: 1-space indent, symbol, ` Task N `, dim `─`, ` Label`
- Detail item: 6-space indent, symbol, ` identifier`
- Sub-detail: 11-space indent, text
- Summary: 1-space indent, symbol, bold text
- Blank line before each task header
- Blank line before summary separator

## Rendering Rules

### Passing Tasks
Show header only. Do NOT enumerate detail items for passing tasks.

### Failing Tasks
Show header + ALL detail items within that task (pass, fail, and missing).

### `--task N` Mode
Show title, separator, single task (header + details if failing). No summary line.

### All Pass Summary
```
 ✓ All tasks passed
```

### Partial Pass Summary
```
 ✗ N of M tasks passed
```

## Detail Types

Each detail item in `results.json` follows one of these rendering patterns.

### `field_errors` — Multiple field errors per detail

Used when a detail has an `errors` array of `{field, expected, got}` objects.
Identifier key varies: `cidr`, `department`, `pair`, etc.

```
      ✗ 10.0.128.0/20
           broadcast_address: incorrect (your answer: 10.0.143.254)
           usable_hosts_aws: incorrect (your answer: 4090)
```

With `--show-answers`:
```
      ✗ 10.0.128.0/20
           broadcast_address: expected 10.0.143.255, got 10.0.143.254
           usable_hosts_aws: expected 4091, got 4090
```

Field names rendered in cyan.

### `single_error` — One error object per detail

Used when a detail has a single `error` object with `{field, expected, got}`.
The detail identifier IS the field name, so don't repeat it in sub-detail.

```
      ✗ issuer_cn
           incorrect (your answer: Some Wrong CN)
```

With `--show-answers`:
```
      ✗ issuer_cn
           expected Real Issuer CN, got Some Wrong CN
```

### `check` — Pass/fail checks with optional message

Used for file-existence and property checks. Has optional `message` and `got_sans` fields.
`--show-answers` has no effect on this type (nothing to hide).

```
      ✗ leaf has SAN DNS:app.sandbox.local
           found: other.example.com
      ✗ my-ca.crt exists
           workspace/my-ca.crt not found
```

### `single_hint` — Single expected/got with optional hint

Used when a detail has top-level `expected`, `got`, and optional `hint` fields.

```
      ✗ cert_b
           incorrect (your answer: expired)
           → Choose one of: expired, missing_san, wrong_issuer
```

With `--show-answers`:
```
      ✗ cert_b
           expected wrong_issuer, got expired
```

Hint line uses dim `→` arrow. Hint is shown regardless of `--show-answers` mode.

### Missing Details (all types)

```
      ○ 192.168.1.64/26
           no answer provided
```

## `--help` Template

Every verify.sh must output this exact text (substituting task count if needed):

```
Usage: verify.sh [OPTIONS]

Verify your sandbox challenge answers.

Options:
  --task N          Verify only task N (1, 2, or 3)
  --show-answers    Show expected values alongside incorrect answers
  --help            Show this help message

Examples:
  bash verify.sh                  Verify all tasks
  bash verify.sh --task 1         Verify only task 1
  bash verify.sh --show-answers   Show expected answers on failures
```

## Architecture

Each verify.sh follows this structure:

1. **Bash layer**: flag parsing (`--help`, `--show-answers`, `--task N`), file guards, engine invocation (stdout → `/dev/null`), then a single `python3 << 'PYEOF'` block
2. **Python layer**: reads `results.json`, renders all output using the format spec above

Environment variables passed from bash to python:
- `SHOW_ANSWERS` — `true` or `false`
- `TASK_FILTER` — empty string or `1`/`2`/`3`
- `RESULTS_PATH` — absolute path to `results.json`

### Python Renderer Skeleton

```python
import json, sys, os

NO_COLOR = os.environ.get('NO_COLOR', '') != '' or not sys.stdout.isatty()
show = os.environ.get('SHOW_ANSWERS', 'false') == 'true'
task_filter = os.environ.get('TASK_FILTER', '')
r = json.load(open(os.environ['RESULTS_PATH']))

def c(s, code, fb):
    return fb if NO_COLOR else f'\033[{code}m{s}\033[0m'
def bold(t):
    return t if NO_COLOR else f'\033[1m{t}\033[0m'
def dim(t):
    return t if NO_COLOR else f'\033[2m{t}\033[0m'
def cyan(t):
    return t if NO_COLOR else f'\033[36m{t}\033[0m'

PASS = c('✓', 32, '+')
FAIL = c('✗', 31, 'x')
MISS = c('○', 33, '?')
SEP = dim(' ' + '─' * 40)

# TASKS list — the ONLY part that varies per sandbox
# Each tuple: (result_key, task_number, label, detail_type, identifier_key)
TASKS = [...]

tasks = [t for t in TASKS if str(t[1]) == task_filter] if task_filter else TASKS

print()
print(f'  {bold("Challenge Title")}')
print(SEP)

passed = 0
for key, num, label, dtype, id_key in tasks:
    task = r[key]
    ok = task['pass']
    if ok:
        passed += 1
    print()
    print(f' {PASS if ok else FAIL} Task {num} {dim("─")} {label}')
    if not ok:
        for d in task['details']:
            # render based on dtype: field_errors, single_error, check, single_hint
            ...

if not task_filter:
    print()
    print(SEP)
    if passed == len(TASKS):
        print(f' {PASS} {bold("All tasks passed")}')
    else:
        print(f' {FAIL} {bold(f"{passed} of {len(TASKS)} tasks passed")}')
print()
```

## No-Color Output Example

With `NO_COLOR=1`:
```
  Subnet Architect Challenge
  ────────────────────────────────────────

 x Task 1 ─ CIDR Block Analysis
      + 172.16.50.0/23
      x 10.0.128.0/20
           broadcast_address: incorrect (your answer: 10.0.143.254)
      ? 192.168.1.64/26
           no answer provided

 + Task 2 ─ VLSM Partitioning

 + Task 3 ─ Overlap Detection

  ────────────────────────────────────────
 x 1 of 3 tasks passed
```
