```mermaid
graph TD
    subgraph Clients ["Thin Clients (TypeScript)"]
        Web["React (Next.js)"]
        Mobile["React Native (Expo)"]
        Shared["TanStack Query Cache / Zod Schemas"]
    end

    subgraph Identity ["Identity (GCP Managed)"]
        Auth["Firebase Authentication"]
    end

    subgraph Gateway ["Orchestration Layer (Node.js/TS)"]
        Fastify["Fastify on Cloud Run"]
        Prisma["Prisma ORM (with RLS Logic)"]
        Jobs["Cloud Tasks Client"]
    end

    subgraph Workers ["Specialist Layer (Python)"]
        FastAPI["FastAPI on Cloud Run"]
        Gemini["Vertex AI: Gemini 2.5 Flash"]
        Pint["Pint (Unit Normalization Engine)"]
    end

    subgraph Persistence ["Authoritative Data (GCP)"]
        Postgres[("Cloud SQL (PostgreSQL)<br/>+ Row Level Security")]
        Redis["Cloud Memorystore<br/>(Density & Rule Cache)"]
    end

    subgraph Pipeline ["Async Workflow"]
        TQ["Cloud Tasks Queue<br/>(Rate Limited & Retryable)"]
    end

    subgraph Observability ["GCP Ops Suite"]
        Log["Cloud Logging"]
        Trace["Cloud Trace"]
        Error["Error Reporting"]
    end

    %% Data Flow
    Web & Mobile --> Shared
    Shared -- "JWT ID Token" --> Auth
    Shared -- "CRUD / Plan Requests" --> Fastify
    
    Fastify -- "1. Set current_user_id" --> Postgres
    Fastify -- "2. Enqueue Ingest" --> TQ
    
    TQ -- "HTTP Target (Idempotent)" --> FastAPI
    
    FastAPI -- "Extract Schema" --> Gemini
    FastAPI -- "Normalization Logic" --> Pint
    FastAPI -- "Upsert Result" --> Postgres
    
    Postgres -.-> Redis
    
    %% Style
    style Gateway fill:#e1f5fe,stroke:#01579b
    style Workers fill:#fff3e0,stroke:#e65100
    style Persistence fill:#e8f5e9,stroke:#1b5e20
    style Pipeline fill:#f3e5f5,stroke:#4a148c