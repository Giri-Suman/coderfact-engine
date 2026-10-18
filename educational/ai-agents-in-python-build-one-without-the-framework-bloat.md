# AI Agents in Python: Build One Without the Framework Bloat

_Stop fighting massive agent frameworks. Build a functional tool-calling loop in 40 lines of clean Python._

## Scroll-stopping hooks

**Hook 1.** I spent three hours debugging LangChain abstraction layers last night before deleting the whole repo and writing a 30-line while loop.

**Hook 2.** Most tutorials make AI agents sound like sci-fi magic, but an agent is literally just a model running inside a while loop until it stops calling functions.

**Hook 3.** If your AI agent needs six nested class wrappers just to check the weather, you aren't building a product — you're adopting someone else's tech debt.

**Hook 4.** Realized at 1 AM that everyone overcomplicates Python agents when all you need is the native OpenAI client and a basic dictionary dispatch.

**Hook 5.** You don't need a massive orchestration framework to build your first agent — you just need Python functions with docstrings and a clean termination check.

## 7 tips that actually move the needle

### Tip 1. Use Pydantic v2 to define tool arguments cleanly instead of hand-writing JSON schemas.
_Why it matters:_ It handles type validation out of the box and converts straight to OpenAI-compatible function schemas.

```python
from pydantic import BaseModel
class LookupUser(BaseModel):
    user_id: int
```

### Tip 2. Map function execution via a plain Python dictionary lookup instead of messy eval or getattr tricks.
_Why it matters:_ It keeps your tool execution sandboxed, explicit, and easy to trace when debugging at night.

```
TOOLS = {'get_weather': get_weather, 'run_query': run_query}
result = TOOLS[func_name](**func_args)
```

### Tip 3. Enforce strict schemas with json_schema in the official openai package.
_Why it matters:_ Setting strict=True guarantees the model returns parameters matching your exact types every time.

```
client.chat.completions.create(model='gpt-4o-mini', tools=tools, tool_choice='auto')
```

### Tip 4. Set an explicit max_iterations counter inside your execution loop.
_Why it matters:_ Without a hard stop, an ambiguous prompt will trap your script in an infinite API burn loop.

```
for _ in range(5):
    # run agent loop
else: raise RuntimeError('Agent loop exceeded limit')
```

### Tip 5. Append the tool execution result straight back to the conversation history as role='tool'.
_Why it matters:_ The model needs to see its own tool_call_id mapped to the return data to produce the final response.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### Tip 6. Use rich.console to print your agent thought steps and tool inputs.
_Why it matters:_ Debugging terminal state across multiple tool hops is impossible without color-coded outputs.

```python
from rich.console import Console
console = Console()
console.log(f'[bold green]Calling tool:[/bold green] {func_name}')
```

### Tip 7. Store raw prompt/response traces locally using sqlite3 or plain jsonlines.
_Why it matters:_ When an agent fails silently, inspecting the raw JSON payloads reveals prompt drift instantly.

```python
import json
with open('agent_trace.jsonl', 'a') as f:
    f.write(json.dumps(messages) + '\n')
```

## Step-by-step procedure

### 1. Install the official client
Skip the third-party wrappers and install just the official client library.

```python
pip install openai
```

### 2. Define a plain Python tool and its JSON schema
Write the function that actually executes your local logic, along with its parameter definition.

```python
def get_order_status(order_id: str):
    return f'Order {order_id} is shipped.'

tools = [{'type': 'function', 'function': {'name': 'get_order_status', 'description': 'Check order status', 'parameters': {'type': 'object', 'properties': {'order_id': {'type': 'string'}}, 'required': ['order_id']}}}]
```

### 3. Initialize message history with a clear system directive
Give the model a job and supply the user's initial prompt inside the message stack.

```
messages = [{'role': 'system', 'content': 'Use provided tools to answer queries.'}, {'role': 'user', 'content': 'Where is order #9482?'}]
```

### 4. Call the API and check for tool calls
Hit the completion endpoint and inspect whether the model chose to invoke a tool.

```python
from openai import OpenAI
client = OpenAI()
res = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
msg = res.choices[0].message
messages.append(msg)
```

### 5. Execute the tool and append the output
Parse the arguments, invoke your local function, and append the payload back to the conversation.

```python
import json
for call in msg.tool_calls or []:
    args = json.loads(call.function.arguments)
    out = get_order_status(**args)
    messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': out})
```

### 6. Run the final completion pass and print the answer
Send the updated history back to the model so it can formulate the final user-facing string.

```python
final = client.chat.completions.create(model='gpt-4o-mini', messages=messages)
print(final.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to send both the assistant message containing tool_calls AND the subsequent role='tool' message back to the API. If you omit the assistant's calling record or mix up tool_call_id, the API immediately throws a 400 validation error.

## X / Twitter thread (copy-paste ready)

**1/** Most developers overcomplicate Python AI agents with heavy frameworks when you can build one in raw Python in 10 minutes. Thread:

**2/** At 1am last night, I ditched a bloated agent dependency. An agent is just a while loop: model decides what to do, you run the code, you return the output.

**3/** First step: define a plain dictionary for function execution. Don't touch eval. Map names to actual callables so you can trace what executes.

**4/** Next: always cap execution with a hard max_iterations check. If the model gets stuck calling tools recursively, you won't blow your API budget.

**5/** Pass tool outputs back with role='tool' and the exact matching tool_call_id. The model needs its own context back to write the final response.

**6/** Build it from scratch once before installing heavy abstractions. What tool are you planning to wire up to an agent first?

## LinkedIn version

Last night at 1:00 AM, I was fighting a tangled web of framework abstractions just trying to get an AI to check a mock database status.

Every error message pointed five layers deep into wrapper code I didn't write and couldn't easily patch. So I deleted the entire virtualenv, pulled up a blank Python file, and wrote out the logic with just the standard OpenAI client.

Here is the reality: an AI agent isn't complex machinery. It is an LLM running inside a loop. The model looks at your schema, outputs a tool name with JSON arguments, your script executes the function, and you append the output back to the message list until the model decides it has enough data to respond.

Once you build this loop yourself with basic dictionaries and control flow, the mystique around 'agentic architectures' completely vanishes. You understand the token cost, you control the timeout bounds, and you can debug it with simple print statements.

Start bare-bones with raw Python before you hand over control of your application flow to third-party abstractions.

#python #softwareengineering #ai #developers #automation

_Tags: python, openai, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*