# ADR 003: Atomic File Write Strategy

## Status
Accepted

## Context
The subtitle generation tool writes critical files:
- Subtitle files (.srt, .ass)
- Processed video files
- Task result manifests

These files must not be corrupted if:
- Process crashes mid-write
- Disk fills up during write
- Multiple processes attempt concurrent writes
- Network storage has latency issues

Corrupted files would lead to:
- Unreadable subtitles
- Failed downloads
- Inconsistent task state
- Poor user experience

## Decision
Use **atomic write operations** for all critical file updates via write-to-temp-then-rename pattern.

### Implementation Pattern
```python
def write_text_atomic(path: Path, content: str) -> None:
    """Write text atomically using temp file + os.replace()"""
    tmp_path = path.with_suffix(path.suffix + '.tmp')
    
    # Write to temporary file
    tmp_path.write_text(content, encoding='utf-8')
    tmp_path.chmod(0o644)
    
    # Atomic rename (POSIX guarantee)
    os.replace(tmp_path, path)
    
    # Cleanup if temp still exists (shouldn't happen)
    if tmp_path.exists():
        tmp_path.unlink()
```

### Key Properties
1. **Atomicity**: `os.replace()` is atomic on POSIX systems
2. **Durability**: Original file remains intact until replacement succeeds
3. **Recovery**: Temp files can be cleaned up on restart
4. **Simplicity**: No locks or complex coordination needed

## Application Areas

### Subtitle Files
When updating edited subtitles:
```python
# In main.py - edit_subtitle endpoint
write_text_atomic(srt_path, new_content)
```

### Task Manifests
When finalizing task results:
```python
# In tasks.py - finalize_pipeline
write_text_atomic(manifest_path, json.dumps(results))
```

### Video Files
When burning subtitles into video:
```python
# Write output to temp, then atomic rename
ffmpeg ... -y temp_output.mp4
os.replace('temp_output.mp4', 'final_output.mp4')
```

## Consequences

### Positive
- **Data Integrity**: No partial writes visible to readers
- **Crash Safety**: System crash leaves original file intact
- **Simplicity**: No need for rollback logic
- **Performance**: Minimal overhead (single extra write)

### Negative
- **Disk Space**: Requires space for both old and new file temporarily
- **Complexity**: Slightly more code than direct write
- **Platform Dependency**: Relies on POSIX `rename()` semantics

### Mitigations
- Windows support: `os.replace()` works on Windows (since Python 3.3)
- Disk space: Temporary files are small compared to video files
- Error handling: Always cleanup temp files in finally blocks

## Alternatives Considered

### Alternative 1: Direct Write
Write directly to target file.

**Rejected** because:
- Crash during write corrupts file
- No recovery possible
- Unacceptable for production use

### Alternative 2: File Locking
Use fcntl/flock to lock file during write.

**Rejected** because:
- Doesn't prevent corruption from crashes
- Adds complexity (lock management, deadlock potential)
- Still vulnerable to partial writes

### Alternative 3: Database Storage
Store subtitles in database instead of files.

**Rejected** because:
- Over-engineering for simple text files
- Adds operational complexity (database maintenance)
- Files are easier to backup and transfer

### Alternative 4: Copy-On-Write Filesystem
Rely on ZFS/Btrfs COW semantics.

**Rejected** because:
- Not portable (requires specific filesystem)
- Doesn't help with application-level consistency
- Still need atomic rename for logical consistency

## Compliance
This decision aligns with:
- **Long-term stability**: Prevents data corruption
- **Maintainability**: Simple, well-understood pattern
- **Testability**: Easy to test crash scenarios
- **Reproducibility**: Same behavior across environments
- **Clear Data Contracts**: Files always in valid state

## Edge Cases Handled

### Concurrent Writes
Multiple processes writing same file:
- Last writer wins (expected behavior)
- No corruption due to atomic rename
- Consider adding versioning if needed

### Disk Full During Write
- Temp file write fails gracefully
- Original file untouched
- Error propagated to caller

### Power Failure
- If before rename: original file intact
- If after rename: new file complete
- Temp file may remain (cleaned up later)

## References
- Python `os.replace()` documentation
- Related pattern: "Temporary File Rename" in POSIX systems
- Implementation: `backend/utils/file_utils.py::write_text_atomic`
