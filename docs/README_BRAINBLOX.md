# The System Blueprint: BrainBlox Architecture

The overall system is structured around a central Integration Service that acts as a traffic controller, ensuring that all internal calls are authenticated and context-aware.

```mermaid
graph TD
    subgraph Frontend (Client)
        A[User Interface] -->|API Calls (HTTP/S)| B(Integration Service);
    end

    subgraph Backend (Microservices Mesh)
        B -->|Authentication| C[User Service];
        B -->|Knowledge CRUD| D[Knowledge Service];
        B -->|Metadata/Tool Query| E[MCP Service];
        
        subgraph AI_CORE [AI & Intelligence Core]
            direction LR
            F[RAG Service] -->|1. Context Retrieval| G(ChromaDB);
            F -->|2. Vector Query| D;
            B -->|3. LLM Prompting| H(Ollama - Mistral-7B);
        end
        
        C -->|Uses| DB(MongoDB Cluster);
        D -->|Persists| DB;
        E -->|Schema/Tools| DB;
        
        subgraph Data & Storage
            DB
            G
            I[MongoDB Container]
        end
        
        style A fill:#2e86c1,color:#ffffff,stroke:#2c3e50
        style B fill:#f39c12,color:#2c3e50,stroke:#e67e22
        style C fill:#5dade2,color:#ffffff,stroke:#3498db
        style D fill:#a9c4d8,color:#2c3e50,stroke:#5da6d8
        style E fill:#8c5e7d,color:#ffffff,stroke:#9b59b6
        style F fill:#f9d896,color:#2c3e50,stroke:#f39c35
        style H fill:#7ed2bf,color:#1a1a1a,stroke:#4caf50
        
    end
```

## Component Breakdown & Data Flow

1. The Entry Point (Frontend)
    **Role :** The user-facing web application.
    **Interacts with :** The Integration Service.
    **Purpose :** Translates user intent (a complex thought) into a structured API call.

2. The Traffic Controller (Integration Service)

    **Role :** The API Gateway. This service is the single point of entry and is responsible for
        - **Authentication :** Validating the user before passing any request and generating and delivering security-tokenfor user and microservices transactions
        - **Routing :** Deciding which specialized microservice to call.
        - **Orchestration :** Coordinating multi-step calls (e.g., calling knowledge-service $\rightarrow$ then passing results to rag-service $\rightarrow$ then calling ollama).

3. The Core Services (The Business Logic)

    **user-service :** Handles all user-related CRUD.
    **knowledge-service :** Handles the core CRUD for knowledge articles and concepts. This is the source data for our RAG system.
    **mcp-service :** Manages the meta-data—what tools/skills are available to the entire system.

4. The AI Core (Intelligence & Context)

    **RAG Service (rag-service) :** This is the intelligence pipeline. When a query comes in, it does not talk directly to the LLM. It first talks to ChromaDB to find relevant context. It then packages that context with the query to create a superior prompt.
    **Vector Database (ChromaDB) :** Stores the high-dimensional embeddings of all knowledge chunks. It powers the rag-service.
    **LLM Engine (Ollama/Mistral-7B) :** This is the inference engine. It takes the highly structured prompt from the rag-service and returns the final, sophisticated answer. I'd like a bind mount. Eventually, we could maintain a customized ollama image ?

5. Data & Persistence Layer

    **MongoDB Cluster (mongodb) :** The persistent storage for structured data (users, article metadata). A cloud atlas cluster is duplicated daily on the local container
    **ChromaDB :** The specialized, dedicated storage for unstructured data embeddings (the vector index). if chromaDB has a cloud free account possibility we could duplicate locally too
