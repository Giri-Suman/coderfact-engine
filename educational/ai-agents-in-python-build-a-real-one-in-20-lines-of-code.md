# AI Agents in Python: Build a Real One in 20 Lines of Code

_Stop calling API wrappers 'agents' — here is how to actually build a loop that executes tools._

## Scroll-stopping hooks

**Hook 1.** I spent three hours last night debugging an 'AI agent' framework only to realize a basic while loop and a function map do the exact same thing.

**Hook 2.** Most AI agent tutorials sell you a 500-line framework dependency when all you actually need is a loop, a prompt, and a JSON schema.

**Hook 3.** If your AI agent breaks every time OpenAI tweaks a response, you didn't build an agent — you built a fragile string parser.

**Hook 4.** You don't need LangChain or LlamaIndex to build a tool-calling agent in Python. You just need native function calling and a system prompt.

**Hook 5.** Built a Python script at 1am to auto-fix my broken build logs using tool calls. Here is the architecture stripped of all framework bloat.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate tool schemas instead of writing raw JSON
_Why it matters:_ It keeps your tool definitions type-safe and updates the LLM schema automatically when your code changes.

```python
from pydantic import BaseModel
class SearchArgs(BaseModel):
    query: str
```

### Tip 2. Bind native Python functions to your client using instructor or standard API tool calls
_Why it matters:_ It stops the model from hallucinating invalid function arguments by enforcing a strict schema contract.

```
tools = [{'type': 'function', 'function': {'name': 'run_query', 'parameters': SearchArgs.model_json_schema()}}]
```

### Tip 3. Implement an explicit execution loop with a maximum iteration cap
_Why it matters:_ An uncapped agent loop will happily burn through $50 of API credits in an infinite retry loop.

```
MAX_TURNS = 5
for _ in range(MAX_TURNS):
    if not response.choices[0].message.tool_calls: break
```

### Tip 4. Append tool outputs back into the conversation history as 'tool' role messages
_Why it matters:_ The model needs to see the literal execution output to decide what step to take next.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### Tip 5. Use tenacity to wrap your external tool calls with automatic retries
_Why it matters:_ Network blips during a tool execution shouldn't crash the entire agent loop.

```python
@retry(stop=stop_after_attempt(3))
def fetch_data(url):
    return requests.get(url).text
```

### Tip 6. Pass a strict system prompt that forces the agent to announce final answers
_Why it matters:_ Without a clear termination signal, the model keeps invoking tools long after it has the answer.

```
SYSTEM = 'Execute tools until you have the answer, then reply with FINAL ANSWER:'
```

### Tip 7. Log raw LLM inputs and outputs to a local file using structlog
_Why it matters:_ When an agent goes off the rails, step-by-step stdout logs are the only way to catch where the reasoning failed.

```python
import structlog
logger = structlog.get_logger()
logger.info('tool_call', name=fn_name, args=args)
```

## Step-by-step procedure

### 1. Set up your Python environment and dependencies
Create a virtualenv and install the official openai and pydantic packages — no heavy agent orchestration libraries required.

```python
pip install openai pydantic
```

### 2. Define your agent tools as pure Python functions
Write the actual functions your agent will execute when it needs outside data or actions.

```python
def get_system_load():
    import os
    return str(os.getloadavg())
```

### 3. Map function signatures to tool definitions
Create a registry dictionary that links function names to their callable objects so the loop can execute them dynamically.

```
TOOL_MAP = {'get_system_load': get_system_load}
```

### 4. Build the core execution while-loop
Send messages to the model. If it returns tool_calls, execute the matching function from your map and append the output.

```
while response.choices[0].message.tool_calls:
    for call in response.choices[0].message.tool_calls:
        out = TOOL_MAP[call.function.name]()
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': out})
```

### 5. Run a multi-step task and print the result
Ask the agent a question requiring real-time tool execution, let it run, and verify it returns a valid answer.

```python
res = run_agent('Check current system load and tell me if it is high.')
print(res)
```

## The mistake almost everyone makes

> ⚠️  Passing tool results back as 'user' or 'system' messages instead of the dedicated 'tool' role. This breaks the context window formatting for OpenAI/Anthropic APIs, causing the model to forget previous steps or repeat tool calls endlessly. Always pass the exact tool_call_id alongside the result using the 'tool' role.

## X / Twitter thread (copy-paste ready)

**1/** Stop pulling in massive framework dependencies just to build a basic AI agent in Python. 🧵

**2/** At 1am last night, I got fed up with abstractions breaking on basic tool calls. So I stripped it all back to native Python.

**3/** Tip 1: Define your tools as plain functions and auto-generate schemas using Pydantic instead of hand-writing JSON.

**4/** Tip 2: Control execution with a basic Python loop and cap it at 5-10 turns max so you don't burn API credits on infinite loops.

**5/** Tip 3: Always append execution results back to the chat history using the explicit 'tool' role with its matching tool_call_id.

**6/** You don't need a framework — just a loop, a function map, and clean state handling. Code your own agent tonight.

## LinkedIn version

I stayed up until 1am last night trying to debug why an 'agent framework' was failing a basic tasks pipeline. 

Turns out, the framework had added three layers of abstraction over what is essentially a simple while loop. When the API response format shifted slightly, everything broke.

So I scrapped the third-party dependencies and wrote a native Python agent from scratch. No bloated abstractions — just raw API calls, Pydantic for tool schemas, and a basic function registry.

Here is the core pattern: you pass your tool schemas to the model, check if it returned a tool_calls payload, map that payload to a local Python function, execute it, and feed the string output back into the message array. You repeat this in a loop until the model gives you a final text response.

Building agents this way gives you full control over error handling, retries, and context window limits. Before you reach for a heavy orchestration package, try building the loop yourself first. You will understand your code better, and it won't randomly break on dependency updates.

python ai engineering softwaredevelopment programming

_Tags: python, aiagents, openai, backend_

---
*By Suman Giri — built with the CoderFact engine.*