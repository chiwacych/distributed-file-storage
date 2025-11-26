"""
Prometheus Metrics for Distributed File Storage System
"""
from prometheus_client import Counter, Histogram, Gauge, Info
import time
from functools import wraps
from typing import Callable


# ============================================================================
# File Operation Metrics
# ============================================================================

# Upload metrics
file_uploads_total = Counter(
    'dfs_file_uploads_total',
    'Total number of file uploads',
    ['status', 'nodes_count']  # status: success/partial/failed, nodes_count: 1/2/3
)

file_upload_duration_seconds = Histogram(
    'dfs_file_upload_duration_seconds',
    'File upload duration in seconds',
    ['nodes_count'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

file_upload_size_bytes = Histogram(
    'dfs_file_upload_size_bytes',
    'File upload size in bytes',
    buckets=[1024, 10240, 102400, 1048576, 10485760, 104857600, 1073741824]  # 1KB to 1GB
)

# Download metrics
file_downloads_total = Counter(
    'dfs_file_downloads_total',
    'Total number of file downloads',
    ['status', 'node']  # status: success/failed, node: minio1/minio2/minio3
)

file_download_duration_seconds = Histogram(
    'dfs_file_download_duration_seconds',
    'File download duration in seconds',
    ['node'],
    buckets=[0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# Delete metrics
file_deletes_total = Counter(
    'dfs_file_deletes_total',
    'Total number of file deletions',
    ['status', 'nodes_count']
)


# ============================================================================
# Replication Metrics
# ============================================================================

replication_syncs_total = Counter(
    'dfs_replication_syncs_total',
    'Total number of replication sync operations',
    ['status']  # status: success/failed/skipped/pending
)

replication_files_synced = Counter(
    'dfs_replication_files_synced',
    'Total number of files synced to nodes',
    ['source_node', 'target_node']
)

replication_duration_seconds = Histogram(
    'dfs_replication_duration_seconds',
    'Replication operation duration in seconds',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0]
)

replication_batch_size = Histogram(
    'dfs_replication_batch_size',
    'Number of files processed in a replication batch',
    buckets=[1, 5, 10, 20, 50, 100]
)

replication_queue_length = Gauge(
    'dfs_replication_queue_length',
    'Number of files waiting to be replicated'
)

replication_status = Gauge(
    'dfs_replication_status',
    'Current replication status (1=syncing, 0=idle)'
)


# ============================================================================
# MinIO Node Health Metrics
# ============================================================================

minio_node_health = Gauge(
    'dfs_minio_node_health',
    'MinIO node health status (1=healthy, 0=unhealthy)',
    ['node']
)

minio_node_files_total = Gauge(
    'dfs_minio_node_files_total',
    'Total number of files on MinIO node',
    ['node']
)

minio_node_storage_bytes = Gauge(
    'dfs_minio_node_storage_bytes',
    'Total storage used on MinIO node in bytes',
    ['node']
)

minio_node_response_time_seconds = Histogram(
    'dfs_minio_node_response_time_seconds',
    'MinIO node response time in seconds',
    ['node', 'operation'],  # operation: stat/get/put/delete
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)


# ============================================================================
# Cache Metrics
# ============================================================================

cache_hits_total = Counter(
    'dfs_cache_hits_total',
    'Total number of cache hits',
    ['cache_type']  # cache_type: metadata/filelist/nodehealth
)

cache_misses_total = Counter(
    'dfs_cache_misses_total',
    'Total number of cache misses',
    ['cache_type']
)

cache_operations_total = Counter(
    'dfs_cache_operations_total',
    'Total number of cache operations',
    ['operation']  # operation: get/set/delete/invalidate
)


# ============================================================================
# Database Metrics
# ============================================================================

db_queries_total = Counter(
    'dfs_db_queries_total',
    'Total number of database queries',
    ['operation', 'table']  # operation: select/insert/update/delete
)

db_query_duration_seconds = Histogram(
    'dfs_db_query_duration_seconds',
    'Database query duration in seconds',
    ['operation'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

db_connections_active = Gauge(
    'dfs_db_connections_active',
    'Number of active database connections'
)


# ============================================================================
# System Metrics
# ============================================================================

system_info = Info(
    'dfs_system',
    'System information'
)

total_files = Gauge(
    'dfs_total_files',
    'Total number of files in the system'
)

total_storage_bytes = Gauge(
    'dfs_total_storage_bytes',
    'Total storage used in bytes'
)

total_users = Gauge(
    'dfs_total_users',
    'Total number of users'
)


# ============================================================================
# API Endpoint Metrics (automatically handled by instrumentator)
# ============================================================================
# These are handled by prometheus-fastapi-instrumentator:
# - http_requests_total
# - http_request_duration_seconds
# - http_requests_in_progress


# ============================================================================
# Helper Functions
# ============================================================================

def track_time(metric: Histogram, labels: dict = None):
    """Decorator to track execution time of a function"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
                raise e
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
                raise e
        
        # Return appropriate wrapper based on whether function is async
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def record_file_upload(status: str, nodes_count: int, duration: float, size_bytes: int):
    """Record file upload metrics"""
    file_uploads_total.labels(status=status, nodes_count=str(nodes_count)).inc()
    file_upload_duration_seconds.labels(nodes_count=str(nodes_count)).observe(duration)
    file_upload_size_bytes.observe(size_bytes)


def record_file_download(status: str, node: str, duration: float):
    """Record file download metrics"""
    file_downloads_total.labels(status=status, node=node).inc()
    file_download_duration_seconds.labels(node=node).observe(duration)


def record_replication_sync(status: str, duration: float = None):
    """Record replication sync metrics"""
    replication_syncs_total.labels(status=status).inc()
    if duration is not None:
        replication_duration_seconds.observe(duration)


def update_node_health(node: str, is_healthy: bool, files_count: int = None, storage_bytes: int = None):
    """Update MinIO node health metrics"""
    minio_node_health.labels(node=node).set(1 if is_healthy else 0)
    if files_count is not None:
        minio_node_files_total.labels(node=node).set(files_count)
    if storage_bytes is not None:
        minio_node_storage_bytes.labels(node=node).set(storage_bytes)


def record_cache_operation(operation_type: str, cache_type: str, hit: bool = None):
    """Record cache operation metrics"""
    cache_operations_total.labels(operation=operation_type).inc()
    if hit is not None:
        if hit:
            cache_hits_total.labels(cache_type=cache_type).inc()
        else:
            cache_misses_total.labels(cache_type=cache_type).inc()


def initialize_system_info():
    """Initialize system information metrics"""
    system_info.info({
        'version': '1.1.0',
        'name': 'Distributed File Storage System',
        'replication_factor': '3',
        'batch_size': '5'
    })
