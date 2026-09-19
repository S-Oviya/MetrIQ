"""
MetrIQ P5 File Storage Service
==============================
Person 5: Workflow + Evidence Engineer

Local file storage abstraction with:
- SHA-256 checksum computation
- Path traversal prevention
- Filename sanitization
- Relative storage references (no internal system absolute paths leaked)
"""

import hashlib
import os
import re
import shutil
import threading
from typing import Optional, Tuple


class StorageSecurityError(ValueError):
    """Raised when an unsafe file path or path traversal attempt is detected."""
    pass


class FileStorageService:
    """
    Thread-safe local filesystem storage service for evidence and attachment files.
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        if base_dir:
            self.base_dir = os.path.abspath(base_dir)
        else:
            # Default to backend/data/evidence directory
            pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.base_dir = os.path.abspath(os.path.join(pkg_dir, "..", "data", "evidence"))
        os.makedirs(self.base_dir, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitizes an untrusted user-supplied filename:
        - Strips path separators and directory navigation (.., /, \\)
        - Removes null bytes and control characters
        - Normalizes to safe alphanumeric characters, dashes, underscores, and dots.
        """
        if not filename:
            return "attachment.bin"
        # Take basename only
        clean = os.path.basename(filename.strip().replace("\\", "/"))
        # Remove null bytes and control characters
        clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", clean)
        # Strip directory traversal sequences
        clean = clean.replace("..", "").strip()
        # Filter dangerous characters, keeping letters, numbers, dot, dash, underscore
        clean = re.sub(r"[^A-Za-z0-9._-]", "_", clean)
        # Avoid hidden files starting with dot
        clean = clean.lstrip(".")
        if not clean:
            return "attachment.bin"
        return clean

    def _resolve_safe_path(self, storage_reference: str) -> str:
        """
        Resolves a storage reference to a physical path,
        strictly verifying that it resides within base_dir (preventing path traversal).
        """
        # Normalize forward/backward slashes
        clean_ref = storage_reference.strip().replace("\\", "/").lstrip("/")
        target_path = os.path.abspath(os.path.join(self.base_dir, clean_ref))
        try:
            common = os.path.commonpath([target_path, self.base_dir])
        except ValueError:
            raise StorageSecurityError(f"Invalid storage reference: '{storage_reference}'. Path traversal detected.")

        if common != self.base_dir:
            raise StorageSecurityError(f"Access denied: path '{storage_reference}' escapes storage root.")

        return target_path

    def compute_checksum(self, content: bytes) -> str:
        """Computes reproducible SHA-256 hexadecimal digest of content."""
        return hashlib.sha256(content).hexdigest()

    def save_file(
        self,
        job_id: str,
        evidence_id: str,
        filename: str,
        content: bytes,
    ) -> Tuple[str, int, str]:
        """
        Saves file content to disk under job folder.
        Returns: (storage_reference, file_size, checksum_sha256)
        """
        with self._lock:
            safe_name = self.sanitize_filename(filename)
            clean_job = self.sanitize_filename(job_id)
            clean_ev_id = self.sanitize_filename(evidence_id)

            relative_ref = f"{clean_job}/{clean_ev_id}_{safe_name}"
            full_path = self._resolve_safe_path(relative_ref)

            # Ensure job directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)

            with open(full_path, "wb") as f:
                f.write(content)

            file_size = len(content)
            checksum = self.compute_checksum(content)

            return relative_ref, file_size, checksum

    def read_file(self, storage_reference: str) -> bytes:
        """Reads file content given its storage reference."""
        full_path = self._resolve_safe_path(storage_reference)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"Storage reference '{storage_reference}' does not exist on disk.")
        with open(full_path, "rb") as f:
            return f.read()

    def delete_file(self, storage_reference: str) -> bool:
        """Deletes file from disk if it exists."""
        with self._lock:
            try:
                full_path = self._resolve_safe_path(storage_reference)
                if os.path.isfile(full_path):
                    os.remove(full_path)
                    return True
                return False
            except Exception:
                return False

    def file_exists(self, storage_reference: str) -> bool:
        """Checks if a storage reference exists on disk."""
        try:
            full_path = self._resolve_safe_path(storage_reference)
            return os.path.isfile(full_path)
        except StorageSecurityError:
            return False

    def clear(self) -> None:
        """Cleans up files in storage base directory (for test isolation)."""
        with self._lock:
            if os.path.isdir(self.base_dir):
                for item in os.listdir(self.base_dir):
                    item_path = os.path.join(self.base_dir, item)
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path, ignore_errors=True)
                    elif os.path.isfile(item_path):
                        try:
                            os.remove(item_path)
                        except OSError:
                            pass


# Global singleton storage service
FILE_STORAGE_SERVICE = FileStorageService()
