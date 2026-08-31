"""FrameShift, as a modular monolith with explicit in-process ports (ADR-0008).

One package, boundaries that could later be separated, and no network service
introduced without measured need. `persistence` is the first port: it owns
canonical encoding, checkpoint digests, and restore.
"""
