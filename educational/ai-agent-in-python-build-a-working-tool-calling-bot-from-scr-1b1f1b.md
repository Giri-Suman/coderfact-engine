# AI Agent in Python: Build a working tool-calling bot from scratch

_Stop overcomplicating agents with heavy frameworks. Here is how you build one in 40 lines of clean Python._

## Scroll-stopping hooks

**Hook 1.** Most developers spend three days fighting LangChain abstractions when a simple while-loop and tool-calling array does the job in 40 lines of Python.

**Hook 2.** I spent half my night figuring out why my AI agent kept hallucinating arguments until I realized I was over-engineering the prompt instead of enforcing JSON schemas.

**Hook 3.** You don't need a massive framework to build a Python AI agent—just the official OpenAI SDK, a function map, and a loop that knows when to stop.

**Hook 4.** Spent way too long at 1am trying to make an LLM run real code—turns out tool calling in Python is dead simple once you strip out the third-party wrapper bloat.

**Hook 5.** If your AI agent breaks every time an API changes, stop using black-box libraries and write the execution loop yourself.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate strict JSON schemas for your Python tools instead of writing raw dictionaries.
_Why it matters:_ It prevents model hallucinations by enforcing exact parameter types before the LLM ever sees the schema.

```python
from pydantic import BaseModel, Field
class SearchArgs(BaseModel):
    query: str = Field(description='The exact web search query')
```

### Tip 2. Bind native Python functions to your model calls using a standard map pattern instead of string parsing.
_Why it matters:_ Mapping the tool name directly to a callable function avoids fragile if-else routing blocks.

```
TOOL_MAP = {'get_weather': get_weather, 'run_query': run_query}
output = TOOL_MAP[tool_call.function.name](**json.loads(tool_call.function.arguments))
```

### Tip 3. Set target parameters to max_completion_tokens and rely on standard stop sequences to keep loops tight.
_Why it matters:_ Uncapped agent responses lead to infinite tool-execution loops that drain your API credits.

```
response = client.chat.completions.create(model='gpt-4o-mini', messages=msgs, tools=tools, max_tokens=300)
```

### Tip 4. Append tool execution results back to the message history with role set explicitly to tool.
_Why it matters:_ The model needs to see its own call history paired with your function's response to formulate the next step.

```
msgs.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### Tip 5. Pass strict=True in your tool definitions when calling OpenAI or local vLLM endpoints.
_Why it matters:_ It forces the model to strictly output valid JSON matching your schema structure 100% of the time.

```
tools = [{'type': 'function', 'function': {'name': 'fetch', 'strict': True, 'parameters': schema}}]
```

### Tip 6. Set up tenacity retry decorators around your raw execution functions.
_Why it matters:_ Flaky external APIs will kill your agent's loop mid-task if you don't handle network blips gracefully.

```python
from tenacity import retry, stop_after_attempt
@retry(stop=stop_after_attempt(3))
def call_api(url): return requests.get(url).json()
```

### Tip 7. Log raw LLM tool calls using python-json-logger rather than standard print statements.
_Why it matters:_ You need structured output to debug multi-step loop failures when an agent gets stuck in a recursive call.

```python
import logging; from pythonjsonlogger import jsonlogger
logger.addHandler(jsonlogger.JsonFormatter())
```

## Step-by-step procedure

### 1. Step 1: Install the native SDKs
Grab the official OpenAI SDK and Pydantic—skip the heavy orchestration frameworks for now.

```python
pip install openai pydantic
```

### 2. Step 2: Define your core executable function
Write a standard Python function that handles a real task, like fetching system stats or hitting a clean API.

```python
def get_system_load():
    import os
    return f'Load average: {os.getloadavg()}'
```

### 3. Step 3: Build the JSON tool schema
Structure the schema so the model understands when and how to trigger your local Python function.

```
tools = [{
    'type': 'function',
    'function': {
        'name': 'get_system_load',
        'description': 'Returns current CPU load averages.',
        'parameters': {'type': 'object', 'properties': {}, 'required': []}
    }
}]
```

### 4. Step 4: Implement the basic execution loop
Create a loop that calls the model, checks if it requested a tool call, executes the Python code, and feeds the answer back.

```python
from openai import OpenAI
import json
client = OpenAI()
msgs = [{'role': 'user', 'content': 'Is the server running hot right now?'}]
TOOL_MAP = {'get_system_load': get_system_load}

while True:
    res = client.chat.completions.create(model='gpt-4o-mini', messages=msgs, tools=tools)
    msg = res.choices[0].message
    msgs.append(msg)
    if not msg.tool_calls:
        print('Final Answer:', msg.content)
        break
    for call in msg.tool_calls:
        fn = TOOL_MAP[call.function.name]
        out = fn(**json.loads(call.function.arguments))
        msgs.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(out)})
```

### 5. Step 5: Run and verify the complete flow
Execute the script and verify that the model successfully triggers the tool, reads the real system return, and prints the final output.

```
python agent.py
# Output: Final Answer: The server load is currently low at (0.42, 0.38, 0.31).
```

## The mistake almost everyone makes

> ⚠️  Forgetting to push the model's initial tool_calls message into the message history array before pushing the tool execution output. The API will throw a 400 validation error—always append the assistant's response message first.

## X / Twitter thread (copy-paste ready)

**1/** Building your first AI agent in Python doesn't require a bloated 10-dependency framework.

**2/** Most 'agent frameworks' are just abstraction wrappers around a basic while-loop and tool routing array.

**3/** Start with native functions. Define your functions, wrap them in clean Pydantic schemas, and map function names to executable callables.

**4/** Use a simple while-loop. If the model returns `tool_calls`, execute your local Python script and append the result back to the payload.

**5/** Always set `strict=True` on your JSON schemas to stop the model from passing invalid arguments that crash your code.

**6/** Strip out the bloat and build it yourself first. Check the full working Python snippet in the drop below.

## LinkedIn version

It was 1am and I was fighting framework abstractions again.

All I wanted was a clean Python script that could read system metrics, decide if something was wrong, and hit a webhook. Instead, I was five levels deep in wrapper stack traces trying to figure out why an internal chain class was stripping out my function arguments.

So I threw out the third-party framework and wrote it from scratch using plain Python and the native SDK.

Turns out an AI agent isn't magic—it's literally just a while-loop. The model gets your prompt, decides if it needs to call a tool, hands you the JSON arguments, and waits for you to feed the result back in. That's it.

Once you build the loop yourself, you realize you don't need heavy abstractions for 90% of use cases. You just need clear tool definitions, strict Pydantic parsing, and a clean function map.

#python #ai #automation #developers #softwareengineering

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*