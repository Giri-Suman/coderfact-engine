# Python AI Agents: Build One Tonight Without LangChain Bloat

_Stop fighting 40 layers of framework abstractions. A working ReAct agent is just 30 lines of clean Python._

## Scroll-stopping hooks

**Hook 1.** Spent 4 hours debugging LangChain imports last night before realizing a ReAct agent is literally just a while loop and tool calling.

**Hook 2.** Most tutorials make AI agents look like rocket science. It's just an LLM outputting JSON and your script running Python functions.

**Hook 3.** I deleted 300 lines of messy orchestration code at 1am and replaced it with native OpenAI tool calls. Everything instantly worked.

**Hook 4.** If you know how to write a Python dictionary and a while loop, you can build an autonomous agent from scratch.

**Hook 5.** Stop downloading massive agent frameworks for side projects. You can write your own in 10 minutes with zero boilerplate.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate tool schemas instead of writing raw JSON
_Why it matters:_ It keeps your schemas in sync with your actual Python types without manual schema authoring.

```python
from pydantic import BaseModel
class SearchQuery(BaseModel):
    query: str
```

### Tip 2. Set tool_choice='auto' in the openai SDK to let the model decide when to stop
_Why it matters:_ The model will automatically return plain text when it finishes executing tools.

```
response = client.chat.completions.create(
    model='gpt-4o-mini', messages=msgs, tools=tools, tool_choice='auto'
)
```

### Tip 3. Implement a hard max_iterations counter in your while loop
_Why it matters:_ Prevents accidental infinite loops that silently drain your API credits at 2am.

```
for _ in range(5):
    # run step
    if not response.tool_calls: break
```

### Tip 4. Map function names to actual callables using a plain Python dict
_Why it matters:_ Avoids messy if-else chains or unsafe eval() calls when dispatching tool executions.

```
TOOL_MAP = {'get_weather': get_weather, 'run_query': run_query}
result = TOOL_MAP[fn_name](**fn_args)
```

### Tip 5. Pass tool outputs back as role='tool' with the matching tool_call_id
_Why it matters:_ The API throws a 400 validation error if you fail to pair IDs correctly.

```
msgs.append({'role': 'tool', 'tool_call_id': tc.id, 'content': str(output)})
```

### Tip 6. Use tenacity to retry flaky API network calls automatically
_Why it matters:_ Keeps your agent loop alive through standard OpenAI rate limits and timeouts.

```python
from tenacity import retry, stop_after_attempt
@retry(stop=stop_after_attempt(3))
def call_llm(msgs): ...
```

### Tip 7. Log message history with rich.pretty instead of standard print
_Why it matters:_ Shows the exact conversational tree and payloads without unreadable JSON walls.

```python
from rich import print as rprint
rprint(messages)
```

## Step-by-step procedure

### 1. Install the official OpenAI package
Keep dependencies lean — you only need the official client to run full agents.

```python
pip install openai
```

### 2. Define a real Python function and its tool schema
Write the tool your agent will execute and define the structure OpenAI expects.

```python
def get_time(): return '01:15 AM IST'

tools = [{'type': 'function', 'function': {'name': 'get_time', 'description': 'Gets current time'}}]
```

### 3. Initialize your message history and client
Set up your system prompt and wrap the conversation in a standard list.

```python
from openai import OpenAI
client = OpenAI()
messages = [{'role': 'user', 'content': 'What time is it right now?'}]
```

### 4. Write the execution loop
Call the model, check for tool calls, execute the mapped function, and append the result.

```
response = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
msg = response.choices[0].message
messages.append(msg)
if msg.tool_calls:
    messages.append({'role': 'tool', 'tool_call_id': msg.tool_calls[0].id, 'content': get_time()})
```

### 5. Run the second pass to verify the final answer
Send the updated message history back to the model to generate the final human-readable response.

```python
final = client.chat.completions.create(model='gpt-4o-mini', messages=messages)
print(final.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's initial response containing the `tool_calls` object to the message array before appending the tool results. The API will reject the request because the tool response has no parent call to reference.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a heavy framework to build an AI agent in Python. Here is the entire architecture in 4 tweets.

**2/** Most agent frameworks wrap standard API calls in 10 layers of abstractions. Last night I stripped them all away. Here's what's actually under the hood.

**3/** 1. Define plain Python functions and map their names to an execution dict: `RUNNERS = {'search': search_db}`.

**4/** 2. Send your tools array to `client.chat.completions.create()`. If `message.tool_calls` exists, the LLM is requesting a function run.

**5/** 3. Execute the function locally, push the return value back with `role: 'tool'`, and call the API one more time for the final answer.

**6/** That's literally the whole loop. No bloat, no magic, complete control. Go build something cool tonight.

## LinkedIn version

It was 1:00 AM last night when I finally got fed up with agent frameworks.

I was debugging a broken dependency chain inside a massive library just to get an LLM to call a simple database query. It felt like using a sledgehammer to crack a peanut.

So I threw out the dependencies, opened an empty script, and wrote the raw agent loop myself. Guess what? It took about 35 lines of vanilla Python.

At its core, an agent isn't magic. It's just an LLM returning structured JSON with a function name, your script running that function, and feeding the output back into the message array until the model decides it has enough context to answer.

Before you reach for a 50k-star orchestration framework for your next side project, build the loop from scratch once. You'll actually understand your error logs, your code won't break on every minor release, and you won't lose half your night to dependency hell.

#python #ai #softwareengineering #coding #developers

_Tags: python, aiagents, openai, coding_

---
*By Suman Giri — built with the CoderFact engine.*