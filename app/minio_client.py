from minio import Minio
from minio.error import S3Error
import os
from typing import List, Dict, Optional
import io
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
import urllib3
import threading
import socket


class MinIOCluster:
    """Manage connections to multiple MinIO nodes for redundancy"""
    
    def __init__(self):
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
        
        # Initialize clients for each MinIO node
        self.nodes = {
            "minio1": {
                "endpoint": os.getenv("MINIO1_ENDPOINT", "minio1:9000"),
                "client": None,
                "name": "MinIO Node 1"
            },
            "minio2": {
                "endpoint": os.getenv("MINIO2_ENDPOINT", "minio2:9000"),
                "client": None,
                "name": "MinIO Node 2"
            },
            "minio3": {
                "endpoint": os.getenv("MINIO3_ENDPOINT", "minio3:9000"),
                "client": None,
                "name": "MinIO Node 3"
            }
        }
        
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize MinIO client connections with custom timeout"""
        for node_id, node_info in self.nodes.items():
            try:
                # Create separate HTTP client for each node with VERY aggressive timeout
                http_client = urllib3.PoolManager(
                    timeout=urllib3.Timeout(connect=0.3, read=3.0),  # Very short connect timeout
                    maxsize=5,
                    retries=urllib3.Retry(
                        total=0,  # No retries - fail immediately
                        connect=0,
                        read=0,
                        redirect=0
                    )
                )
                
                client = Minio(
                    node_info["endpoint"],
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=False,  # Set to True if using HTTPS
                    http_client=http_client
                )
                node_info["client"] = client
                print(f"✓ Connected to {node_info['name']} at {node_info['endpoint']}")
            except Exception as e:
                print(f"✗ Failed to connect to {node_info['name']}: {str(e)}")
    
    def ensure_bucket(self, bucket_name: str = "dfs-files"):
        """Ensure bucket exists on all nodes with versioning enabled"""
        results = {}
        for node_id, node_info in self.nodes.items():
            try:
                client = node_info["client"]
                if not client.bucket_exists(bucket_name):
                    client.make_bucket(bucket_name)
                    results[node_id] = f"Bucket '{bucket_name}' created"
                else:
                    results[node_id] = f"Bucket '{bucket_name}' already exists"
                
                # Enable versioning on bucket
                from minio.commonconfig import ENABLED
                from minio.versioningconfig import VersioningConfig
                client.set_bucket_versioning(bucket_name, VersioningConfig(ENABLED))
                results[node_id] += " (versioning enabled)"
            except Exception as e:
                results[node_id] = f"Error: {str(e)}"
        return results
    
    def upload_file_to_all_nodes(
        self, 
        file_data: bytes, 
        object_name: str, 
        bucket_name: str = "dfs-files",
        content_type: str = "application/octet-stream"
    ) -> Dict[str, Dict]:
        """
        Upload file to all MinIO nodes in parallel for redundancy
        Returns status for each node
        """
        results = {}
        file_size = len(file_data)
        
        def upload_to_node(node_id: str, node_info: dict) -> tuple:
            """Helper function to upload to a single node"""
            try:
                client = node_info["client"]
                file_stream = io.BytesIO(file_data)
                
                start_time = datetime.now()
                client.put_object(
                    bucket_name,
                    object_name,
                    file_stream,
                    file_size,
                    content_type=content_type
                )
                upload_time = (datetime.now() - start_time).total_seconds()
                
                return (node_id, {
                    "status": "success",
                    "message": f"Uploaded to {node_info['name']}",
                    "upload_time": upload_time,
                    "endpoint": node_info["endpoint"]
                })
            except Exception as e:
                return (node_id, {
                    "status": "error",
                    "message": str(e),
                    "endpoint": node_info["endpoint"]
                })
        
        # Upload to all nodes in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit upload tasks for all nodes
            future_to_node = {
                executor.submit(upload_to_node, node_id, node_info): node_id
                for node_id, node_info in self.nodes.items()
            }
            
            # Collect results as they complete with aggressive timeout
            try:
                for future in as_completed(future_to_node, timeout=5.0):  # 8s → 5s max
                    try:
                        node_id, result = future.result(timeout=0.3)  # 0.5s → 0.3s per result
                        results[node_id] = result
                    except Exception as e:
                        node_id = future_to_node[future]
                        results[node_id] = {
                            "status": "error",
                            "message": f"Upload timeout or error: {str(e)}",
                            "endpoint": self.nodes[node_id]["endpoint"]
                        }
            except FutureTimeoutError:
                # Handle overall timeout - mark any pending nodes as failed
                for future, node_id in future_to_node.items():
                    if node_id not in results:
                        results[node_id] = {
                            "status": "error",
                            "message": f"Upload timeout after 5s",
                            "endpoint": self.nodes[node_id]["endpoint"]
                        }
        
        return results
    
    def get_file_from_node(
        self, 
        object_name: str, 
        node_id: str = None,
        bucket_name: str = "dfs-files"
    ) -> Optional[bytes]:
        """
        Retrieve file from specified node, or try all nodes if not specified
        """
        nodes_to_try = [node_id] if node_id else list(self.nodes.keys())
        
        for nid in nodes_to_try:
            if nid not in self.nodes:
                continue
                
            try:
                client = self.nodes[nid]["client"]
                response = client.get_object(bucket_name, object_name)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except Exception as e:
                print(f"Failed to get file from {nid}: {str(e)}")
                continue
        
        return None
    
    def check_file_exists_on_nodes(
        self, 
        object_name: str, 
        bucket_name: str = "dfs-files",
        use_threads: bool = True
    ) -> Dict[str, bool]:
        """Check if file exists on each node in parallel
        
        Args:
            use_threads: If False, check sequentially (use when already in thread pool)
        
        Returns:
            Dict with node_id -> True (exists), False (doesn't exist), or None (node offline/unreachable)
        """
        results = {}
        
        def check_file_on_node(node_id: str, node_info: dict) -> tuple:
            """Helper to check file on single node"""
            try:
                client = node_info["client"]
                client.stat_object(bucket_name, object_name)
                return (node_id, True)
            except S3Error as e:
                if e.code == "NoSuchKey":
                    return (node_id, False)  # File confirmed not to exist
                else:
                    # Other S3 errors (connection issues, etc)
                    return (node_id, None)
            except Exception:
                # Network/timeout errors - node is offline
                return (node_id, None)
        
        if not use_threads:
            # Sequential check - for use when already in thread pool
            for node_id, node_info in self.nodes.items():
                node_id, exists = check_file_on_node(node_id, node_info)
                results[node_id] = exists
        else:
            # Check all nodes in parallel (8s timeout handles multiple offline nodes)
            with ThreadPoolExecutor(max_workers=3) as executor:
                future_to_node = {
                    executor.submit(check_file_on_node, node_id, node_info): node_id
                    for node_id, node_info in self.nodes.items()
                }
                
                try:
                    for future in as_completed(future_to_node, timeout=8.0):
                        try:
                            node_id, exists = future.result(timeout=1.0)
                            results[node_id] = exists
                        except Exception:
                            node_id = future_to_node[future]
                            results[node_id] = None  # Node offline/unreachable
                except FutureTimeoutError:
                    # Mark remaining nodes as offline/unreachable
                    for future, node_id in future_to_node.items():
                        if node_id not in results:
                            results[node_id] = None
        
        return results
    
    def delete_file_from_all_nodes(
        self, 
        object_name: str, 
        bucket_name: str = "dfs-files"
    ) -> Dict[str, Dict]:
        """Delete file from all nodes"""
        results = {}
        for node_id, node_info in self.nodes.items():
            try:
                client = node_info["client"]
                client.remove_object(bucket_name, object_name)
                results[node_id] = {
                    "status": "success",
                    "message": "File deleted"
                }
            except Exception as e:
                results[node_id] = {
                    "status": "error",
                    "message": str(e)
                }
        return results
    
    def list_files(
        self, 
        bucket_name: str = "dfs-files",
        node_id: str = "minio1"
    ) -> List[Dict]:
        """List all files from a specific node"""
        try:
            client = self.nodes[node_id]["client"]
            objects = client.list_objects(bucket_name, recursive=True)
            
            files = []
            for obj in objects:
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag
                })
            return files
        except Exception as e:
            print(f"Error listing files from {node_id}: {str(e)}")
            return []
    
    def get_node_health(self) -> Dict[str, Dict]:
        """Check health status of all nodes in parallel"""
        health_status = {}
        
        def check_node_health(node_id: str, node_info: dict) -> tuple:
            """Helper function to check a single node's health"""
            try:
                client = node_info["client"]
                # Try to list buckets as a health check
                client.list_buckets()
                return (node_id, {
                    "healthy": True,
                    "endpoint": node_info["endpoint"],
                    "name": node_info["name"],
                    "message": "Node is operational"
                })
            except Exception as e:
                return (node_id, {
                    "healthy": False,
                    "endpoint": node_info["endpoint"],
                    "name": node_info["name"],
                    "message": str(e)
                })
        
        # Check all nodes in parallel with timeout
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_node = {
                executor.submit(check_node_health, node_id, node_info): node_id
                for node_id, node_info in self.nodes.items()
            }
            
            try:
                for future in as_completed(future_to_node, timeout=2.0):  # Max 2 seconds total
                    try:
                        node_id, health = future.result(timeout=0.5)
                        health_status[node_id] = health
                    except Exception as e:
                        node_id = future_to_node[future]
                        health_status[node_id] = {
                            "healthy": False,
                            "endpoint": self.nodes[node_id]["endpoint"],
                            "name": self.nodes[node_id]["name"],
                            "message": f"Health check timeout: {str(e)}"
                        }
            except FutureTimeoutError:
                # Mark any remaining nodes as unhealthy
                for future, node_id in future_to_node.items():
                    if node_id not in health_status:
                        health_status[node_id] = {
                            "healthy": False,
                            "endpoint": self.nodes[node_id]["endpoint"],
                            "name": self.nodes[node_id]["name"],
                            "message": "Health check timeout after 2s"
                        }
        
        return health_status
    
    def generate_presigned_url(
        self,
        object_name: str,
        bucket_name: str = "dfs-files",
        node_id: str = "minio1",
        expires: timedelta = timedelta(hours=1)
    ) -> Optional[str]:
        """Generate a presigned URL for file download"""
        try:
            client = self.nodes[node_id]["client"]
            url = client.presigned_get_object(bucket_name, object_name, expires=expires)
            return url
        except Exception as e:
            print(f"Error generating presigned URL: {str(e)}")
            return None
    
    def list_object_versions(
        self,
        object_name: str,
        bucket_name: str = "dfs-files",
        node_id: str = "minio1"
    ) -> List[Dict]:
        """List all versions of an object"""
        try:
            client = self.nodes[node_id]["client"]
            versions = []
            
            # Use list_objects with versions=True to get all versions
            objects = client.list_objects(
                bucket_name,
                prefix=object_name,
                recursive=False,
                include_version=True
            )
            
            for obj in objects:
                if obj.object_name == object_name:
                    versions.append({
                        "version_id": obj.version_id,
                        "is_latest": obj.is_latest,
                        "last_modified": obj.last_modified,
                        "size": obj.size,
                        "etag": obj.etag
                    })
            
            # Sort by last_modified descending (newest first)
            versions.sort(key=lambda x: x["last_modified"], reverse=True)
            return versions
        except Exception as e:
            print(f"Error listing object versions: {str(e)}")
            return []
    
    def get_object_version(
        self,
        object_name: str,
        version_id: str,
        bucket_name: str = "dfs-files",
        node_id: str = "minio1"
    ) -> Optional[bytes]:
        """Download a specific version of an object"""
        try:
            client = self.nodes[node_id]["client"]
            response = client.get_object(
                bucket_name,
                object_name,
                version_id=version_id
            )
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            print(f"Error getting object version: {str(e)}")
            return None
    
    def delete_object_version(
        self,
        object_name: str,
        version_id: str,
        bucket_name: str = "dfs-files"
    ) -> Dict[str, str]:
        """Delete a specific version from all nodes"""
        results = {}
        for node_id, node_info in self.nodes.items():
            try:
                client = node_info["client"]
                client.remove_object(
                    bucket_name,
                    object_name,
                    version_id=version_id
                )
                results[node_id] = "Version deleted successfully"
            except Exception as e:
                results[node_id] = f"Error: {str(e)}"
        return results


# Initialize global MinIO cluster
minio_cluster = MinIOCluster()
