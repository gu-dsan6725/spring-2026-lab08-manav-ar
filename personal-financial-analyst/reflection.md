## Reflection 

There were no specific questions mentioned in the exercise.md so the following reflections are based off of the key learnings for the exercise.

### 1. Orchestrator-workers vs single agent

A single agent handling everything including data fetching, research, negotiation scripts, and tax analysis and would require an expensive model, a massive prompt, and sequential execution. The orchestrator workers pattern decomposes the problem, the orchestrator handles high-level reasoning, delegation, and synthesis, while three focused workers handle well-scoped subtasks in parallel. This achieves roughly 75% cost reduction and roughly 3x speed improvement (parallel execution), while keeping each agent's prompt simple and focused.

### 2. Haiku for sub-agents instead of Sonnet 

The sub-agent tasks like researching alternatives, writing negotiation scripts, identifying deductions are well-defined and template driven. A well-structured prompt makes Haiku highly effective for these focused tasks because the agent does not need to plan, coordinate, or make strategic decisions. Only the orchestrator needs Sonnet's stronger reasoning capabilities for analyzing spending patterns, deciding which agents to invoke, reading their outputs, and synthesizing everything into a coherent final report. This is a practical application of using the cheapest model that can reliably complete each task.

### 3. File-based communication work between agents

Each sub-agent writes its output to a known markdown file (e.g., `data/agent_outputs/research_results.md`). After all agents complete, the orchestrator reads these files using its Read tool and synthesizes the contents. The advantage is simplicity and debuggability, you can inspect any agent's output by opening the file. The downside is that file paths must be exact, and there is no structured schema for the outputs. Stating the exact file path at the start, middle, and end of each sub-agent prompt mitigates the filename drift problem.

### 4. MCP vs direct function calls 

MCP provides a standardized, loosely coupled interface between agents and data sources. The bank and credit card servers run as independent processes, can be restarted or updated without touching the agent code, and could serve multiple clients simultaneously. Direct function calls would tightly couple the data layer to the agent, making it harder to swap data sources, test independently, or reuse the servers in other contexts. MCP also provides automatic tool discovery — the agent learns what tools are available by connecting to the server.

### 5. Parallelisation of sub-agents 

The orchestrator's system prompt explicitly instructs Claude to invoke all sub-agents simultaneously, and the Claude Agent SDK handles the parallel execution mechanics when the orchestrator issues multiple Agent tool calls in a single turn. Without the explicit prompt instruction, Claude tends to invoke agents one at a time and wait for each result before proceeding, which is safe but slow. The tasks are independent making parallelization both safe and efficient.