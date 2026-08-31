# AI agents in Python: Stop overcomplicating with bloated frameworks

_Build a raw, dependency-free agent loop in 20 lines of Python before you drown in LangChain boilerplate._

## Scroll-stopping hooks

**Hook 1.** I stayed up until 2 AM fighting with LangChain's abstractions just to realize a basic AI agent is literally just a while loop and an API call.

**Hook 2.** You don't need a heavy enterprise framework to build an AI agent—most of them are just overpriced wrappers around a basic system prompt.

**Hook 3.** Spent my entire evening debugging custom tools in a bloated agent framework, got mad, deleted the repo, and wrote a clean Python loop instead.

**Hook 4.** If you can write a basic Python function and parse a JSON response, you've already got everything you need to build your first autonomous agent.

**Hook 5.** We've overcomplicated AI agents to the point where devs think they need 10 dependencies just to make LLMs call a math function.

## 7 tips that actually move the needle

### Tip 1. Use pydantic for structured outputs instead of raw string parsing
_Why it matters:_ It forces the LLM to return valid JSON that conforms to your exact tool schemas.

```
class ToolCall(BaseModel):
  name: str
  args: dict
```

### Tip 2. Define your tools as simple Python functions and generate their JSON schemas dynamically
_Why it matters:_ Writing JSON schemas manually at 1am is a recipe for syntax errors.

```python
def add(a: int, b: int):
  return a + b
```

### Tip 3. Use instructor to patch your OpenAI client
_Why it matters:_ It handles the validation retries automatically when the LLM messes up the schema.

```python
import instructor; client = instructor.from_openai(OpenAI())
```

### Tip 4. Keep a strict messages list to manage the conversation state
_Why it matters:_ Agents need to remember previous tool execution results to decide their next step.

```
messages.append({"role": "tool", "content": result})
```

### Tip 5. Set a hard limit on the agent's iteration loop
_Why it matters:_ An infinite loop calling paid APIs will drain your wallet faster than you can hit Ctrl+C.

```
for _ in range(max_iterations):
```

### Tip 6. Use rich for terminal logging
_Why it matters:_ Seeing your agent's thoughts, tool calls, and outputs in color makes debugging the reasoning loop 10x easier.

```python
from rich import print; print('[bold green]Tool output:[/bold green]', res)
```

### Tip 7. Use python-dotenv to manage your API keys
_Why it matters:_ Hardcoding your OpenAI or Anthropic keys in your script is a security disaster waiting to happen.

```python
from dotenv import load_dotenv; load_dotenv()
```

## Step-by-step procedure

### 1. Step 1: Set up your environment
Install the bare essentials—just OpenAI and Pydantic. No heavy agent frameworks needed.

```python
pip install openai pydantic python-dotenv
```

### 2. Step 2: Define your tools
Create simple Python functions that your agent can call, like a calculator or a weather API fetcher.

```python
def calculate_tax(amount: float) -> float:
    return amount * 0.18
```

### 3. Step 3: Setup the system prompt
Instruct the LLM on how to output tool calls. Tell it to respond in a structured format when it needs to run a tool.

```
prompt = "You can use calculate_tax. Output JSON with tool name and arguments."
```

### 4. Step 4: Build the execution loop
Write a loop that calls the LLM, checks if it requested a tool, runs the local function, and sends the result back.

```
while running:
    response = call_llm(messages)
    if response.tool_call:
        res = run_tool(response.tool_call)
        messages.append(res)
```

### 5. Step 5: Run and verify the agent
Ask the agent a question that requires the tool, like calculating tax on 1500, and watch it execute the local function and return the final answer.

```
run_agent("What is the tax on 1500 USD?")
```

## The mistake almost everyone makes

> ⚠️  Trying to use complex framework agents for simple tasks. Fix: Write a raw while loop first, see where it breaks, and only then pull in external libraries if you absolutely must.

## X / Twitter thread (copy-paste ready)

**1/** Stop drowning in bloated AI frameworks just to run a basic agent.

**2/** Most agent frameworks are just over-engineered wrappers around a system prompt and a while loop.

**3/** Tip 1: Use Pydantic to enforce structured JSON outputs from your LLM so you don't have to parse raw text.

**4/** Tip 2: Keep your tools as plain Python functions and map them to a dictionary for easy execution.

**5/** Tip 3: Set a hard limit on your execution loop—infinite API loops get expensive real quick.

**6/** Build it raw first. You'll actually understand how your agent works instead of debugging 5 layers of framework code.

## LinkedIn version

It was 1:30 AM and I was fighting with a popular AI framework just to get an agent to call a simple database query tool. The documentation was a maze of nested classes, custom runnables, and hidden prompts. I got so annoyed that I deleted the virtual environment and started over with a blank Python file.

Turns out, an AI agent isn't magic. It is literally just a loop: ask the LLM what to do, parse its structured response, run the local function it asked for, and feed the result back into the conversation history. You don't need 15 dependencies and an enterprise wrapper for that.

By building your own agent loop using bare-minimum tools like Pydantic and the native OpenAI client, you gain absolute control over the execution flow. You can see exactly where the tokens are going, how the prompt is formatted, and why a tool call failed.

Next time you want to build an automation tool, resist the urge to install the latest trending library. Write the raw loop first. You'll save hours of debugging and actually understand how your system works under the hood.

I built a lightweight agent loop for CoderFact this way and it runs faster, uses less memory, and doesn't break every time a dependency updates.

#python #aiagents #softwareengineering #backend #automation

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*