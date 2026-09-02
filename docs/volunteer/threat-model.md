# Volunteer Mode Threat Model: API Observability

When a volunteer donor runs tasks using a third-party LLM provider, what can the provider observe, and can they distinguish volunteer tasks from regular interactive usage?

This document outlines the observability profile for each adapter class and defines the recommended default posture.

## Key Finding

**The network topology of the coordination layer — how tasks are discovered and claimed — does not change what a single donor's API call looks like to a provider.**

The call is made locally by the donor's own machine regardless of whether discovery is centralized, federated, or peer-to-peer. Provider-opacity is therefore an adapter/client concern, not a networking concern; a decentralized transport does not address it.

## Observability by Adapter Class

When a third-party provider adapter is used, the provider can observe:
- **Auth Principal**: The API key (e.g. Anthropic, OpenAI) used to authenticate.
- **Source IP**: The network origin of the request (the donor's machine).
- **Request Shape**: The structure of the request, such as chat completion format, system prompts, tool schemas, and token usage.
- **Client Metadata**: Request headers, such as `User-Agent`.
- **Pacing**: The frequency and rhythm of requests, which often differs significantly from human typing in interactive coding sessions.

### Is Volunteer Mode Distinguishable?
Yes. Although adapters do not send explicit "Volunteer Mode" flags, a provider can easily distinguish automated task execution from interactive human coding:
1. **Tool Definitions**: Adapters inject specific Bernstein tools (e.g., `run_command`, `replace_in_file`).
2. **System Prompts**: Specific instructions and context used by the orchestrator are included.
3. **Pacing**: An agent executes continuously and rapidly, unlike human-paced interaction.
4. **Volume**: Volunteer tasks typically consume tokens at a much higher and sustained rate.

## Recommended Default Posture

For anything a provider would forbid, the recommendation is **never** to "hide it" but rather to avoid the provider entirely.

The **provider-independent path** — using local-model and self-hosted-endpoint adapters (the `core/endpoints/` tier) — removes the third party from the loop entirely.

**This is the recommended default posture.** In volunteer mode, when no provider adapter is explicitly chosen, the system defaults to a local or self-hosted adapter if one is available.
