"""
File validation service for document uploads.
"""

import os
import magic
from pathlib import Path
from typing import List, Tuple

from fastapi import UploadFile
from app.schemas.document import (
    ALLOWED_EXTENSIONS, 
    ALLOWED_MIME_TYPES, 
    MAX_FILE_SIZE, 
    MIN_FILE_SIZE,
    FileValidationError
)


class FileValidator:
    """Service for validating uploaded files."""
    
    @staticmethod
    def validate_file(file: UploadFile) -> Tuple[bool, List[FileValidationError]]:
        """
        Validate an uploaded file for security and format compliance.
        
        Args:
            file: The uploaded file to validate
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        # Check if file exists and has content
        if not file or not file.filename:
            errors.append(FileValidationError(
                field="file",
                message="No file provided",
                code="FILE_MISSING"
            ))
            return False, errors
        
        # Validate filename
        filename_errors = FileValidator._validate_filename(file.filename)
        errors.extend(filename_errors)
        
        # Validate file size
        size_errors = FileValidator._validate_file_size(file)
        errors.extend(size_errors)
        
        # Validate file extension
        extension_errors = FileValidator._validate_extension(file.filename)
        errors.extend(extension_errors)
        
        # Validate MIME type
        mime_errors = FileValidator._validate_mime_type(file)
        errors.extend(mime_errors)
        
        # Check for malicious content (basic security check)
        security_errors = FileValidator._validate_security(file)
        errors.extend(security_errors)
        
        return len(errors) == 0, errors
    
    @staticmethod
    def _validate_filename(filename: str) -> List[FileValidationError]:
        """Validate filename for security and format."""
        errors = []
        
        # Check for empty filename
        if not filename or filename.strip() == "":
            errors.append(FileValidationError(
                field="filename",
                message="Filename cannot be empty",
                code="FILENAME_EMPTY"
            ))
            return errors
        
        # Check filename length
        if len(filename) > 255:
            errors.append(FileValidationError(
                field="filename",
                message="Filename too long (max 255 characters)",
                code="FILENAME_TOO_LONG"
            ))
        
        # Check for dangerous characters
        dangerous_chars = ['<', '>', ':', '"', '|', '?', '*', '\0']
        if any(char in filename for char in dangerous_chars):
            errors.append(FileValidationError(
                field="filename",
                message="Filename contains invalid characters",
                code="FILENAME_INVALID_CHARS"
            ))
        
        # Check for path traversal attempts
        if '..' in filename or filename.startswith('/') or '\\' in filename:
            errors.append(FileValidationError(
                field="filename",
                message="Filename contains path traversal characters",
                code="FILENAME_PATH_TRAVERSAL"
            ))
        
        return errors
    
    @staticmethod
    def _validate_file_size(file: UploadFile) -> List[FileValidationError]:
        """Validate file size."""
        errors = []
        
        # Get file size
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        if file_size < MIN_FILE_SIZE:
            errors.append(FileValidationError(
                field="file_size",
                message="File is empty",
                code="FILE_EMPTY"
            ))
        
        if file_size > MAX_FILE_SIZE:
            errors.append(FileValidationError(
                field="file_size",
                message=f"File too large (max {MAX_FILE_SIZE // (1024*1024)}MB)",
                code="FILE_TOO_LARGE"
            ))
        
        return errors
    
    @staticmethod
    def _validate_extension(filename: str) -> List[FileValidationError]:
        """Validate file extension."""
        errors = []
        
        file_ext = Path(filename).suffix.lower()
        
        if not file_ext:
            errors.append(FileValidationError(
                field="extension",
                message="File must have an extension",
                code="EXTENSION_MISSING"
            ))
        elif file_ext not in ALLOWED_EXTENSIONS:
            errors.append(FileValidationError(
                field="extension",
                message=f"File type not supported. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
                code="EXTENSION_NOT_ALLOWED"
            ))
        
        return errors
    
    @staticmethod
    def _validate_mime_type(file: UploadFile) -> List[FileValidationError]:
        """Validate MIME type using python-magic."""
        errors = []
        
        try:
            # Read first 2048 bytes for MIME detection
            file.file.seek(0)
            file_header = file.file.read(2048)
            file.file.seek(0)
            
            # Detect MIME type
            detected_mime = magic.from_buffer(file_header, mime=True)
            
            # Check if detected MIME type is allowed
            if detected_mime not in ALLOWED_MIME_TYPES:
                # Special case for markdown files (often detected as text/plain)
                file_ext = Path(file.filename).suffix.lower()
                if file_ext in ['.md', '.markdown'] and detected_mime == 'text/plain':
                    # Allow markdown files detected as text/plain
                    pass
                else:
                    errors.append(FileValidationError(
                        field="mime_type",
                        message=f"File type not supported. Detected: {detected_mime}",
                        code="MIME_TYPE_NOT_ALLOWED"
                    ))
        
        except Exception as e:
            errors.append(FileValidationError(
                field="mime_type",
                message=f"Could not detect file type: {str(e)}",
                code="MIME_DETECTION_FAILED"
            ))
        
        return errors
    
    @staticmethod
    def _validate_security(file: UploadFile) -> List[FileValidationError]:
        """Basic security validation."""
        errors = []
        
        try:
            # Read first 1024 bytes for security checks
            file.file.seek(0)
            file_header = file.file.read(1024)
            file.file.seek(0)
            
            # Check for executable signatures (basic malware detection)
            executable_signatures = [
                b'MZ',  # Windows PE
                b'\x7fELF',  # Linux ELF
                b'\xca\xfe\xba\xbe',  # Java class
                b'PK\x03\x04',  # ZIP (could contain executables)
            ]
            
            for signature in executable_signatures:
                if file_header.startswith(signature):
                    # Allow ZIP for DOCX files
                    if signature == b'PK\x03\x04' and file.filename.lower().endswith('.docx'):
                        continue
                    
                    errors.append(FileValidationError(
                        field="security",
                        message="File appears to be executable or archive",
                        code="SECURITY_EXECUTABLE_DETECTED"
                    ))
                    break
        
        except Exception as e:
            # Don't fail validation on security check errors, just log
            pass
        
        return errors
    
    @staticmethod
    def get_file_info(file: UploadFile) -> dict:
        """Get detailed file information."""
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        
        try:
            file_header = file.file.read(2048)
            file.file.seek(0)
            detected_mime = magic.from_buffer(file_header, mime=True)
        except:
            detected_mime = file.content_type or "application/octet-stream"
        
        return {
            "filename": file.filename,
            "size": file_size,
            "content_type": detected_mime,
            "extension": Path(file.filename).suffix.lower()
        }