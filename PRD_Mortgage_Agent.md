PRD: Mortgage Agent (RAG-Based Advisor for Canadian Home Buyers)

1) Summary

Build a conversational Mortgage Agent that helps Canadian home buyers (starting with First-Time Home Buyers) understand mortgage concepts, compare options, and navigate the home-buying journey using grounded, citation-backed answers from a curated knowledge base. The agent must include usage controls (question limits + character limits) and logging from day one, with a long-term architecture that supports automated corpus updates and a news/scraper pipeline.

2) Problem Statement

Mortgage information is high-stakes, complex, and fragmented. Buyers face:

Confusing terminology (fixed vs variable, insured vs uninsured, prepayment, amortization, stress test, closing costs).

Generic advice online that doesn’t match their context (province, down payment, credit profile, timeline).

High risk of misinformation/hallucinations from general-purpose AI.

Time pressure during offer/closing windows.

Core problem: Users need fast, trustworthy, context-aware explanations and checklists—without needing to become mortgage experts.

3) Goals and Non-Goals
Goals (MVP)

Provide accurate, grounded answers with citations from an approved corpus.

Help users progress through key workflows:

“Am I ready?” readiness + budgeting

Mortgage basics and trade-offs

Document checklist and timeline

Closing costs and fee awareness

Enforce guardrails:

No personalized financial/legal advice beyond general education + prompts to consult professionals.

Refuse or redirect when asked for disallowed content (e.g., guaranteed approvals, fraud, manipulation).

Include logging (questions, retrieved sources, model output, refusals, latency, token usage, errors).

Include usage constraints:

Max questions per user/session/day (configurable)

Max characters per question (configurable)

Non-Goals (MVP)

Not a lender/broker replacement; no rate-locking, applications, or underwriting decisions.

No direct integration to lender systems (e.g., bank origination platforms) in MVP.

No handling of sensitive documents (uploads) in MVP unless explicitly designed with security/privacy requirements.

4) Target Users and Personas
Primary Persona: First-Time Home Buyer (FTHB)

Age: 25–40

Context: buying in Ontario/GTA (initial focus), limited mortgage literacy

Needs: step-by-step guidance, explanations, “what should I do next?” checklists, cost clarity

Secondary Persona: Upgrader / Family Buyer

Already owns a home; needs refinancing/porting/bridge financing explanations

Tertiary Persona: Mortgage Associate / Advisor (future)

Uses agent as a “knowledge copilot” to quickly find policy/process answers (requires separate compliance design)

5) Key Use Cases (User Stories)
Education and Clarity

As a buyer, I want simple explanations of key mortgage concepts with examples.

As a buyer, I want to understand the pros/cons of fixed vs variable given my risk tolerance.

Readiness and Budgeting

As a buyer, I want a checklist of inputs I should gather (income, down payment, debts, timeline).

As a buyer, I want to estimate “cash needed to close” (high-level ranges + components).

Journey Guidance

As a buyer, I want a timeline of steps from pre-approval to closing.

As a buyer, I want document checklists (employment, income, down payment, ID, etc.).

Risk and Compliance-Safe Guidance

As a buyer, I want to know what can go wrong (closing delays, appraisal shortfalls, rate holds).

As a user, I want the agent to be transparent about uncertainty and cite sources.

6) Scope
In Scope (MVP)

Conversational UI (web CLI or simple web app)

Retrieval-Augmented Generation (RAG) over curated corpus

Citations in every factual answer (where applicable)

Logging + basic analytics

Usage limits (Q count + character limit)

Safety policies and refusal modes

Admin/config for limits and corpus version

Out of Scope (MVP)

Automated news scraping live in production (design for it, don’t ship it first)

Rate shopping via live APIs

User document ingestion (T4s, paystubs, bank statements)

Province-by-province legal nuance beyond general info

7) UX Requirements
Core Conversation Behaviors

Ask 1–3 targeted clarifying questions when needed (e.g., province, down payment range, timeline), otherwise answer directly.

Provide:

Direct answer

Short rationale

“Next steps” checklist (when relevant)

Citations (links/titles from corpus)

“Limitations / confirm with a professional” note for high-stakes topics

Usage Controls (Hard Requirements)

Question limit: configurable (e.g., 20 per day per user in MVP)

Character limit per question: configurable (e.g., 800–1,200 chars)

When limits exceeded:

Provide a brief message explaining limit

Suggest compressing question / starting a new session / upgrading plan (if applicable)

Log the event

Response Quality Requirements

Prefer structured formatting:

bullets, tables (light), steps

Avoid overconfidence: include uncertainty language if corpus doesn’t support an answer.

Never invent rates, fees, or policy rules without citations.

8) Functional Requirements
RAG + Answering

Ingest documents into a knowledge base with metadata (source, date, jurisdiction).

Retrieve top-k relevant chunks with embeddings + optional keyword hybrid search.

Generate response grounded only in retrieved content.

