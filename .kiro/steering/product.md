# Product Overview

Fast Chat is a RAG (Retrieval-Augmented Generation) chatbot application. Users upload documents (PDF, TXT, DOCX, Markdown), which are chunked, embedded, and stored in a PostgreSQL vector database (pgvector). Users then chat with an AI assistant that retrieves relevant document chunks via semantic search to ground its responses.

Key capabilities:
- Document upload, processing, text extraction, and vector embedding
- Conversational chat with RAG-powered context retrieval
- Multi-LLM provider support (OpenAI, Anthropic, Google) with priority-based failover
- Conversation history and memory management via Redis
- Cost tracking for LLM usage
- Environment and user role management
- Monitoring and metrics collection
