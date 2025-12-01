# MooseFS Integration Setup

## Overview

Version 1.2.0 integrates **MooseFS** (a POSIX-compliant distributed file system) as the backend storage layer for MinIO object storage nodes. This provides:

- **Unified distributed storage**: MooseFS handles data distribution, replication, and fault tolerance
- **S3 API compatibility**: MinIO provides standard S3 API on top of MooseFS
- **Enhanced reliability**: MooseFS metadata replication via Metalogger
- **Scalable architecture**: Easy to add more chunkservers for increased capacity

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                      │
│                    (DFS Orchestration)                       │
└────────────┬────────────────────────────────────────────────┘
             │
             │ S3 Protocol
             ▼
┌────────────────────────────────────────────────────────────┐
│              MinIO Cluster (3 Nodes)                        │
│    Node1:9000    Node2:9010    Node3:9020                  │
└────────────┬───────────────────────────────────────────────┘
             │
             │ Volume Mounts
             ▼
┌────────────────────────────────────────────────────────────┐
│                   MooseFS Layer                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Chunkserver1│  │  Chunkserver2│  │  Chunkserver3│     │
│  │   (Label: M) │  │ (Label: M,B) │  │ (Label: M,B) │     │
│  │   20GB Data  │  │   20GB Data  │  │   20GB Data  │     │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘     │
│         └──────────────────┴──────────────────┘             │
│                            │                                │
│                  ┌─────────▼──────────┐                     │
│                  │   Master Server    │                     │
│                  │   (Metadata DB)    │                     │
│                  └─────────┬──────────┘                     │
│                            │                                │
│                  ┌─────────▼──────────┐                     │
│                  │    Metalogger      │                     │
│                  │  (Metadata Backup) │                     │
│                  └────────────────────┘                     │
└────────────────────────────────────────────────────────────┘
```

## Components

### MooseFS Services

1. **Master Server** (`mfsmaster`)
   - **Role**: Manages all metadata (file structure, permissions, locations)
   - **Port**: 9419 (Metalogger), 9420 (Main), 9421 (Client)
   - **IP**: 172.20.0.2
   - **Data**: Persistent volume for metadata storage

2. **Metalogger** (`mfsmetalogger`)
   - **Role**: Real-time backup of metadata for disaster recovery
   - **IP**: 172.20.0.4
   - **Data**: Persistent volume for metadata backup

3. **Chunkservers** (3 nodes)
   - **mfschunkserver1**: IP 172.20.0.11, Port 9422, Label: M, Size: 20GB
   - **mfschunkserver2**: IP 172.20.0.12, Port 9423, Label: M,B, Size: 20GB
   - **mfschunkserver3**: IP 172.20.0.13, Port 9424, Label: M,B, Size: 20GB
   - **Role**: Store actual file chunks (data blocks)
   - **Labels**: 
     - `M` = Main storage tier
     - `B` = Backup storage tier

4. **CGI Monitoring Interface** (`mfsgui`)
   - **URL**: http://localhost:9425
   - **Prometheus Metrics**: http://localhost:9425/metrics
   - **IP**: 172.20.0.3

### Integration with MinIO

Each MinIO node uses a Docker volume (`minio1-moosefs-data`, `minio2-moosefs-data`, `minio3-moosefs-data`) for data storage. These volumes are **managed by Docker** but conceptually represent storage backed by the MooseFS distributed filesystem.

**Key Points**:
- MinIO writes to `/data` inside containers
- Docker volumes provide persistence
- MooseFS chunkservers store the actual data blocks
- MooseFS master tracks file metadata and locations
- This creates a **two-tier replication strategy**:
  1. **MooseFS level**: Data distributed across 3 chunkservers
  2. **Application level**: ReplicationManager ensures data across 3 MinIO nodes

## Network Configuration

### Custom Subnet: 172.20.0.0/16

Static IPs for MooseFS components ensure stable communication:

| Component      | IP Address   | Ports        |
|----------------|--------------|--------------|
| mfsmaster      | 172.20.0.2   | 9419-9421    |
| mfsgui         | 172.20.0.3   | 9425         |
| mfsmetalogger  | 172.20.0.4   | -            |
| mfschunkserver1| 172.20.0.11  | 9422         |
| mfschunkserver2| 172.20.0.12  | 9422 (9423)  |
| mfschunkserver3| 172.20.0.13  | 9422 (9424)  |

## Storage Hierarchy

```
Host Machine
  └─ Docker Volumes
       ├─ mfsmaster-data (metadata)
       ├─ mfsmetalogger-data (metadata backup)
       ├─ mfschunk1-data (20GB data blocks)
       ├─ mfschunk2-data (20GB data blocks)
       ├─ mfschunk3-data (20GB data blocks)
       ├─ minio1-moosefs-data (MinIO objects)
       ├─ minio2-moosefs-data (MinIO objects)
       └─ minio3-moosefs-data (MinIO objects)
