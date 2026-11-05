# AI agent in Python: Build one from scratch without framework bloat

_Stop wrestling with massive frameworks—a simple while-loop and tool calls get you 90% there._

## Scroll-stopping hooks

**Hook 1.** I spent 3 hours debugging LangChain abstraction layers last night before realizing a simple while-loop in vanilla Python does the exact same thing.

**Hook 2.** Most AI agent tutorials sell you massive frameworks you don't need—here's how to build one with just `openai` and standard Python functions.

**Hook 3.** Your first Python AI agent doesn't need a vector database, 10 dependencies, or a complex graph—it just needs a execution loop.

**Hook 4.** I finally stopped fighting agent framework black magic at 1 AM and wrote a 40-line Python loop that actually works.

**Hook 5.** Building an AI agent is literally just giving a model access to functions and looping until it stops asking to call them.

## 7 tips that actually move the needle

### Tip 1. Use the official `openai` SDK with `tools` instead of wrapper libraries
_Why it matters:_ It gives you full visibility into the raw message history and tool payload structures.

```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model='gpt-4o', messages=msgs, tools=my_tools)
```

### Tip 2. Define tool schemas using standard Python type hints via Pydantic
_Why it matters:_ It handles JSON schema generation automatically so you don't write raw schemas by hand.

```python
from pydantic import BaseModel, Field
class FetchUrl(BaseModel):
    url: str = Field(description='The target web address')
```

### Tip 3. Bind native Python functions to a dispatch dictionary
_Why it matters:_ It keeps your tool execution logic map clean and eliminates massive `if-elif` chains.

```
REGISTRY = {'get_weather': get_weather, 'run_query': run_query}
result = REGISTRY[tool_call.function.name](**json.loads(tool_call.function.arguments))
```

### Tip 4. Append tool outputs back to the message array using the `tool` role
_Why it matters:_ The LLM requires the exact `tool_call_id` in history to correlate responses.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### Tip 5. Cap your execution loop using a strict `max_iters` variable
_Why it matters:_ It prevents runaway agent loops from draining your API credits when tool calls fail.

```
for _ in range(MAX_ITERS):
    # agent logic here
else:
    raise TimeoutError('Agent hit max iterations')
```

### Tip 6. Print colored terminal outputs with `rich.console` for debugging step transitions
_Why it matters:_ You need clear visually separated logs to track what the model thinks vs what the tools return.

```python
from rich import print
print(f'[bold green]Tool Call:[/bold green] {call.function.name}')
```

### Tip 7. Use `python-dotenv` to isolate environment variables from code
_Why it matters:_ Hardcoding keys causes accidental git leaks—load them once at the script entrypoint.

```python
from dotenv import load_dotenv
load_dotenv()
```

## Step-by-step procedure

### 1. Install the core dependencies
Grab the bare minimum packages needed to talk to the API and parse types.

```python
pip install openai pydantic python-dotenv
```

### 2. Define a concrete Python function to serve as a tool
Write a normal function that returns a string or standard data type.

```python
def get_system_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()
```

### 3. Format the function metadata for the API
Create the tool definition payload so the model knows when and how to call it.

```
tools = [{
    'type': 'function',
    'function': {
        'name': 'get_system_time',
        'description': 'Returns current system timestamp',
        'parameters': {'type': 'object', 'properties': {}}
    }
}]
```

### 4. Build the while-loop execution engine
Construct the main cycle that calls the API, runs requested functions, and appends results.

```
messages = [{'role': 'user', 'content': 'What time is it right now?'}]
while True:
    res = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: break
    for call in msg.tool_calls:
        out = get_system_time()
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': out})
```

### 5. Verify the final output response
Run your script to ensure the agent executes the tool and delivers a natural language answer.

```python
print(messages[-1]['content'])
```

## The mistake almost everyone makes

> ⚠️  Forgetting to push the assistant's intermediate message containing `tool_calls` back into the history before appending the `tool` response message. Fix: always do `messages.append(response_message)` right after getting it from the API, *before* running your Python tool functions.

## X / Twitter thread (copy-paste ready)

**1/** Building your first AI agent in Python doesn't require massive frameworks. Here's how to build one from scratch in under 50 lines.

**2/** Frameworks hide the mechanics—which makes debugging a nightmare at 1 AM. An agent is just a loop: LLM decides to call a tool, you run it, pass the result back, repeat.

**3/** Tip 1: Skip heavy abstractions. Use the standard `openai` SDK and pass native functions in the `tools` array.

**4/** Tip 2: Use a central dictionary to map function names to executable Python code: `FUNCS[name](**args)`. Clean and predictable.

**5/** Tip 3: Always cap your agent's while-loop with `max_iters = 5` to stop infinite retry cycles from torching your API budget.

**6/** Try building your execution loop manually first. Once you see the raw control flow, high-level tools make way more sense.

## LinkedIn version

I spent three hours last night wrestling with heavy agent frameworks. The documentation was full of high-level abstractions, but my local code kept crashing inside opaque dependency graphs.

So at 1 AM, I wiped the script and went back to basic Python. No extra libraries, no black-box graph orchestrators—just the raw OpenAI SDK, a couple of custom functions, and a simple `while` loop.

Turns out an AI agent isn't magic. You send your message history to the model with a list of tool definitions. If the model wants data, it hands you a tool call payload. You execute that function locally, append the output to your message array with the matching call ID, and loop back to the model.

Once you build this loop yourself, the mechanics become crystal clear. You see every payload going out and coming back. You control the state, the error handling, and the iteration caps—without fighting framework bloat.

If you're looking to build agents, try writing your first execution loop by hand before reaching for a high-level wrapper. It takes 40 lines of Python and saves hours of late-night debugging.

python textai softwareengineering webdevelopment automation

_Tags: python, aiagents, backend, automation_

---
*By Suman Giri — built with the CoderFact engine.*