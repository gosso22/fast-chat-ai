"""
Unit tests for text chunking service.
Tests chunking accuracy, overlap preservation, and metadata tracking.
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, patch

from app.services.text_chunker import (
    TextChunkingService,
    TokenBasedChunker,
    ChunkingOptions,
    ChunkMetadata,
    TextChunk,
    TextChunkingError
)


class TestChunkingOptions:
    """Test ChunkingOptions validation and configuration."""
    
    def test_valid_options(self):
        """Test creating valid chunking options."""
        options = ChunkingOptions(
            chunk_size=800,
            chunk_overlap=150,
            min_chunk_size=50,
            encoding_name="cl100k_base"
        )
        
        assert options.chunk_size == 800
        assert options.chunk_overlap == 150
        assert options.min_chunk_size == 50
        assert options.encoding_name == "cl100k_base"
    
    def test_default_options(self):
        """Test default chunking options."""
        options = ChunkingOptions()
        
        assert options.chunk_size == 1000
        assert options.chunk_overlap == 200
        assert options.min_chunk_size == 50
        assert options.encoding_name == "cl100k_base"
        assert options.preserve_sentences is True
        assert options.preserve_paragraphs is True
    
    def test_invalid_chunk_size(self):
        """Test validation of invalid chunk size."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkingOptions(chunk_size=0)
        
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            ChunkingOptions(chunk_size=-100)
    
    def test_invalid_chunk_overlap(self):
        """Test validation of invalid chunk overlap."""
        with pytest.raises(ValueError, match="chunk_overlap cannot be negative"):
            ChunkingOptions(chunk_overlap=-50)
        
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            ChunkingOptions(chunk_size=500, chunk_overlap=500)
        
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            ChunkingOptions(chunk_size=500, chunk_overlap=600)
    
    def test_invalid_min_chunk_size(self):
        """Test validation of invalid minimum chunk size."""
        with pytest.raises(ValueError, match="min_chunk_size must be positive"):
            ChunkingOptions(min_chunk_size=0)
        
        with pytest.raises(ValueError, match="min_chunk_size cannot be greater than chunk_size"):
            ChunkingOptions(chunk_size=500, min_chunk_size=600)


class TestChunkMetadata:
    """Test ChunkMetadata functionality."""
    
    def test_metadata_creation(self):
        """Test creating chunk metadata."""
        doc_id = uuid4()
        metadata = ChunkMetadata(
            document_id=doc_id,
            chunk_index=0,
            start_position=0,
            end_position=100,
            token_count=50,
            character_count=100,
            has_overlap=False
        )
        
        assert metadata.document_id == doc_id
        assert metadata.chunk_index == 0
        assert metadata.start_position == 0
        assert metadata.end_position == 100
        assert metadata.token_count == 50
        assert metadata.character_count == 100
        assert metadata.has_overlap is False
        assert metadata.overlap_start is None
        assert metadata.overlap_end is None
    
    def test_metadata_with_overlap(self):
        """Test metadata with overlap information."""
        doc_id = uuid4()
        metadata = ChunkMetadata(
            document_id=doc_id,
            chunk_index=1,
            start_position=80,
            end_position=200,
            token_count=75,
            character_count=120,
            has_overlap=True,
            overlap_start=0,
            overlap_end=20
        )
        
        assert metadata.has_overlap is True
        assert metadata.overlap_start == 0
        assert metadata.overlap_end == 20
    
    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        doc_id = uuid4()
        metadata = ChunkMetadata(
            document_id=doc_id,
            chunk_index=0,
            start_position=0,
            end_position=100,
            token_count=50,
            character_count=100,
            has_overlap=False,
            source_info={"test": "value"}
        )
        
        result = metadata.to_dict()
        
        assert result["document_id"] == str(doc_id)
        assert result["chunk_index"] == 0
        assert result["start_position"] == 0
        assert result["end_position"] == 100
        assert result["token_count"] == 50
        assert result["character_count"] == 100
        assert result["has_overlap"] is False
        assert result["source_info"] == {"test": "value"}


