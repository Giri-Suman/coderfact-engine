# AI Agents in Python: Build one from scratch without bloated frameworks

_Stop fighting LangChain docs. You only need 40 lines of clean Python and an LLM API._

## Scroll-stopping hooks

**Hook 1.** Most tutorials hand you a massive LangChain dependency tree just to build a loop that calls a weather function.

**Hook 2.** Spent four hours last night debugging agent abstractions before deleting the package and writing it in raw Python in 20 minutes.

**Hook 3.** An AI agent isn't magic—it's literally just a while-loop feeding model outputs back into tool inputs until it says stop.

**Hook 4.** You don't need a heavy framework to build production agents; you just need function calling and basic control flow.

**Hook 5.** The fastest way to understand AI agents is building one with zero dependencies besides the official OpenAI SDK.

## 7 tips that actually move the needle

### Tip 1. Use litellm instead of provider-specific SDKs to switch models without changing schemas
_Why it matters:_ It normalizes function calling payloads across OpenAI, Anthropic, and local Ollama instances.

```python
from litellm import completion
res = completion(model='ollama/llama3', messages=msgs, tools=tools)
```

### Tip 2. Define tool schemas using Pydantic instead of writing raw JSON by hand
_Why it matters:_ Manual JSON schemas always break when you forget a required field or mistype a property type.

```python
from pydantic import BaseModel
class Query(BaseModel):
    location: str
```

### Tip 3. Set a hard MAX_TURNS limit on your agent's execution loop
_Why it matters:_ Without an explicit exit counter, hallucinated tool calls will happily burn your API budget at 2 AM.

```
for _ in range(MAX_TURNS):
    # invoke model and process tool calls
```

### Tip 4. Dispatch tool execution dynamically using a plain Python dict lookup
_Why it matters:_ Chained if-else blocks get messy fast once your agent supports more than two tools.

```
registry = {'get_weather': get_weather}
fn = registry[tool_call.function.name]
```

### Tip 5. Return tool results with role='tool' and the exact matching tool_call_id
_Why it matters:_ Modern LLMs reject tool execution messages if the correlation IDs don't match the original assistant call.

```
msgs.append({'role': 'tool', 'tool_call_id': tc.id, 'content': result})
```

### Tip 6. Validate tool arguments with json.loads inside a try-except block before calling functions
_Why it matters:_ Models occasionally emit malformed JSON or trailing commas that crash runtime execution.

```
try: args = json.loads(tc.function.arguments)
except json.JSONDecodeError: continue
```

### Tip 7. Print colored terminal traces with rich to see agent thought steps in real-time
_Why it matters:_ Debugging multi-turn tool calling without clear console logs will make you lose your mind.

```python
from rich import print
print(f'[bold green]Tool call:[/bold green] {tc.function.name}')
```

## Step-by-step procedure

### 1. Install the lightweight dependencies
Grab just the bare essentials so your environment stays clean and predictable.

```python
pip install openai python-dotenv
```

### 2. Write a standard Python function and mock data
Keep your tools pure and testable independent of any model logic.

```python
def get_user_balance(user_id: str) -> str:
    return f'Balance for {user_id}: $420.50'
```

### 3. Define the OpenAI tool schema
Describe the function parameters accurately so the LLM understands when and how to call it.

```
tools = [{'type': 'function', 'function': {'name': 'get_user_balance', 'description': 'Get account balance', 'parameters': {'type': 'object', 'properties': {'user_id': {'type': 'string'}}, 'required': ['user_id']}}}]
```

### 4. Implement the core agent loop
Send the message stack, check if the model invoked a tool, run it, and append the output.

```python
from openai import OpenAI
import json
client = OpenAI()
msgs = [{'role': 'user', 'content': 'What is the balance for user_101?'}]
for _ in range(5):
    res = client.chat.completions.create(model='gpt-4o-mini', messages=msgs, tools=tools)
    msg = res.choices[0].message
    msgs.append(msg)
    if not msg.tool_calls:
        break
    for tc in msg.tool_calls:
        args = json.loads(tc.function.arguments)
        out = get_user_balance(**args)
        msgs.append({'role': 'tool', 'tool_call_id': tc.id, 'content': out})
```

### 5. Run the script and verify the response
Execute your script—the model will call your function, read the balance, and summarize the answer naturally.

```
python agent.py
# Output: The balance for user_101 is $420.50.
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's intermediate message (the one containing tool_calls) back into the conversation history before appending the tool results, which immediately triggers a 400 API error from providers.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a 50MB dependency chain to build an AI agent in Python. Here's how to build one in 40 lines.

**2/** Spent way too long last night debugging third-party wrapper abstractions before realizing raw OpenAI function calling is literally just a while loop.

**3/** Step 1: Write a normal Python function and document it with a standard OpenAI tool schema dict.

**4/** Step 2: Loop the completion API. If res.choices[0].message.tool_calls exists, execute the matching function.

**5/** Step 3: Always push both the assistant message AND the tool output back into your messages array with the right tool_call_id.

**6/** Full runnable agent pattern with zero magic wrappers: stop overcomplicating simple loops.

## LinkedIn version

It was 1:30 AM last night when I finally killed my virtual environment in frustration.

I was trying to test a simple automation flow using one of the trendy AI agent frameworks. Three hours evaporated into stack traces inside nested abstraction layers, dealing with breaking changes between minor versions, and reading docs that looked like academic research papers.

So I backed up, installed just the base OpenAI SDK, and wrote it out by hand. An AI agent isn't black magic. At its core, it's just a while-loop. You pass an array of messages and tool definitions to a model. If the model responds with a tool call instead of text, you run that function in Python, push the result back onto the message stack, and let the model loop again.

The entire working script took 40 lines of code. It executed faster, was immediately obvious to debug, and didn't hide runtime errors under five levels of inheritance.

Before pulling in heavy orchestration frameworks for your next automation project, try writing the loop yourself. You'll understand the mechanics ten times better, and your codebase won't break on next week's release cycle.

#python #softwaredevelopment #automation #ai #programming

_Tags: python, aiagents, developers, automation_

---
*By Suman Giri — built with the CoderFact engine.*