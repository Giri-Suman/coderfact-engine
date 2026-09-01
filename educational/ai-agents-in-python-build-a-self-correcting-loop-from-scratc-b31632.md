# AI Agents in Python: Build a self-correcting loop from scratch

_Stop fighting heavy frameworks—write a clean agent loop in under 50 lines of Python_

## Scroll-stopping hooks

**Hook 1.** Spent last night debugging a 500-line framework setup only to realize I could write the same agent in 30 lines of raw Python. Here is the stripped-back pattern.

**Hook 2.** Everyone talks about AI agents like they are sci-fi, but they are literally just while-loops with an LLM inside making decisions. Let's build one from scratch.

**Hook 3.** I got tired of writing brittle API wrappers that break the second a payload changes. Built a tiny self-correcting agent at 2 AM to handle it instead.

**Hook 4.** You don't need a heavy enterprise framework to build an AI agent that actually does real work. A system prompt, a tool registry, and a loop is all it takes.

**Hook 5.** Most agent tutorials show you how to call OpenAI and print the response. That is just an API call—here is how you build an actual execution loop.

## 7 tips that actually move the needle

### Tip 1. Enforce structured outputs with Pydantic
_Why it matters:_ It forces the LLM to return predictable JSON that matches your schema instead of chaotic markdown.

```python
from pydantic import BaseModel
class Action(BaseModel):
    tool: str
    args: dict
```

### Tip 2. Use OpenAI response_format parameter
_Why it matters:_ It guarantees the API payload conforms to your Pydantic schema so your parser never crashes.

```
client.chat.completions.create(
    model='gpt-4o-mini',
    response_format=Action
)
```

### Tip 3. Build a manual dictionary tool registry
_Why it matters:_ Avoids complex routing systems and keeps your execution logic transparent and easy to debug.

```
tools = {
    'fetch_data': run_db_query,
    'write_file': save_to_disk
}
```

### Tip 4. Validate LLM outputs with the instructor library
_Why it matters:_ It wraps your client calls and handles automatic retries if the JSON validation fails.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 5. Implement a hard iteration budget
_Why it matters:_ Keeps your API costs under control and prevents the agent from looping infinitely when stuck.

```
if loop_count > 5:
    raise Exception('Agent budget exceeded')
```

### Tip 6. Load credentials securely with python-dotenv
_Why it matters:_ Keeps your sensitive API keys out of your codebase and avoids accidental git commits.

```python
from dotenv import load_dotenv
import os
load_dotenv()
```

### Tip 7. Configure standard logging over print statements
_Why it matters:_ Gives you a clear execution trace so you can see exactly why your agent went sideways at step 3.

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Step-by-step procedure

### 1. Step 1: Define the tool schema
Create a Pydantic model that defines the structure of the action your agent can take, including the tool name and arguments.

```python
from pydantic import BaseModel
class ToolCall(BaseModel):
    name: str
    arguments: dict
```

### 2. Step 2: Set up the local tool registry
Write the actual Python functions your agent can run, and map their string names inside a dictionary.

```python
def get_stock(symbol: str):
    return f'{symbol} is at $150'
tools = {'get_stock': get_stock}
```

### 3. Step 3: Initialize the message log
Create a list to hold the conversation history, starting with a system prompt that tells the model how to use the tools.

```
messages = [{'role': 'system', 'content': 'You are an assistant with access to tools.'}]
```

### 4. Step 4: Write the execution loop
Create a while-loop that calls the LLM, parses the tool call, runs the local function, and feeds the output back to the model.

```
response = client.chat.completions.create(model='gpt-4o', response_format=ToolCall, messages=messages)
tool_result = tools[response.name](**response.arguments)
messages.append({'role': 'tool', 'content': tool_result})
```

### 5. Step 5: Run and verify the agent
Trigger the loop with a query that requires tool execution, and print the final output to verify it successfully resolved the task.

```
query = 'Check the stock price for AAPL'
# Run loop and print final response
```

## The mistake almost everyone makes

> ⚠️  Letting the agent loop infinitely when a tool encounters an error. The LLM will often try the exact same failing call again, burning your API credits. Fix this by catching exceptions inside the loop, passing the error traceback back to the LLM as a tool result, and incrementing a hard loop counter.

## X / Twitter thread (copy-paste ready)

**1/** AI agents aren't magic—they're just while-loops with an LLM inside making decisions.

**2/** Spent half of last night fighting heavy agent frameworks before throwing them out to build a clean, 50-line Python implementation.

**3/** First, use Pydantic to enforce structured outputs. If the LLM doesn't return predictable JSON, your parsing logic will crash immediately.

**4/** Second, build a manual tool registry using a simple Python dictionary. Don't overcomplicate routing with magic decorators.

**5/** Third, set a hard iteration limit. An agent stuck in an error loop is a quick way to burn through your API budget.

**6/** Build your own loop first before adopting heavy abstractions. Check out CoderFact for the full breakdown.

## LinkedIn version

It was 1 AM last night, and I was staring at a stack trace from a popular agent framework. All I wanted was to build a simple script that searches a local database, summarizes the results, and writes a file. Instead, I was debugging abstract class inheritance and magic wrappers.

So I deleted the package and started over with raw Python.

Turns out, a functional AI agent is incredibly simple. You need three things: a system prompt defining the goal, a Pydantic model to force structured outputs, and a standard while-loop that executes local functions based on the LLM's decisions. No magic, no hidden abstractions.

By building the execution loop myself, I cut the codebase down to 50 lines. It runs faster, I can actually debug it with simple print statements, and it doesn't break when an API update happens.

Before you reach for a massive framework for your next automation project, try writing the loop yourself. You'll actually understand how the agent thinks.

#python #aiagents #automation #backend #coderfact

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*