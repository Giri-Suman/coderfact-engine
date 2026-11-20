# AI Agent in Python: Stop using basic wrapper loops

_How I finally got an agent to loop tools without exploding my API bill at 1 AM._

## Scroll-stopping hooks

**Hook 1.** Most 'AI agents' in Python are just while loops wrapping an OpenAI call until your wallet bleeds out.

**Hook 2.** I wasted three hours last night because my Python agent kept hallucinating tool arguments in a infinite loop.

**Hook 3.** You don't need LangChain to build a working AI agent — 50 lines of raw Python and cheap function calling is enough.

**Hook 4.** Stop prompting your LLM to 'be an agent' and start giving it a strict schema-driven execution loop.

**Hook 5.** Built a Python agent yesterday that actually stops when it finishes the task instead of repeating itself endlessly.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to define tool schemas instead of writing raw JSON manually
_Why it matters:_ It handles type validation and auto-generates the exact JSON schema the OpenAI API expects.

```python
from pydantic import BaseModel
class SearchArgs(BaseModel):
    query: str
```

### Tip 2. Set a hard max_iterations limit on your execution while loop
_Why it matters:_ It prevents runaway API calls when the model gets stuck in a tool-calling feedback loop.

```
while iterations < 5 and not task_complete:
    iterations += 1
```

### Tip 3. Bind native Python functions to a dispatch dictionary mapping
_Why it matters:_ It lets you execute incoming tool calls dynamically without writing messy nested if-else blocks.

```
tools = {'get_weather': get_weather}
result = tools[tool_name](**args)
```

### Tip 4. Append tool execution outputs back into the messages array as role='tool'
_Why it matters:_ The LLM needs the exact execution result in context to decide its next action or finalize the answer.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(output)})
```

### Tip 5. Force JSON mode or strict structured outputs using response_format
_Why it matters:_ It guarantees the model returns parseable arguments every single time instead of conversational text.

```
client.chat.completions.create(model='gpt-4o-mini', response_format={'type': 'json_object'})
```

### Tip 6. Log raw API request/response payloads to a local debug file
_Why it matters:_ You can't debug agent reasoning errors without seeing the full context payload sent on each step.

```python
import logging; logging.basicConfig(filename='agent.log', level=logging.DEBUG)
```

### Tip 7. Use gpt-4o-mini or Claude Haiku while prototyping agent logic
_Why it matters:_ Agent loops burn tokens fast, so testing control flow on lightweight models saves serious money.

```
MODEL = 'gpt-4o-mini' # Switch to gpt-4o only after the loop stops breaking
```

## Step-by-step procedure

### 1. Step 1: Install prerequisites and setup the client
Grab the official client and initialize it with your API key.

```python
pip install openai pydantic
from openai import OpenAI
client = OpenAI()
```

### 2. Step 2: Define your executable Python functions and schemas
Write real Python functions that do work, like fetching system metrics or calling external APIs.

```python
def get_cpu_usage():
    return 'CPU usage is 12%'

tool_definitions = [{'type': 'function', 'function': {'name': 'get_cpu_usage', 'description': 'Check system CPU usage'}}]
```

### 3. Step 3: Build the main execution loop
Initialize your message array and kick off a simple loop that sends context to the model.

```
messages = [{'role': 'user', 'content': 'Is the server running fine?'}]
res = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tool_definitions)
```

### 4. Step 4: Handle tool calls and append results
Check if the model requested a function call, run it locally, and send the output back.

```
msg = res.choices[0].message
if msg.tool_calls:
    messages.append(msg)
    # Run get_cpu_usage locally and append role='tool' response
```

### 5. Step 5: Run final answer synthesis
Pass the updated message history back to the model to generate the final response.

```python
final_res = client.chat.completions.create(model='gpt-4o-mini', messages=messages)
print(final_res.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant message containing the tool_calls array back to history before pushing the tool result — this breaks OpenAI's schema validation with a 400 Bad Request. Always push the assistant message first, then the tool output.

## X / Twitter thread (copy-paste ready)

**1/** Most 'AI agent' frameworks are bloated over-engineering. You can build a reliable agent in under 50 lines of Python.

**2/** Spent way too long last night fixing broken loops because I was overcomplicating context history. Here is how it actually works.

**3/** 1/ Define your tools using standard Python functions and export their JSON schemas to the model.

**4/** 2/ Create an explicit while-loop with a hard limit (max 5 iterations) to catch runaway execution loops.

**5/** 3/ Push tool outputs directly back to the message array with role='tool' so the model sees what happened.

**6/** Stop pulling in massive frameworks for simple tasks. Build the raw execution loop yourself first: https://coderfact.com

## LinkedIn version

I sat down at 11 PM last night to quickly script a small automation agent in Python. By 1 AM, I was staring at a $14 OpenAI bill and an infinite loop where my model kept calling the same web-scraper tool with slightly different typos.

Most agent tutorials tell you to import massive third-party abstractions. But abstractions hide the fundamental reality: an agent is literally just a loop sending tool results back to an API until the task is marked done.

When you build it manually using raw Python lists and OpenAI function calls, the magic fades and you get actual control. You can cap execution depth, intercept hallucinated arguments before they run, and inspect every step in plain text.

Once you enforce strict Pydantic models for argument parsing and lock down a simple dispatch dictionary, the whole system becomes dead simple to debug—no framework magic required.

If you want to build tools that don't randomly drain your credits while you sleep, build your first execution loop from scratch.

python
ai
backend
softwareengineering
tech

_Tags: python, aiagents, backend, automation_

---
*By Suman Giri — built with the CoderFact engine.*