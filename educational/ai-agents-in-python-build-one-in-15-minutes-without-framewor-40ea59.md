# AI agents in Python: build one in 15 minutes without framework bloat

_Stop drowning in complex nested wrappers. Here is how to build a working agent using raw Python._

## Scroll-stopping hooks

**Hook 1.** Spent last night fighting a massive agent framework's nested abstractions just to make one API call, so I threw it all out and built an agent with 50 lines of raw Python.

**Hook 2.** Most AI agent tutorials make you install ten different packages before you even write a loop. You actually only need one library and a basic while-loop.

**Hook 3.** I stayed up until 2 AM trying to debug an agent that got stuck in an infinite loop because of a hidden prompt template. Here is the dead-simple way to build one that actually stops.

**Hook 4.** You don't need a massive enterprise framework to build an AI agent that can run terminal commands and fetch APIs.

**Hook 5.** After wasting half a day on 'agentic workflows' that just generated weird JSON errors, I went back to basics. Here is the minimal Python setup that actually works.

## 7 tips that actually move the needle

### Tip 1. Use litellm instead of native provider SDKs
_Why it matters:_ It standardizes LLM inputs and outputs so you can swap from OpenAI to Anthropic with a single environment variable change.

```python
from litellm import completion; response = completion(model='gpt-4o', messages=[{'role': 'user', 'content': 'Hi'}])
```

### Tip 2. Enforce structured JSON outputs directly in the API call
_Why it matters:_ It stops the LLM from outputting conversational filler when you need clean, parseable tool calls.

```
response = completion(model='gpt-4o', messages=messages, response_format={'type': 'json_object'})
```

### Tip 3. Validate LLM payloads with pydantic
_Why it matters:_ It catches malformed or missing arguments before they hit your execution logic and crash your script.

```
class ToolCall(BaseModel):
    action: str
    arg: str
```

### Tip 4. Write a simple while-loop with a hard iteration cap
_Why it matters:_ You don't need complex state machines—a basic loop with a max turn counter prevents runaway API bills.

```
max_turns = 5
for turn in range(max_turns):
    # agent logic here
```

### Tip 5. Manage your API keys with python-dotenv
_Why it matters:_ Hardcoding keys is the fastest way to get your OpenAI account drained on GitHub.

```python
from dotenv import load_dotenv
import os
load_dotenv()
```

### Tip 6. Mock your LLM responses during local testing
_Why it matters:_ Testing agents with live APIs at 1 AM gets expensive fast; mocking lets you verify your execution loop for free.

```python
from unittest.mock import patch
with patch('litellm.completion') as mock_run:
```

### Tip 7. Feed tool errors back into the chat history
_Why it matters:_ If a tool execution fails, appending the traceback to the messages history lets the LLM self-correct on its next turn.

```
except Exception as e:
    messages.append({'role': 'user', 'content': f'Tool failed: {str(e)}'})
```

## Step-by-step procedure

### 1. Step 1: Install the bare essentials
Install only what you need to make API calls and validate data. Avoid heavy agent frameworks.

```python
pip install litellm pydantic python-dotenv
```

### 2. Step 2: Define your local tools
Create standard Python functions that your agent can run, like fetching weather or reading a file.

```python
def get_weather(location: str):
    return f'It is currently raining in {location}.'
```

### 3. Step 3: Write the system prompt
Instruct the LLM on how to format its thoughts and tool calls in raw JSON.

```
system_prompt = 'You are an agent. Respond ONLY in JSON with keys: "thought", "action", and "arg".'
```

### 4. Step 4: Build the execution loop
Call the model, parse its JSON response, execute the requested tool, and append the result back to the message list.

```
response = completion(model='gpt-4o', messages=messages)
# Parse response, run tool, append result
```

### 5. Step 5: Run and verify the agent
Ask the agent a question that requires your local tool and watch it resolve the task in your terminal.

```
python agent.py 'Should I take an umbrella in Kolkata?'
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run without a hard iteration limit. If the LLM gets confused or hits an error, it will loop endlessly and run up a massive API bill in minutes. Always set a max_loops safety guard.

## X / Twitter thread (copy-paste ready)

**1/** AI agents in Python: how to build one in 15 minutes without bloated frameworks.

**2/** Spent last night fighting over-engineered wrappers just to run a simple tool-use loop. You do not need them.

**3/** Step 1: Use LiteLLM and Pydantic. LiteLLM lets you swap models instantly, and Pydantic ensures the LLM output does not crash your code.

**4/** Step 2: Write a simple while-loop with a hard stop (max 5 iterations). Never trust an LLM not to run up your API bill.

**5/** Step 3: Feed tool errors back to the model. If a function fails, append the error to the chat history so the agent can self-correct.

**6/** Built this for CoderFact to automate some boring dev tasks. Check the full setup and stop overcomplicating your agents.

## LinkedIn version

It was 1 AM last night, and I was staring at a 200-line stack trace from a popular AI agent framework. All I wanted was a simple script that could check an API and write a file. Instead, I got lost in a maze of nested abstractions, custom chain objects, and undocumented prompt templates.

I got so annoyed that I deleted the entire virtual environment and started over with a blank Python file. No bloated frameworks. Just raw Python, a basic while-loop, and LiteLLM to handle the API calls.

It took me exactly 45 lines of code to get a fully working agent that could call local Python functions, handle errors, and self-correct. And the best part? I can actually debug it with a simple print statement.

If you are trying to build your first AI agent, step away from the massive frameworks first. Build a simple run-loop yourself. Learn how to parse the JSON output, how to execute the tools, and how to feed the results back to the model. You will actually understand what is happening under the hood.

I wrote down the exact minimal setup we use at CoderFact to keep things fast and maintainable.

#python #aiagents #softwareengineering #automation

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*