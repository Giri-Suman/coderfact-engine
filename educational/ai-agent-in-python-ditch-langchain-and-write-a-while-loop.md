# AI agent in Python: ditch LangChain and write a while loop

_Stop overcomplicating agents with heavy abstractions. A while-loop and tool calls get it done._

## Scroll-stopping hooks

**Hook 1.** Most dev tutorials make AI agents look like dark magic with 15 nested abstractions, but it's literally just a while-loop handling JSON.

**Hook 2.** Spent until 1am wrestling with an agent framework before realizing 40 lines of raw Python does the exact same thing faster.

**Hook 3.** You do not need LangChain, CrewAI, or an enterprise SDK to build your first working Python agent today.

**Hook 4.** An AI agent is just an LLM that knows how to spit out structured tool calls until it decides it's finished talking.

**Hook 5.** I was genuinely annoyed last night when I stripped out three libraries and my agent suddenly became reliable.

## 7 tips that actually move the needle

### Tip 1. Use standard litellm instead of provider-specific SDKs
_Why it matters:_ It gives you a consistent OpenAI-compatible interface across every model provider without lock-in.

```python
from litellm import completion
resp = completion(model="gpt-4o-mini", messages=messages, tools=tools)
```

### Tip 2. Define tools with pydantic schemas rather than raw dicts
_Why it matters:_ It guarantees type validation on LLM arguments before your code executes them.

```python
from pydantic import BaseModel
class WeatherArgs(BaseModel):
    city: str
```

### Tip 3. Keep a strict max_iterations counter in your execution loop
_Why it matters:_ Prevents infinite tool-calling loops that silently drain your API credits at 2am.

```
for _ in range(10):
    if done: break
```

### Tip 4. Inspect raw message history with rich.print
_Why it matters:_ Pretty-printing the exact tool calls and role payloads makes prompt bugs obvious instantly.

```python
from rich import print
print(messages)
```

### Tip 5. Return plain strings from your tool runner functions
_Why it matters:_ LLMs digest concise string errors and results far better than complex serialized structures.

```python
def run_tool(name, args):
    return f"Error: {e}" if err else str(result)
```

### Tip 6. Run local checks with ollama before spending API credits
_Why it matters:_ Lets you debug your while-loop flow entirely offline using small function-calling models.

```
ollama run llama3.1
```

### Tip 7. Store tools in a simple dictionary mapping name to function
_Why it matters:_ Avoids messy dynamic dispatching or metaprogramming when routing model calls.

```
tool_map = {"get_weather": fetch_weather}
result = tool_map[call.function.name](**args)
```

## Step-by-step procedure

### 1. Install litellm and define your tool registry
Install litellm and create a dictionary mapping string names to standard Python functions.

```python
import json
from litellm import completion
def get_weather(city: str): return f"28°C, sunny in {city}"
registry = {"get_weather": get_weather}
```

### 2. Declare the tool schema for the model
Write the OpenAI-format tool declaration describing the function and arguments.

```
tools = [{"type": "function", "function": {"name": "get_weather", "description": "Get city weather", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
```

### 3. Initialize conversation history
Create a standard list with a user prompt that clearly requires tool execution.

```
messages = [{"role": "user", "content": "What is the weather in Kolkata right now?"}]
```

### 4. Implement the core agent loop
Call the LLM, append its response, execute any tool calls, and feed the output back into the message list.

```
while True:
    res = completion(model="gpt-4o-mini", messages=messages, tools=tools).choices[0].message
    messages.append(res)
    if not res.tool_calls: break
    for call in res.tool_calls:
        args = json.loads(call.function.arguments)
        out = registry[call.function.name](**args)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": str(out)})
```

### 5. Print the final output to verify completion
Inspect the final assistant message once the while-loop breaks to confirm it answered using the tool output.

```python
print(messages[-1].content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's intermediate tool_calls message back to the messages list before appending the role='tool' response, which triggers a schema validation error from the API. Always append the message containing the tool calls first, then the tool results matched by tool_call_id.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a heavy framework to build an AI agent in Python. Here's the raw loop that does it in under 40 lines:

**2/** At 1am yesterday I threw out a massive agent dependency. An agent is literally an LLM in a while loop that halts when tool_calls is empty.

**3/** Step 1: Set up a plain python dictionary of tools, like `registry = {'fetch_db': fetch_db}`. Skip dynamic magic.

**4/** Step 2: Hit litellm.completion with your tools array. It works identical across OpenAI, Anthropic, or local Ollama.

**5/** Step 3: If `message.tool_calls` exists, execute the func, append `role: 'tool'`, and loop. If not, break and return the text.

**6/** Strip out the boilerplate. Build the simple loop once so you actually understand what your tools are doing under the hood.

## LinkedIn version

I stayed up until 1am yesterday debugging an agent framework that refused to pass arguments cleanly to a local script. Stack traces 30 layers deep, weird abstractions, and zero visibility into what was actually breaking.

So I killed the entire virtualenv and started over with zero agent libraries.

Here is the dirty secret: an AI agent is literally just a while-loop. You pass a list of messages and tool schemas to an LLM. If the model responds with function calls, you run those functions locally, append the output to the history with role 'tool', and loop again. When it returns raw text without calls, you break the loop.

That's the whole architecture. No chain abstractions, no mystery wrappers, no vendor lock-in. Just 30 lines of Python using litellm and native dictionaries.

If you want to understand agents, build the bare-metal loop yourself before touching a third-party framework. It saves hours of frustration and actually works.

#python #ai #softwareengineering #developer

_Tags: python, ai, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*