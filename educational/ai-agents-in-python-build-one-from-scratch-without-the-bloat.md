# AI Agents in Python: Build One from Scratch Without the Bloat

_Stop installing massive frameworks just to run a while loop with tool calls. Build it clean._

## Scroll-stopping hooks

**Hook 1.** Most AI agent tutorials make you install 40 dependencies before you even understand what an agent actually is.

**Hook 2.** Spent until 1am wrestling with an agent framework before realizing the whole pattern is literally just a while loop and a schema.

**Hook 3.** You do not need LangChain to build an agent—Python's standard library and a bare client work better anyway.

**Hook 4.** An agent is not magic: it's a model in a while loop picking a JSON tool definition until it decides to stop.

**Hook 5.** If your agent framework breaks every time a dependency updates, write the 40 lines of raw Python yourself.

## 7 tips that actually move the needle

### Tip 1. Use litellm instead of vendor-specific SDKs to keep your client unified
_Why it matters:_ It lets you swap between local Ollama models and cloud providers without rewriting function calling logic.

```python
from litellm import completion
res = completion(model='gpt-4o-mini', messages=msgs, tools=tools)
```

### Tip 2. Validate every tool response with Pydantic before handing it back to the loop
_Why it matters:_ Models hallucinate invalid tool inputs—Pydantic catches bad types before your Python runtime crashes.

```python
from pydantic import BaseModel
class SearchQuery(BaseModel): query: str; limit: int = 5
```

### Tip 3. Map function names directly to Python callables via a simple dictionary
_Why it matters:_ Avoid dangerous eval calls by keeping execution explicitly contained in a single registry.

```
TOOL_MAP = {'run_sql': run_sql, 'fetch_url': fetch_url}
output = TOOL_MAP[tool_name](**tool_args)
```

### Tip 4. Cap your agent execution loop with a strict iteration counter
_Why it matters:_ Without a hard stop, a failing tool call puts your model into an infinite, wallet-draining retry cycle.

```
for _ in range(MAX_STEPS):
    if not response.choices[0].message.tool_calls: break
```

### Tip 5. Use rich to pretty-print execution traces during local debugging
_Why it matters:_ Seeing agent thoughts, tool payloads, and outputs formatted clearly in the terminal saves hours of log hunting.

```python
from rich import print
print(f'[bold yellow]Calling:[/bold yellow] {func_name}')
```

### Tip 6. Inject tool errors back into the conversation history instead of raising exceptions
_Why it matters:_ Giving the error string to the LLM lets it fix its own parameters on the subsequent pass.

```
msgs.append({'role': 'tool', 'tool_call_id': call_id, 'content': str(err)})
```

### Tip 7. Test tool routing locally with ollama run llama3.1 to avoid API costs
_Why it matters:_ You can debug tool parameter extraction locally before spending a dime on API tokens.

```
ollama pull llama3.1:8b
# points litellm to localhost:11434
```

## Step-by-step procedure

### 1. Write the raw Python functions you want the model to use
Define ordinary Python functions with type hints and explicit return values that solve your task.

```python
def get_stock(symbol: str) -> str:
    return f'${symbol.upper()} is currently at $150'
```

### 2. Define the JSON schema describing your tool signatures
Format your functions using OpenAI-compatible schema specs so the LLM understands when and how to call them.

```
tools = [{'type': 'function', 'function': {'name': 'get_stock', 'parameters': {'type': 'object', 'properties': {'symbol': {'type': 'string'}}, 'required': ['symbol']}}}]
```

### 3. Set up your tool execution registry
Create a dictionary mapping function names as strings directly to the Python functions you authored.

```
available_tools = {'get_stock': get_stock}
```

### 4. Construct the while loop that handles tool calls
Check if the LLM output contains tool calls, execute them using your registry, and append outputs to the message thread.

```python
import json
# call LLM -> parse call -> call func -> append result to msgs
```

### 5. Execute the loop and verify the final answer in your terminal
Pass a multi-step prompt, run the script, and ensure the agent executes the tool and outputs the final message.

```
python agent.py
# Output: 'AAPL is currently at $150.'
```

## The mistake almost everyone makes

> ⚠️  Crashing when the LLM outputs malformed JSON inside tool arguments. Fix it by wrapping json.loads in a try/except block and returning the json.JSONDecodeError string back to the model as a tool role message so it retries with valid syntax.

## X / Twitter thread (copy-paste ready)

**1/** Built an agent framework from scratch last night because 400 lines of third-party abstractions were driving me crazy.

**2/** Turns out, an AI agent isn't complex architecture. It's just a while loop, a message list, and an execution registry.

**3/** 1/ Use litellm so you aren't married to OpenAI or Anthropic SDKs when switching providers.

**4/** 2/ Map tool names to actual functions using a basic dict — don't overengineer execution layers.

**5/** 3/ When a tool fails, pass the raw error back as a message. The model will usually correct its arguments.

**6/** Strip away the framework hype and write the core loop yourself. Full code breakdown on CoderFact.

## LinkedIn version

At 1am last night, I sat staring at a stack trace six layers deep inside an agent framework, mildly annoyed that a simple tool call required this much plumbing.

All I wanted was a Python script that checks data, decides if it needs more info, runs a function, and prints the result. Somehow that meant four separate packages, abstract memory layers, and broken dependencies.

So I scrapped the libraries and wrote the loop manually. Strip away the jargon, and an AI agent is straightforward: a model call, a list of JSON schemas, and a loop that executes local functions until the model decides it has enough context to reply.

Building it from scratch taught me more about function calling in an hour than days of reading vendor documentation. You handle the errors directly, control token usage, and your code doesn't explode whenever a package bumps a minor version.

If you're building agents, write the bare-bones Python version first before adopting heavy frameworks. You'll realize how little of that extra code you actually need.

#python #softwareengineering #buildinpublic #developers

_Tags: python, aiagents, automation, programming_

---
*By Suman Giri — built with the CoderFact engine.*