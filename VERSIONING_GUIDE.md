# MinIO File Versioning Guide - v1.2.0

## Overview

Version 1.2.0 adds comprehensive file versioning support to the distributed file storage system. Every time a file is uploaded with the same name, MinIO automatically creates a new version while preserving all previous versions.

## Features

### ✅ Automatic Versioning
- **Bucket-level versioning** enabled on all MinIO nodes
- **Automatic version IDs** assigned to each file upload
- **Version metadata** tracked (timestamp, size, ETag)
- **Latest version flag** to identify current version

### ✅ Version Management APIs

#### 1. List All Versions of a File
```http
GET /api/files/{file_id}/versions
```

**Response:**
```json
{
  "file_id": 1,
  "filename": "document.pdf",
  "object_name": "abc123-document.pdf",
  "versions": [
    {
      "version_id": "xyz789",
      "is_latest": true,
      "last_modified": "2025-11-26T10:30:00",
      "size": 102400,
      "etag": "d41d8cd98f00b204e9800998ecf8427e"
    },
    {
      "version_id": "abc456",
      "is_latest": false,
      "last_modified": "2025-11-25T14:20:00",
      "size": 98304,
      "etag": "098f6bcd4621d373cade4e832627b4f6"
    }
  ],
  "total_versions": 2
}
```

#### 2. Download Specific Version
```http
GET /api/files/{file_id}/versions/{version_id}/download
```

**Headers:**
- `Content-Disposition`: `attachment; filename={original_filename}`
- `X-Version-ID`: `{version_id}`

#### 3. Delete Specific Version
```http
DELETE /api/files/{file_id}/versions/{version_id}
```

**Response:**
```json
{
  "message": "Version deleted",
  "file_id": 1,
  "version_id": "abc456",
  "results": {
    "minio1": "Version deleted successfully",
    "minio2": "Version deleted successfully",
    "minio3": "Version deleted successfully"
  }
}
```

## Usage Examples

### Uploading Multiple Versions

1. **Upload original file:**
   ```bash
   POST /api/upload
   # Creates version 1 (version_id: v1)
   ```

2. **Upload updated file (same filename):**
   ```bash
   POST /api/upload
   # Creates version 2 (version_id: v2)
   # Version 1 is preserved
   ```

3. **Upload another update:**
   ```bash
   POST /api/upload
   # Creates version 3 (version_id: v3)
   # Versions 1 & 2 are preserved
   ```

### Retrieving Version History

```python
import requests

# Get all versions
response = requests.get('http://localhost:8000/api/files/1/versions')
versions = response.json()['versions']

print(f"Total versions: {versions['total_versions']}")
for v in versions['versions']:
    status = "CURRENT" if v['is_latest'] else "OLD"
    print(f"[{status}] Version {v['version_id']}: {v['size']} bytes, {v['last_modified']}")
```

### Downloading Old Version

```python
import requests

# Download version abc456
response = requests.get(
    'http://localhost:8000/api/files/1/versions/abc456/download',
    stream=True
)

with open('document_v1.pdf', 'wb') as f:
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
```

### Cleaning Up Old Versions

```python
import requests

# Delete specific version
response = requests.delete(
    'http://localhost:8000/api/files/1/versions/abc456'
)
print(response.json())
```

## Technical Implementation

### MinIO Configuration

Versioning is enabled when buckets are created:

```python
from minio.commonconfig import ENABLED
from minio.versioningconfig import VersioningConfig

client.set_bucket_versioning(
    "dfs-files", 
    VersioningConfig(ENABLED)
)
```

### Version Listing

Uses MinIO's `list_objects` with `include_version=True`:

```python
objects = client.list_objects(
    bucket_name,
    prefix=object_name,
    recursive=False,
    include_version=True
)
```

### Version Download

Specifies `version_id` in get_object():

```python
response = client.get_object(
    bucket_name,
    object_name,
    version_id=version_id
)
```

## Storage Considerations

### Space Usage
- Each version consumes storage space
- Recommend periodic cleanup of old versions
- Consider retention policies (e.g., keep last 10 versions)

### Performance
- Listing versions is fast (metadata only)
- Downloading specific version has no overhead
- Deleting versions frees up storage immediately

## Best Practices

1. **Version Retention Policy**
   - Keep last N versions (e.g., 10)
   - Delete versions older than X days (e.g., 90 days)
   - Archive important versions before deletion

2. **Version Documentation**
   - Add comments/metadata when uploading new versions
   - Track why changes were made
   - Document breaking changes between versions

3. **Storage Monitoring**
   - Monitor total storage usage
   - Track version count per file
   - Alert when storage exceeds threshold

4. **Rollback Procedure**
   - Test old versions before promoting
   - Keep audit log of version changes
   - Document rollback steps

## API Testing

### Using cURL

```bash
# List versions
curl http://localhost:8000/api/files/1/versions

# Download version
curl -O -J http://localhost:8000/api/files/1/versions/xyz789/download

# Delete version
curl -X DELETE http://localhost:8000/api/files/1/versions/abc456
```

### Using Python Requests

```python
import requests

# List versions
versions = requests.get('http://localhost:8000/api/files/1/versions').json()

# Download specific version
file_data = requests.get(
    'http://localhost:8000/api/files/1/versions/xyz789/download'
).content

# Delete version
result = requests.delete(
    'http://localhost:8000/api/files/1/versions/abc456'
).json()
```

## Troubleshooting

### Versioning Not Working
**Issue**: New uploads overwrite instead of creating versions

**Solution**: Ensure versioning is enabled
```python
# Check versioning status
from minio import Minio
client = Minio('minio1:9000', ...)
config = client.get_bucket_versioning('dfs-files')
print(config.status)  # Should be "Enabled"
```

### Cannot List Versions
**Issue**: API returns empty version list

**Solution**: Check object exists and versioning was enabled before uploads

### Version Download Fails
**Issue**: 404 error when downloading version

**Solution**: Verify version_id is correct (get from list_object_versions)

## Future Enhancements

- [ ] Version comparison (diff between versions)
- [ ] Batch version operations
- [ ] Version restore endpoint
- [ ] Automated version cleanup policies
- [ ] Version metadata/comments
- [ ] Version size optimization (delta storage)

---

**Version**: 1.2.0  
**Date**: November 26, 2025  
**Branch**: feat/minio-versioning
