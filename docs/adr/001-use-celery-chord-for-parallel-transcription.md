# ADR 001: Use Celery Chord for Parallel Transcription

## Status
Accepted

## Context
The AI Video Subtitle Tool needs to process videos of varying lengths efficiently. For longer videos (>60 seconds), sequential transcription becomes a bottleneck, leading to poor user experience and potential timeout issues.

### Requirements
- Support videos from short clips (<30s) to full-length movies (2+ hours)
- Provide progress feedback during processing
- Handle failures gracefully without losing entire task
- Scale horizontally with multiple workers

## Decision
Use Celery's `chord` primitive to parallelize video segment transcription for videos longer than 60 seconds.

### Architecture
```
Split Video → [Segment 1] ─┐
          → [Segment 2] ──┼→ Chord Barrier → Merge & Finalize
          → [Segment N] ─┘
```

### Implementation Details
1. **Segment Splitting**: Videos are split into segments using scene detection or fixed intervals
2. **Parallel Processing**: Each segment is transcribed independently via Celery tasks
3. **Chord Barrier**: Waits for all segment tasks to complete before proceeding
4. **Merge Phase**: Segments are merged with timestamp adjustments
5. **Fallback**: If chord is unavailable, gracefully fall back to sequential processing

## Consequences

### Positive
- **Performance**: ~N× speedup for N-segment videos (limited by worker count)
- **Scalability**: Can add more workers to handle increased load
- **Fault Isolation**: Failure in one segment doesn't affect others
- **Progress Tracking**: Can report per-segment completion

### Negative
- **Complexity**: More complex error handling and state management
- **Resource Usage**: Higher memory usage when processing many segments simultaneously
- **Dependency**: Requires Redis backend for Celery chord support

### Mitigations
- Implemented fallback to sequential mode if chord unavailable
- Added proper cleanup for temporary segment files
- Used atomic writes to prevent corruption during merge

## Alternatives Considered

### Alternative 1: Always Sequential
**Rejected** because:
- Unacceptable performance for long videos
- Doesn't leverage available compute resources
- Poor user experience

### Alternative 2: Manual Fan-out/Fan-in
**Rejected** because:
- Reinventing wheel (Celery chord already solves this)
- More error-prone
- Harder to maintain

### Alternative 3: External Queue System (RabbitMQ + separate orchestration)
**Rejected** because:
- Over-engineering for current scale
- Adds operational complexity
- Redis already required for other features

## Compliance
This decision aligns with:
- Long-term stability: Uses battle-tested Celery primitives
- Maintainability: Clear separation of concerns
- Testability: Each segment task can be tested independently
- Reproducibility: Deterministic segment splitting and merging

## References
- Celery Chord Documentation: https://docs.celeryq.dev/en/stable/userguide/canvas.html#chords
- Related ADR: ADR 002 (Uniform Segment Payload Design)
- Implementation: `backend/tasks.py::transcribe_full_video_pipeline`
