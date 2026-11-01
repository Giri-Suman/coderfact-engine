# AI Agents in Python: Build One Without Framework Bloat

_Stop fighting LangChain abstraction layers. Build a functional tool-calling agent loop in 40 lines._

## Scroll-stopping hooks

**Hook 1.** I spent three hours debugging a framework's agent executor last night before realizing it was just an while loop calling a function.

**Hook 2.** You don't need a 50MB framework to build an AI agent—just a clean Python loop and a dictionary of tool functions.

**Hook 3.** Most AI agent tutorials sell you massive abstractions before you even understand what a tool-calling loop actually does.

**Hook 4.** I replaced a buggy LangChain setup with 35 lines of vanilla Python at 1 AM, and it hasn't broken since.

**Hook 5.** If your AI agent framework hides the actual HTTP payload it sends to the model, you're going to hate debugging it later.

## 7 tips that actually move the needle

### Tip 1. Use litellm instead of official SDKs for unified provider API calls
_Why it matters:_ It normalizes function calling across OpenAI, Anthropic, and local Ollama models with a single interface.

```python
from litellm import completion
response = completion(model="gpt-4o", messages=messages, tools=tools)
```

### Tip 2. Map schema tool names directly to Python functions via a dispatch dictionary
_Why it matters:_ Avoids endless `if/elif` statements when the model decides which tool to execute.

```
TOOL_MAP = {"get_weather": get_weather, "search_db": search_db}
output = TOOL_MAP[tool_call.function.name](**json.loads(tool_call.function.arguments))
```

### Tip 3. Set a hard loop limit on your agent's execution while-loop
_Why it matters:_ Prevents runaway API bills when the model gets stuck in an infinite tool-calling loop.

```
MAX_ITERATIONS = 5
while max_iterations > 0:
    max_iterations -= 1
```

### Tip 4. Append the tool's raw output back to the message history with role 'tool'
_Why it matters:_ The LLM needs to see its own requested action and the resulting output in the message chain to formulate the final response.

```
messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(result)})
```

### Tip 5. Typehint your tool functions using Pydantic schemas
_Why it matters:_ You can auto-generate valid JSON schemas for the LLM using Pydantic's built-in schema generator.

```python
from pydantic import BaseModel
class WeatherInput(BaseModel):
    location: str
```

### Tip 6. Use rich.console for terminal output tracing
_Why it matters:_ Seeing model thought processes and tool execution side-by-side saves hours of print-statement debugging.

```python
from rich import print
print(f"[bold blue]Tool Executed:[/bold blue] {result}")
```

### Tip 7. Inject system time into the system message dynamically
_Why it matters:_ LLMs have static cutoffs and will struggle with time-relative queries unless explicitly grounded.

```python
import datetime
system_msg = f"Current time: {datetime.datetime.now().isoformat()}"
```

## Step-by-step procedure

### 1. Step 1: Define your Python tool functions
Write clean Python functions that perform specific tasks like fetching API data or reading local files.

```python
def fetch_user(user_id: str) -> str:
    return f"User {user_id}: Active subscriber"
```

### 2. Step 2: Build the JSON Schema for tool calls
Format your tool descriptions so the LLM understands what arguments it needs to supply.

```
tools = [{
    "type": "function",
    "function": {
        "name": "fetch_user",
        "description": "Fetch status for a user ID",
        "parameters": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"]
        }
    }
}]
```

### 3. Step 3: Initialize your message stack
Create a list containing your system instructions and the initial user request.

```
messages = [
    {"role": "system", "content": "You are an assistant with access to user tools."},
    {"role": "user", "content": "Check the status of user_123"}
]
```

### 4. Step 4: Implement the execution while-loop
Query the model, check if it wants to invoke a tool, run the function, and append the output to your message array.

```python
from litellm import completion
import json

while True:
    res = completion(model="gpt-4o", messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls:
        break
    for tool in msg.tool_calls:
        val = fetch_user(**json.loads(tool.function.arguments))
        messages.append({"role": "tool", "tool_call_id": tool.id, "content": val})
```

### 5. Step 5: Verify the final text output
Print the final message content from the model once all tool calls are processed and the loop exits.

```python
print(messages[-1].content)
# Output: User user_123 is currently an active subscriber.
```

## The mistake almost everyone makes

> ⚠️  Passing tool results back as standard 'user' or 'system' messages instead of using the proper 'tool' role with a matching `tool_call_id`. The API will reject the request or hallucinate state. Fix: match the `tool_call_id` from the model's call exactly.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a 500-page framework to build your first AI agent in Python. Here is how it actually works under the hood 🧵

**2/** At its core, an agent isn't magic—it is just an LLM sitting inside a standard Python while-loop with permission to ask you to run functions.

**3/** 1. Define plain Python functions for the tasks you want done (e.g., querying a database or hitting an API endpoint).

**4/** 2. Pass JSON schemas of those functions to the LLM via litellm. The model responds with JSON telling you which function to execute.

**5/** 3. Execute that function in your code, attach the result back to the message list under the 'tool' role, and call the API again.

**6/** Strip away the framework bloat and you have an agent in under 40 lines. Build the loop yourself first so you actually know how to debug it.

## LinkedIn version

I stayed up until 1 AM last night fighting a massive abstraction layer in an AI framework. Every time something broke, I had to dig through five layers of wrappers just to find out what payload was sent to the model.

So I threw out the dependency and rewrote the logic. Turns out, an AI agent isn't black magic—it's just a Python while-loop with access to a function registry.

You pass the model a list of tools defined as JSON schemas. The model responds saying, "Hey, run `get_user_data` with argument `id=102`." You parse that JSON in Python, execute your actual code, pass the output back into the array, and let the model finish its thought.

Building this manually takes less than 40 lines of code. No opaque abstractions, no broken background chains, and no mystery bugs hiding deep in third-party libraries.

Frameworks are great once you hit scale, but if you haven't built an agent loop from scratch with plain Python, you're going to spend hours guessing when things fail.

#python #aiengineering #softwaredevelopment #coding

_Tags: python, aiagents, backend, automation_

---
*By Suman Giri — built with the CoderFact engine.*