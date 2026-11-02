# AI Agents in Python: Build One Tonight Without Framework Overhead

_Stop overcomplicating agents with heavy frameworks—here is how to build a working loop in 30 lines._

## Scroll-stopping hooks

**Hook 1.** I spent three hours debugging a LangChain abstraction before realizing a while-loop and the OpenAI API do the exact same thing.

**Hook 2.** Most 'AI agent frameworks' are just an expensive wrapper around a system prompt and a tool-execution loop.

**Hook 3.** You do not need a 50MB framework to build an AI agent—just Python, pydantic, and a basic loop.

**Hook 4.** At 1 AM, I deleted all my agent dependencies and rewrote the entire bot in raw Python. It ran faster and stopped crashing.

**Hook 5.** If your AI agent breaks and you cannot trace the stack because of five layers of framework abstractions, read this.

## 7 tips that actually move the needle

### Tip 1. Use OpenAI's official `openai` SDK with `tools` binding instead of framework wrappers
_Why it matters:_ It keeps your call stack transparent and avoids silent framework-level state mutations.

```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
```

### Tip 2. Validate tool call arguments with `pydantic` before executing them
_Why it matters:_ LLMs occasionally hallucinate invalid JSON types that crash unvalidated local functions.

```python
from pydantic import BaseModel, ValidationError
class SearchArgs(BaseModel):
    query: str
```

### Tip 3. Maintain an explicit `messages` list array as your agent's execution memory
_Why it matters:_ Appending assistant tool requests and system tool responses directly gives you full control over token limits.

```
messages.append(response.choices[0].message)
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': result})
```

### Tip 4. Cap your main loop iterations with a strict safety counter
_Why it matters:_ Unbounded while-loops will drain your API credits if the model gets stuck in an execution cycle.

```
MAX_TURNS = 5
for _ in range(MAX_TURNS):
    # run agent step
```

### Tip 5. Define tools as JSON schema objects directly or extract them with `pydantic.BaseModel.model_json_schema()`
_Why it matters:_ Native schemas eliminate black-box parsing bugs introduced by third-party decorators.

```
schema = {"type": "function", "function": {"name": "get_weather", "parameters": WeatherModel.model_json_schema()}}
```

### Tip 6. Log raw HTTP payloads using `httpx` logging when debugging model outputs
_Why it matters:_ It shows exactly what JSON payload the model received vs what your code processed.

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Tip 7. Return structured error strings from tools back into the context instead of raising exceptions
_Why it matters:_ Passing errors to the model lets it self-correct and attempt alternative tool arguments.

```
except Exception as e:
    return f"Error executing tool: {str(e)}"
```

## Step-by-step procedure

### 1. Step 1: Install official bindings
Install only the essential packages needed for API calls and schema validation.

```python
pip install openai pydantic
```

### 2. Step 2: Define your python tools and schemas
Write standard Python functions and create their corresponding tool definitions.

```python
def add(a: int, b: int) -> str:
    return str(a + b)

tools = [{'type': 'function', 'function': {'name': 'add', 'description': 'Add two numbers', 'parameters': {'type': 'object', 'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}}, 'required': ['a', 'b']}}}]
```

### 3. Step 3: Map tool names to executable functions
Create a dispatch dictionary to map string function names from the model response to real Python code.

```
available_tools = {'add': add}
```

### 4. Step 4: Build the execution loop
Handle model calls, inspect `tool_calls`, run local functions, and pass results back.

```
messages = [{'role': 'user', 'content': 'What is 42 + 58?'}]
while True:
    res = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls:
        break
    for call in msg.tool_calls:
        fn = available_tools[call.function.name]
        args = json.loads(call.function.arguments)
        out = fn(**args)
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': out})
```

### 5. Step 5: Verify agent completion and print final response
Run the script to watch the agent trigger the local Python function and print the evaluated answer.

```python
print(messages[-1].content)
# Output: 42 + 58 is 100.
```

## The mistake almost everyone makes

> ⚠️  Passing raw tool execution failures straight into Python's top-level exception handler. This crashes your script immediately. Fix: Catch errors inside the loop and pass the exception string back as a tool response message so the model can retry with fixed parameters.

## X / Twitter thread (copy-paste ready)

**1/** You do not need a framework to build an AI agent in Python. A simple while-loop and 30 lines of code work better.

**2/** Framework abstractions sound nice until it is 1 AM and you are tracing deep call stacks just to see why a tool payload failed.

**3/** Tip 1: Use raw OpenAI function calling with explicit `messages` state. Keeping state in a basic list gives you total control over tokens.

**4/** Tip 2: Map function names directly to local functions via a dictionary dispatch table instead of complex agent registries.

**5/** Tip 3: Never crash on tool errors. Catch exceptions and send `{'role': 'tool', 'content': f'Error: {err}'}` back to the model so it self-corrects.

**6/** Build your first agent from scratch tonight. You will actually understand how it works. Code sample above.

## LinkedIn version

It was 1 AM when I finally uninstalled three agent libraries from my project. I was tired of digging through abstraction layers just to figure out why an LLM tool call returned a malformed dictionary.

Every framework promises magic until you need custom execution logic. Then you realize you are fighting someone else's architecture choices just to run a basic function loop.

Here is the reality: an AI agent is just an LLM sitting inside a loop. The model looks at your conversation history, decides if it needs a tool, and returns a schema. Your code runs that tool locally and hands the output back to the model. That is all.

When you build this loop yourself using plain Python, everything clears up. You manage the context window directly. You validate inputs with Pydantic. You handle errors without mysterious framework crashes.

Stop relying on massive orchestrators for basic tasks. Build the raw loop once so you actually understand how tools and models talk to each other.

python ai automation webdevelopment

_Tags: python, ai, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*