# AI Agent in Python: Build a basic tool-calling loop

_Stop paying for fancy orchestration frameworks when 30 lines of raw Python and an API client do the exact same thing._

## Scroll-stopping hooks

**Hook 1.** Most AI agent frameworks are just over-engineered `while` loops wrapping an API call. I spent three hours debugging a black-box abstraction before deleting it and writing 30 lines of plain Python.

**Hook 2.** You don't need LangChain, CrewAI, or AutoGen to build a functional AI agent. You need a `while` loop, a list of JSON schemas, and basic Python function execution.

**Hook 3.** The secret to building an AI agent isn't complex prompt engineering. It's giving an LLM a tool schema and executing the JSON it sends back until it stops asking for tools.

**Hook 4.** I stayed up till 1am figuring out why my LLM kept hallucinating function arguments. Turned out I was overcomplicating agent state when a simple messages array was all it needed.

**Hook 5.** If you can write a standard Python `dict` and a `while` loop, you can build a custom AI agent from scratch in under ten minutes.

## 7 tips that actually move the needle

### Tip 1. Use official OpenAI or Anthropic SDKs directly instead of abstraction layers
_Why it matters:_ It keeps your call stack transparent and makes response debugging instant.

```python
from openai import OpenAI
client = OpenAI()
res = client.chat.completions.create(model="gpt-4o", messages=msgs, tools=tools)
```

### Tip 2. Define tools using Pydantic models and generate schemas automatically
_Why it matters:_ Writing JSON Schema dicts manually is error-prone and wastes dev time.

```python
from pydantic import BaseModel, Field
class WeatherInput(BaseModel):
    location: str = Field(description="City name")
```

### Tip 3. Map function names directly to callable Python functions in a registry dict
_Why it matters:_ Avoids messy `if/elif` chains when executing tool calls returned by the model.

```
TOOL_MAP = {"get_weather": fetch_weather, "search_db": search_db}
result = TOOL_MAP[tool_call.function.name](**json.loads(tool_call.function.arguments))
```

### Tip 4. Append tool execution outputs back into the `messages` array as role `tool`
_Why it matters:_ The model needs the execution result context to answer the user's original query.

```
messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(output)})
```

### Tip 5. Set an explicit `max_iters` safeguard inside your execution loop
_Why it matters:_ Prevents runaway tool-calling loops from draining your API credits when the model gets stuck.

```
max_iters = 5
while max_iters > 0:
    max_iters -= 1
```

### Tip 6. Pass structured error messages back to the LLM when tool calls fail
_Why it matters:_ Modern models will self-correct their input arguments if you return the exception trace.

```
except Exception as e:
    messages.append({"role": "tool", "tool_call_id": tool.id, "content": f"Error: {str(e)}"})
```

### Tip 7. Inspect raw API responses using Python's `logging` module or `rich.print`
_Why it matters:_ Seeing the exact raw JSON response clarifies whether the LLM output tool calls or plain text.

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Step-by-step procedure

### 1. Step 1: Install dependencies and define your local function
Set up a clean virtual environment and install the official OpenAI Python SDK.

```python
pip install openai

def get_weather(location: str):
    return f"22°C and clear in {location}"
```

### 2. Step 2: Declare the tool schema for the API
Define the JSON structure telling the model what function exists and what parameters it accepts.

```
tools = [{
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get current weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"]
        }
    }
}]
```

### 3. Step 3: Initialize the message context array
Store the initial system instruction and the user prompt in a standard Python list.

```
messages = [
    {"role": "system", "content": "You are a helpful assistant with weather tools."},
    {"role": "user", "content": "What is the weather like in Kolkata right now?"}
]
```

### 4. Step 4: Build the while-loop execution engine
Query the API, execute requested tool calls dynamically, and append results back to state.

```python
import json
from openai import OpenAI
client = OpenAI()

while True:
    res = client.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls:
        break
    for tool in msg.tool_calls:
        args = json.loads(tool.function.arguments)
        out = get_weather(**args)
        messages.append({"role": "tool", "tool_call_id": tool.id, "content": str(out)})
```

### 5. Step 5: Print the final model response
Verify that the agent ran the local function, ingested the output, and answered your prompt.

```python
print(messages[-1].content)
# Output: "The weather in Kolkata is currently 22°C and clear."
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the model's intermediate assistant message (containing `tool_calls`) back to the messages array before sending the tool response. If you skip this, the API returns a 400 error because the tool message has no corresponding caller.

## X / Twitter thread (copy-paste ready)

**1/** AI agents aren't magic—they're just function pointers wrapped in a basic while loop. Here's how to build one in 30 lines of Python without third-party frameworks.

**2/** Most agent frameworks hide what's happening under five layers of abstractions. If you want to actually understand tool calling, build the core loop yourself first.

**3/** Step 1: Define your Python functions and write a matching JSON schema object for the LLM API.

**4/** Step 2: Send your query along with the schema array using the official `openai` SDK.

**5/** Step 3: Check if `response.message.tool_calls` exists. If yes, run your local function with those arguments and feed the output back as a `tool` role message.

**6/** Repeat that in a loop until the LLM returns plain text. That's literally the whole agent loop. Simple, inspectable, and zero bloat.

## LinkedIn version

It was 1am when I gave up on debugging an agent framework that was silently failing inside a 10-layer abstract class.

All I wanted was a simple script that fetched API data, processed it, and answered a user query. Instead, I was staring at hidden execution flows and unhelpful tracebacks. So I deleted the library, opened a clean file, and wrote the logic manually.

Turns out, a functional AI agent in Python requires exactly three core parts: a message history array, a tool JSON schema, and a while loop that executes local functions whenever the model requests them.

When the LLM decides it needs real-time data, it hands you a function name and arguments. You run the function, append the result to your message list, and post it back to the API. When it has enough context, it returns plain text and breaks the loop.

Building this from scratch takes about ten minutes and strips away all the magic. Before reaching for heavy external abstractions, write the tool loop yourself—you'll save hours of debugging later.

#python #aiengineering #backend #coding #softwareengineering

_Tags: python, aiagents, openai, webdev_

---
*By Suman Giri — built with the CoderFact engine.*