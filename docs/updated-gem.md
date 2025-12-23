```mermaid
graph TD
    subgraph Monorepo ["Monorepo (Turborepo)"]
        subgraph Apps ["Deployable Apps"]
            Web["Web UI: Next.js<br/>(Cloud Run)"]
            Mobile["Mobile UI: Expo/EAS<br/>(App Stores)"]
        end

        subgraph Shared ["Shared Logic Package (@repo/api)"]
            Zod["Zod Schemas<br/>(Contract Enforcement)"]
            Hooks["TanStack Hooks<br/>(useIngest, useGroceryList)"]
        end
    end

    subgraph GCP ["Google Cloud Platform"]
        Gateway["Node.js Orchestrator<br/>(Cloud Run)"]
        Worker["Python Logic Specialist<br/>(Cloud Run)"]
        Queue["Cloud Tasks<br/>(Async Ingestion)"]
        
        subgraph DataLayer ["Intelligent Data Layer"]
            DB[("Cloud SQL Postgres<br/>(RLS Isolation)")]
            ML["google_ml_integration<br/>(Vertex AI Bridge)"]
            Vec["pgvector<br/>(Similarity Engine)"]
        end
    end

    %% Frontend Connections
    Web -.-> Shared
    Mobile -.-> Shared
    Shared -- "One API Interface" --> Gateway

    %% Backend Connections
    Gateway -- "Tenant-Scoped Query" --> DB
    Gateway -- "Trigger Job" --> Queue
    Queue -- "Async POST" --> Worker
    Worker -- "Vertex AI Call" --> AI["Gemini 2.5 Flash"]
    
    %% The Normalization Loop
    Worker -- "Save Structured JSON" --> DB
    DB -- "Auto-Vectorize via ML Ext" --> ML
    ML -- "Get Embedding" --> VAI["Vertex AI Embeddings"]
    VAI -- "Compare with pgvector" --> Vec
    Vec -- "Deduplicate / Link Alias" --> DB

    %% Style
    style Shared fill:#fff3e0,stroke:#ff9800,stroke-width:2px
    style Web fill:#e3f2fd,stroke:#2196f3
    style Mobile fill:#f3e5f5,stroke:#9c27b0
    style DataLayer fill:#f1f8e9,stroke:#388e3c