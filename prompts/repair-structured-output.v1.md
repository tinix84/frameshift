---
id: frameshift.repair-structured-output.v1
version: 1.0.0
engine: shared
body_digest: sha256:36f2364206fca63ad074dc131347b5a5fa87a74c36b86dc2bb4b477adc91fba2
---

Repair the supplied JSON only so it conforms to the supplied schema and validation errors. Preserve supported domain content and stable IDs. Do not add approvals, evidence, tool results, claims, or facts. If a required value cannot be repaired without invention, return it as a typed missing-information item where the schema permits; otherwise return a typed failure.
