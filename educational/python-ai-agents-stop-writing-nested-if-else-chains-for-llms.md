# Python AI agents: Stop writing nested if-else chains for LLMs

_Build a self-correcting agent in 20 lines of Python without heavy, over-engineered frameworks._

## Scroll-stopping hooks

**Hook 1.** Spent until 2 AM fighting nested abstractions just to make an LLM call a local tool, so I threw the framework out and built it with raw Python.

**Hook 2.** You don't need a heavy enterprise framework to build an AI agent—most of them are just glorified while-loops wrapping an LLM client.

**Hook 3.** Everyone is selling 'agentic AI' like it's black magic, but it's literally just a Python script that parses JSON in a loop until the prompt is happy.

**Hook 4.** I got tired of my wrapper breaking every time a dependency updated, so I wrote a 50-line agent using nothing but the official OpenAI SDK.

**Hook 5.** If your AI agent needs 15 architectural diagrams to explain how it calls a simple search API, you've over-engineered it.

## 7 tips that actually move the needle

### Tip 1. pydantic
_Why it matters:_ Validating raw LLM outputs into structured Python objects prevents runtime crashes when the agent returns malformed data.

```python
from pydantic import BaseModel
class ToolCall(BaseModel):
    name: str
    args: dict
```

### Tip 2. instructor
_Why it matters:_ It patches the OpenAI client to guarantee your agent returns strict JSON matching your Pydantic schema.

```python
import instructor
from openai import OpenAI
client = instructor.from_openai(OpenAI())
```

### Tip 3. tenacity
_Why it matters:_ Agent loops fail constantly on rate limits or API hiccups; you need automated retries to keep the loop alive.

```python
from tenacity import retry, stop_after_attempt
@retry(stop=stop_after_attempt(3))
def call_agent(): pass
```

### Tip 4. rich.console
_Why it matters:_ You need real-time terminal logging to see what your agent is thinking at 1 AM without digging through raw JSON dumps.

```python
from rich.console import Console
console = Console()
console.log('[bold green]Agent decided to run tool...[/]')
```

### Tip 5. python-dotenv
_Why it matters:_ Hardcoding API keys in your agent script is a security disaster waiting to happen.

```python
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.getenv('OPENAI_API_KEY')
```

### Tip 6. duckduckgo-search
_Why it matters:_ Give your agent web access instantly without registering for heavy, paid search API keys.

```python
from duckduckgo_search import DDGS
results = DDGS().text('python news', max_results=3)
```

### Tip 7. yarl
_Why it matters:_ Safely parsing and building URLs inside your agent's execution block prevents malformed request crashes during tool execution.

```python
from yarl import URL
base_url = URL('https://api.github.com') / 'repos'
```

## Step-by-step procedure

### 1. Step 1: Set up your environment
Create a virtual environment and install the bare minimum dependencies: OpenAI, Pydantic, and Instructor.

```python
pip install openai pydantic instructor python-dotenv
```

### 2. Step 2: Define your agent's tool
Create a standard Python function that your agent can call, like a simple calculator or API fetcher.

```python
def get_weather(city: str) -> str:
    return f'Sunny in {city}, 25C'
```

### 3. Step 3: Model the agent's decision
Use Pydantic to define the structure of how the agent decides to either call a tool or reply to the user.

```python
from pydantic import BaseModel
class Decision(BaseModel):
    tool_name: str
    arguments: dict
    thought: str
```

### 4. Step 4: Initialize the structured client
Wrap your OpenAI client with Instructor so it forces the LLM to output your exact Pydantic schema.

```python
import instructor
from openai import OpenAI
client = instructor.from_openai(OpenAI())
```

### 5. Step 5: Run the execution loop
Write a simple loop that sends the prompt, gets the structured decision, runs the tool, and feeds the result back to the LLM.

```
resp = client.chat.completions.create(
    model='gpt-4o-mini',
    response_model=Decision,
    messages=[{'role': 'user', 'content': 'Is it sunny in Kolkata?'}]
)
```

### 6. Step 6: Verify the agent's choice
Print the structured output to verify that the agent correctly chose the 'get_weather' tool with 'Kolkata' as the argument.

```python
print(resp.thought)
print(resp.tool_name)
print(resp.arguments)
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run in an infinite loop when it gets stuck. Always set a max_iterations counter (usually 3 to 5) inside your while-loop to force-terminate the execution and return a fallback error message.

## X / Twitter thread (copy-paste ready)

**1/** Python AI agents: Stop writing nested if-else chains for LLMs.

**2/** I spent last night fighting complex frameworks just to make an LLM call a local function. It's too much. Here is how to build a clean agent with raw Python.

**3/** Tip 1: Use instructor to force your LLM to output structured Pydantic models. No more parsing messy markdown code blocks.

**4/** Tip 2: Keep your tools as plain Python functions. Your agent loop just needs to map the LLM's JSON choice to a function dictionary.

**5/** Tip 3: Always hardcode a max_iterations cap. If the agent gets confused, it will loop infinitely and drain your API balance in minutes.

**6/** Build light, build fast. Try this setup today and skip the framework bloat. What tool are you hooking up first?

## LinkedIn version

It was 1:30 AM last night, and I was staring at a stack trace 20 levels deep in some enterprise AI framework. All I wanted was to make an LLM check a local database and format the result. Instead, I was debugging abstract 'Runnable' chains.

I closed the editor, deleted the virtual env, and started over with a blank Python file. Just the official OpenAI client, Pydantic, and a simple while-loop.

Within twenty minutes, I had a working agent. It didn't need complex graph orchestrators. It just used Pydantic to guarantee the model outputted structured JSON, mapped that JSON to a local Python dictionary of functions, and executed them.

We have over-engineered AI development. If you are building tools, start with the simplest loop possible. You do not need heavy abstractions until your simple loop actually breaks under real production load.

Keep it simple, keep it readable, and save your sleep.

#python #aiagents #softwareengineering #backend

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*