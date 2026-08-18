# ADR-0008: Start as a modular monolith

- Status: accepted
- Date: 2026-08-18
- Deciders: initial maintainers
- Supersedes: none

## Context

The domain boundaries are still being learned. Early distribution would add operational and consistency complexity before real usage validates the model.

## Decision

Implement the first application as a modular monolith with explicit in-process ports for engines, runtime adapters, capability broker, validation, and persistence. Preserve boundaries that can later be separated, but do not introduce network services without measured need.

## Consequences

The first vertical slice is faster to build and test transactionally. Module interfaces and contracts remain clear. Independent scaling and failure isolation are deferred.

## Alternatives considered

- Microservices from inception: strong isolation but high coordination and deployment cost.
- Single undifferentiated module: simplest initially but erodes domain and security boundaries.

## Validation

Architecture tests enforce module dependencies; deployment telemetry later informs any extraction ADR.
