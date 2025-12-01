# Prometheus Monitoring & Grafana Dashboards

## Overview

This distributed file storage system includes comprehensive monitoring using **Prometheus** for metrics collection and **Grafana** for visualization.

## Components

### 1. Prometheus
- **Port:** 9090
- **URL:** http://localhost:9090
- **Configuration:** `prometheus.yml`
- **Scrape Interval:** 10-30 seconds depending on target

### 2. Grafana
- **Port:** 3000
- **URL:** http://localhost:3000
- **Default Credentials:**
  - Username: `admin`
  - Password: `admin123`

### 3. Exporters
- **Redis Exporter:** Port 9121
- **PostgreSQL Exporter:** Port 9187
- **MinIO Metrics:** Built-in on port 9000

## Available Metrics

### File Operation Metrics

#### Uploads
- `dfs_file_uploads_total` - Total file uploads (labels: status, nodes_count)
- `dfs_file_upload_duration_seconds` - Upload duration histogram
- `dfs_file_upload_size_bytes` - Upload size histogram

#### Downloads
- `dfs_file_downloads_total` - Total file downloads (labels: status, node)
- `dfs_file_download_duration_seconds` - Download duration histogram

#### Deletes
- `dfs_file_deletes_total` - Total file deletions (labels: status, nodes_count)

### Replication Metrics
- `dfs_replication_syncs_total` - Total sync operations (labels: status)
- `dfs_replication_files_synced` - Files synced between nodes (labels: source_node, target_node)
- `dfs_replication_duration_seconds` - Replication duration histogram
- `dfs_replication_batch_size` - Batch size histogram
- `dfs_replication_queue_length` - Files waiting to be replicated (gauge)
- `dfs_replication_status` - Current sync status (1=syncing, 0=idle)

### MinIO Node Health Metrics
- `dfs_minio_node_health` - Node health status (labels: node)
- `dfs_minio_node_files_total` - Total files on node (labels: node)
- `dfs_minio_node_storage_bytes` - Storage used on node (labels: node)
- `dfs_minio_node_response_time_seconds` - Node response time histogram

### Cache Metrics
- `dfs_cache_hits_total` - Cache hits (labels: cache_type)
- `dfs_cache_misses_total` - Cache misses (labels: cache_type)
- `dfs_cache_operations_total` - Cache operations (labels: operation)

### Database Metrics
- `dfs_db_queries_total` - Database queries (labels: operation, table)
- `dfs_db_query_duration_seconds` - Query duration histogram
- `dfs_db_connections_active` - Active database connections

### System Metrics
- `dfs_system_info` - System information
- `dfs_total_files` - Total files in system
- `dfs_total_storage_bytes` - Total storage used
- `dfs_total_users` - Total users

### HTTP API Metrics (Auto-instrumented)
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request duration
- `http_requests_in_progress` - Current requests

## Quick Start

### 1. Start All Services
```bash
docker-compose up -d
```

### 2. Access Prometheus
Visit http://localhost:9090 and run queries:

```promql
# Upload success rate
rate(dfs_file_uploads_total{status="success"}[5m])

# Average upload duration
rate(dfs_file_upload_duration_seconds_sum[5m]) / rate(dfs_file_upload_duration_seconds_count[5m])

# Files pending replication
dfs_replication_queue_length

# Cache hit rate
rate(dfs_cache_hits_total[5m]) / (rate(dfs_cache_hits_total[5m]) + rate(dfs_cache_misses_total[5m]))

# Node health status
dfs_minio_node_health
```

### 3. Access Grafana
1. Visit http://localhost:3000
2. Login with `admin` / `admin123`
3. Navigate to Dashboards
4. Create new dashboard or import pre-built ones

## Example Grafana Dashboards

### Dashboard 1: System Overview
**Panels:**
- Total Files & Storage (Single Stat)
- Upload/Download Rate (Graph)
- Node Health Status (Stat)
- Replication Queue (Graph)

### Dashboard 2: Performance Metrics
**Panels:**
- Upload Duration (Heatmap)
- Download Duration (Heatmap)
- API Response Times (Graph)
- Cache Hit Rate (Graph)

