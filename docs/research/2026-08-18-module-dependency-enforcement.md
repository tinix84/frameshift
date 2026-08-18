# How comparable projects enforce module dependency rules in the candidate ecosystems

Research for issue [#36](https://github.com/tinix84/frameshift/issues/36). Inputs to the
language decision on [#34](https://github.com/tinix84/frameshift/issues/34) and
[#35](https://github.com/tinix84/frameshift/issues/35). **Not a recommendation.**

> This file lives only on branch `research/module-dependency-enforcement` and must never
> reach `main`. The repository's documentation authority map allows only ADRs and
> `CONTEXT.md` as tracked prose.

## 1. Question

ADR-0008 commits FrameShift to a modular monolith with in-process ports for **engines,
runtime adapters, capability broker, validation, persistence**, and its Validation clause
says "architecture tests enforce module dependencies". Nobody can write that test until
the language and the enforcement mechanism are known.

For each candidate ecosystem (Python, TypeScript/Node, Go, Rust): what is the standard way
to enforce module-dependency rules in CI, what does it cost in dependencies and
maintenance, and how does it express the canonical illegal edges —

- an **engine** importing **persistence** directly, and
- an **adapter** importing the **store**?

**Date checked:** 2026-08-18. **Versions checked** (all resolved from the package registry
or the tool's own repository on that date):

| Tool | Version | Released |
|---|---|---|
| import-linter | 2.13 | 2026-07-03 |
| grimp (import-linter's graph engine) | >=3.14 (pinned floor) | — |
| ruff | 0.16.3 | 2026-08-13 |
| flake8-tidy-imports | current `main` (646 commits) | — |
| pytest-archon | 0.0.7 | 2025-09-19 |
| dependency-cruiser | 18.2.0 | — |
| eslint-plugin-boundaries | 7.2.0 | 2026-08-09 |
| @nx/eslint-plugin | 23.1.1 | 2026-07-30 |
| tsarch (ts-arch) | 5.4.1 | 2024-12-23 |
| Go `internal/` rule | `go help packages`, Go `master` | — |
| depguard | current `master`; also bundled in golangci-lint | — |
| go-arch-lint | config `version: 3`, current `master` | — |
| Rust visibility rules | The Rust Reference, current | — |
| cargo-deny | 0.20.2 | 2026-07-09 |
| layered-crate | 0.4.6 | 2026-07-12 |

## 2. Answer in one paragraph

Only **Go and Rust can make the illegal edge a compile error, and neither does it for free
in the shape ADR-0008 describes.** Go's `internal/` rule is a real language-level guarantee
— "Code in or below a directory named `internal` is importable only by code that shares the
same import path above the internal directory" — but it is a *prefix* rule, so it protects a
module from everything *outside its own subtree*; it cannot express "engine must not import
persistence" between two siblings unless persistence's implementation is nested as
`persistence/internal/store`, which is exactly the idiom Go projects use. Rust enforces at
the **crate** boundary, not the module boundary: a crate can only name what its
`Cargo.toml` `[dependencies]` lists, so five crates in a workspace give compile-time
enforcement with zero tooling — but inside one crate `pub(crate)` gives no protection at
all, because, as the `layered-crate` README puts it, "Rust allows you to import anything
anywhere in the same crate". Python and TypeScript have no language mechanism whatsoever
and must bolt on a linter: in Python the de facto standard is **import-linter** (15.1M
downloads/month, ~4 runtime deps, a declarative `forbidden` or `layers` contract in
`pyproject.toml`, run as `lint-imports`), with **ruff** as a zero-dependency but much
blunter alternative (a global `banned-api` ban plus a per-directory `.ruff.toml`, no
from→to rule) and **pytest-archon** as a one-dependency in-test option; in TypeScript the
two live options are **dependency-cruiser** (12.1M/month, 18 runtime deps, path-regex
`forbidden` rules) and **eslint-plugin-boundaries** (6.2M/month, 6 deps, rides the existing
ESLint run), with `@nx/eslint-plugin` only sensible if the repo already is an Nx workspace
and **tsarch effectively abandoned** (last release 2024-12-23, still declaring
`typescript: ^3.8.3`). Every static tool in every ecosystem is blind to the same three
things: runtime string-driven imports (`importlib`, `import()` of a computed specifier,
reflection), dependency injection that hands an engine a persistence object it never
imported, and — in Go and Rust alike — a violation routed through a legally-imported
interface.

## 3. Per-ecosystem sections

### 3.1 Python

Python has **no language-level module boundary**. Everything is enforced by a linter run in
CI. Three options are genuinely in use.

#### 3.1.1 import-linter — the de facto standard

**What it is.** A dedicated architecture linter: "Import Linter allows you to impose
constraints on the imports between your Python modules." It builds a full import graph via
`grimp` ("Builds a queryable graph of the imports within one or more Python packages") and
checks declarative *contracts* against it.

**Dependency cost.** Version 2.13, `requires_python >=3.10`. Runtime dependencies:

```
"click>=6"
"grimp>=3.14"
"rich>=14.2.0"
"tomli>=1.2.1; python_version < \"3.11\""
"typing-extensions>=3.10.0.0"
```

Four runtime packages on Python 3.11+ (`tomli` drops out). `grimp` ships compiled wheels
(its graph core is Rust). This is a **dev dependency only** — it never enters the shipped
package — but it does end the "zero-dependency repository" property for the CI environment.
15,150,744 downloads in the last month.

**Config syntax for "engines must not import persistence".** The `forbidden` contract,
verbatim field structure from the docs:

```toml
[tool.importlinter]
root_package = "frameshift"

[[tool.importlinter.contracts]]
name = "Engines must not import persistence"
type = "forbidden"
source_modules = [
    "frameshift.engines",
]
forbidden_modules = [
    "frameshift.persistence",
]
```

The documented fields are `source_modules` ("A list of modules that should not import the
forbidden modules. Supports wildcards"), `forbidden_modules` ("A list of modules that
should not be imported by the source modules"), `ignore_imports`,
`unmatched_ignore_imports_alerting`, `allow_indirect_imports` ("If `True`, allow indirect
imports to forbidden modules without interpreting them as a reason to mark the contract
broken"), and `as_packages` (default `True` — modules are treated as packages, so
descendants are covered).

Crucially, **indirect imports are checked by default** — an engine reaching persistence via
a third module is caught, not just the direct edge. That is the single most valuable
property for ADR-0008's five-port model.

For all five ADR-0008 modules at once, the `layers` contract is more compact and expresses
the whole stack in one rule:

```toml
[[tool.importlinter.contracts]]
name = "My layers contract"
type = "layers"
layers = [
    "mypackage.high",
    "mypackage.medium",
    "mypackage.low",
]
```

"The order is from higher to lower level layers" — higher layers may import lower ones, not
the reverse. (Whether FrameShift's five ports are actually a total order, or a partial one
needing several `forbidden` contracts, is a design question, not a tooling one.)

**How it runs in CI.** A single command:

```console
lint-imports
```

Config is discovered from `setup.cfg`, `.importlinter`, or `pyproject.toml` in the current
directory. Non-zero exit on violation. There is also a documented pre-commit hook.

**What it cannot catch.**
- The root package **must be importable**: "The `root_package` _must be importable_:
  usually this means it has been installed using a Python package manager, or it's in the
  current directory." So CI must install the package — heavier than `python script.py`.
- Static analysis only (grimp parses source). Runtime `importlib.import_module(name)` with
  a computed `name`, `__import__`, and plugin-registry lookups are invisible.
- Dependency injection: if the composition root imports persistence and hands the object to
  an engine, no import edge exists and no contract fires.
- Imports under `if TYPE_CHECKING:` are included by default; `exclude_type_checking_imports = true`
  removes them. Which behaviour you want is a real choice, not a default to accept blindly.
- External packages are *not* statically analysed: "Unlike root packages, external packages
  are *not* statically analyzed, so no imports from external packages will be checked."

**Maintenance burden.** Low. One TOML block per rule, colocated with the rest of the
project config. `ignore_imports` gives a documented escape hatch that leaves an audit trail
in the config rather than in scattered `# noqa` comments.

#### 3.1.2 ruff — zero dependencies, much blunter

**What it is.** The general-purpose Python linter, which ports flake8-tidy-imports' rules:
`TID251 banned-api` — "Checks for banned imports."

**Dependency cost.** Version 0.16.3, released 2026-08-13. **`requires_dist` is `None` — ruff
has zero Python dependencies.** It is a single prebuilt Rust binary distributed as a wheel
(18 wheels for that version). 326,444,811 downloads/month. For a repo that prizes
dependency-freedom this is the cheapest possible option by a wide margin.

**Config syntax — and its limitation.** The documented example is:

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"os.path" = {msg = "Use `pathlib.Path` instead"}
```

This is a **global** ban: it says "nobody may import this", not "engines may not import
persistence". There is no from→to relation in the rule itself.

The workaround exploits ruff's hierarchical config discovery. From the configuration docs:
"Similar to ESLint, Ruff supports hierarchical configuration, such that the 'closest' config
file in the directory hierarchy is used for every individual file, with all paths in the
config file … being resolved relative to the directory containing that config file." So a
`src/frameshift/engines/.ruff.toml` containing the ban applies only to files under
`engines/`:

```toml
# src/frameshift/engines/.ruff.toml
extend = "../../../pyproject.toml"

[lint.flake8-tidy-imports.banned-api]
"frameshift.persistence" = { msg = "ADR-0008: engines must not import persistence" }
```

The `extend` line is mandatory, not cosmetic: "Unlike ESLint, Ruff does not merge settings
across configuration files; instead, the 'closest' configuration file is used, and any
parent configuration files are ignored." Omit it and the engines directory silently loses
every other lint rule in the project.

`lint.flake8-tidy-imports.banned-module-level-imports` also exists (bans a module at
module level only, permitting it inside a function). *Unverified:* I could not retrieve a
concrete TOML example for it from the settings page — the excerpt was truncated.

**How it runs in CI.** `ruff check .` — already in most Python CI pipelines, so this adds
zero new CI steps.

**What it cannot catch.** Everything import-linter misses, plus: **no transitive/indirect
detection at all.** Ruff sees one file at a time and matches import statements against a
prefix list. An engine that imports `frameshift.validation`, which imports
`frameshift.persistence`, passes. It also cannot express "these five modules form a layer
order" — you get N scattered config files, one per constrained directory.

**Maintenance burden.** Low per rule, but the per-directory `.ruff.toml` scheme scatters
architecture knowledge across the tree and the `extend` requirement is a trap. The
architecture is no longer readable in one place.

#### 3.1.3 pytest-archon — architecture rules as tests

**What it is.** An ArchUnit-style fluent API that expresses architecture rules as ordinary
pytest tests. Version 0.0.7 (2025-09-19), 98,423 downloads/month.

**Dependency cost.** One runtime dependency: `pytest>=7.2`. If the project already uses
pytest, this is effectively free.

**Config syntax** (verbatim from the README, adapted to FrameShift's names below it):

```python
(
    archrule("name", comment="some comment")
    .match("pytest_archon.col*")
    .exclude("pytest_archon.colgate")
    .should_not_import("pytest_archon.import_finder")
    .should_import("pytest_archon.core*")
    .check("pytest_archon")
)
```

For ADR-0008 that reads as `archrule("engines-not-persistence").match("frameshift.engines*").should_not_import("frameshift.persistence*").check("frameshift")`.

**How it runs in CI.** It is a pytest test — it runs in the existing test command, which
matches ADR-0008's own phrasing ("architecture tests enforce module dependencies") more
literally than a separate linter does.

**What it cannot catch.** The README is unusually explicit about its own scope, and the
defaults are the permissive ones:
- Default: "Checks all imports, including those in functions and conditional blocks, plus
  transitive dependencies."
- `only_toplevel_imports=True` — "Ignores conditional and nested imports".
- `skip_type_checking=True` — "Excludes imports within `if typing.TYPE_CHECKING` blocks".
- `only_direct_imports=True` — "Skips transitive dependency analysis".
- Documented interaction: "When `only_toplevel_imports=True` is enabled, the
  `skip_type_checking` option becomes ineffective."

Same blind spots as any static tool for `importlib` and injection.

**Maintenance burden.** Low, but rules live in Python code rather than declarative config,
so they are code to be reviewed and can drift into cleverness. Version `0.0.7` after several
years signals a small, slow project — a bus-factor risk that import-linter, at 15M
downloads/month, does not have.

#### 3.1.4 flake8-tidy-imports — mentioned for completeness

Config from its README:

```
[flake8]
banned-modules =
  mock = Use unittest.mock.
  {python2to3}
```

418,423 downloads/month; actively maintained (646 commits on `main`). But it requires flake8
as a runner, its rules are the ones ruff already reimplements, and its own README points
elsewhere for this job: for "more advanced control of imports in your project", it
recommends `import-linter`. **A tool recommending its competitor for exactly FrameShift's
use case is a finding, not a footnote.**

### 3.2 TypeScript / Node

TypeScript has **no language-level module boundary either**, and — worth stating plainly
because it is a common assumption — **project references do not create one.** The handbook
describes what referencing a project does: "Importing modules from a referenced project will
instead load its _output_ declaration file (`.d.ts`)"; "Build mode … will automatically
build the referenced project if needed". Nothing in the handbook makes importing from a
*non*-referenced project an error. Project references are an organizational and build
feature, not an enforcement one.

#### 3.2.1 dependency-cruiser — the general-purpose graph validator

**What it is.** A standalone dependency-graph analyser and validator with a `forbidden`
rules section. It is the most widely used tool of this class: 12,101,201 downloads/month.

**Dependency cost.** Version 18.2.0. Node `^22||^24||>=26`. **18 runtime dependencies**:
`acorn`, `acorn-jsx`, `acorn-walk`, `acorn-loose`, `acorn-jsx-walk`, `commander`,
`enhanced-resolve`, `ignore`, `interpret`, `is-installed-globally`, `json5`, `picomatch`,
`prompts`, `rechoir`, `safe-regex`, `semver`, `tsconfig-paths-webpack-plugin`,
`watskeburt`. That is the heaviest option in this whole report by direct dependency count.

**Config syntax.** A rule is a `from`/`to` pair; the documented minimal shape is:

```json
{
  "name": "kebab-cased-name",
  "comment": "(optional) description of the rule",
  "severity": "warn",
  "from": {},
  "to": {}
}
```

and the README's own sample rule shows the path-regex form:

```json
{
  "forbidden": [
    {
      "name": "not-to-test",
      "comment": "don't allow dependencies from outside the test folder to test",
      "severity": "error",
      "from": { "pathNot": "^test" },
      "to": { "path": "^test" }
    }
  ]
}
```

For FrameShift, `from: { "path": "^src/engines" }`, `to: { "path": "^src/persistence" }`.
`severity: "error"` is the CI-relevant setting: "The 'error' severity will make some
reporters (at least the `err` one) return a non-zero exit code, so if you want e.g. a build
to stop when there's a rule violated: use that." Default severity is `warn`, which does
**not** fail the build — an easy way to ship a rule that never fires.

The docs also warn about the obvious naive formulation of a mutual-independence rule
(matching a folder against itself flags intra-folder edges too), and note the alternative —
enumerating every pair — is "heavy maintenance … especially when your business components
breed like a litter of rabbits". Group matching exists for this.

**How it runs in CI.** `npx depcruise src` (from v13 the `--config` flag is no longer
needed). Output is "in an eslint-like format".

**What it cannot catch.** It *does* model async `import()` — `dynamic` is a first-class
condition, e.g. `"to": { "dynamic": true }` — so statically-written dynamic imports are
visible. It cannot see a computed specifier, `require(variable)`, a registry/DI lookup, or
anything resolved at runtime. Type-only imports are distinguished (`type-only`, "only
available for TypeScript sources, only for tsPreCompilationDeps !== false").

**Maintenance burden.** Moderate. Rules are regexes over paths, which means a directory
rename silently disarms a rule — a real hazard and the main argument against this class of
tool. It is a separate CI step with its own config file and a large dependency tree to keep
patched.

#### 3.2.2 eslint-plugin-boundaries — rides the existing ESLint run

**What it is.** "An ESLint plugin that helps you maintain clean architecture by enforcing
boundaries between different parts of your codebase." 6,197,326 downloads/month.

**Dependency cost.** Version 7.2.0 (2026-08-09). Six runtime dependencies: `chalk`,
`handlebars`, `micromatch`, `eslint-module-utils`, `@boundaries/elements`,
`eslint-import-resolver-node`. Peer: `eslint >=6.0.0`. Meaningfully lighter than
dependency-cruiser, and it adds no new CI step if ESLint is already running.

**Config syntax.** Two parts — classify, then constrain. Verbatim from the README:

```javascript
settings: {
  "boundaries/elements": [
    { type: "controller", pattern: "controllers/*" },
    { type: "model", pattern: "models/*" },
    { type: "view", pattern: "views/*" }
  ],
  ...
}
```

```javascript
{
  rules: {
    "boundaries/dependencies": [2, {
      default: "disallow",
      policies: [
        // Allow controllers to depend on models and views
        {
          from: { element: { type: "controller" } },
          allow: {
            to: { element: { types: { anyOf: ["model", "view"] } } },
          },
        },
        ...
      ]
    }]
  }
}
```

`default: "disallow"` is the important knob: it makes the policy list an **allowlist**, so a
newly added sixth module is illegal until someone says otherwise. That is the fail-closed
posture ADR-0008's "preserve boundaries that can later be separated" implies, and neither
import-linter's `forbidden` contract nor dependency-cruiser's `forbidden` section gives it
without extra work (import-linter's `layers` contract does).

For FrameShift the elements would be `engine`, `adapter`, `broker`, `validation`,
`persistence`, and the absence of an `allow` policy from `engine` to `persistence` is the
rule.

**How it runs in CI.** `eslint .` — no new step.

**What it cannot catch.** ESLint sees one file at a time: **no transitive analysis**, so an
engine → validation → persistence path is invisible. It is also inherently a source-file
linter — DI, runtime registries, and computed `import()` are all out of scope.

**Maintenance burden.** Low-to-moderate. Classification is glob-based (same rename hazard),
but the policy block is a single readable table of the architecture, which the ruff and
scattered-config approaches are not.

#### 3.2.3 @nx/eslint-plugin (`@nx/enforce-module-boundaries`) — only if you already use Nx

**What it is.** Nx's tag-based boundary rule, driven by the Nx project graph rather than
file paths. 12,820,338 downloads/month — but that number reflects Nx adoption generally, not
adoption of this rule as a standalone choice.

**Dependency cost.** Version 23.1.1 (2026-07-30). Eleven runtime dependencies, including
`@nx/js@23.1.1` and `@nx/devkit@23.1.1` — i.e. **it pulls in the Nx toolchain.** Adopting it
means adopting Nx's workspace model (projects, `project.json`, tags). For a repo with no
application code yet, that is a build-system decision disguised as a lint decision.

**Config syntax** (flat config, from the Nx docs):

```javascript
'@nx/enforce-module-boundaries': [
  'error',
  {
    allow: [],
    depConstraints: [
      {
        sourceTag: 'scope:shared',
        onlyDependOnLibsWithTags: ['scope:shared'],
      },
      {
        sourceTag: 'scope:admin',
        onlyDependOnLibsWithTags: ['scope:shared', 'scope:admin'],
      },
    ],
  },
],
```

`onlyDependOnLibsWithTags` is an allowlist, so it is fail-closed like
eslint-plugin-boundaries. Tags attach to *projects*, not paths — so a directory rename does
not disarm the rule, which is a genuine advantage over every path-regex tool here.

**How it runs in CI.** `eslint .`, via Nx's task runner.

**What it cannot catch.** Same file-at-a-time ESLint limits. Additionally, the rule only
constrains *cross-project* imports — anything inside a single Nx project is unconstrained.

**Maintenance burden.** Low once Nx is in place; very high if it is not, because the cost is
the whole build system.

#### 3.2.4 tsarch — check the date before considering it

`tsarch` presents the nicest API for ADR-0008's phrasing:

```typescript
it("business logic should not depend on the ui", async ()=> {
    const rule = filesOfProject()
        .inFolder("business")
        .shouldNot()
        .dependOnFiles()
        .inFolder("ui")

    await expect(rule).toPassAsync()
})
```

But the registry facts argue against it: latest version **5.4.1, published 2024-12-23** —
roughly twenty months stale as of this check — and its declared dependencies are
`{"@zerollup/ts-helpers": "^1.7.18", "fs": "0.0.1-security", "path": "^0.12.7",
"plantuml-parser": "0.0.16", "typescript": "^3.8.3", "walk-sync": "^2.2.0"}`. Two red
flags: it declares `typescript: ^3.8.3` (TypeScript 3.8 is from 2020), and it depends on
`fs@0.0.1-security` and `path`, which are npm **name-squatter placeholders** for Node
built-ins — a package that should never appear in a dependency list. 151,846 downloads/month
is non-trivial but consistent with existing installs rather than new adoption. Treat as
unmaintained.

### 3.3 Go

**This is where the language does the work — with a specific and important caveat.**

#### 3.3.1 The `internal/` rule — native, compile-time, zero dependencies

**What it is.** A rule of the `go` command itself, not a linter. Verbatim from
`go help packages` (source: `src/cmd/go/internal/help/helpdoc.go` in the Go repository):

> Internal packages
>
> Code in or below a directory named "internal" is importable only
> by code that shares the same import path above the internal directory.
> Here's an example directory layout of a module example.com/m:
>
> ```
>     /home/user/modules/m/
>             go.mod                 (declares module example.com/m)
>             crash/
>                 bang/              (go code in package bang)
>                     b.go
>             foo/                   (go code in package foo)
>                 f.go
>                 bar/               (go code in package bar)
>                     x.go
>                 internal/
>                     baz/           (go code in package baz)
>                         z.go
>                 quux/              (go code in package quux)
>                     y.go
> ```
>
> The code in z.go is imported as "example.com/m/foo/internal/baz", but that
> import statement can only appear in packages with the import path prefix
> "example.com/m/foo". The packages "example.com/m/foo", "example.com/m/foo/bar", and
> "example.com/m/foo/quux" can all import "foo/internal/baz", but the package
> "example.com/m/crash/bang" cannot.

**The caveat that decides everything.** This is a **prefix rule, not a pairwise rule.** It
lets a subtree hide its implementation from everything outside that subtree. It cannot say
"engines must not import persistence" if both are siblings — `m/engines` and
`m/persistence` are mutually importable, and no `internal/` placement changes that in
general.

What it *can* express, and what real Go projects do, is:

```
frameshift/
    engines/                       (public port)
    persistence/
        store.go                   (public port: interfaces only)
        internal/
            store/                 (the actual implementation — unreachable from engines)
    adapters/
        internal/...
```

Then "an adapter importing the store" is a **compile error**, enforced by `go build`, with
no tool, no config, and no dependency. But "an engine importing the persistence *port*" is
legal by construction — which is arguably correct under ADR-0008 (engines call in-process
*ports*), but it means the illegal edge you can enforce natively is
*implementation*-reaching, not *module*-reaching. Deciding which of those ADR-0008 actually
forbids is a design question this report cannot settle.

**Maintenance burden.** Zero ongoing. The cost is up-front: the directory layout *is* the
policy, so changing the architecture means moving files.

#### 3.3.2 `go vet` — explicitly not this

For the record, so nobody assumes otherwise: `go vet`'s analyzer set is `appends, asmdecl,
assign, atomic, bools, buildtag, cgocall, composites, copylocks, defers, directive,
errorsas, framepointer, hostport, httpresponse, ifaceassert, loopclosure, lostcancel,
nilfunc, printf, shift, sigchanyzer, slog, stdmethods, stdversion, stringintconv,
structtag, testinggoroutine, tests, timeformat, unmarshal, unreachable, unsafeptr,
unusedresult`. **None of them checks import restrictions or dependency rules.**

#### 3.3.3 depguard — the pairwise rule Go's `internal/` cannot express

**What it is.** "A Go linter that checks package imports are in a list of acceptable
packages."

**Dependency cost.** Either a standalone binary
(`go install github.com/OpenPeeDeeP/depguard/cmd/depguard@latest`) or — decisively — **it is
bundled in golangci-lint**, confirmed by its presence in golangci-lint's own
`.golangci.reference.yml`. If golangci-lint is already in CI (it is, in most Go projects),
depguard costs **zero additional dependencies**.

**Config syntax.** From the README; a file matching `^\.?depguard\.(yaml|yml|json|toml)$`:

```json
{
  "main": {
    "files": [
      "$all",
      "!$test"
    ],
    "listMode": "Strict",
    "allow": [
      "$gostd",
      "github.com/OpenPeeDeeP"
    ],
    "deny": {
      "reflect": "Who needs reflection",
    }
  }
}
```

The `files` glob is what makes it pairwise. For FrameShift:

```yaml
engines:
  files:
    - "**/engines/**"
  deny:
    frameshift/persistence: "ADR-0008: engines must not import persistence"
```

Note the README's own warning: "Should always prefix a file glob with `**/` as files are
matched against absolute paths." Getting that wrong yields a rule that matches nothing —
a silently-passing architecture test, the worst possible failure mode.

`listMode` is `Original` (legacy, "not recommended"), `Strict` ("everything is denied unless
in allowed"), or `Lax` ("everything is allowed unless it is denied"). `Strict` is the
fail-closed option. Variables `$all`, `$test`, `$gostd` reduce boilerplate. Allow/deny are
**prefix** matches unless suffixed with `$` for exact match — worth knowing, since
`frameshift/persistence` also matches `frameshift/persistencetest`.

**How it runs in CI.** `golangci-lint run`, or the standalone binary.

**What it cannot catch.** Import statements only. Interface-mediated access, `plugin`
loading, reflection, and injection are all invisible. No transitive analysis: engines →
validation → persistence passes.

**Maintenance burden.** Low. One YAML block per constrained module inside the existing
`.golangci.yml`.

#### 3.3.4 go-arch-lint — layer declarations for the whole architecture

**What it is.** A "Linter used to enforce some good project structure and validate top level
architecture (code layers)". Unlike depguard's per-package deny lists, it declares the whole
layer graph in one file.

**Dependency cost.** A standalone binary or a Docker image
(`docker run --rm -v ${PWD}:/app fe3dback/go-arch-lint:latest-stable-release check --project-path /app`).
Building from source "requires go 1.25+". Not bundled in golangci-lint, so it is a separate
CI step and a separate thing to version-pin.

**Config syntax** (`version: 3`, verbatim from the README):

```yaml
version: 3
workdir: internal
components:
  handler:    { in: handlers/* }           # wildcard one level
  service:    { in: services/** }          # wildcard many levels
  repository: { in: domain/*/repository }  # wildcard DDD repositories
  model:      { in: models }               # match exactly one package

commonComponents:
  - models

deps:
  handler:
    mayDependOn:
      - service
  service:
    mayDependOn:
      - repository
```

`mayDependOn` is an **allowlist** — this is the fail-closed, whole-architecture-in-one-file
form, and it maps directly onto ADR-0008's five ports. `repository` here has no `deps` entry
at all, so it may depend on nothing but `commonComponents`.

**How it runs in CI.** `go-arch-lint check --project-path .`; the README explicitly
recommends "add linter into CI workflow".

**What it cannot catch.** Same static-import limits. The README's own broken-code example is
telling: it catches `main.go` wiring a `repository` into a `handler` — but only because
`main.go` imports both and the component rule fires on the *import*, not on the injection.
An engine handed a persistence object through an interface it legally imports is invisible.

**Maintenance burden.** Low config, moderate operational: an extra binary to pin, and the
project is a single-maintainer effort (no golangci-lint bundling to fall back on).

### 3.4 Rust

**Rust enforces at the crate boundary, and only at the crate boundary.** This is the finding
most likely to be assumed wrong.

#### 3.4.1 Crate/workspace structure — native, compile-time, zero dependencies

**What it is.** "A _workspace_ is a collection of one or more packages, called _workspace
members_, that are managed together." Members depend on each other via path dependencies:

```toml
[dependencies]
other_member = { path = "../other_member" }
```

A crate can only refer to crates named in its `Cargo.toml`. So if `frameshift-engines`
does not list `frameshift-persistence` in `[dependencies]`, `use frameshift_persistence::…`
is a **compile error** — enforced by `rustc`, with no linter, no config, no CI step, and no
dependency.

The enforcement mechanism is *absence*: **there is no `forbid` directive.** The Cargo
workspace documentation describes no configuration, lint, or feature that prevents a member
from declaring a path dependency on another; the only thing stopping someone is not adding
the line. That has one concrete consequence: **the "architecture test" in Rust is a diff
review of `Cargo.toml`, not a CI check.** A PR that adds three lines to `[dependencies]`
turns an illegal edge legal and nothing fails.

Mitigation is possible without new tooling — assert the dependency graph in a test or CI
step by parsing `cargo metadata --format-version 1` output. *Unverified:* I did not confirm
a widely-used, named tool that does this; projects appear to hand-roll it.

#### 3.4.2 `pub(crate)` and module visibility — does NOT do this job

The Rust Reference gives the two access rules:

> With the notion of an item being either public or private, Rust allows item accesses in
> two cases:
>
> 1. If an item is public, then it can be accessed externally from some module `m` if you
>    can access all the item's ancestor modules from `m`. You can also potentially be able
>    to name the item through re-exports. See below.
> 2. If an item is private, it may be accessed by the current module and its descendants.

and the scoped forms:

> - `pub(in path)` makes an item visible within the provided `path`. `path` must be a simple
>   path which resolves to an ancestor module of the item whose visibility is being declared.
> - `pub(crate)` makes an item visible within the current crate.
> - `pub(super)` makes an item visible to the parent module. This is equivalent to `pub(in super)`.
> - `pub(self)` makes an item visible to the current module. This is equivalent to `pub(in self)` or not using `pub` at all.

Read rule 2 and `pub(crate)` together: **inside a single crate, `pub(crate)` gives zero
protection between sibling modules.** If `engines` and `persistence` are both modules of one
crate, `pub(crate) fn save()` in `persistence` is fully callable from `engines`. The
`layered-crate` README states the problem directly: "Since Rust allows you to import
anything anywhere in the same crate, the dependency can become a mess over long time."

The one visibility construct that *is* pairwise is `pub(in path)` — but `path` "must resolve
to an **ancestor** module of the item", so like Go's `internal/` it is a containment rule,
not a sibling rule. It can hide `persistence::internal` from everything outside
`persistence`; it cannot hide `persistence` from `engines`.

#### 3.4.3 cargo-deny — check what it actually does

Worth stating explicitly because the name invites the wrong assumption. cargo-deny 0.20.2
runs four checks: **advisories, bans, licenses, sources**. The `bans` check is documented as:
"The bans check is used to deny (or allow) specific crates, as well as detect and handle
multiple versions of the same crate." It operates on the **external dependency graph** —
supply-chain and license hygiene. **It does not enforce source-level import rules between
local modules, and it is not an architecture linter.** (5.1M total downloads, 1.38M in the
recent window — heavily used, just for a different job.)

#### 3.4.4 Third-party Rust arch linters — they exist, they are barely used

Three exist. Their registry numbers are the finding:

| Crate | Latest | Last updated | Total downloads | Recent downloads |
|---|---|---|---|---|
| `layered-crate` | 0.4.6 | 2026-07-12 | 6,394 | 127 |
| `cargo-deplint` | 0.1.0 | 2023-09-08 | 6,186 | 626 |
| `cargo-archtest` | 0.1.8 | 2021-06-15 | 8,509 | 60 |

Compare `cargo-deny` at 1,376,041 recent downloads. **The answer to "what do comparable Rust
projects actually use" is: workspace splitting, not a linter.**

`layered-crate` is the only actively-developed one and it is the closest analogue to
import-linter's `layers` contract. Its `Layerfile.toml`:

```toml
[crate]
exclude = []

[layer.layer1]
depends-on = ["layer2"]
impl = []

[layer.layer2]
```

Run `layered-crate`; "you will get an error if anything in `layer2` imports from `layer1`".
Its implementation strategy is worth knowing before adopting: "During the layer checking,
the layer and its dependencies are split into different crates" — it literally synthesizes
temporary crates and compiles them. That gives real compile-time enforcement, but it means
the tool inherits every cross-crate restriction: `pub(crate)` items and `impl`s for types in
lower layers stop working unless you list them under `impl = [...]`, and doing so "loosens"
the check ("`layer1` can also import from `layer2`'s dependencies"). The README also carries
an explicit warning about procedural macros. High-leverage, high-friction, single-maintainer,
127 recent downloads.

## 4. Comparison table

| Ecosystem | Tool | Dependency cost | Expresses "engines ⇏ persistence" | Transitive? | Fail-closed? | Native or bolt-on | In practice (downloads) |
|---|---|---|---|---|---|---|---|
| Python | **import-linter 2.13** | 4 runtime deps (click, grimp, rich, typing-extensions) | Yes — `forbidden` contract, or `layers` for all five ports | **Yes, by default** | `layers` yes; `forbidden` no | Bolt-on (separate CI step) | 15.1M/mo |
| Python | **ruff 0.16.3** | **Zero** — single static binary | Weakly — global `banned-api` + per-dir `.ruff.toml` with `extend` | No | No | Bolt-on (already in most CI) | 326M/mo |
| Python | **pytest-archon 0.0.7** | 1 (`pytest`) | Yes — `archrule(...).should_not_import(...)` | Yes by default; opt out | No | Bolt-on (in-test) | 98k/mo |
| Python | flake8-tidy-imports | 1 (`flake8`) | Weakly — global `banned-modules` | No | No | Bolt-on | 418k/mo; its own README defers to import-linter |
| TS/Node | **dependency-cruiser 18.2.0** | **18 runtime deps**; Node ≥22 | Yes — `from.path` / `to.path` regexes | Yes (`reachable`, transitive rules) | No (default `severity: warn`) | Bolt-on (separate CI step) | 12.1M/mo |
| TS/Node | **eslint-plugin-boundaries 7.2.0** | 6 deps + eslint peer | Yes — element types + `policies` | **No** | **Yes** (`default: "disallow"`) | Bolt-on (rides existing ESLint) | 6.2M/mo |
| TS/Node | @nx/eslint-plugin 23.1.1 | 11 deps incl. `@nx/js`, `@nx/devkit` — **pulls in Nx** | Yes — `sourceTag` / `onlyDependOnLibsWithTags` | No | **Yes** (allowlist) | Bolt-on; requires Nx workspace | 12.8M/mo (tracks Nx adoption) |
| TS/Node | tsarch 5.4.1 | 6 deps incl. `typescript@^3.8.3`, squatter `fs`/`path` | Yes — nicest API | *Unverified* | No | Bolt-on (in-test) | 152k/mo; **last release 2024-12-23 — treat as unmaintained** |
| Go | **`internal/` rule** | **Zero — the compiler** | **Only as a containment rule** (nest the impl under `persistence/internal/`); not sibling-to-sibling | N/A — compile error | Yes | **Native, compile-time** | Universal |
| Go | **depguard** | **Zero if golangci-lint is present** (bundled) | Yes — `files` globs + `deny` map | No | Yes (`listMode: Strict`) | Bolt-on, but inside the standard runner | Ships in golangci-lint |
| Go | go-arch-lint (v3 config) | Standalone binary / Docker; go 1.25+ to build | Yes — `components` + `deps.mayDependOn` allowlist | *Unverified* | **Yes** (allowlist) | Bolt-on (separate binary) | Single-maintainer |
| Go | `go vet` | Zero | **No — no such analyzer exists** | — | — | Native but irrelevant | — |
| Rust | **workspace crates + `[dependencies]`** | **Zero — the compiler** | **Yes, exactly** — omit the dep and it will not compile | N/A — compile error | Yes | **Native, compile-time** | Universal |
| Rust | `pub(crate)` / `pub(in path)` | Zero | **No** within one crate — every `pub(crate)` item is visible to every sibling module | — | — | Native but insufficient | Universal |
| Rust | cargo-deny 0.20.2 | Standalone binary | **No — external crate graph only** (advisories/bans/licenses/sources) | — | — | Bolt-on, different job | 1.38M recent |
| Rust | layered-crate 0.4.6 | Standalone binary; rewrites `RUSTFLAGS`; macro caveats | Yes — `Layerfile.toml` `depends-on` allowlist | Compile-time via synthesized crates | Yes | Bolt-on | **127 recent downloads** |

## 5. What this means for FrameShift

Trade-offs only. The language decision belongs to a live session on #34/#35.

**a) "Architecture tests enforce module dependencies" means two different things depending
on the language.** In Go and Rust it can mean *the illegal edge does not compile* — there is
no test to write and no test to forget to run. In Python and TypeScript it always means *a
CI job someone can skip, downgrade to a warning, or silence per-line*. If ADR-0008's
Validation clause is meant as a guarantee rather than a check, that distinction is the whole
decision.

**b) But neither compiled language gives the guarantee in the shape ADR-0008 states, for
free.** Go's `internal/` is a *containment* rule: it makes the persistence *implementation*
unreachable from engines, while leaving the persistence *port* importable. Rust's crate
graph is the only mechanism here that expresses the pairwise rule exactly — but it costs
five crates, five `Cargo.toml` files, the loss of `pub(crate)` and cross-module `impl`
between ports, and it is enforced by *absence*, so the "test" is a `Cargo.toml` diff review
rather than a red CI job. Both compiled options convert an architecture rule into a
**directory/package layout commitment made up front**, which is a larger and less reversible
decision than adding a linter — and ADR-0008 explicitly says the domain boundaries "are
still being learned".

**c) The dependency-free constraint has one clean winner and one honest tension.** Go and
Rust cost literally zero (the compiler), and in Go depguard is free too if golangci-lint is
already present. In Python, ruff is the only zero-dependency option (0.16.3 declares no
Python dependencies at all) — but it cannot express a from→to rule without scattering
`.ruff.toml` files with mandatory `extend` lines, and it sees no transitive path. The tool
that actually does the job well, import-linter, costs four dev dependencies and requires the
package to be *installed* in CI, which is a step up from today's `python scripts/validate_repo.py`.
TypeScript is the worst on this axis: the strongest option (dependency-cruiser) is also the
heaviest thing in this report at 18 direct runtime dependencies.

**d) Transitive detection is where the tools genuinely differ, and it is under-appreciated.**
For a five-port model, the failure that actually happens is not `engines → persistence`; it
is `engines → validation → persistence`. Only **import-linter** (by default) and
**pytest-archon** (by default) catch it. **eslint-plugin-boundaries, @nx/enforce-module-boundaries,
depguard, and ruff all miss it** — they are file-at-a-time import matchers. dependency-cruiser
has transitive machinery but you must reach for it deliberately. If FrameShift wants the
indirect edge caught, that is a strong constraint on the Python/TS tool choice specifically.

**e) Fail-closed vs fail-open is a design choice the tool makes for you.** ADR-0008 says
"preserve boundaries that can later be separated". An allowlist (import-linter `layers`,
eslint-plugin-boundaries `default: "disallow"`, Nx `onlyDependOnLibsWithTags`, go-arch-lint
`mayDependOn`, layered-crate `depends-on`) makes a *sixth* module illegal by default. A
denylist (import-linter `forbidden`, dependency-cruiser, depguard, ruff) only catches edges
someone remembered to forbid. Since the ports are still being learned, the allowlist form
degrades more safely — but it also generates more churn during exactly the period when
boundaries are moving.

**f) Path-regex rules silently disarm on rename.** Every glob/regex tool here
(dependency-cruiser, eslint-plugin-boundaries, depguard, go-arch-lint, ruff's per-directory
scheme) will pass green after a directory rename that leaves the rule matching nothing.
depguard's README even warns about the `**/` prefix for this reason. The tools that do *not*
have this failure mode are the ones keyed to module identity rather than paths:
import-linter (Python module names), Nx (project tags), and both compilers. For a repo whose
whole validation philosophy is "the build fails on structural drift", a rule that can quietly
stop applying is a specific hazard worth weighing.

**g) No tool in any ecosystem catches the violation FrameShift is most exposed to.** The
capability broker and the runtime adapters are, by ADR-0005 and ADR-0001, indirection layers
— they exist to hand engines things engines did not import. **Every mechanism in this
report, compiler rules included, is blind to a persistence handle injected through a
legally-imported interface.** Static import rules protect the *shape* of the code, not the
*flow* of capability. If ADR-0008's real concern is "an engine must not reach the store",
import enforcement is a necessary but strictly partial answer in every candidate language,
and something else — a broker-level capability check, or a runtime assertion — carries the
rest regardless of which language wins.

**h) Ecosystem maturity is uneven and should not be assumed symmetric.** Python's answer
(import-linter) is mature, single-purpose, and downloaded 15M times a month. Go's answer is
the compiler plus a linter already bundled in the standard runner. TypeScript has two
healthy competing tools. Rust, uniquely, has **no meaningfully-adopted architecture linter
at all** — `layered-crate` at 127 recent downloads, `cargo-archtest` untouched since 2021 —
because the ecosystem's answer is to split crates. That means picking Rust means committing
to the workspace-splitting discipline; there is no popular tool to fall back on if the
five-crate layout turns out to be premature.

## 6. Sources

Every URL below was fetched on **2026-08-18**. Registry data (versions, dependency lists,
download counts) came from the official package APIs.

**Python**
- <https://import-linter.readthedocs.io/en/stable/contract_types/forbidden/> — `forbidden` contract config example and full field list (`source_modules`, `forbidden_modules`, `allow_indirect_imports`, `as_packages`).
- <https://import-linter.readthedocs.io/en/stable/contract_types/layers/> — `layers` contract syntax and "The order is from higher to lower level layers".
- <https://raw.githubusercontent.com/seddonym/import-linter/master/docs/get_started/run.md> — `lint-imports` CLI, all flags, pre-commit hook config.
- <https://raw.githubusercontent.com/seddonym/import-linter/master/docs/get_started/configure.md> — config file locations, `root_package` must-be-importable requirement, `include_external_packages`, `exclude_type_checking_imports`.
- <https://pypi.org/pypi/import-linter/json> — version 2.13, released 2026-07-03, `requires_python`, full `requires_dist`.
- <https://raw.githubusercontent.com/seddonym/grimp/master/README.rst> (redirects to `python-grimp/grimp`) — grimp's role as the import-graph builder.
- <https://docs.astral.sh/ruff/rules/banned-api/> — TID251 rule identity and description.
- <https://docs.astral.sh/ruff/settings/#lint_flake8-tidy-imports_banned-api> — the `banned-api` TOML example.
- <https://docs.astral.sh/ruff/configuration/> — hierarchical config discovery, `.ruff.toml` > `ruff.toml` > `pyproject.toml`, and the no-merging / `extend` caveat.
- <https://pypi.org/pypi/ruff/json> — version 0.16.3, released 2026-08-13, `requires_dist: None`.
- <https://github.com/jwbargsten/pytest-archon> — `archrule` fluent syntax and the documented import-scope options.
- <https://pypi.org/pypi/pytest-archon/json> — version 0.0.7, released 2025-09-19, single `pytest>=7.2` dependency.
- <https://github.com/adamchainz/flake8-tidy-imports> — `banned-modules` setup.cfg syntax; README's own pointer to import-linter for advanced use.
- <https://pypistats.org/api/packages/{import-linter,pytest-archon,flake8-tidy-imports,ruff}/recent> — monthly download counts. *(Note: pypistats is a derived aggregator over PyPI's own download data, not a first-party endpoint; the counts are indicative only.)*

**TypeScript / Node**
- <https://raw.githubusercontent.com/sverweij/dependency-cruiser/main/doc/rules-reference.md> — minimal rule shape, `name`/`severity`/`comment` semantics, the `^src/business-components/...` forbidden example, `dynamic` condition, `type-only` dependency type, the "heavy maintenance" note on per-pair rules.
- <https://raw.githubusercontent.com/sverweij/dependency-cruiser/main/README.md> — `depcruise --init`, `npx depcruise src`, the `not-to-test` sample rule.
- <https://registry.npmjs.org/dependency-cruiser/latest> — version 18.2.0, full runtime `dependencies`, Node engine range.
- <https://raw.githubusercontent.com/javierbrea/eslint-plugin-boundaries/master/README.md> — `boundaries/elements` classification and the `boundaries/dependencies` policies block with `default: "disallow"`.
- <https://registry.npmjs.org/eslint-plugin-boundaries> — version 7.2.0 (2026-08-09), dependencies, eslint peer range.
- <https://nx.dev/features/enforce-module-boundaries> — `@nx/enforce-module-boundaries` flat-config example with `depConstraints` / `sourceTag` / `onlyDependOnLibsWithTags`; providing package.
- <https://registry.npmjs.org/@nx/eslint-plugin> — version 23.1.1 (2026-07-30), dependencies including `@nx/js` and `@nx/devkit`.
- <https://raw.githubusercontent.com/ts-arch/ts-arch/main/README.md> — the `filesOfProject().inFolder(...).shouldNot().dependOnFiles()` API.
- <https://registry.npmjs.org/tsarch> — version 5.4.1, published 2024-12-23, dependency list including `typescript: ^3.8.3`, `fs: 0.0.1-security`, `path: ^0.12.7`.
- <https://www.typescriptlang.org/docs/handbook/project-references.html> — what project references do and do not enforce.
- <https://api.npmjs.org/downloads/point/last-month/…> — official npm download counts.

**Go**
- <https://raw.githubusercontent.com/golang/go/master/src/cmd/go/internal/help/helpdoc.go> — the verbatim "Internal packages" text served by `go help packages`, including the `example.com/m` layout. This is the `go` command's own source, i.e. the normative statement of the rule.
- <https://go.dev/s/go14internal> — referenced by the above as the detailed design; not separately fetched.
- <https://pkg.go.dev/cmd/vet> — the full analyzer list; used to establish that no import-restriction check exists.
- <https://raw.githubusercontent.com/OpenPeeDeeP/depguard/master/README.md> — config file discovery regex, JSON/YAML examples, `files`/`allow`/`deny`/`listMode` semantics, the `**/` glob warning, `$all`/`$test`/`$gostd` variables, prefix-vs-`$`-exact matching.
- <https://raw.githubusercontent.com/golangci/golangci-lint/main/.golangci.reference.yml> — confirms depguard is bundled in golangci-lint and documents its `list-mode` values there.
- <https://raw.githubusercontent.com/fe3dback/go-arch-lint/master/README.md> — `version: 3` config with `components`, `commonComponents`, `deps.mayDependOn`; Docker invocation; go 1.25+ build requirement; CI recommendation.
- <https://go.dev/ref/mod> — checked for `internal` and found none; recorded so the negative is on the record.

**Rust**
- <https://doc.rust-lang.org/reference/visibility-and-privacy.html> — the two access rules and the `pub(in path)` / `pub(crate)` / `pub(super)` / `pub(self)` definitions with the `outer_mod` example. This is the language reference, i.e. normative.
- <https://doc.rust-lang.org/cargo/reference/workspaces.html> — workspace definition, path dependencies between members, and the absence of any forbid mechanism.
- <https://embarkstudios.github.io/cargo-deny/> — the four checks (advisories, bans, licenses, sources).
- <https://embarkstudios.github.io/cargo-deny/checks/bans/index.html> — "The bans check is used to deny (or allow) specific crates, as well as detect and handle multiple versions of the same crate"; confirms external-graph scope.
- <https://raw.githubusercontent.com/Pistonite/layered-crate/main/README.md> — the "Rust allows you to import anything anywhere in the same crate" statement, `Layerfile.toml` syntax, the synthesized-crate implementation strategy, the `impl = [...]` loosening, `RUSTFLAGS` behaviour, and the proc-macro warning.
- <https://crates.io/api/v1/crates/{cargo-deplint,layered-crate,cargo-archtest,cargo-deny}> — official crates.io API: versions, last-updated timestamps, total and recent download counts.

**Repository context (not external)**
- `docs/adr/0008-modular-monolith-first.md`, `CONTEXT.md`, `AGENTS.md`, `scripts/validate_repo.py`, `evals/run.py`, `docs/agents/issue-tracker.md`.

### Explicitly unverified

- A concrete TOML example for ruff's `lint.flake8-tidy-imports.banned-module-level-imports` (the settings page excerpt was truncated).
- Whether go-arch-lint performs transitive/indirect dependency analysis.
- Whether tsarch performs transitive analysis (not pursued given its maintenance status).
- A named, widely-used tool that asserts Rust workspace dependency edges from `cargo metadata` in CI. Projects appear to hand-roll this; I found no standard.
- import-linter's behaviour on `importlib`/`__import__` is not documented as such on the pages fetched; the "static analysis only" characterisation is inferred from grimp's stated design (it builds the graph by analysing package source) rather than quoted from a limitations section.
