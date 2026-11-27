# AI Agents in Python: Stop using raw loops for LLMs

_Build a dead-simple, tool-calling agent in 30 lines of Python without heavy frameworks._

## Scroll-stopping hooks

**Hook 1.** I stayed up till 2 AM debugging why my Python script kept looping infinitely, only to realize I was overcomplicating AI agents.

**Hook 2.** You don't need LangChain, CrewAI, or a 500MB dependency tree to build a working AI agent in Python.

**Hook 3.** Most tutorial AI agents are just While loops hiding behind expensive abstractions. Here's how they actually work under the hood.

**Hook 4.** Spent my midnight coding session stripping down an AI agent to its absolute bare essentials in pure Python.

**Hook 5.** If your AI script can't decide when to call a function and when to stop talking, it isn't an agent yet.

## 7 tips that actually move the needle

### Tip 1. Use the official `google-genai` or `openai` SDK directly instead of massive wrapper frameworks.
_Why it matters:_ Wrapper frameworks obscure tool-calling errors and add unnecessary latency to simple loops.

```python
from google import genai
client = genai.Client()
```

### Tip 2. Define your tools as standard Python functions with type hints and explicit docstrings.
_Why it matters:_ LLMs rely entirely on docstrings and type annotations to figure out argument schemas.

```python
def add(a: int, b: int) -> int:
    """Adds two numbers together."""
    return a + b
```

### Tip 3. Set `max_iters` guards inside your execution loop.
_Why it matters:_ Without a hard iteration limit, a hallucinating model will burn through your API credits in seconds.

```
for _ in range(5):
    # run agent loop
    break
```

### Tip 4. Pass function execution results back to the model as structured tool responses.
_Why it matters:_ The LLM needs to see the output of its requested action to synthesize the final answer.

```
messages.append({'role': 'tool', 'content': result})
```

### Tip 5. Use `pydantic` to validate inputs before executing local functions.
_Why it matters:_ Models occasionally pass stringified integers or missing keys that break unshielded Python code.

```python
from pydantic import validate_call
@validate_call
def safe_search(query: str): pass
```

### Tip 6. Print colored terminal outputs for tool calls using `rich`.
_Why it matters:_ Visualizing when the agent switches from thinking to tool execution makes debugging trivial.

```python
from rich import print
print('[bold green]Executing Tool:[/bold green]', func_name)
```

### Tip 7. Log full system messages and tool payloads with `logging` at DEBUG level.
_Why it matters:_ When an agent goes off the rails, you need to see the exact prompt sequence sent to the API.

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Step-by-step procedure

### 1. Set up your virtual environment and minimal dependencies
Create a clean dir and install just the official API SDK — skip the heavy agent abstractions.

```python
pip install google-genai pydantic
```

### 2. Define a concrete Python function for the agent to use
Write a basic tool with clear type annotations and a descriptive docstring.

```python
def get_system_time() -> str:
    """Returns the current system time in ISO format."""
    from datetime import datetime
    return datetime.now().isoformat()
```

### 3. Register the tool list with the model client
Pass your python functions directly into the model initialization parameters.

```python
from google import genai
client = genai.Client()
tools = [get_system_time]
```

### 4. Build the core reasoning-action loop
Loop until the model returns a text response instead of a tool call request.

```
chat = client.chats.create(model='gemini-2.5-flash', config={'tools': tools})
response = chat.send_message('What time is it right now?')
```

### 5. Handle execution and feedback
If the model requests a function call, execute it locally and send the output back.

```
if response.function_calls:
    for call in response.function_calls:
        res = get_system_time()
        response = chat.send_message(res)
```

### 6. Run the script and verify tool execution in terminal
Run your script to confirm the model successfully triggers your local Python function and formats the output.

```
python agent.py
# Output: The current system time is 2026-03-30T01:15:00.
```

## The mistake almost everyone makes

> ⚠️  Forgetting to supply descriptive docstrings to python functions passed as tools. The fix: always write a clear 1-2 sentence docstring explaining what the function does and what parameters it expects.

## X / Twitter thread (copy-paste ready)

**1/** Building your first AI agent in Python is way simpler than framework docs make it look.

**2/** Spent last night stripping down agentic loops to raw code. You don't need 10 layers of abstractions.

**3/** Tip 1: Define your tools using standard Python functions with explicit docstrings and type hints.

**4/** Tip 2: Use native API SDKs directly so you can see exact model requests and response payloads.

**5/** Tip 3: Always add a hard loop limit (`max_iters=5`) to prevent runaway API spend when models get stuck.

**6/** Drop the bloated frameworks for your first build. Write the 30-line loop yourself first.

## LinkedIn version

I wasted two hours last night fighting with framework abstractions before I scrapped everything and built an AI agent with 30 lines of standard Python.

We've been conditioned to think building 'agents' requires importing massive third-party libraries, complex DAG state managers, and hidden prompts. But fundamentally, an agent is just a loop: the LLM decides to run a tool, you execute that tool locally, and you feed the result back to the model.

When you build this loop manually using native SDKs, the magic disappears — and that's a good thing. You suddenly get total control over error handling, execution guards, and state context without digging through abstract stack traces.

If you're building your first tool-calling script, start with raw Python functions, strict type hints, and simple `while` loops before reaching for standard agent frameworks.

Strip away the noise and inspect the actual payloads — you'll figure it out much faster.

python ai softwaredevelopment webdevelopment automation

_Tags: python, aiagents, genai, backend_

---
*By Suman Giri — built with the CoderFact engine.*