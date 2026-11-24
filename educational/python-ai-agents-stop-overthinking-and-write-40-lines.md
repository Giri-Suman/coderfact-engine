# Python AI Agents: Stop Overthinking and Write 40 Lines

_You don't need LangChain or 12 abstractions to build an agent that actually runs tools._

## Scroll-stopping hooks

**Hook 1.** Spent four hours last night wrestling with massive agent frameworks before realizing an AI agent is literally just a while loop and an API call.

**Hook 2.** Most tutorials make AI agents look like PhD-level architecture, but you can build one in raw Python before your coffee goes cold.

**Hook 3.** If you know how to call an API and parse a dictionary, you already know 90% of how to build an AI agent.

**Hook 4.** Stop installing 400MB dependencies just to ask GPT-4o to check the weather and run a terminal command.

**Hook 5.** I stayed up till 1am debugging an agent loop because I forgot models don't actually run code—they just output JSON saying they want to.

## 7 tips that actually move the needle

### Tip 1. Use the official `openai` client with typed tool definitions instead of generic wrappers
_Why it matters:_ It keeps your stack minimal and avoids silent failure modes hidden inside multi-layer abstractions.

```
tools = [{"type": "function", "function": {"name": "get_stock", "parameters": {...}}}]
```

### Tip 2. Route tool calls using a direct dictionary lookup pattern instead of sprawling `if/else` ladders
_Why it matters:_ It maps the string name returned by the model straight to the callable function cleanly.

```
TOOL_MAP = {"get_stock": get_stock}
result = TOOL_MAP[fn_name](**arguments)
```

### Tip 3. Always validate model-generated arguments with `pydantic` before execution
_Why it matters:_ Models occasionally emit malformed JSON or drop required arguments under token pressure.

```
class QueryArgs(BaseModel): symbol: str
clean = QueryArgs.model_validate_json(raw_json)
```

### Tip 4. Append the tool call AND the tool output back to `messages` history in exact sequence
_Why it matters:_ Skipping the tool response message breaks the conversation schema and crashes the next completion request.

```
messages.append({"role": "tool", "tool_call_id": call.id, "content": str(output)})
```

### Tip 5. Enforce a hard max-iteration safety counter inside your `while` loop
_Why it matters:_ An unconstrained agent will burn your API credits instantly if it gets stuck hallucinating tool params.

```
for _ in range(5):  # hard ceiling instead of while True
```

### Tip 6. Use `pydantic-ai` if you eventually outgrow bare Python scripts
_Why it matters:_ It stays close to vanilla Python and avoids the endless dependency sprawl of older frameworks.

```python
from pydantic_ai import Agent
agent = Agent('openai:gpt-4o')
```

### Tip 7. Log raw completions with `rich.print` during tool loops instead of guessing what was returned
_Why it matters:_ You need to see whether the model chose to call a tool or reply with raw text at 1am.

```python
from rich import print
print(response.choices[0].message.tool_calls)
```

## Step-by-step procedure

### 1. Install the official client
Keep it lean. You only need the official OpenAI SDK and Python 3.10+.

```python
pip install openai
```

### 2. Define a plain Python tool function
Write the exact task you want the agent to execute, returning a string or JSON-serializable value.

```python
def get_system_uptime():
    return "System online: load 0.42, uptime 14 days"
```

### 3. Describe the tool in JSON Schema
Tell the model what the function does and what parameters it accepts so it knows when to trigger it.

```
tools = [{"type": "function", "function": {"name": "get_system_uptime", "description": "Checks server load and uptime."}}]
```

### 4. Send the prompt with tools enabled
Query the model with your message and pass the tools list inside the request.

```python
from openai import OpenAI
client = OpenAI()
messages = [{"role": "user", "content": "How is the server doing?"}]
res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
```

### 5. Execute the tool call and send results back
Check if the model requested a tool, run your local function, push the output to the history, and call the API once more.

```python
msg = res.choices[0].message
if msg.tool_calls:
    messages.append(msg)
    messages.append({"role": "tool", "tool_call_id": msg.tool_calls[0].id, "content": get_system_uptime()})
    final = client.chat.completions.create(model="gpt-4o-mini", messages=messages)
    print(final.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the model's intermediate message containing `tool_calls` before appending the actual tool result. If you send a `role: tool` message without the preceding assistant message that triggered it, the API rejects the payload with a 400 Bad Request.

## X / Twitter thread (copy-paste ready)

**1/** An AI agent isn't magic—it's a while loop, an API call, and a dictionary of local functions.

**2/** Spent half of last night reading framework docs before realizing I could just write this in 40 lines of pure Python.

**3/** Step 1: Write your tool functions as normal Python code, then map their names in a dictionary like `TOOLS = {'run': run}`.

**4/** Step 2: Send the user prompt to OpenAI with `tools=` defined. The model doesn't execute anything—it just outputs JSON with args.

**5/** Step 3: Parse the args, call your local function, and push the output back into the message array with `role: 'tool'`.

**6/** Re-run the completion call and you're done. Build the tiny version first before installing giant frameworks.

## LinkedIn version

Last night around 1am, I caught myself reading 80 pages of framework documentation just to make an AI model read a local file and report back.

It felt ridiculous. Every framework out there adds three layers of abstraction, proprietary schema classes, and 500MB of dependencies for something that is fundamentally straightforward.

An AI agent is not a mysterious black box. Strip away the marketing, and it's a loop: you ask the model a question, it inspects your list of tools, and if it needs one, it returns JSON saying 'please run function X with parameter Y'. Your script runs that function, feeds the output back into the conversation, and asks the model to wrap up.

Once I deleted the third-party agent libraries and wrote the loop in raw Python using just the OpenAI client, everything clicked. It took 40 lines. The debugging became instantaneous, token usage was obvious, and there were no weird internal errors breaking the trace.

Don't let the hype convince you that building practical automation requires complex wrappers. Learn the underlying loop first—you'll save yourself hours of frustration.

#python #automation #softwareengineering #webdevelopment

_Tags: python, aiagents, automation, developers_

---
*By Suman Giri — built with the CoderFact engine.*