"""
Text chunking service with overlap strategy for RAG applications.
Implements configurable token limits and overlap functionality to preserve context continuity.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from uuid import uuid4, UUID

import tiktoken

logger = logging.getLogger(__name__)


@dataclass
class ChunkingOptions:
    """Configuration options for text chunking."""
    
    chunk_size: int = 1000  # Maximum tokens per chunk
    chunk_overlap: int = 200  # Overlap tokens between chunks
    min_chunk_size: int = 50  # Minimum tokens for a valid chunk
    encoding_name: str = "cl100k_base"  # OpenAI's encoding for GPT-3.5/4
    preserve_sentences: bool = True  # Try to break at sentence boundaries
    preserve_paragraphs: bool = True  # Try to break at paragraph boundaries
    
    def __post_init__(self):
        """Validate chunking options."""
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if self.min_chunk_size <= 0:
            raise ValueError("min_chunk_size must be positive")
        if self.min_chunk_size > self.chunk_size:
            raise ValueError("min_chunk_size cannot be greater than chunk_size")


@dataclass
class ChunkMetadata:
    """Metadata for a text chunk."""
    
    document_id: UUID
    chunk_index: int
    start_position: int
    end_position: int
    token_count: int
    character_count: int
    has_overlap: bool
    overlap_start: Optional[int] = None
    overlap_end: Optional[int] = None
    source_info: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "document_id": str(self.document_id),
            "chunk_index": self.chunk_index,
            "start_position": self.start_position,
            "end_position": self.end_position,
            "token_count": self.token_count,
            "character_count": self.character_count,
            "has_overlap": self.has_overlap,
            "overlap_start": self.overlap_start,
            "overlap_end": self.overlap_end,
            "source_info": self.source_info or {}
        }


@dataclass
class TextChunk:
    """A chunk of text with metadata."""
    
    id: UUID
    content: str
    metadata: ChunkMetadata
    
    def __post_init__(self):
        """Validate chunk data."""
        if not self.content.strip():
            raise ValueError("Chunk content cannot be empty")
        if len(self.content) != (self.metadata.end_position - self.metadata.start_position):
            logger.warning(
                f"Chunk {self.id}: content length ({len(self.content)}) doesn't match "
                f"position range ({self.metadata.end_position - self.metadata.start_position})"
            )


class TextChunkingError(Exception):
    """Custom exception for text chunking errors."""
    
    def __init__(self, message: str, document_id: Optional[UUID] = None, original_error: Optional[Exception] = None):
        self.message = message
        self.document_id = document_id
        self.original_error = original_error
        super().__init__(self.message)


class BaseTextChunker(ABC):
    """Abstract base class for text chunkers."""
    
    @abstractmethod
    def chunk_text(
        self,
        text: str,
        document_id: UUID,
        options: ChunkingOptions
    ) -> List[TextChunk]:
        """Chunk text into smaller segments."""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str, encoding_name: str = "cl100k_base") -> int:
        """Count tokens in text."""
        pass


class TokenBasedChunker(BaseTextChunker):
    """Token-based text chunker with overlap strategy."""
    
    def __init__(self):
        self._encodings: Dict[str, tiktoken.Encoding] = {}
    
    def _get_encoding(self, encoding_name: str) -> tiktoken.Encoding:
        """Get or create tiktoken encoding."""
        if encoding_name not in self._encodings:
            try:
                self._encodings[encoding_name] = tiktoken.get_encoding(encoding_name)
            except Exception as e:
                logger.error(f"Failed to load encoding {encoding_name}: {e}")
                # Fallback to default encoding
                self._encodings[encoding_name] = tiktoken.get_encoding("cl100k_base")
        return self._encodings[encoding_name]
    
    def count_tokens(self, text: str, encoding_name: str = "cl100k_base") -> int:
        """Count tokens in text using tiktoken."""
        try:
            encoding = self._get_encoding(encoding_name)
            return len(encoding.encode(text))
        except Exception as e:
            logger.error(f"Failed to count tokens: {e}")
            # Fallback to rough word-based estimation
            return len(text.split()) * 1.3  # Rough approximation
    
    def chunk_text(
        self,
        text: str,
        document_id: UUID,
        options: ChunkingOptions
    ) -> List[TextChunk]:
        """
        Chunk text into segments with overlap strategy.
        
        Args:
            text: The text to chunk
            document_id: ID of the source document
            options: Chunking configuration options
            
        Returns:
            List of TextChunk objects
            
        Raises:
            TextChunkingError: If chunking fails
        """
        try:
            if not text.strip():
                raise TextChunkingError("Cannot chunk empty text", document_id)
            
            encoding = self._get_encoding(options.encoding_name)
            chunks = []
            
            # Split text into sentences and paragraphs for better boundary detection
            sentences = self._split_into_sentences(text) if options.preserve_sentences else [text]
            
            current_chunk_text = ""
            current_start_pos = 0
            chunk_index = 0
            
            for sentence in sentences:
                # Check if adding this sentence would exceed chunk size
                potential_chunk = current_chunk_text + (" " if current_chunk_text else "") + sentence
                token_count = self.count_tokens(potential_chunk, options.encoding_name)
                
                if token_count <= options.chunk_size:
                    # Add sentence to current chunk
                    if current_chunk_text:
                        current_chunk_text += " " + sentence
                    else:
                        current_chunk_text = sentence
                else:
                    # Current chunk is full, create chunk if it meets minimum size
                    if current_chunk_text and self.count_tokens(current_chunk_text, options.encoding_name) >= options.min_chunk_size:
                        chunk = self._create_chunk(
                            current_chunk_text,
                            document_id,
                            chunk_index,
                            current_start_pos,
                            current_start_pos + len(current_chunk_text),
                            options,
                            len(chunks) > 0  # Has overlap if not first chunk
                        )
                        chunks.append(chunk)
                        chunk_index += 1
                        
                        # Calculate overlap for next chunk
                        if options.chunk_overlap > 0:
                            overlap_text = self._get_overlap_text(current_chunk_text, options)
                            current_start_pos = current_start_pos + len(current_chunk_text) - len(overlap_text)
                            current_chunk_text = overlap_text + " " + sentence
                        else:
                            current_start_pos = current_start_pos + len(current_chunk_text)
                            current_chunk_text = sentence
                    else:
                        # Current chunk too small, just add the sentence
                        if current_chunk_text:
                            current_chunk_text += " " + sentence
                        else:
                            current_chunk_text = sentence
            
            # Handle remaining text
            if current_chunk_text and self.count_tokens(current_chunk_text, options.encoding_name) >= options.min_chunk_size:
                chunk = self._create_chunk(
                    current_chunk_text,
                    document_id,
                    chunk_index,
                    current_start_pos,
                    current_start_pos + len(current_chunk_text),
                    options,
                    len(chunks) > 0  # Has overlap if not first chunk
                )
                chunks.append(chunk)
            
            if not chunks:
                # If no chunks were created, create one from the entire text
                chunk = self._create_chunk(
                    text,
                    document_id,
                    0,
                    0,
                    len(text),
                    options,
                    False
                )
                chunks.append(chunk)
            
            logger.info(
                f"Successfully chunked document {document_id} into {len(chunks)} chunks "
                f"with {options.chunk_size} max tokens and {options.chunk_overlap} overlap"
            )
            
            return chunks
            
        except TextChunkingError:
            raise
        except Exception as e:
            raise TextChunkingError(
                f"Failed to chunk text: {str(e)}",
                document_id,
                e
            )
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for better chunking boundaries."""
        import re
        
        # Simple sentence splitting - can be enhanced with more sophisticated NLP
        sentence_endings = re.compile(r'[.!?]+\s+')
        sentences = sentence_endings.split(text)
        
        # Clean up and filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def _get_overlap_text(self, chunk_text: str, options: ChunkingOptions) -> str:
        """Extract overlap text from the end of a chunk."""
        if options.chunk_overlap <= 0:
            return ""
        
        encoding = self._get_encoding(options.encoding_name)
        tokens = encoding.encode(chunk_text)
        
        if len(tokens) <= options.chunk_overlap:
            return chunk_text
        
        # Get the last N tokens for overlap
        overlap_tokens = tokens[-options.chunk_overlap:]
        overlap_text = encoding.decode(overlap_tokens)
        
        return overlap_text
    
    def _create_chunk(
        self,
        content: str,
        document_id: UUID,
        chunk_index: int,
        start_pos: int,
        end_pos: int,
        options: ChunkingOptions,
        has_overlap: bool
    ) -> TextChunk:
        """Create a TextChunk with metadata."""
        token_count = self.count_tokens(content, options.encoding_name)
        
        # Calculate overlap positions if applicable
        overlap_start = None
        overlap_end = None
        if has_overlap and options.chunk_overlap > 0:
            overlap_text = self._get_overlap_text(content, options)
            if overlap_text:
                overlap_start = 0
                overlap_end = len(overlap_text)
        
        metadata = ChunkMetadata(
            document_id=document_id,
            chunk_index=chunk_index,
            start_position=start_pos,
            end_position=end_pos,
            token_count=token_count,
            character_count=len(content),
            has_overlap=has_overlap,
            overlap_start=overlap_start,
            overlap_end=overlap_end,
            source_info={
                "chunking_method": "token_based",
                "encoding": options.encoding_name,
                "chunk_size": options.chunk_size,
                "chunk_overlap": options.chunk_overlap
            }
        )
        
        return TextChunk(
            id=uuid4(),
            content=content,
            metadata=metadata
        )


