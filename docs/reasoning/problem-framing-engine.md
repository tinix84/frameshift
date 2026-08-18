# Problem-framing engine

## Objective

Transform a raw request into candidate problem frames at useful abstraction levels without prematurely selecting a solution.

## Inputs

- Intake statements and conversation excerpts selected for use.
- Stakeholders, known outcomes, current/desired state, constraints, and evidence.
- Existing frames and corrections.
- Runtime capabilities and workspace policy.

## Method

### 1. Semantic-role classification

Classify each material statement as observation, need, outcome, problem, function, requirement, constraint, assumption, proposal, or question. Multiple labels are allowed with a primary label. Human wording is preserved.

### 2. Solution-disguise detection

Trigger abstraction-up when the statement specifies a component, topology, vendor, implementation, or action but lacks the outcome it serves. The engine asks “what changes if this succeeds?” and “for whom?”

### 3. Why/how ladder

- **Why/up:** desired product or business outcome, stakeholder value, system purpose.
- **How/down:** functions, mechanisms, architectures, components.

Each rung records scope, boundary, measures, assumptions, and loss introduced by moving levels. Stop upward expansion when the user reaches an outcome they own and can measure; stop downward expansion before selecting an implementation unless needed for testability.

### 4. Boundary exploration

Propose boundaries such as component, subsystem, full product, lifecycle, operations, supply chain, portfolio/platform, and business model when relevant. Avoid forced coverage of irrelevant levels.

### 5. Candidate frames

Create two to five frames that are materially different in outcome, boundary, stakeholder, or time horizon. Each frame includes:

- concise question in “How might we … so that … while …?” form;
- current and desired states;
- included and excluded scope;
- success measures;
- hard constraints versus assumptions;
- likely leverage areas;
- risks of choosing the frame; and
- open questions/evidence needs.

### 6. Challenge

Test whether the frame embeds a preferred solution, optimizes a proxy, omits a stakeholder, assumes causality, or makes success unmeasurable.

## Output

An `EngineResult` containing classifications, abstraction ladder, candidate frames, conflicts, missing information, and a required `frame_selection` checkpoint.

## Human gate

Only a human can mark a frame `working`. The approval binds to the frame content digest and session revision. An edit creates a new candidate digest.

## Example

Input: “What can we modify in the motor and inverter to improve performance?”

- Proposed solution boundary: motor/inverter changes.
- Upward outcome: improve vehicle performance.
- Further upward question: which performance measure and why?
- Candidate business frame: improve vehicle contribution margin while meeting minimum acceleration/range.
- Alternative interventions now include platform reuse, supply-chain choices, pack modularity, feature positioning, and powertrain changes.

## Quality checks

- At least one frame is solution-neutral.
- Outcomes have an owner and observable measure or an open measurement question.
- Constraints and assumptions are not conflated.
- Exclusions are explicit.
- The original request remains traceable.
