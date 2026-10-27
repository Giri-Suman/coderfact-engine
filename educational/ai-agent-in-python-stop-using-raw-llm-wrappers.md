# AI Agent in Python: Stop using raw LLM wrappers

_Build a dead-simple Python loop that lets an LLM actually execute code and hit APIs._

## Scroll-stopping hooks

**Hook 1.** Spent until 2am figuring out why my 'AI agent' kept hallucinating false API responses — turns out I just needed a structured execution loop.

**Hook 2.** Most Python AI agent frameworks add 500 layers of abstraction you don't need just to call a function.

**Hook 3.** An AI agent isn't magic, it's literally just a `while` loop feeding tool outputs back into a system prompt.

**Hook 4.** If you can write a standard Python function with type hints, you already know how to build a custom AI agent.

**Hook 5.** Stop importing massive agent frameworks until you've built one from scratch with standard library tools and basic API calls.

## 7 tips that actually move the needle

### Tip 1. Use pydantic-ai or instructor instead of parsing raw JSON strings from the model
_Why it matters:_ It handles retry logic automatically when the LLM outputs malformed schemas.

```python
from pydantic import BaseModel
class Response(BaseModel):
    action: str
    query: str
```

### Tip 2. Bind native Python functions using OpenAI's tools parameter directly
_Why it matters:_ It forces the model to return structured tool calls rather than guessing text formats.

```
tools = [{'type': 'function', 'function': {'name': 'get_weather'}}]
response = client.chat.completions.create(model='gpt-4o', messages=msgs, tools=tools)
```

### Tip 3. Set a hard loop limit inside your message execution while-loop
_Why it matters:_ It stops your agent from burning through your API quota when it gets stuck in an infinite tool-calling recursion.

```
MAX_TURNS = 5
for _ in range(MAX_TURNS):
    if not response.choices[0].message.tool_calls: break
```

### Tip 4. Append tool execution outputs back to the message history as 'tool' role messages
_Why it matters:_ The model needs the literal execution result in context to formulate its next step or final answer.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### Tip 5. Log raw LLM inputs and outputs using rich or icecream instead of generic print statements
_Why it matters:_ You need to see the exact message payload order to debug context window corruptions.

```python
from icecream import ic
ic(response.choices[0].message)
```

### Tip 6. Use duckduckgo-search for zero-API-key web access inside your tools
_Why it matters:_ It gives your agent real-time web capabilities without signing up for expensive search APIs.

```python
from duckduckgo_search import DDGS
results = DDGS().text('python news', max_results=3)
```

### Tip 7. Isolate tool execution using Python's built-in subprocess module for local side-effects
_Why it matters:_ It prevents buggy agent actions from cluttering your main runtime memory state.

```python
import subprocess
out = subprocess.run(['ls', '-la'], capture_output=True, text=True).stdout
```

## Step-by-step procedure

### 1. Step 1: Define your execution tools as pure functions
Write clean Python functions with docstrings and type hints for the tasks your agent needs to perform.

```python
def calculate(expression: str) -> str:
    """Evaluates a math expression."""
    return str(eval(expression))
```

### 2. Step 2: Map function signatures to LLM tool definitions
Create a dictionary array defining the tool names and expected arguments for the API payload.

```
tools = [{'type': 'function', 'function': {'name': 'calculate', 'description': 'Evaluates math', 'parameters': {'type': 'object', 'properties': {'expression': {'type': 'string'}}, 'required': ['expression']}}}]
```

### 3. Step 3: Initialize your context array and prompt
Set up a standard message context with systemic instructions on how and when to use tools.

```
messages = [{'role': 'system', 'content': 'You are a helpful assistant. Use tools when needed.'}, {'role': 'user', 'content': 'What is 42 * 1337?'}]
```

### 4. Step 4: Build the execution while-loop
Send messages to the model, inspect if it wants to invoke a tool, and route the execution locally.

```
response = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
msg = response.choices[0].message
messages.append(msg)
```

### 5. Step 5: Run the tool and feed the payload back
Execute the matching function based on tool_calls, collect the output string, and pass it back to the context.

```
if msg.tool_calls:
    tool_call = msg.tool_calls[0]
    res = calculate(json.loads(tool_call.function.arguments)['expression'])
    messages.append({'role': 'tool', 'tool_call_id': tool_call.id, 'content': res})
```

### 6. Step 6: Trigger the final response generation
Call the completions endpoint one last time so the model synthesizes the executed output into a human-readable reply.

```python
final_res = client.chat.completions.create(model='gpt-4o', messages=messages)
print(final_res.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Passing raw non-string objects (like dicts or ints) back as the tool content in message history. The OpenAI/Anthropic APIs will throw validation errors — always cast your tool returns to `str()` or JSON strings before appending.

## X / Twitter thread (copy-paste ready)

**1/** Most developers overcomplicate AI agents — it's literally just a loop calling local Python functions.

**2/** I spent hours debugging black-box frameworks before throwing them out to build a plain agent loop in under 30 lines.

**3/** Tip 1: Define plain Python functions and map them directly using the native `tools` parameter in OpenAI or Anthropic SDKs.

**4/** Tip 2: Wrap your execution logic in a bounded `while` loop — never let an agent run unbounded or it will burn through your API key.

**5/** Tip 3: Always stringify tool outputs before appending them back into the message payload as a `tool` role message.

**6/** Build it raw first to understand the architecture, then pick a framework. Full step-by-step code in my CoderFact drop.

## LinkedIn version

It was 1am, and I was staring at a cryptic stack trace coming from a massive third-party agent framework. All I wanted was an LLM that could query a local database and format a weekly digest. Instead, I had five layers of abstraction breaking on a simple dictionary format.

So I scrubbed the imports and went back to standard Python. Turns out, an AI agent isn't some mystical pattern — it's just a while-loop that knows how to route JSON function calls to actual code.

Here's what changed my perspective: when you pass a list of native functions to an LLM via tool declarations, the model doesn't execute anything. It just responds with a structured JSON string saying, 'Hey, run this function with these arguments.' You execute it locally, stringify the output, attach it back to the message history, and make one more API call.

Once you build this loop manually using plain Python and the base SDK, you realize you don't need heavy abstractions for 90% of automation tasks. You keep complete control over execution, context window limits, and error handling.

If you've been putting off building automated agents because the popular libraries seem bloated, write a raw loop first. It takes 30 lines of code and actually makes sense.

#python #ai #developer #automation #coderfact

_Tags: python, aiagents, backend, automation_

---
*By Suman Giri — built with the CoderFact engine.*