# AI Agents in Python: Stop overthinking LangChain and just write a loop

_Spent till 2am wrestling bloated frameworks before realizing an agent is just an LLM in a while-loop._

## Scroll-stopping hooks

**Hook 1.** Most tutorials make AI agents sound like rocket science when it's literally just a while-loop and a Python dictionary.

**Hook 2.** I wasted three hours debugging LangChain abstraction layers last night before throwing it out and writing a 40-line native agent.

**Hook 3.** If you know how to write a basic Python function, you already know how to build an autonomous agent.

**Hook 4.** Stop importing massive agent frameworks for simple tasks—here is the raw pattern that actually works.

**Hook 5.** Built an agent at 1am to automate my PR reviews because I was sick of clicking the same three buttons in GitHub.

## 7 tips that actually move the needle

### Tip 1. Use the official openai Python SDK with native function calling instead of wrapping everything in heavy frameworks.
_Why it matters:_ It keeps your stack trace readable and prevents unexpected dependency breakage when libraries update.

```python
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
```

### Tip 2. Define your tool schemas using pydantic models and convert them directly via pydantic.tools.
_Why it matters:_ You get automatic schema validation and type checking without writing messy nested JSON definitions by hand.

```python
from pydantic import BaseModel
class SearchInput(BaseModel):
    query: str
```

### Tip 3. Keep an explicit messages list acting as working memory and append both tool calls and results back to it.
_Why it matters:_ If you don't feed the tool's output back into the array with role='tool', the model will hallucinate its own answers.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': result})
```

### Tip 4. Use the instructor library if you want guaranteed structured outputs from your tool responses.
_Why it matters:_ It wraps client calls to force responses into strict Pydantic structures on failure.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 5. Set a hard MAX_ITERATIONS counter inside your execution loop to prevent runaway token bills.
_Why it matters:_ Agents can easily get trapped in infinite recursive loops when a tool returns an unexpected error.

```
for _ in range(5):
    # agent logic here
    if not response.choices[0].message.tool_calls: break
```

### Tip 6. Execute terminal commands safely using subprocess.run with a strict timeout parameter.
_Why it matters:_ A command that hangs or waits for stdin will freeze your agent forever without throwing a standard exception.

```python
import subprocess
res = subprocess.run(['git', 'status'], capture_output=True, text=True, timeout=10)
```

### Tip 7. Log raw LLM responses to a local SQLite file using sqlite3 rather than relying on bloated cloud tracing tools early on.
_Why it matters:_ You can inspect exactly why the model chose a specific tool at 2am without configuring API keys for third-party dashboards.

```python
import sqlite3
db = sqlite3.connect('agent_runs.db')
```

## Step-by-step procedure

### 1. Install the official OpenAI package
Keep your environment clean—just install the official client and set your API key in your shell.

```python
pip install openai
export OPENAI_API_KEY='your-key'
```

### 2. Define a real Python function the agent can run
Write standard Python code that does something useful, like fetching directory contents or querying an API.

```python
import os
def list_files(path='.'):
    return str(os.listdir(path))
```

### 3. Create the JSON tool definition
Tell the model what the function does, its parameters, and when to pick it.

```
tools = [{'type': 'function', 'function': {'name': 'list_files', 'description': 'Lists files in directory', 'parameters': {'type': 'object', 'properties': {'path': {'type': 'string'}}}}}]
```

### 4. Map function names to actual callables
Create a simple dispatch dictionary so the script can execute the function the LLM chooses dynamically.

```
available_tools = {'list_files': list_files}
```

### 5. Write the while-loop runner and execute
Send the prompt, check if the LLM returned a tool_call, execute it, append the answer, and repeat until it finishes.

```python
messages = [{'role': 'user', 'content': 'What files are in the current folder?'}]
while True:
    res = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: print(msg.content); break
    for call in msg.tool_calls:
        fn = available_tools[call.function.name]
        output = fn()
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': output})
```

## The mistake almost everyone makes

> ⚠️  Forgetting to send the assistant's initial message containing the `tool_calls` object back to the API along with the tool output. If you only send the tool output without the preceding assistant call, the OpenAI API throws an immediate 400 invalid_request_error.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a 500-page framework to build an AI agent in Python. Here is the entire architecture in 6 tweets.

**2/** Spent hours fighting broken dependency trees last night before remembering that an agent is just an LLM sitting inside a while-loop.

**3/** 1/ Use native OpenAI tool-calling. Define your Python functions, describe them in a simple dict, and let the model pick the tool.

**4/** 2/ Build a dispatch table. Map function names to actual local functions: `tools = {'get_weather': get_weather}`. No fancy routing needed.

**5/** 3/ Run a while-loop with an iteration cap. If `message.tool_calls` exists, run the function, append the result to `messages`, and repeat.

**6/** That's literally the whole loop. Drop the bloated frameworks and write raw Python—your stack traces will actually make sense.

## LinkedIn version

It was 1:30am last night and I was deep into a debugging rabbit hole.

I just wanted to build a simple agent that reads a folder of markdown files, finds broken links, and fixes them. Instead, I spent two hours trying to figure out why an abstraction layer was swallowing my exceptions and hiding the actual traceback.

I deleted the entire virtual environment, opened a blank `agent.py` file, and decided to do it the simple way.

Turns out, building an agent in native Python takes about 40 lines of code. You define your local functions, hand their schemas to OpenAI's tool-calling API, and run a while-loop. When the model requests a tool, you execute the Python function, append the output to your message array, and send it back.

No bloated wrappers. No hidden magic. If a tool fails, you see the exact line number where your code broke. Sometimes the simplest architectural pattern is the one we spend the longest time avoiding.

#python #softwareengineering #ai #automation #developers

_Tags: python, aiagents, automation, coding_

---
*By Suman Giri — built with the CoderFact engine.*