# FAOS Codex Architecture

This document captures the initial design blueprint for FAOS Codex. The goal is to establish clear subsystem boundaries and data flows that can scale as we introduce advanced capabilities in subsequent iterations.

## System Context

FAOS Codex operates on a developer's local machine, acting as an orchestration layer between:

- **End Users** who describe desired software in natural language.
- **Local Large Language Models (LLMs)** that synthesize code and documentation.
- **Local Execution Environments** that optionally validate generated artefacts.

## Major Subsystems

### 1. Interaction Front-End
- **Responsibilities:**
  - Provide the primary user experience (initially a command-line interface).
  - Display generated outputs, status updates, and error messages.
  - Collect iterative feedback to drive refinement cycles.
- **Key Interfaces:**
  - Consumes events emitted by the orchestration core.
  - Sends normalized user intents to the orchestration core.

### 2. Orchestration & Project Management Core
- **Responsibilities:**
  - Maintain session state, including prompts, generated files, execution results, and metadata.
  - Coordinate asynchronous operations involving the LLM gateway and execution sandbox.
  - Persist artefacts using a pluggable storage layer (local filesystem in the first iteration).
  - Enforce project lifecycle workflows (creation, update, finalize, archive).
- **Key Interfaces:**
  - Exposes services for the front-end to create/update project tasks.
  - Invokes the model gateway for generation requests.
  - Manages sandbox jobs and aggregates their results.

### 3. Model Gateway (LLM Interface Layer)
- **Responsibilities:**
  - Abstract the specifics of the local LLM API (REST endpoints, streaming protocols, etc.).
  - Handle prompt templating, response validation, and error handling.
  - Provide observability hooks (latency, token counts, cost estimation).
- **Key Interfaces:**
  - Receives sanitized prompts from the orchestration core.
  - Returns structured responses (raw text, code blocks, diagnostics) suitable for downstream processing.

### 4. Execution Sandbox (Optional, Pluggable)
- **Responsibilities:**
  - Execute generated code in an isolated environment (containers, virtual environments, or subprocesses).
  - Stream logs and test results back to the orchestration core.
  - Enforce resource constraints and security policies.
- **Key Interfaces:**
  - Accepts execution plans and environment specifications from the orchestration core.
  - Emits execution artefacts (stdout/stderr, exit codes, coverage reports).

## Cross-Cutting Concerns

- **Configuration Management:** Centralized settings for LLM endpoints, storage directories, and sandbox behaviour. Early iterations can rely on `.env` files or simple YAML, with the option to migrate to more sophisticated solutions later.
- **Logging & Telemetry:** Structured logging for traceability, with hooks that can integrate into observability stacks.
- **Extensibility:** Each subsystem is implemented as a discrete package, enabling future swaps (e.g., switching from CLI to web UI) without rewriting unrelated components.

## Initial Development Roadmap

1. Establish the CLI front-end and orchestration skeleton with in-memory storage.
2. Implement the model gateway targeting a local HTTP LLM endpoint with configurable parameters.
3. Introduce persistent project storage and workspace management.
4. Add optional sandbox integration for executing generated code safely.
5. Layer in advanced features such as iterative refinement, templated project scaffolds, and multi-agent coordination.

This architecture lays the foundation for building FAOS Codex incrementally while maintaining clear separation of concerns.