class TestTextChunk:
    """Test TextChunk functionality."""
    
    def test_chunk_creation(self):
        """Test creating a text chunk."""
        doc_id = uuid4()
        chunk_id = uuid4()
        metadata = ChunkMetadata(
            document_id=doc_id,
            chunk_index=0,
            start_position=0,
            end_position=20,
            token_count=10,
            character_count=20,
            has_overlap=False
        )
        
        chunk = TextChunk(
            id=chunk_id,
            content="This is a test chunk",
            metadata=metadata
        )
        
        assert chunk.id == chunk_id
        assert chunk.content == "This is a test chunk"
        assert chunk.metadata == metadata
    
    def test_empty_chunk_validation(self):
        """Test validation of empty chunk content."""
        doc_id = uuid4()
        metadata = ChunkMetadata(
            document_id=doc_id,
            chunk_index=0,
            start_position=0,
            end_position=0,
            token_count=0,
            character_count=0,
            has_overlap=False
        )
        
        with pytest.raises(ValueError, match="Chunk content cannot be empty"):
            TextChunk(
                id=uuid4(),
                content="   ",  # Only whitespace
                metadata=metadata
            )


class TestTokenBasedChunker:
    """Test TokenBasedChunker functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.chunker = TokenBasedChunker()
        self.doc_id = uuid4()
    
    def test_token_counting(self):
        """Test token counting functionality."""
        text = "This is a simple test sentence."
        token_count = self.chunker.count_tokens(text)
        
        # Should return a reasonable token count
        assert isinstance(token_count, int)
        assert token_count > 0
        assert token_count < len(text.split()) * 2  # Reasonable upper bound
    
    def test_empty_text_chunking(self):
        """Test chunking empty text raises error."""
        options = ChunkingOptions()
        
        with pytest.raises(TextChunkingError, match="Cannot chunk empty text"):
            self.chunker.chunk_text("", self.doc_id, options)
        
        with pytest.raises(TextChunkingError, match="Cannot chunk empty text"):
            self.chunker.chunk_text("   ", self.doc_id, options)
    
    def test_small_text_single_chunk(self):
        """Test chunking small text creates single chunk."""
        text = "This is a short text that should fit in one chunk."
        options = ChunkingOptions(chunk_size=1000, chunk_overlap=200)
        
        chunks = self.chunker.chunk_text(text, self.doc_id, options)
        
        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].metadata.document_id == self.doc_id
        assert chunks[0].metadata.chunk_index == 0
        assert chunks[0].metadata.start_position == 0
        assert chunks[0].metadata.end_position == len(text)
        assert chunks[0].metadata.has_overlap is False
        assert chunks[0].metadata.token_count > 0
        assert chunks[0].metadata.character_count == len(text)
    
    def test_large_text_multiple_chunks(self):
        """Test chunking large text creates multiple chunks."""
        # Create a text that will definitely need multiple chunks
        sentences = [
            "This is the first sentence of a long document.",
            "This is the second sentence with more content.",
            "Here we have the third sentence continuing the text.",
            "The fourth sentence adds even more content to the document.",
            "Fifth sentence keeps building up the content length.",
            "Sixth sentence continues to expand the document size.",
            "Seventh sentence adds more words to reach chunk limits.",
            "Eighth sentence helps ensure we exceed single chunk capacity.",
            "Ninth sentence provides additional content for chunking.",
            "Tenth sentence completes our test document content."
        ]
        text = " ".join(sentences)
        
        # Use small chunk size to force multiple chunks
        options = ChunkingOptions(chunk_size=50, chunk_overlap=10, min_chunk_size=5)
        
        chunks = self.chunker.chunk_text(text, self.doc_id, options)
        
        # Should create multiple chunks
        assert len(chunks) > 1
        
        # Verify chunk properties
        for i, chunk in enumerate(chunks):
            assert chunk.metadata.document_id == self.doc_id
            assert chunk.metadata.chunk_index == i
            assert chunk.metadata.token_count > 0
            assert chunk.metadata.character_count > 0
            assert len(chunk.content.strip()) > 0
            
            # Check overlap (except for first chunk)
            if i > 0:
                assert chunk.metadata.has_overlap is True
            else:
                assert chunk.metadata.has_overlap is False
    
    def test_chunk_overlap_functionality(self):
        """Test that chunk overlap preserves context continuity."""
        # Create text with clear sentence boundaries
        text = "First sentence here. Second sentence follows. Third sentence continues. Fourth sentence ends."
        
        options = ChunkingOptions(chunk_size=20, chunk_overlap=5, min_chunk_size=3)
        
        chunks = self.chunker.chunk_text(text, self.doc_id, options)
        
        if len(chunks) > 1:
            # Check that overlapping chunks share some content
            for i in range(1, len(chunks)):
                current_chunk = chunks[i]
                assert current_chunk.metadata.has_overlap is True
                assert current_chunk.metadata.overlap_start is not None
                assert current_chunk.metadata.overlap_end is not None
    
    def test_chunk_metadata_accuracy(self):
        """Test accuracy of chunk metadata."""
        text = "This is a test document with multiple sentences. Each sentence should be processed correctly."
        options = ChunkingOptions(chunk_size=100, chunk_overlap=10, min_chunk_size=20)
        
        chunks = self.chunker.chunk_text(text, self.doc_id, options)
        
        for chunk in chunks:
            # Verify metadata consistency
            assert chunk.metadata.character_count == len(chunk.content)
            assert chunk.metadata.end_position > chunk.metadata.start_position
            assert chunk.metadata.token_count > 0
            
            # Verify source info
            assert "chunking_method" in chunk.metadata.source_info
            assert "encoding" in chunk.metadata.source_info
            assert "chunk_size" in chunk.metadata.source_info
            assert "chunk_overlap" in chunk.metadata.source_info
    
    def test_sentence_splitting(self):
        """Test sentence splitting functionality."""
        text = "First sentence. Second sentence! Third sentence? Fourth sentence."
        sentences = self.chunker._split_into_sentences(text)
        
        # Should split into multiple sentences
        assert len(sentences) > 1
        assert all(s.strip() for s in sentences)  # No empty sentences
    
    def test_overlap_text_extraction(self):
        """Test overlap text extraction."""
        chunk_text = "This is a longer chunk of text that will be used for overlap testing."
        options = ChunkingOptions(chunk_overlap=10)
        
        overlap_text = self.chunker._get_overlap_text(chunk_text, options)
        
        assert len(overlap_text) > 0
        assert len(overlap_text) < len(chunk_text)
        # Overlap should be from the end of the original text
        assert chunk_text.endswith(overlap_text) or overlap_text in chunk_text


class TestTextChunkingService:
    """Test TextChunkingService functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = TextChunkingService()
        self.doc_id = uuid4()
    
    def test_service_initialization(self):
        """Test service initialization."""
        service = TextChunkingService()
        assert service.chunker is not None
        assert isinstance(service.chunker, TokenBasedChunker)
        
        # Test with custom chunker
        custom_chunker = Mock()
        service = TextChunkingService(chunker=custom_chunker)
        assert service.chunker == custom_chunker
    
    def test_chunk_document_text_valid_params(self):
        """Test chunking with valid parameters."""
        text = "This is a test document that will be chunked into smaller pieces for processing."
        
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=800,
            chunk_overlap=150
        )
        
        assert len(chunks) >= 1
        assert all(isinstance(chunk, TextChunk) for chunk in chunks)
        assert all(chunk.metadata.document_id == self.doc_id for chunk in chunks)
    
    def test_chunk_document_text_invalid_chunk_size(self):
        """Test chunking with invalid chunk size."""
        text = "Test text"
        
        # Too small
        with pytest.raises(ValueError, match="chunk_size must be between 500 and 1000 tokens"):
            self.service.chunk_document_text(
                text=text,
                document_id=self.doc_id,
                chunk_size=400,
                chunk_overlap=150
            )
        
        # Too large
        with pytest.raises(ValueError, match="chunk_size must be between 500 and 1000 tokens"):
            self.service.chunk_document_text(
                text=text,
                document_id=self.doc_id,
                chunk_size=1200,
                chunk_overlap=150
            )
    
    def test_chunk_document_text_invalid_overlap(self):
        """Test chunking with invalid overlap."""
        text = "Test text"
        
        # Too small
        with pytest.raises(ValueError, match="chunk_overlap must be between 100 and 200 tokens"):
            self.service.chunk_document_text(
                text=text,
                document_id=self.doc_id,
                chunk_size=800,
                chunk_overlap=50
            )
        
        # Too large
        with pytest.raises(ValueError, match="chunk_overlap must be between 100 and 200 tokens"):
            self.service.chunk_document_text(
                text=text,
                document_id=self.doc_id,
                chunk_size=800,
                chunk_overlap=250
            )
    
    def test_count_tokens(self):
        """Test token counting through service."""
        text = "This is a test sentence for token counting."
        token_count = self.service.count_tokens(text)
        
        assert isinstance(token_count, int)
        assert token_count > 0
    
    def test_get_chunk_statistics_empty(self):
        """Test statistics for empty chunk list."""
        stats = self.service.get_chunk_statistics([])
        
        expected = {
            "total_chunks": 0,
            "total_tokens": 0,
            "total_characters": 0,
            "average_tokens_per_chunk": 0,
            "chunks_with_overlap": 0,
            "overlap_percentage": 0
        }
        
        assert stats == expected
    
    def test_get_chunk_statistics_with_chunks(self):
        """Test statistics calculation with actual chunks."""
        text = "This is a longer test document that should be split into multiple chunks for testing purposes. " * 10
        
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=500,
            chunk_overlap=100
        )
        
        stats = self.service.get_chunk_statistics(chunks)
        
        assert stats["total_chunks"] == len(chunks)
        assert stats["total_tokens"] > 0
        assert stats["total_characters"] > 0
        assert stats["average_tokens_per_chunk"] > 0
        assert 0 <= stats["overlap_percentage"] <= 100
        
        if len(chunks) > 1:
            assert stats["chunks_with_overlap"] > 0
            assert stats["overlap_percentage"] > 0


