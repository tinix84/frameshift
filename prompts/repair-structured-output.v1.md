---
id: frameshift.repair-structured-output.v1
version: 1.0.0
engine: shared
---

Repair the supplied JSON only so it conforms to the supplied schema and validation errors. Preserve supported domain content and stable IDs. Do not add approvals, evidence, tool results, claims, or facts. If a required value cannot be repaired without invention, return it as a typed missing-information item where the schema permits; otherwise return a typed failure.
