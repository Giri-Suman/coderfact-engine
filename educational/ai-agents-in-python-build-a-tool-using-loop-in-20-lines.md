# AI Agents in Python: Build a Tool-Using Loop in 20 Lines

_Stop paying for fancy agent frameworks when a basic WHILE loop and an API call do the exact same thing._

## Scroll-stopping hooks

**Hook 1.** I stayed up till 2am debugging LangChain abstractions just to realize a 15-line Python loop with native tool calling does the exact same job.

**Hook 2.** Most 'AI agent' frameworks are just bloated wrappers around a while loop that checks if the model wants to call a function.

**Hook 3.** You don't need a massive framework to build an AI agent—just raw Python, the OpenAI SDK, and a simple execution loop.

**Hook 4.** I spent three hours fixing a broken agent orchestration library before I wiped the script and built my own agent from scratch in 20 lines.

**Hook 5.** If your AI agent breaks every time a dependency updates, you built a wrapper on a wrapper. Here is how to build one using plain Python.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate JSON schemas for your Python functions
_Why it matters:_ Manually writing OpenAI tool definitions in raw JSON is annoying and breaks the moment you change a function argument.

```python
from pydantic import TypeAdapter
schema = TypeAdapter(my_function).json_schema
```

### Tip 2. Bind your execution loop to a strict while state instead of recursing
_Why it matters:_ Recursive agent calls will blow through your API credits in seconds if the model gets stuck in a loop.

```
while response.choices[0].finish_reason == 'tool_calls':
    execute_and_append()
```

### Tip 3. Execute function calls using a dispatch dictionary instead of eval()
_Why it matters:_ Using eval() on LLM outputs is an instant remote code execution vulnerability.

```
TOOLS = {'get_weather': get_weather}
result = TOOLS[tool_name](**kwargs)
```

### Tip 4. Pass tool response messages back with the matching tool_call_id
_Why it matters:_ The OpenAI API completely rejects the conversation history if the tool payload ID does not match the assistant prompt ID.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(res)})
```

### Tip 5. Set system prompts that explicitly force JSON tool arguments
_Why it matters:_ Models occasionally dump plain text inside arguments unless forced by system instructions.

```
system_prompt = 'You are an agent. Use tools for real-time data. Never guess.'
```

### Tip 6. Use rich.live to stream agent thoughts and tool calls in your CLI
_Why it matters:_ Watching a blank terminal for 10 seconds while the agent works makes you think your script froze.

```python
from rich.console import Console
console.log(f'[bold blue]Calling {tool_name}...')`
```

### Tip 7. Add a hard break flag after 5 loop iterations
_Why it matters:_ It prevents runaway agent loops when an LLM fails to satisfy its stopping condition.

```
if iterations > 5:
    raise TimeoutError('Agent loop limit reached')
```

## Step-by-step procedure

### 1. Step 1: Define your raw Python tools
Write standard Python functions with clear type hints and docstrings. The docstrings become the instructions for the model.

```python
def fetch_order_status(order_id: str) -> str:
    """Fetches shipping status for a given order ID."""
    return f"Order {order_id} is currently in transit."
```

### 2. Step 2: Map tools to the OpenAI Tool Schema
Register the function signature so the LLM knows what tools it can request.

```
tools = [{
    "type": "function",
    "function": {
        "name": "fetch_order_status",
        "description": "Fetches shipping status for a given order ID.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"]
        }
    }
}]
```

### 3. Step 3: Initialize your message history
Set up the initial system instructions and the user prompt in a standard dictionary format.

```
messages = [
    {"role": "system", "content": "You answer questions using tools."},
    {"role": "user", "content": "Where is my parcel #9941?"}
]
```

### 4. Step 4: Build the execution while loop
Call the API, check if the LLM wants to invoke a tool, run the function locally, and feed the output back into the message array.

```python
import json
from openai import OpenAI
client = OpenAI()

for _ in range(5):
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls:
        break
    for call in msg.tool_calls:
        args = json.loads(call.function.arguments)
        out = fetch_order_status(**args)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
```

### 5. Step 5: Print the final assistant response
Once the loop finishes without requesting more tools, extract and display the final textual answer.

```python
print(messages[-1].content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's initial response (containing the tool_calls request) back to the messages array before sending the tool output. If you only send the tool output, the API throws an invalid messages payload error. Make sure to append `res.choices[0].message` first, then your tool response.

## X / Twitter thread (copy-paste ready)

**1/** I spent half my night fighting third-party agent framework abstractions—so I scrapped them and built one from scratch in raw Python.

**2/** Turns out an 'AI Agent' isn't magic. It's just a while loop checking if an LLM wants to run a function on your machine.

**3/** Step 1: Write pure Python functions with clear docstrings and map them to your LLM's function schema.

**4/** Step 2: Create a dispatch dictionary mapping function names to execution logic. Avoid eval() like the plague.

**5/** Step 3: Run a loop that appends tool outputs back to the chat array using the exact tool_call_id returned by the API.

**6/** Stop pulling in 50 heavy dependencies for basic tasks. Build your execution loop yourself and actually control your pipeline.

## LinkedIn version

It was 1:30 AM, and I was staring at a 400-line stack trace from an agent framework I imported to handle a basic workflow at CoderFact.

All I wanted was to let an LLM run a couple of local Python utility functions, read the output, and give me a summary. Instead, I was fighting broken abstractions, hidden internal prompts, and dependencies that updated overnight.

So I wiped the file and wrote a simple execution loop from scratch using raw Python and the standard OpenAI SDK.

It took 20 lines of code. The logic is straightforward: send the prompt to the API, check if the response contains function requests, map those requests to a local dictionary of functions, and pass the results right back into the message history array inside a basic while loop.

No black boxes. No heavy frameworks breaking every update cycle. Just pure Python doing exactly what it was written to do.

python #ai #backend #automation #developer

_Tags: python, aiagents, openai, automation_

---
*By Suman Giri — built with the CoderFact engine.*