class TestChunkingIntegration:
    """Integration tests for the complete chunking pipeline."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = TextChunkingService()
        self.doc_id = uuid4()
    
    def test_requirements_compliance_chunk_size(self):
        """Test compliance with requirement 2.1 - chunk size 500-1000 tokens."""
        text = "This is a test document. " * 200  # Create substantial text
        
        # Test minimum allowed chunk size
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=500,
            chunk_overlap=100
        )
        
        for chunk in chunks:
            assert chunk.metadata.token_count <= 500
        
        # Test maximum allowed chunk size
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=1000,
            chunk_overlap=100
        )
        
        for chunk in chunks:
            assert chunk.metadata.token_count <= 1000
    
    def test_requirements_compliance_overlap(self):
        """Test compliance with requirement 2.1 - overlap 100-200 tokens."""
        text = "This is a test document with multiple sentences. " * 50
        
        # Test minimum allowed overlap
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=800,
            chunk_overlap=100
        )
        
        # Verify overlap exists in multi-chunk scenarios
        if len(chunks) > 1:
            overlap_chunks = [c for c in chunks if c.metadata.has_overlap]
            assert len(overlap_chunks) > 0
        
        # Test maximum allowed overlap
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=800,
            chunk_overlap=200
        )
        
        if len(chunks) > 1:
            overlap_chunks = [c for c in chunks if c.metadata.has_overlap]
            assert len(overlap_chunks) > 0
    
    def test_requirements_compliance_metadata_tracking(self):
        """Test compliance with requirement 2.5 - metadata tracking."""
        text = "This is a test document for metadata tracking. " * 20
        
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=600,
            chunk_overlap=150
        )
        
        for i, chunk in enumerate(chunks):
            # Verify required metadata fields
            assert chunk.metadata.document_id == self.doc_id
            assert chunk.metadata.chunk_index == i
            assert chunk.metadata.start_position >= 0
            assert chunk.metadata.end_position > chunk.metadata.start_position
            assert chunk.metadata.token_count > 0
            assert chunk.metadata.character_count > 0
            assert isinstance(chunk.metadata.has_overlap, bool)
            
            # Verify source info tracking
            assert "chunking_method" in chunk.metadata.source_info
            assert "encoding" in chunk.metadata.source_info
            assert "chunk_size" in chunk.metadata.source_info
            assert "chunk_overlap" in chunk.metadata.source_info
    
    def test_context_continuity_preservation(self):
        """Test that overlap preserves context continuity between chunks."""
        # Create text with clear context that should be preserved
        text = """
        The artificial intelligence revolution is transforming industries worldwide. 
        Machine learning algorithms are becoming increasingly sophisticated, enabling 
        computers to perform tasks that were once thought to be exclusively human. 
        Natural language processing has advanced to the point where AI systems can 
        understand and generate human-like text with remarkable accuracy. This 
        technological advancement is reshaping how we work, communicate, and solve 
        complex problems across various domains.
        """
        
        chunks = self.service.chunk_document_text(
            text=text,
            document_id=self.doc_id,
            chunk_size=600,
            chunk_overlap=150
        )
        
        if len(chunks) > 1:
            # Check that overlapping content exists between consecutive chunks
            for i in range(1, len(chunks)):
                current_chunk = chunks[i]
                previous_chunk = chunks[i-1]
                
                assert current_chunk.metadata.has_overlap is True
                
                # The overlap should preserve some context from the previous chunk
                if current_chunk.metadata.overlap_end:
                    overlap_content = current_chunk.content[:current_chunk.metadata.overlap_end]
                    # Overlap content should appear in or relate to previous chunk
                    assert len(overlap_content.strip()) > 0