# AI Agent in Python: Stop Installing Huge Frameworks First

_Build a working autonomous loop with standard libraries before touching LangChain or CrewAI._

## Scroll-stopping hooks

**Hook 1.** Most tutorials hand you a 400MB framework just to run an LLM inside a while-loop. You don't need LangChain to build your first agent.

**Hook 2.** Spent four hours debugging dependency conflicts at 1am just to realize an 'agent' is literally an LLM calling a Python function in a loop.

**Hook 3.** If you can write a basic dictionary and a while-loop in Python, you can write an autonomous agent from scratch tonight.

**Hook 4.** Stop letting framework abstractions hide how tool calling works—it's just JSON schemas and recursive calls.

**Hook 5.** You don't have an agent problem, you have a context-window parsing problem. Here is how to build one with raw OpenAI SDK.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to generate strict tool schemas automatically
_Why it matters:_ It prevents the model from hallucinating non-existent parameters and crashing your script.

```python
from pydantic import BaseModel
class Search(BaseModel):
    query: str
```

### Tip 2. Map function names directly to Python callables via a dict lookup
_Why it matters:_ Avoids messy if-else chains when the model returns a tool call name.

```
TOOL_MAP = {'search_db': search_db, 'send_email': send_email}
result = TOOL_MAP[tool_call.function.name](**args)
```

### Tip 3. Cap your loop with a hard max_iterations counter
_Why it matters:_ Runaway loops burn through API credits in minutes when the model gets confused.

```
for _ in range(5):
    # run agent step
    if done: break
```

### Tip 4. Append the tool execution result back as a 'tool' role message
_Why it matters:_ The LLM needs the output explicitly paired with its tool_call_id to continue reasoning.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(output)})
```

### Tip 5. Log your raw payloads using litellm or rich
_Why it matters:_ You can't fix bad agent decisions without inspecting the exact tokens sent to the API.

```python
import rich
rich.print(response.choices[0].message)
```

### Tip 6. Set temperature to 0.0 for deterministic tool dispatching
_Why it matters:_ Higher randomness causes the model to invent arguments or skip required keys.

```
client.chat.completions.create(model='gpt-4o-mini', temperature=0.0, ...)
```

### Tip 7. Use python-dotenv to isolate your keys early
_Why it matters:_ Hardcoding API tokens into your scratchpad script always ends in a leaked key.

```python
from dotenv import load_dotenv
load_dotenv()
```

## Step-by-step procedure

### 1. Install the official OpenAI package and python-dotenv
Keep your environment lean so you aren't debugging dependency conflicts at midnight.

```python
pip install openai python-dotenv
```

### 2. Define a plain Python function and its JSON schema
Write the function you want the agent to use and define its signature for the API.

```python
def get_weather(city: str):
    return f'{city} is 28C and humid'

tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {'type': 'object', 'properties': {'city': {'type': 'string'}}, 'required': ['city']}}}]
```

### 3. Initialize your messages list and call the model with tools
Pass the user query alongside the tool definitions so the model knows it can execute code.

```python
from openai import OpenAI
client = OpenAI()
messages = [{'role': 'user', 'content': 'What is the weather in Kolkata?'}]
res = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
```

### 4. Intercept tool calls and execute the Python code
Check if finish_reason is 'tool_calls', parse the arguments with json.loads, and run your function.

```python
import json
msg = res.choices[0].message
messages.append(msg)
if msg.tool_calls:
    call = msg.tool_calls[0]
    args = json.loads(call.function.arguments)
    out = get_weather(**args)
    messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': out})
```

### 5. Run the final completion to verify output
Send the updated message history back to the model so it can formulate the final human-readable answer.

```python
final = client.chat.completions.create(model='gpt-4o-mini', messages=messages)
print(final.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's initial response containing the `tool_calls` object before sending the tool output back. The OpenAI API will throw a 400 error immediately if a tool response doesn't directly follow its corresponding assistant call.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a heavy framework to build an AI agent in Python. Here's the raw loop.

**2/** Wasted hours last night untangling massive agent libraries before stripping it down to standard Python.

**3/** Tip 1: An agent is just an LLM + a tool map dict + a while-loop. Don't overcomplicate it.

**4/** Tip 2: Always pass your function schemas explicitly and set temperature=0 for consistent arguments.

**5/** Tip 3: Always cap the loop with a max_iterations guard so an edge case doesn't burn your wallet.

**6/** Write it bare-metal first. Once you understand the message cycle, then pick your framework.

## LinkedIn version

It was 1:30 AM last night when I finally deleted my third agent framework of the week.

I just wanted a Python script to check an API, parse the JSON, and summarize the result. Somehow, I ended up with 400MB of dependencies, abstract base classes I couldn't trace, and a recursion error that made zero sense.

So I scrapped the entire virtual environment and went back to basics. Just the official OpenAI client, a simple dictionary, and a standard while-loop. Turns out, an 'AI agent' isn't some mystical new architecture—it's an LLM outputting a structured function name, your code executing that function, and feeding the output back into the conversation history.

Once you wire that message loop manually, the mystery evaporates. You see exactly where the tokens go, where the context gets bloated, and why tool calls fail.

Frameworks are great once you outgrow your own architecture. But if you haven't built the loop from scratch at least once, you're just debugging someone else's assumptions.

#python #softwareengineering #buildinpublic #developers

_Tags: python, aiagents, automation, softwaredevelopment_

---
*By Suman Giri — built with the CoderFact engine.*