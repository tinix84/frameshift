# Environment adapters

Adapters translate FrameShift's canonical execution contract to a runtime. They are thin: they may map messages, tools, structured-output modes, and operational metadata, but may not change domain state, safety gates, or schemas.

Each adapter directory contains a human-readable bootstrap and a capability manifest example. A production adapter must pass the conformance requirements in the runtime-portability contract, issue #19.
