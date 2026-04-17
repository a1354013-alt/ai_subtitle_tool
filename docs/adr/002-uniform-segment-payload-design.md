# ADR 002: Uniform Segment Payload Design

## Status
Accepted

## Context
The subtitle generation pipeline consists of multiple stages:
1. Split video into segments
2. Transcribe each segment
3. Merge transcribed segments
4. Translate (optional)
5. Finalize and package results

Each stage needs to pass structured data to the next stage. Early implementations used different payload formats for different stages, leading to compatibility issues and implicit conversion logic.

## Decision
Use a **single, uniform payload format** throughout the entire pipeline, specifically designed for the `finalize_pipeline()` function.

### Payload Structure
```python
{
    "start": float,        # Segment start time in seconds
    "end": float,          # Segment end time in seconds  
    "text": str,           # Transcribed text
    "segments": [...]      # Optional: nested Whisper segments with word-level timing
}
```

### Key Principles
1. **Single Source of Truth**: Only one payload format exists
2. **Explicit Conversion**: Any deviation must be explicitly converted
3. **No Implicit Merging**: Reject mixed formats rather than guessing
4. **Type Safety**: All fields are strictly typed and validated

## Implementation

### Pipeline Flow
```
split_video() 
    → List[VideoSegment]
    
transcribe_segment_task()
    → List[UniformPayload]
    
merge_and_finalize_task()
    → Validates all payloads match uniform format
    → Calls finalize_pipeline([UniformPayload, ...])
```

### Validation
```python
def finalize_pipeline(segments, ...):
    # Strict validation - reject non-uniform payloads
    for seg in segments:
        assert isinstance(seg, dict)
        assert "start" in seg and isinstance(seg["start"], (int, float))
        assert "end" in seg and isinstance(seg["end"], (int, float))
        assert "text" in seg and isinstance(seg["text"], str)
    # ... proceed with known-good format
```

## Consequences

### Positive
- **Clarity**: No ambiguity about expected format
- **Maintainability**: Changes to format are localized
- **Debuggability**: Errors caught early with clear messages
- **Testability**: Easy to create test fixtures with known format
- **Extensibility**: New fields can be added without breaking existing code

### Negative
- **Rigidity**: Less flexible for experimental features
- **Boilerplate**: Need explicit conversion for external data sources

### Mitigations
- Helper functions for common conversions
- Clear error messages when validation fails
- Documentation of payload contract

## Alternatives Considered

### Alternative 1: Multiple Format Support
Allow `finalize_pipeline()` to accept multiple formats and auto-detect.

**Rejected** because:
- Implicit logic is hard to understand and debug
- Easy to introduce bugs when formats evolve
- Makes testing more complex (need to test all format combinations)

### Alternative 2: Protocol Buffers / Schema Validation
Use formal schema definition (e.g., Protobuf, Pydantic models).

**Rejected** because:
- Over-engineering for current scale
- Adds dependency and complexity
- Current dict-based approach is sufficient

### Alternative 3: Class-Based Payload
Use dataclass or named tuple for payload.

**Partially Adopted**: Considered for future refactoring, but current dict approach is simpler for Celery serialization.

## Compliance
This decision aligns with:
- **Long-term stability**: Clear contracts prevent drift
- **Maintainability**: Single format = single place to update
- **Testability**: Easy to validate and mock
- **Reproducibility**: Same input always produces same output
- **Clear Data Contracts**: Explicit schema documented in code

## References
- Related ADR: ADR 001 (Celery Chord for Parallel Transcription)
- Implementation: `backend/tasks.py::finalize_pipeline`
- Validation: `backend/pipeline_segments.py`
