# Auto-Sync Replication Behavior

## Overview

The auto-sync background task runs every 30 seconds and automatically replicates files to nodes that are missing them. It intelligently handles three node states:

- **✅ Has file** (`True`) - Node is online and has the file
- **❌ Missing file** (`False`) - Node is online but doesn't have the file  
- **⚠️ Offline** (`None`) - Node is unreachable (network timeout, container stopped, etc.)

## How It Works

### File Existence Check

For each file, auto-sync checks all 3 nodes in parallel with a 2-second timeout:

```python
existence_status = check_file_exists_on_nodes(object_name, bucket_name)
# Returns: {'minio1': True, 'minio2': False, 'minio3': None}
```

### Sync Decision Logic

```python
if nodes_with_file > 0 and (nodes_without_file > 0 or nodes_offline > 0):
    # Sync to nodes where exists = False (skip offline nodes)
```

**Syncing happens when:**
- At least 1 node HAS the file (source available)
- AND at least 1 node is missing the file OR offline

**Syncing is skipped when:**
- No nodes have the file (no source)
- All nodes have the file (fully replicated)
- File only exists on offline nodes (no accessible source)

### Target Selection

Auto-sync only copies to nodes with `exists = False`:
- ✅ **Copies to** reachable nodes missing the file
- ⏭️ **Skips** offline nodes (they'll be synced when they come back online)

## Example Scenarios

### Scenario 1: Upload with 1 Node Offline

**Initial State:**
```
Upload file.txt with minio2 OFFLINE
Result: minio1 ✅, minio3 ✅, minio2 ⚠️ (offline)
```

**Auto-Sync Cycle 1 (minio2 still offline):**
```
Check: minio1=True, minio3=True, minio2=None
Decision: 2 have, 0 missing, 1 offline → Skip (can't sync to offline node)
Log: "File X - On 2 node(s), Missing from 0 node(s), 1 offline. Syncing..."
Action: Try to sync but node is offline, wait for next cycle
```

**Auto-Sync Cycle 2 (minio2 back online):**
```
Check: minio1=True, minio3=True, minio2=False
Decision: 2 have, 1 missing, 0 offline → SYNC!
Log: "File X - On 2 node(s), Missing from 1 node(s), 0 offline. Syncing..."
Action: Copy from minio1 to minio2 ✅
Result: "Auto-sync completed: 1 file(s) synced"
```

### Scenario 2: Upload with 2 Nodes Offline

**Initial State:**
```
Upload file.txt with minio2 and minio3 OFFLINE
Result: minio1 ✅, minio2 ⚠️, minio3 ⚠️
```

**Auto-Sync Cycle 1 (both still offline):**
```
Check: minio1=True, minio2=None, minio3=None
Decision: 1 have, 0 missing, 2 offline → Skip
Log: "File X - On 1 node(s), Missing from 0 node(s), 2 offline. Syncing..."
```

**Auto-Sync Cycle 2 (minio2 comes back):**
```
Check: minio1=True, minio2=False, minio3=None
Decision: 1 have, 1 missing, 1 offline → SYNC to minio2!
Log: "File X - On 1 node(s), Missing from 1 node(s), 1 offline. Syncing..."
Action: Copy from minio1 to minio2 ✅
```

**Auto-Sync Cycle 3 (minio3 comes back):**
```
Check: minio1=True, minio2=True, minio3=False
Decision: 2 have, 1 missing, 0 offline → SYNC to minio3!
Log: "File X - On 2 node(s), Missing from 1 node(s), 0 offline. Syncing..."
Action: Copy from minio1 to minio3 ✅
```

## Why You Might See "All Files Fully Replicated"

This message appears when:

1. **All reachable nodes have all files**
   - Offline nodes don't count as "missing"
   - Auto-sync waits for them to come back online

2. **Only offline nodes are missing files**
   - Can't sync to unreachable nodes
   - Will retry in next cycle

3. **Files only exist on offline nodes**
   - No source available to copy from
   - Will sync once source node comes back online

## Verification

To verify auto-sync is working, check the logs:

```powershell
# Watch auto-sync in real-time
docker-compose logs fastapi -f | Select-String "Auto-sync|Syncing"

# Check specific file sync
docker-compose logs fastapi --tail 100 | Select-String "filename"
```

**Expected log patterns:**

```
🔄 Auto-sync: Checking for incomplete replications...
  🔍 File 24 (verify.txt): 2 have, 1 missing, 0 offline - Status: {'minio2': False, 'minio1': True, 'minio3': True}
  ⚠ File 24 (verify.txt) - On 2 node(s), Missing from 1 node(s), 0 offline. Syncing...
    ✓ Synced to MinIO Node 2
✓ Auto-sync completed: 1 file(s) synced
```

## Performance Characteristics

- **Cycle Interval**: 30 seconds
- **Node Check Timeout**: 2 seconds per check (parallelized)
- **File Transfer**: Blocking operation run in thread pool (doesn't block event loop)
- **Maximum Sync Time**: ~4 seconds for single file to offline-then-online node

## Troubleshooting

### "Error processing file X: cannot schedule new futures after interpreter shutdown"

This is a harmless error that can occur during container restart. The next auto-sync cycle will process the file successfully.

### Auto-sync says "All files fully replicated" but I know a node is missing files

Check if that node is offline:
```powershell
docker-compose ps
```

Auto-sync doesn't count offline nodes as "missing" - it waits for them to come back online, then syncs.

### Auto-sync is syncing but says "0 offline" when I know a node is down

Check the debug logs:
```powershell
docker-compose logs fastapi --tail 50 | Select-String "🔍"
```

If a node is truly down, it should show `None` in the Status dict. If it shows `False`, the node is online but doesn't have the file.

## Summary

✅ **Auto-sync DOES work when nodes come back online**  
✅ **It syncs to nodes where `exists = False` (confirmed missing)**  
✅ **It skips nodes where `exists = None` (offline/unreachable)**  
✅ **Runs every 30 seconds without blocking the application**  
✅ **Syncs incrementally as nodes come back online**  

The key improvement was distinguishing between "node doesn't have file" (False) and "node is offline" (None), allowing auto-sync to make intelligent decisions about when and where to sync.