class TextChunkingService:
    """Main service for text chunking operations."""
    
    def __init__(self, chunker: Optional[BaseTextChunker] = None):
        self.chunker = chunker or TokenBasedChunker()
    
    def chunk_document_text(
        self,
        text: str,
        document_id: UUID,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        encoding_name: str = "cl100k_base"
    ) -> List[TextChunk]:
        """
        Chunk document text with specified parameters.
        
        Args:
            text: The text to chunk
            document_id: ID of the source document
            chunk_size: Maximum tokens per chunk (500-1000)
            chunk_overlap: Overlap tokens between chunks (100-200)
            encoding_name: Token encoding to use
            
        Returns:
            List of TextChunk objects
            
        Raises:
            TextChunkingError: If chunking fails
            ValueError: If parameters are invalid
        """
        # Validate parameters according to requirements
        if not (500 <= chunk_size <= 1000):
            raise ValueError("chunk_size must be between 500 and 1000 tokens")
        if not (100 <= chunk_overlap <= 200):
            raise ValueError("chunk_overlap must be between 100 and 200 tokens")
        
        options = ChunkingOptions(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            encoding_name=encoding_name
        )
        
        return self.chunker.chunk_text(text, document_id, options)
    
    def count_tokens(self, text: str, encoding_name: str = "cl100k_base") -> int:
        """Count tokens in text."""
        return self.chunker.count_tokens(text, encoding_name)
    
    def get_chunk_statistics(self, chunks: List[TextChunk]) -> Dict[str, Any]:
        """Get statistics about a list of chunks."""
        if not chunks:
            return {
                "total_chunks": 0,
                "total_tokens": 0,
                "total_characters": 0,
                "average_tokens_per_chunk": 0,
                "chunks_with_overlap": 0,
                "overlap_percentage": 0
            }
        
        total_tokens = sum(chunk.metadata.token_count for chunk in chunks)
        total_characters = sum(chunk.metadata.character_count for chunk in chunks)
        chunks_with_overlap = sum(1 for chunk in chunks if chunk.metadata.has_overlap)
        
        return {
            "total_chunks": len(chunks),
            "total_tokens": total_tokens,
            "total_characters": total_characters,
            "average_tokens_per_chunk": total_tokens / len(chunks),
            "chunks_with_overlap": chunks_with_overlap,
            "overlap_percentage": (chunks_with_overlap / len(chunks)) * 100
        }