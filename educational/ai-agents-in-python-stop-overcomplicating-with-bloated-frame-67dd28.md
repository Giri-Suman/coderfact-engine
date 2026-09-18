# AI agents in Python: stop overcomplicating with bloated frameworks

_Build a functional, self-correcting agent in 30 lines of clean Python without LangChain's overhead._

## Scroll-stopping hooks

**Hook 1.** I spent till 2 AM trying to debug a 50-line framework agent before realizing I could write the entire loop myself in 15 lines of raw Python.

**Hook 2.** Most AI agent tutorials force you into massive frameworks when all you actually need is a simple while loop and a system prompt.

**Hook 3.** Stop wrapping basic API calls in five layers of abstract classes—your first AI agent should just be a Python script that calls a function.

**Hook 4.** I finally got sick of agentic bloat and built a bare-minimum tool-calling loop last night—here is how to do it without losing your mind.

**Hook 5.** You don't need a vector database or a complex graph orchestrator to build an agent that actually gets things done.

## 7 tips that actually move the needle

### Tip 1. Use the direct openai SDK instead of orchestration wrappers
_Why it matters:_ Direct SDKs let you see the exact payload going back and forth without magic abstractions hiding your bugs.

```python
from openai import OpenAI
client = OpenAI()
```

### Tip 2. Enforce structured outputs using Pydantic models
_Why it matters:_ It prevents the model from returning messy text when your system expects clean, parsable JSON arguments.

```python
from pydantic import BaseModel
class ToolCall(BaseModel):
    name: str
    args: dict
```

### Tip 3. Use instructor to patch your LLM client for easy parsing
_Why it matters:_ It handles the validation retry loop under the hood so you don't have to write messy try-except blocks.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 4. Print raw system messages using the rich library
_Why it matters:_ Seeing the actual agent thoughts in colored terminal output saves you hours of print-statement hell.

```python
from rich import print
print(f'[bold yellow]Agent thought:[/bold yellow] {thought}')
```

### Tip 5. Keep your tools as simple Python functions with type hints
_Why it matters:_ Modern LLMs read the docstrings and type annotations directly to understand how and when to call them.

```python
def calculate_tax(amount: float) -> float:
    """Calculates a flat 10% tax."""
    return amount * 0.1
```

### Tip 6. Set a hard recursion limit inside your execution loop
_Why it matters:_ If your agent gets stuck in an infinite loop calling the same broken tool, it will drain your API credits in minutes.

```
if loop_count > 5:
    raise Exception('Max iterations reached')
```

### Tip 7. Use python-dotenv to manage your API keys securely
_Why it matters:_ Hardcoding your OpenAI key in a script is the fastest way to get it leaked on GitHub.

```python
from dotenv import load_dotenv
load_dotenv()
```

## Step-by-step procedure

### 1. Step 1: Install the bare essentials
Skip the heavy frameworks and install just the OpenAI SDK and python-dotenv to keep your environment clean.

```python
pip install openai python-dotenv
```

### 2. Step 2: Define your system prompt
Write a clear prompt that instructs the model how to think, use tools, and format its output.

```
SYSTEM_PROMPT = 'You are a helpful assistant. You must use tools to answer questions.'
```

### 3. Step 3: Create a local Python tool
Write a standard Python function that the agent can call, complete with clear type hints and a descriptive docstring.

```python
def get_weather(city: str) -> str:
    """Get current weather for a city."""
    return f'Sunny in {city}'
```

### 4. Step 4: Set up the execution loop
Write a while loop that sends the user query to the model, checks if it wants to call a tool, runs the tool, and feeds the result back.

### 5. Step 5: Run and verify the agent
Execute your script with a query that requires the tool, and watch the terminal print out the step-by-step reasoning and final answer.

```
python agent.py
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run without a strict iteration cap. If the model experiences hallucination or fails to parse a tool output, it can enter an infinite loop, calling the API hundreds of times and racking up a massive bill. Fix this by wrapping your agent loop in a simple counter 'for _ in range(max_turns):' and breaking out immediately if it exceeds the limit.

## X / Twitter thread (copy-paste ready)

**1/** I stayed up until 2 AM fighting bloated AI frameworks, so I threw them out and built a raw Python agent in 30 lines.

**2/** Most tutorials make agents look like magic, but they are just while loops. You send a prompt, check for tool calls, run the local function, and send the result back.

**3/** Tip 1: Use basic Python functions as your tools. LLMs can read your docstrings and type hints directly to figure out how to call them.

**4/** Tip 2: Always set a strict recursion limit. If your agent gets confused, it will loop infinitely and drain your API wallet in minutes.

**5/** Tip 3: Ditch the wrappers and use the native OpenAI or Anthropic SDKs. You'll actually understand what is happening under the hood.

**6/** I wrote down the exact 5-step script I used to get this working. Stop overcomplicating your builds and write clean Python instead.

## LinkedIn version

It was 1 AM last night, and I was staring at a stack trace from a popular AI orchestration framework. All I wanted was a simple agent to fetch some data and format it. Instead, I was digging through five layers of abstract classes, trying to figure out why a basic tool call was failing.

I got annoyed, deleted the virtual environment, and decided to write it from scratch. No bloated wrappers. No over-engineered graphs. Just raw Python.

It turns out, an AI agent is just a while loop. You give the LLM a system prompt, let it decide if it needs to call a function, execute that function locally, and pass the result back to the model. By using standard Python functions with clear docstrings, the model knows exactly what to do.

Doing this yourself teaches you how agents actually work. You realize you don't need magic libraries to handle state or routing—you just need clean code, a solid system prompt, and a strict loop limit so your API bill doesn't skyrocket.

Stop overcomplicating your AI stack. Build the loop yourself first, understand the mechanics, and only pull in heavy frameworks when you absolutely run out of options.

python ai development automation backend

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*