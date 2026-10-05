# AI agents in Python: Stop overcomplicating with heavy frameworks

_How to build a functional, self-correcting agent in 50 lines of clean Python without the bloat._

## Scroll-stopping hooks

**Hook 1.** I stayed up until 2 AM fighting nested abstractions just to realize a basic AI agent is literally just a while-loop and a system prompt.

**Hook 2.** Everyone selling you an 'AI Agent' course is hiding a simple truth: you don't need complex orchestration frameworks to build something that actually works.

**Hook 3.** My rule for writing automation tools at CoderFact: if the library's dependency tree is larger than my actual agent logic, I am throwing it out.

**Hook 4.** You don't need a vector database, a graph orchestrator, or 15 API keys to build your first agent—just raw Python and the basic OpenAI client.

**Hook 5.** Spent half of last night debugging why my agent was stuck in an infinite loop because I trusted a heavy framework to handle the state. Here is how I stripped it down.

## 7 tips that actually move the needle

### Tip 1. Use pydantic for structured outputs
_Why it matters:_ It forces the LLM to return valid JSON that your Python script can actually parse without flaky regex hacks.

```
class Action(BaseModel):
  tool: str
  tool_input: str
```

### Tip 2. Patch your client with instructor
_Why it matters:_ It handles the Pydantic validation and auto-retries behind the scenes without adding heavy abstractions.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 3. Implement a strict iteration limit
_Why it matters:_ A simple counter prevents your agent from running away in an infinite loop and draining your API budget when it gets confused.

```
for _ in range(max_iterations):
```

### Tip 4. Use duckduckgo-search for live data
_Why it matters:_ It gives your agent a simple, free tool to fetch real-time web results without needing complex scraping setup or API keys.

```python
from duckduckgo_search import DDGS
results = DDGS().text('Python news')
```

### Tip 5. Map tool strings to actual Python functions with a dictionary
_Why it matters:_ It keeps your tool execution logic clean and avoids complex, hard-to-debug routing frameworks.

```
tools = {'search': run_search, 'calculate': run_math}
```

### Tip 6. Use tenacity for API resilience
_Why it matters:_ API rate limits and transient network blips should not crash your long-running automation script.

```python
@retry(stop=stop_after_attempt(3))
def call_llm(): ...
```

### Tip 7. Use rich for console logging
_Why it matters:_ Standard print statements make agent execution traces unreadable—colored panels help you see what the agent is thinking.

```python
from rich import print
print('[bold green]Agent action:[/bold green]', action)
```

## Step-by-step procedure

### 1. Step 1: Set up your virtual environment
Create a clean workspace and install the bare minimum dependencies needed to handle OpenAI calls and data validation.

```python
pip install openai pydantic instructor duckduckgo-search
```

### 2. Step 2: Define your agent's tool schema
Write a Pydantic class that defines what tools the agent can call and what arguments they require so the LLM knows exactly how to respond.

```
class ToolCall(BaseModel):
  tool_name: str
  arguments: str
```

### 3. Step 3: Write the actual tool functions
Create plain Python functions for the agent to use, like a simple calculator or web searcher, and map them in a dictionary.

```python
def calculate(expr):
  return str(eval(expr))
tools = {'math': calculate}
```

### 4. Step 4: Craft a tight system prompt
Explain the scratchpad loop to the LLM, listing the available tools and instructing it to output a final answer when done.

```
prompt = "You have access to: math. Use them to solve the query."
```

### 5. Step 5: Build the execution loop
Write a loop that feeds the user prompt to the LLM, parses the tool call, runs the Python function, and feeds the result back until the agent finishes.

```
for i in range(5):
  response = get_llm_response()
  # run tool, append to history
```

### 6. Step 6: Run and verify the agent
Ask the agent a multi-step question like 'What is 45 * 12, then add 100' and watch it call the calculator tool and print the correct final answer of 640.

```
agent.run('What is 45 * 12, then add 100')
```

## The mistake almost everyone makes

> ⚠️  Allowing the agent to run in an infinite loop when it gets confused. Fix this by setting a strict max_iterations counter inside your loop to force-terminate the run.

## X / Twitter thread (copy-paste ready)

**1/** I stayed up until 2 AM fighting nested abstractions just to realize a basic AI agent is literally just a while-loop and a system prompt.

**2/** You don't need heavy frameworks or 15 API keys to build something that works. Here is how I build lightweight agents for CoderFact using raw Python.

**3/** Tip 1: Use the instructor library with Pydantic. It forces the LLM to return clean, structured JSON so your code doesn't break on parsing.

**4/** Tip 2: Keep your execution loop simple. A basic while-loop with a strict max_iterations counter prevents infinite loops and saved my API bill.

**5/** Tip 3: Give it simple tools. A basic Python function wrapped in a dictionary is all your agent needs to fetch real-world data or run math.

**6/** Stop overcomplicating your stack. Build it raw first, see how it behaves, then scale. What are you building next?

## LinkedIn version

It was 1 AM last night, and I was staring at a stack trace that looked like a 10-story building. All I wanted was a simple Python script to fetch some data, process it, and write a report. Instead, I was deep in the internals of a popular 'agentic' framework, trying to figure out why a simple prompt was causing an infinite loop.

That is when I realized we have overcomplicated AI agents. We have wrapped a very simple concept—a language model inside a loop that can call functions—in so many layers of abstraction that we can no longer debug our own code.

So I deleted the directory, started a fresh virtual environment, and wrote a raw Python loop. I used Pydantic to force structured outputs and a simple dictionary to map string names to actual Python functions. No magic, no hidden prompts, just clean code.

The result? It worked on the first try, ran twice as fast, and I actually understood every single line of execution. If you are building tools, start with the bare minimum before pulling in heavy libraries.

Sometimes the best framework is just a while-loop and a well-written system prompt.

#python #aiagents #softwareengineering #coderfact #backenddev

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*