"""
Robust Replication Manager
===========================

This module implements a robust, non-blocking replication system with:
- Health-aware replication (only sync to healthy nodes)
- Batch processing to prevent thread pool exhaustion
- Timeout protection on all operations
- Priority-based scheduling (recent uploads first)
- Concurrent processing with proper resource management
"""

import asyncio
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
import logging

from sqlalchemy.orm import Session
from models import FileMetadata, ReplicationStatus
from minio_client import minio_cluster

logger = logging.getLogger(__name__)


class ReplicationManager:
    """Manages file replication across MinIO nodes"""
    
    def __init__(self, max_workers: int = 6):
        """
        Initialize replication manager
        
        Args:
            max_workers: Maximum concurrent replication operations
        """
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="replication")
        self.is_syncing = False
        self._sync_lock = asyncio.Lock()
        
    async def get_nodes_health(self) -> Dict[str, bool]:
        """Get current health status of all nodes (async-safe)"""
        loop = asyncio.get_event_loop()
        health_status = await loop.run_in_executor(
            self.executor,
            minio_cluster.get_node_health
        )
        
        # Convert to simple dict: node_id -> is_healthy
        # health_status is already a dict of {node_id: {healthy: bool, ...}}
        return {
            node_id: info.get("healthy", False)
            for node_id, info in health_status.items()
        }
    
    async def check_file_replication_status(
        self,
        file_obj: FileMetadata,
        timeout: float = 3.0
    ) -> Tuple[Dict[str, Optional[bool]], Dict[str, bool]]:
        """
        Check file existence and node health
        
        Returns:
            (existence_status, health_status)
            - existence_status: {node_id: True/False/None}
            - health_status: {node_id: True/False}
        """
        async def check_existence():
            loop = asyncio.get_event_loop()
            # Call with keyword arguments for clarity
            def check_wrapper():
                return minio_cluster.check_file_exists_on_nodes(
                    object_name=file_obj.object_key,
                    bucket_name="dfs-files",
                    use_threads=False  # Already in executor
                )
            return await loop.run_in_executor(self.executor, check_wrapper)
        
        async def check_health():
            return await self.get_nodes_health()
        
        # Run both checks concurrently
        try:
            existence, health = await asyncio.gather(
                asyncio.wait_for(check_existence(), timeout=timeout),
                asyncio.wait_for(check_health(), timeout=timeout)
            )
            return existence, health
        except asyncio.TimeoutError:
            logger.warning(f"Timeout checking replication status for file {file_obj.id}")
            return {}, {}
        except Exception as e:
            logger.error(f"Error checking replication status for file {file_obj.id}: {str(e)}")
            return {}, {}
    
    def _sync_file_to_node_blocking(
        self,
        file_obj: FileMetadata,
        source_node: str,
        target_node: str,
        db: Session
    ) -> Dict:
        """
        Blocking operation to sync a single file to a node
        
        Returns:
            Dict with status, message, and timing info
        """
        start_time = datetime.now()
        
        try:
            # Get file data from source
            file_data = minio_cluster.get_file_from_node(
                object_name=file_obj.object_key,
                node_id=source_node,
                bucket_name="dfs-files"
            )
            
            if not file_data:
                return {
                    "status": "error",
                    "message": f"Failed to retrieve file from source node {source_node}",
                    "duration": (datetime.now() - start_time).total_seconds()
                }
            
            # Upload to target node
            node_info = minio_cluster.nodes[target_node]
            client = node_info["client"]
            file_stream = io.BytesIO(file_data)
            
            client.put_object(
                "dfs-files",
                file_obj.object_key,
                file_stream,
                len(file_data),
                content_type=file_obj.content_type or "application/octet-stream"
            )
            
            # Update replication status in database
            replication = db.query(ReplicationStatus).filter(
                ReplicationStatus.file_id == file_obj.id,
                ReplicationStatus.node_name == target_node
            ).first()
            
            if replication:
                replication.is_replicated = True
                replication.replication_timestamp = datetime.now()
                replication.checksum = file_obj.checksum
                replication.error_message = None
            else:
                new_replication = ReplicationStatus(
                    file_id=file_obj.id,
                    object_key=file_obj.object_key,
                    node_name=target_node,
                    is_replicated=True,
                    replication_timestamp=datetime.now(),
                    checksum=file_obj.checksum
                )
                db.add(new_replication)
            
            db.commit()
            
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "status": "success",
                "message": f"Synced to {node_info['name']}",
                "duration": duration,
                "size": len(file_data)
            }
            
        except Exception as e:
            db.rollback()
            duration = (datetime.now() - start_time).total_seconds()
            return {
                "status": "error",
                "message": str(e),
                "duration": duration
            }
    
    async def sync_file(
        self,
        file_obj: FileMetadata,
        db: Session,
        timeout: float = 20.0  # Increased to handle multiple offline nodes
    ) -> Dict:
        """
        Sync a single file to all missing healthy nodes
        
        Args:
            file_obj: File metadata object
            db: Database session
            timeout: Maximum time for entire operation
            
        Returns:
            Dict with sync results and statistics
        """
        try:
            # Check file status and node health (10s timeout handles multiple offline nodes)
            existence, health = await self.check_file_replication_status(file_obj, timeout=10.0)
            
            if not existence or not health:
                return {
                    "file_id": file_obj.id,
                    "filename": file_obj.filename,
                    "status": "skipped",
                    "message": "Could not determine replication status",
                    "synced_to": []
                }
            
            # Categorize nodes
            nodes_with_file = [nid for nid, exists in existence.items() if exists is True]
            nodes_without_file = [nid for nid, exists in existence.items() if exists is False]
            healthy_nodes = [nid for nid, is_healthy in health.items() if is_healthy]
            
            # Nodes that need syncing: missing file AND healthy
            targets = [nid for nid in nodes_without_file if nid in healthy_nodes]
            
            if not targets:
                if len(nodes_with_file) == 3:
                    return {
                        "file_id": file_obj.id,
                        "filename": file_obj.filename,
                        "status": "complete",
                        "message": "Fully replicated",
                        "synced_to": []
                    }
                else:
                    return {
                        "file_id": file_obj.id,
                        "filename": file_obj.filename,
                        "status": "pending",
                        "message": f"Waiting for nodes to come online (have: {len(nodes_with_file)}/3)",
                        "synced_to": []
                    }
            
            if not nodes_with_file:
                return {
                    "file_id": file_obj.id,
                    "filename": file_obj.filename,
                    "status": "error",
                    "message": "No source node available",
                    "synced_to": []
                }
            
            # Select source node (prefer healthy ones)
            source_node = nodes_with_file[0]
            for node in nodes_with_file:
                if node in healthy_nodes:
                    source_node = node
                    break
            
            # Sync to target nodes concurrently
            loop = asyncio.get_event_loop()
            sync_tasks = []
            
            for target in targets:
                task = loop.run_in_executor(
                    self.executor,
                    self._sync_file_to_node_blocking,
                    file_obj,
                    source_node,
                    target,
                    db
                )
                sync_tasks.append((target, task))
            
            # Wait for all syncs with timeout
            results = {}
            synced_to = []
            
            try:
                for target, task in sync_tasks:
                    result = await asyncio.wait_for(task, timeout=timeout)
                    results[target] = result
                    if result["status"] == "success":
                        synced_to.append(target)
            except asyncio.TimeoutError:
                logger.warning(f"Timeout syncing file {file_obj.id}")
            
            return {
                "file_id": file_obj.id,
                "filename": file_obj.filename,
                "status": "synced" if synced_to else "failed",
                "message": f"Synced to {len(synced_to)}/{len(targets)} target nodes",
                "synced_to": synced_to,
                "details": results
            }
            
        except Exception as e:
            logger.error(f"Error syncing file {file_obj.id}: {str(e)}")
            return {
                "file_id": file_obj.id,
                "filename": file_obj.filename,
                "status": "error",
                "message": str(e),
                "synced_to": []
            }
    
    async def sync_batch(
        self,
        files: List[FileMetadata],
        db: Session,
        batch_size: int = 5,
        timeout_per_file: float = 15.0
    ) -> Dict:
        """
        Sync multiple files in batches to prevent resource exhaustion
        
        Args:
            files: List of file objects to sync
            db: Database session
            batch_size: Number of files to process concurrently
            timeout_per_file: Maximum time per file operation
            
        Returns:
            Summary of sync operations
        """
        summary = {
            "total": len(files),
            "synced": 0,
            "complete": 0,
            "pending": 0,
            "failed": 0,
            "skipped": 0,
            "details": []
        }
        
        # Process in batches
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            tasks = [self.sync_file(f, db, timeout=timeout_per_file) for f in batch]
            
            # Wait for batch to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    summary["failed"] += 1
                    logger.error(f"Batch sync exception: {str(result)}")
                else:
                    status = result.get("status", "error")
                    if status == "synced":
                        summary["synced"] += 1
                    elif status == "complete":
                        summary["complete"] += 1
                    elif status == "pending":
                        summary["pending"] += 1
                    elif status == "skipped":
                        summary["skipped"] += 1
                    else:
                        summary["failed"] += 1
                    
                    summary["details"].append(result)
        
        return summary
    
    async def sync_all(
        self,
        db: Session,
        priority_recent: bool = True,
        max_age_hours: Optional[int] = None
    ) -> Dict:
        """
        Sync all incomplete replications
        
        Args:
            db: Database session
            priority_recent: If True, sync recent uploads first
            max_age_hours: Only sync files uploaded within this many hours (None = all)
            
        Returns:
            Detailed sync summary
        """
        # Import metrics here to avoid circular imports
        from metrics import record_replication_sync, replication_status, replication_queue_length
        
        # Prevent concurrent sync operations
        if self.is_syncing:
            return {
                "status": "busy",
                "message": "Sync operation already in progress"
            }
        
        async with self._sync_lock:
            self.is_syncing = True
            replication_status.set(1)  # Mark as syncing
            sync_start_time = datetime.now()
            
            try:
                # Query files
                query = db.query(FileMetadata).filter(FileMetadata.is_deleted == False)
                
                if max_age_hours:
                    cutoff = datetime.now() - timedelta(hours=max_age_hours)
                    query = query.filter(FileMetadata.upload_timestamp >= cutoff)
                
                if priority_recent:
                    query = query.order_by(FileMetadata.upload_timestamp.desc())
                
                files = query.all()
                
                # Update queue length metric
                replication_queue_length.set(len(files))
                
                if not files:
                    duration = (datetime.now() - sync_start_time).total_seconds()
                    record_replication_sync("skipped", duration)
                    return {
                        "status": "success",
                        "message": "No files to sync",
                        "summary": {
                            "total": 0,
                            "synced": 0,
                            "complete": 0,
                            "pending": 0,
                            "failed": 0,
                            "skipped": 0,
                            "details": []
                        }
                    }
                
                # Sync in batches
                summary = await self.sync_batch(files, db, batch_size=5, timeout_per_file=15.0)
                
                # Record metrics
                duration = (datetime.now() - sync_start_time).total_seconds()
                if summary['synced'] > 0:
                    record_replication_sync("success", duration)
                else:
                    record_replication_sync("complete", duration)
                
                # Update queue length to pending files
                replication_queue_length.set(summary['pending'])
                
                return {
                    "status": "success",
                    "message": f"Sync completed: {summary['synced']} files synced, {summary['complete']} already complete",
                    "summary": summary
                }
                
            except Exception as e:
                duration = (datetime.now() - sync_start_time).total_seconds()
                record_replication_sync("failed", duration)
                raise
            finally:
                self.is_syncing = False
                replication_status.set(0)  # Mark as idle


# Global replication manager instance
replication_manager = ReplicationManager(max_workers=6)
