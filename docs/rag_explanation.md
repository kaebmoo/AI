# RAG (Retrieval-Augmented Generation) Implementation

This document explains how RAG is implemented in the backend to enhance AI responses with domain-specific knowledge.

## Overview

The system uses **Vanna.AI** strategies combined with **ChromaDB** (Vector Database) to implement RAG. This allows the AI to "look up" relevant database schemas, documentation, and SQL examples before generating a response, rather than relying solely on its pre-trained knowledge.

## Architecture

### Core Components

1.  **AIService** ([app/services/ai_service.py](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py)):
    -   The main orchestrator for AI interactions.
    -   Initializes [VannaService](file:///Users/seal/Documents/GitHub/AI/app/services/vanna_service.py#9-213).
    -   Injects retrieved context into prompts during [query_hybrid](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py#1210-1581).

2.  **VannaService** ([app/services/vanna_service.py](file:///Users/seal/Documents/GitHub/AI/app/services/vanna_service.py)):
    -   Manages the "Brain" (Knowledge Base).
    -   Handles embedding and retrieval using ChromaDB.
    -   Syncs data sources to the vector store.

3.  **ChromaDB** (`./chroma_db`):
    -   Local vector database storing embeddings for efficient similarity search.

### Data Sources (The "Brain")

The RAG system is trained on three key types of information:

| Collection | Source | Purpose |
| :--- | :--- | :--- |
| **DDL** | Database Schema metadata | Helps AI understand table structures, columns, and types. |
| **Documentation** | [docs/DATABASE_TABLES_GUIDE.md](file:///Users/seal/Documents/GitHub/AI/docs/DATABASE_TABLES_GUIDE.md), `schema_business_rules`, `schema_semantic_mapping` | Provides business context, column descriptions, and mapping rules. |
| **SQL** | [golden_examples](file:///Users/seal/Documents/GitHub/AI/app/services/vanna_service.py#139-147) table | "Few-shot" learning examples showing correct SQL for specific questions. |

## Process Flow

When a user asks a question in **Hybrid Mode**, the following process occurs:

### 1. Retrieval (Step 1)
The [AIService](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py#909-1753) calls [_get_vanna_context_string(question)](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py#1628-1659), which triggers `VannaService.get_rag_context`:
-   **Embedding**: The user's question is converted into a vector.
-   **Search**: ChromaDB finds the nearest neighbors in the DDL, Documentation, and SQL collections.
-   **Filtering**: Results are filtered by `VANNA_DISTANCE_THRESHOLD` to ensure relevance.

### 2. Augmentation (Step 2)
The retrieved information is formatted into a context block:

```markdown
### Relevant Tables (Schema):
CREATE TABLE ...

### Relevant Rules & Dictionary:
- Revenue calculation excludes canceled orders...

### Similar Examples (Golden SQL):
- SELECT sum(amount) FROM ...
```

### 3. Generation (Step 3)
This context block is **injected** into the prompt sent to the LLM (Claude/Gemini/Matcha):

> **System/User Prompt:**
> Context: [Injected RAG Context]
> Question: "Total revenue last month?"
> Task: Generate SQL checking the schema above...

### 4. Execution
The AI generates SQL based on this augmented, accurate context, which is then validated and executed against the database.

## Key Code References

-   **Context Injection**: [app/services/ai_service.py](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py) (lines 1323-1337 in [query_hybrid](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py#1210-1581))
-   **Retrieval Logic**: [app/services/vanna_service.py](file:///Users/seal/Documents/GitHub/AI/app/services/vanna_service.py) ([get_rag_context](file:///Users/seal/Documents/GitHub/AI/app/services/vanna_service.py#175-213))
-   **Context Formatting**: [app/services/ai_service.py](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py) ([_get_vanna_context_string](file:///Users/seal/Documents/GitHub/AI/app/services/ai_service.py#1628-1659))