### Dashboard 3: Node Health
**Panels:**
- Node Status (Stat with Thresholds)
- Files per Node (Bar Gauge)
- Storage per Node (Bar Gauge)
- Node Response Times (Graph)

### Dashboard 4: Replication Status
**Panels:**
- Replication Queue Length (Graph)
- Sync Operations (Counter)
- Files Synced per Hour (Graph)
- Replication Duration (Heatmap)

## Sample PromQL Queries

### Upload Success Rate (Last 5 Minutes)
```promql
sum(rate(dfs_file_uploads_total{status="success"}[5m])) / sum(rate(dfs_file_uploads_total[5m])) * 100
```

### Average Upload Size
```promql
rate(dfs_file_upload_size_bytes_sum[5m]) / rate(dfs_file_upload_size_bytes_count[5m])
```

### Files Pending Replication
```promql
dfs_replication_queue_length
```

### Cache Hit Ratio
```promql
sum(rate(dfs_cache_hits_total[5m])) / (sum(rate(dfs_cache_hits_total[5m])) + sum(rate(dfs_cache_misses_total[5m]))) * 100
```

### Unhealthy Nodes
```promql
count(dfs_minio_node_health == 0)
```

### Files per Node
```promql
dfs_minio_node_files_total
```

### API Request Rate by Endpoint
```promql
sum(rate(http_requests_total[5m])) by (handler)
```

### 95th Percentile Upload Duration
```promql
histogram_quantile(0.95, rate(dfs_file_upload_duration_seconds_bucket[5m]))
```

## Alerting Rules (Optional)

Create `prometheus_rules.yml`:

```yaml
groups:
  - name: dfs_alerts
    interval: 30s
    rules:
      - alert: NodeUnhealthy
        expr: dfs_minio_node_health == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "MinIO node {{ $labels.node }} is unhealthy"
          
      - alert: HighReplicationQueue
        expr: dfs_replication_queue_length > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High replication queue: {{ $value }} files pending"
          
      - alert: LowCacheHitRate
        expr: |
          sum(rate(dfs_cache_hits_total[5m])) / 
          (sum(rate(dfs_cache_hits_total[5m])) + sum(rate(dfs_cache_misses_total[5m]))) < 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Cache hit rate below 50%"
          
      - alert: HighUploadFailureRate
        expr: |
          sum(rate(dfs_file_uploads_total{status="failed"}[5m])) / 
          sum(rate(dfs_file_uploads_total[5m])) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Upload failure rate above 10%"
```

## Viewing Metrics

### Via Prometheus UI
1. Go to http://localhost:9090
2. Click "Graph"
3. Enter PromQL query
4. View table or graph

### Via Grafana
1. Go to http://localhost:3000
2. Click "Explore" in sidebar
3. Select "Prometheus" datasource
4. Enter PromQL query
5. Run query

### Via API Endpoint
```bash
# View all metrics
curl http://localhost:8000/metrics

# Query Prometheus API
curl 'http://localhost:9090/api/v1/query?query=dfs_total_files'
```

## Troubleshooting

### Prometheus not scraping
- Check `prometheus.yml` configuration
- Verify services are running: `docker-compose ps`
- Check targets in Prometheus UI: http://localhost:9090/targets

### Grafana not showing data
- Verify datasource configuration
- Check Prometheus is running and accessible
- Test query in Prometheus UI first

### Missing metrics
- Check FastAPI is exposing `/metrics` endpoint
- Verify instrumentator is initialized
- Check for import errors in logs

## Best Practices

1. **Set appropriate scrape intervals** - Balance between data granularity and storage
2. **Use recording rules** for complex queries used frequently
3. **Set retention policies** to manage storage:
   ```yaml
   command:
     - '--storage.tsdb.retention.time=30d'
   ```
4. **Monitor the monitors** - Track Prometheus/Grafana performance
5. **Use labels wisely** - Don't create high-cardinality labels
6. **Create alerts** for critical metrics
7. **Document custom dashboards** for team knowledge sharing

## Retention & Storage

Default retention: 15 days

To change:
```yaml
prometheus:
  command:
    - '--storage.tsdb.retention.time=30d'
    - '--storage.tsdb.retention.size=10GB'
```

## Version
**Monitoring Stack Version:** 1.1.0  
**Last Updated:** November 19, 2025