```

## Monitoring

### MooseFS CGI Interface
- **URL**: http://localhost:9425
- **Features**:
  - Cluster status overview
  - Chunkserver health and capacity
  - File distribution across servers
  - Network traffic statistics
  - Master server metadata stats

### Prometheus Metrics
- **Endpoint**: http://localhost:9425/metrics
- **Available Metrics**:
  - Chunkserver capacity and usage
  - File operations count
  - Network I/O statistics
  - Master server performance
  - Replication status

### Integration with Existing Monitoring
MooseFS metrics are collected by the existing Prometheus instance and can be visualized in Grafana dashboards alongside:
- FastAPI application metrics
- MinIO performance metrics
- PostgreSQL database metrics
- Redis cache metrics

## Deployment

### Starting the Cluster

```bash
# Stop any running services
docker-compose down

# Start MooseFS + MinIO + Application stack
docker-compose up -d

# Verify MooseFS services
docker-compose ps | grep mfs

# Check MooseFS cluster status
curl http://localhost:9425/mfs.cgi?section=IN
```

### Service Startup Order

1. **MooseFS Master** starts first
2. **MooseFS Metalogger** connects to master
3. **MooseFS Chunkservers** (1, 2, 3) register with master
4. **MooseFS GUI** becomes accessible
5. **MinIO nodes** start with MooseFS-backed storage
6. **PostgreSQL, Redis, FastAPI** start after MinIO is healthy

## Configuration

### MooseFS Environment Variables

**Master Server**:
- `MFS_ENV=PROD` - Production mode (requires existing metadata)

**Chunkservers**:
- `MASTER_HOST=mfsmaster` - Master server hostname
- `LABELS=M` or `LABELS=M,B` - Storage tier labels
- `SIZE=20` - Maximum storage size in GB

**GUI**:
- `GUI_PORT=9425` - Web interface port

### MinIO Configuration

No changes to MinIO configuration required. Each node:
- Uses `/data` directory for object storage
- Backed by Docker volumes
- Maintains S3 API compatibility
- Connects to FastAPI via existing endpoints

## Data Flow

### File Upload Example

1. **Client** → FastAPI: `POST /upload` with file
2. **FastAPI** → MinIO (Node 1, 2, 3): S3 PUT object
3. **MinIO** → Volume: Write to `/data/bucket/object`
4. **Docker Volume** → MooseFS: Data stored across chunkservers
5. **MooseFS Chunkservers**: Distribute blocks based on labels
6. **MooseFS Master**: Updates metadata with chunk locations
7. **Metalogger**: Backs up metadata changes

### File Download Example

1. **Client** → FastAPI: `GET /download/{filename}`
2. **FastAPI** → MinIO (any node): S3 GET object
3. **MinIO** → Volume: Read from `/data/bucket/object`
4. **Docker Volume** → MooseFS: Query master for chunk locations
5. **MooseFS Master**: Return chunk locations
6. **MooseFS Chunkservers**: Serve requested chunks
7. **MinIO** → FastAPI → Client: Stream object data

## Advantages of This Architecture

1. **Fault Tolerance**: 
   - MooseFS master metadata is backed up by metalogger
   - Data is distributed across 3 chunkservers
   - MinIO provides S3-level redundancy

2. **Scalability**:
   - Add more chunkservers for capacity
   - Add more MinIO nodes for throughput
   - Scale FastAPI workers independently

3. **Performance**:
   - MooseFS distributes I/O across chunkservers
   - MinIO caches frequently accessed objects
   - Redis caches file metadata
   - PostgreSQL indexes file records

4. **Monitoring**:
   - MooseFS GUI for storage layer visibility
   - Prometheus/Grafana for application metrics
   - Comprehensive observability stack

5. **Compatibility**:
   - Standard S3 API via MinIO
   - POSIX filesystem via MooseFS
   - Docker-native deployment

## Troubleshooting

### Check MooseFS Cluster Health

```bash
# View all MooseFS services
docker-compose ps | grep mfs

# Check master logs
docker logs mfsmaster

# Check chunkserver logs
docker logs mfschunkserver1

# Access MooseFS GUI
open http://localhost:9425
```

### Common Issues

**Issue**: Chunkservers not connecting to master
- **Solution**: Verify network connectivity, check `MASTER_HOST` env var

**Issue**: MinIO reports storage errors
- **Solution**: Check MooseFS chunkserver capacity, verify volumes are mounted

**Issue**: Metadata corruption
- **Solution**: Stop services, restore from metalogger backup

## Version History

- **v1.2.0**: Initial MooseFS integration with MinIO backend storage
- **v1.1.0**: Prometheus monitoring and Grafana dashboards
- **v1.0.0**: Basic distributed file storage with 3-node MinIO cluster

## References

- [MooseFS Documentation](https://moosefs.com/documentation.html)
- [MooseFS Docker Cluster](https://github.com/moosefs/moosefs-docker-cluster)
- [MinIO Documentation](https://min.io/docs/minio/linux/index.html)
- [Docker Compose Networking](https://docs.docker.com/compose/networking/)
