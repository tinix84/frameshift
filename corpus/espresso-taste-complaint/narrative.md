# Espresso taste complaint

## Request as it arrived

"My espresso is not like an Italian espresso."

## Why it misleads

The sentence is an observation with two hidden loads. It bundles several
deviations (sour shots, bitter shots, no crema, no consistency) into one claim,
so no single cause can be tested against it. It also assumes a reference that
does not exist as one specification: published Italian parameter sets disagree
on brew temperature, extraction time and dose.

Branching the causes immediately (machine, water, coffee, grind, roast,
pressure, perception) produces a fishbone with no way to rank its branches.

## Reframe

Specify the symptom before analysing it. Following the IS / IS NOT problem
specification, each deviation becomes one object and one deviation, described
across what, where, when and extent, with the closest case where it does not
occur. The contrasts, not the branch list, decide which part of the cause tree
is worth analysing.

Here the specification splits the complaint into two deviations:

- D1, taste alternating between sour and bitter from shot to shot, never in the
  same sip;
- D2, no crema although a pressurized basket is used, a basket that normally
  forms foam whatever the grind.

The decisive contrast is where: the same pre-ground bag brewed fine at a bar.
That retires the coffee as a sole cause and moves the working frame to repeatable
extraction on the home machine.

## What the session shows

`espresso-taste-complaint.session.json` is a version-2 session in the causal
phase. It is the reference for documentation and tests; the Mermaid file beside
it is a derived view and is regenerated from the JSON, never edited.

- **Bowtie structure.** The symptom statements are the knots. Above them sit the
  ladder (component, subsystem, system with an operations boundary, product) and
  four candidate frames. Below them sits one shared causal graph, because the
  same factors (grind, temperature, scale) feed several symptoms.
- **Frame shift with history.** The supply-chain frame was raised on a first
  answer that the coffee was also bad at the bar, then rejected when the person
  corrected it. Both statements remain; a `contradicts` edge records the
  correction and nothing is deleted.
- **Cross-links by shared nodes, not by tags.** Mechanisms such as the pump
  against coffee-bed operating point connect the grind and pressure branches.
  Tags in `extensions.tags` are views for filtering.
- **Competing hypotheses kept.** Scale, temperature drift and a coffee-machine
  interaction stay open; channeling and stale coffee are demoted with the
  evidence that demoted them; the brand hypothesis is rejected.
- **Expansion layer.** Draft nodes mark where analysis would continue: the
  discriminating evidence plan (log, descale, log again), a recoverability risk,
  and a perception branch for cup temperature, setting and remembered reference.

No edge uses `causes`: nothing here is a supported causal assertion yet.

## Downstream change

The person must measure shot time and cup quantity spread before and after
descaling. Only that result can promote a hypothesis. The symptom specification
lives in `extensions.symptom_specification` because no canonical field holds it;
it is the worked example for adding one.
