"""
Tests for file validation service.
"""

import pytest
from io import BytesIO
from unittest.mock import Mock, patch

from fastapi import UploadFile
from starlette.datastructures import Headers
from app.services.file_validator import FileValidator
from app.schemas.document import ALLOWED_EXTENSIONS, MAX_FILE_SIZE


class TestFileValidator:
    """Test file validation functionality."""

    def create_mock_file(self, filename: str, content: bytes = b"test content", content_type: str = "text/plain"):
        """Helper to create mock UploadFile."""
        file_obj = BytesIO(content)
        return UploadFile(
            filename=filename,
            file=file_obj,
            headers=Headers({"content-type": content_type})
        )
    
    def test_valid_text_file(self):
        """Test validation of valid text file."""
        file = self.create_mock_file("test.txt", b"Hello world", "text/plain")
        
        with patch('magic.from_buffer', return_value="text/plain"):
            is_valid, errors = FileValidator.validate_file(file)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_valid_pdf_file(self):
        """Test validation of valid PDF file."""
        # PDF header signature
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj"
        file = self.create_mock_file("document.pdf", pdf_content, "application/pdf")
        
        with patch('magic.from_buffer', return_value="application/pdf"):
            is_valid, errors = FileValidator.validate_file(file)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_valid_markdown_file(self):
        """Test validation of valid markdown file."""
        md_content = b"# Test Document\n\nThis is a test markdown file."
        file = self.create_mock_file("readme.md", md_content, "text/plain")
        
        with patch('magic.from_buffer', return_value="text/plain"):
            is_valid, errors = FileValidator.validate_file(file)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_missing_file(self):
        """Test validation with no file provided."""
        is_valid, errors = FileValidator.validate_file(None)
        
        assert not is_valid
        assert len(errors) == 1
        assert errors[0].code == "FILE_MISSING"
    
    def test_empty_filename(self):
        """Test validation with empty filename."""
        file = self.create_mock_file("", b"content")

        is_valid, errors = FileValidator.validate_file(file)

        assert not is_valid
        # Empty filename triggers FILE_MISSING since `not file.filename` is True for ""
        assert any(error.code in ("FILENAME_EMPTY", "FILE_MISSING") for error in errors)
    
    def test_filename_too_long(self):
        """Test validation with overly long filename."""
        long_filename = "a" * 300 + ".txt"
        file = self.create_mock_file(long_filename, b"content")
        
        is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "FILENAME_TOO_LONG" for error in errors)
    
    def test_dangerous_filename_characters(self):
        """Test validation with dangerous characters in filename."""
        dangerous_files = [
            "test<script>.txt",
            "test|pipe.txt", 
            'test"quote.txt',
            "test*wildcard.txt"
        ]
        
        for filename in dangerous_files:
            file = self.create_mock_file(filename, b"content")
            is_valid, errors = FileValidator.validate_file(file)
            
            assert not is_valid
            assert any(error.code == "FILENAME_INVALID_CHARS" for error in errors)
    
    def test_path_traversal_filename(self):
        """Test validation with path traversal attempts."""
        traversal_files = [
            "../../../etc/passwd",
            "..\\windows\\system32\\config",
            "/etc/shadow",
            "test/../../../file.txt"
        ]
        
        for filename in traversal_files:
            file = self.create_mock_file(filename, b"content")
            is_valid, errors = FileValidator.validate_file(file)
            
            assert not is_valid
            assert any(error.code == "FILENAME_PATH_TRAVERSAL" for error in errors)
    
    def test_empty_file(self):
        """Test validation with empty file."""
        file = self.create_mock_file("test.txt", b"")
        
        is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "FILE_EMPTY" for error in errors)
    
    def test_file_too_large(self):
        """Test validation with file exceeding size limit."""
        # Create file larger than MAX_FILE_SIZE
        large_content = b"x" * (MAX_FILE_SIZE + 1)
        file = self.create_mock_file("large.txt", large_content)
        
        is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "FILE_TOO_LARGE" for error in errors)
    
    def test_unsupported_extension(self):
        """Test validation with unsupported file extension."""
        file = self.create_mock_file("malware.exe", b"content")
        
        is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "EXTENSION_NOT_ALLOWED" for error in errors)
    
    def test_missing_extension(self):
        """Test validation with missing file extension."""
        file = self.create_mock_file("noextension", b"content")
        
        is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "EXTENSION_MISSING" for error in errors)
    
    def test_unsupported_mime_type(self):
        """Test validation with unsupported MIME type."""
        file = self.create_mock_file("test.txt", b"content")
        
        with patch('magic.from_buffer', return_value="application/x-executable"):
            is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "MIME_TYPE_NOT_ALLOWED" for error in errors)
    
    def test_executable_detection(self):
        """Test detection of executable files."""
        # Windows PE executable signature
        pe_content = b"MZ\x90\x00" + b"x" * 100
        file = self.create_mock_file("test.txt", pe_content)
        
        with patch('magic.from_buffer', return_value="text/plain"):
            is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "SECURITY_EXECUTABLE_DETECTED" for error in errors)
    
    def test_docx_file_allowed(self):
        """Test that DOCX files (ZIP format) are allowed."""
        # ZIP signature (used by DOCX)
        zip_content = b"PK\x03\x04" + b"x" * 100
        file = self.create_mock_file("document.docx", zip_content)
        
        with patch('magic.from_buffer', return_value="application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
            is_valid, errors = FileValidator.validate_file(file)
        
        assert is_valid
        assert len(errors) == 0
    
    def test_get_file_info(self):
        """Test file information extraction."""
        content = b"Test file content"
        file = self.create_mock_file("test.txt", content, "text/plain")
        
        with patch('magic.from_buffer', return_value="text/plain"):
            info = FileValidator.get_file_info(file)
        
        assert info["filename"] == "test.txt"
        assert info["size"] == len(content)
        assert info["content_type"] == "text/plain"
        assert info["extension"] == ".txt"
    
    def test_mime_detection_failure(self):
        """Test handling of MIME detection failures."""
        file = self.create_mock_file("test.txt", b"content")
        
        with patch('magic.from_buffer', side_effect=Exception("Magic failed")):
            is_valid, errors = FileValidator.validate_file(file)
        
        assert not is_valid
        assert any(error.code == "MIME_DETECTION_FAILED" for error in errors)
    
    def test_all_allowed_extensions(self):
        """Test that all allowed extensions pass validation."""
        for ext in ALLOWED_EXTENSIONS:
            filename = f"test{ext}"
            file = self.create_mock_file(filename, b"test content")
            
            # Mock appropriate MIME type for each extension
            mime_map = {
                ".txt": "text/plain",
                ".pdf": "application/pdf", 
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".md": "text/plain",
                ".markdown": "text/plain"
            }
            
            with patch('magic.from_buffer', return_value=mime_map.get(ext, "text/plain")):
                is_valid, errors = FileValidator.validate_file(file)
            
            assert is_valid, f"Extension {ext} should be valid but got errors: {errors}"