Provide citations mapped to chunks (source title + section).

If retrieval confidence is low:

Ask a clarifying question, OR

Say “I don’t have enough verified info in my sources” and suggest what to look up.

Logging and Observability

Log at minimum:

user_id/session_id (hashed)

timestamp

user question length + counts

retrieval query, retrieved doc ids, similarity scores

model name/version

output length

citations used

refusal category (if any)

latency

errors/exceptions

Admin/Config

Configurable limits (Q/day, Q/session, chars/question)

Configurable corpus version and “approved sources” list

Feature flags: citations required, strict grounding on/off (keep on by default)

9) Non-Functional Requirements
Security & Privacy

Do not store raw PII unless explicitly required.

If user shares sensitive info, redact in logs (basic regex redaction in MVP; improve later).

Separate “app logs” from “analytics” tables.

Performance

P95 response time target: < 8 seconds (MVP target; adjust based on infra).

Retrieval + generation should be resilient to partial failures (fallback responses).

Reliability

Graceful degradation if vector store is down: “I can’t access my knowledge base right now.”

10) Safety, Compliance, and Guardrails
Disclaimers (MVP)

“Educational information only; not financial/legal advice.”

“Verify with a licensed mortgage professional / lawyer for decisions.”

Guardrail Rules

Must refuse:

Fraud (misrepresenting income/down payment)

Instructions to manipulate approvals

Requests for private lender internal policy not in corpus

Must be careful:

Anything that looks like individualized advice (“What mortgage should I pick?”) → provide framework + questions to ask + recommend professionals.

11) Data Sources and Corpus Strategy
MVP Corpus (Curated)

Government of Canada / FCAC pages (mortgage basics)

Provincial land transfer tax pages (Ontario initial)

CMHC high-level insured mortgage guidance (general)

Reputable lender educational pages (if approved)

Your own curated internal notes/checklists (versioned)

Each doc must include:

Source name

URL (or stored PDF reference)

Publish/updated date

Jurisdiction tag (Canada / Ontario / etc.)

Long-Term Corpus Automation (Future)

Scheduled ingestion pipelines:

Re-fetch known URLs

Diff and re-embed changed content

Quality gate before promotion to “approved”

News/scraper agent:

Only after adding moderation + source vetting + “unverified” staging layer

12) Proposed Architecture
MVP High-Level Components

Client/UI

Simple web app or CLI

API Service

Auth (lightweight), rate limiting, input validation

Orchestrator

Guardrails → Retrieval → Prompt assembly → LLM call → Citation rendering

Vector Store

e.g., local (FAISS) for MVP or hosted vector DB

Document Store

raw docs + chunk metadata

Logging/Analytics

structured events (SQLite/Postgres in MVP)

Request Flow

Validate input (character limit, question limit)

Classify intent (education, readiness, timeline, costs)

Retrieve top-k chunks (k configurable)

Generate response with strict grounding + citations

Post-process:

enforce “no citations = no claim”

add disclaimers when needed

Log everything

13) Prompting and System Behaviors (Spec)

System instruction highlights:

“Use only retrieved sources; if not present, say you don’t know.”

“Provide citations for factual statements.”

“Ask clarifying questions if jurisdiction/time-sensitive detail matters.”

14) Metrics and Success Criteria
Product Metrics

Task completion: % sessions that reach a “next steps checklist” output

User-rated helpfulness (thumbs up/down)

Repeat usage within 7 days

Quality Metrics (Eval)

Groundedness rate (claims supported by citations)

Hallucination rate (unsupported claims)

Refusal precision (refuse when should; don’t refuse when shouldn’t)

Operational Metrics

P95 latency

Retrieval hit rate (did we retrieve anything useful?)

Error rate

15) Testing Plan
Offline Evaluation (Pre-Launch)

Create a “golden set” of ~50–100 Qs:

fixed vs variable, closing costs, down payment rules, timelines, etc.

Score:

correctness (SME review)

citation coverage

clarity + actionability

Guardrail Testing

Prompt injection tests (“ignore your rules…”)

Fraud requests, illegal advice requests, unsupported policy requests

Load/Perf Smoke

Concurrency tests + cold start tests

16) Rollout Plan
Milestone 1: PRD + Skeleton (Week 1 equivalent work)

Repo structure, config, logging schema, basic UI

Milestone 2: MVP RAG

Ingestion + chunking + vector store + retrieval + citations

Milestone 3: Guardrails + Limits

Question caps, char caps, refusals, prompt injection hardening

Milestone 4: Evaluation Harness

Golden set runner + regression checks per corpus/model change

Milestone 5: Beta

Small user group, feedback loop, iterate

17) Risks and Mitigations

Hallucinations → strict grounding, citations required, “don’t know” policy

Outdated info → doc dates visible, staging pipeline for updates

User over-trust → repeated disclaimers + professional escalation guidance

Scope creep → keep to FTHB educational workflows for MVP
