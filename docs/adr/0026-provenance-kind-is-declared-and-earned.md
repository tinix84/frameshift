# ADR-0026: A reasoner declares a provenance kind, and its sources must earn it

- Status: accepted
- Date: 2026-10-10
- Deciders: repository owner, through the design decision on #257
- Supersedes: none

## Context

`add_node` rewrites every reasoner-supplied node as provenance kind `assumed`,
with the note "Supplied by the reasoner; not established", and keeps only the
source ids. In the espresso simulation (#252) all 43 nodes lose their kind.
Symptom knots the person observed, mechanisms cited from the literature and
inferred hypotheses all read as guesses.

The rewrite was meant to keep anything a reasoner supplies from becoming
established. It does that by conflating two things `CONTEXT.md` keeps apart:

- **evidence basis**: where a claim came from (`observed`, `sourced`,
  `inferred`, `assumed`, `unknown`);
- **status**: whether it has been decided.

#254 now guards status directly: a reasoner offers only `draft` or `proposed`.

## Decision

**Provenance kind is the reasoner's to declare and its sources' to earn.** A
reasoner-supplied node keeps the kind it declares when its source ids meet the
rule for that kind:

| Kind | The source ids must include |
|---|---|
| `observed` | an intake record (`intake_`), or a statement (`stmt_`) whose own provenance kind is `observed`: the person's own words |
| `sourced` | at least one referenced artifact (`art_`) |
| `inferred` | at least one source of any registered namespace |
| `assumed`, `unknown` | nothing |

Every source id must also satisfy ADR-0012: a registered prefix, and resolution
for namespaces inside canonical state. A node whose declared kind is not
earned is refused with `invariant_violation`; it is never rewritten to another
kind.

**What is stored.** `add_node` takes an optional `provenance` object with
`kind`, `source_ids` and an optional `note`. When the rule admits it, that
object is stored exactly as given, with no default note added. A node that
supplies no `provenance` keeps today's behaviour: kind `assumed`, its
`source_ids`, and the note "Supplied by the reasoner; not established."

**#256 comes first.** The `observed` guarantee depends on statements whose kind
is `observed` really being the person's words. Today `add_statement` gives that
kind to every statement, including those a reasoner adds, so a reasoner could
add a statement and then cite it to earn `observed`. #257 must not ship before
#256 restricts `observed` to the person's own statements.

**Kind never promotes.** Whatever kind a node carries, its status stays `draft`
or `proposed` until a person decides (#254).

**Scope.** The rule applies to edges when they take declared provenance
(#258). Until then, an edge keeps today's provenance: `assumed`, citing its two
ends. It applies to symptom specifications (ADR-0027). Ladder rungs already
store a declared provenance unchecked (ADR-0024). Bringing them under the rule
is a follow-up, not part of this decision.

## Consequences

The graph keeps its evidence picture: a cited mechanism is distinguishable from
a guess, which is what AGENTS.md asks for when it says to label provenance
explicitly.

The rule checks the shape of the evidence, not its truth. A reasoner can still
cite a statement loosely. The person reviewing at a gate sees the citation and
judges it; the application only guarantees that `observed` points back to the
person and `sourced` to an artifact.

`sourced` resolves only as far as ADR-0012 allows: an `art_` id is accepted on
its prefix, because the session cannot see the artifact.

## Alternatives considered

- **Keep any schema-valid kind.** Simplest, but a reasoner could label a guess
  `observed`, the strongest basis, with nothing behind it.
- **Keep rewriting to `assumed` and store the declared kind as an extension.**
  Most conservative, but it keeps the evidence picture outside the contract,
  where nothing validates it.

## Validation

#257, after #256: tests accept each kind with sources that earn it and refuse
each kind without them. Status is unaffected. After the change, the espresso
`compare` shows no node-provenance difference. All 43 reference nodes and 52
reference edges meet the rule, judged by the kinds of the reference's own
statements.
