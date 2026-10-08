# Python AI Agents: Stop overcomplicating the loop

_How I finally built a working autonomous agent at 2 AM without drowning in framework boilerplate._

## Scroll-stopping hooks

**Hook 1.** I stayed up until 2 AM fighting with agent frameworks only to realize we are overcomplicating the hell out of this.

**Hook 2.** You do not need a massive, bloated framework to build an AI agent that actually does real work.

**Hook 3.** Most AI agent tutorials show you how to print 'Hello World' but fail the second you try to connect a real database.

**Hook 4.** I got tired of waiting for complex agent runtimes to spin up, so I wrote a raw Python loop instead.

**Hook 5.** If your AI agent framework requires 15 imports just to call a single tool, you are being scammed.

## 7 tips that actually move the needle

### Tip 1. Use pydantic for structured outputs
_Why it matters:_ It stops the LLM from hallucinating bad JSON and guarantees your tools get the exact argument types they expect.

```
class ToolCall(BaseModel):
  tool_name: str
  arguments: dict
```

### Tip 2. Patch your client with the instructor library
_Why it matters:_ It handles the validation errors behind the scenes and forces the LLM to retry until it fits your Pydantic schema.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 3. Decorate API calls with tenacity
_Why it matters:_ LLM APIs rate-limit or fail randomly, and you need automatic backoff so your agent loop does not crash mid-task.

```
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
```

### Tip 4. Use rich for real-time terminal logging
_Why it matters:_ Seeing the agent's thought process and tool execution in colored blocks makes debugging 10x faster.

```python
from rich.console import Console
console = Console()
```

### Tip 5. Load credentials using python-dotenv
_Why it matters:_ Hardcoding API keys in your agent script is a disaster waiting to happen when you push to GitHub.

```python
from dotenv import load_dotenv
load_dotenv()
```

### Tip 6. Swap models instantly with litellm
_Why it matters:_ It lets you switch your agent from OpenAI to Claude or local Ollama models with zero changes to your loop logic.

```
response = litellm.completion(model='claude-3', messages=m)
```

### Tip 7. Add live search with duckduckgo-search
_Why it matters:_ It is a free, zero-auth way to let your agent query the live internet without signing up for expensive search APIs.

```python
from duckduckgo_search import DDGS
results = DDGS().text('query')
```

## Step-by-step procedure

### 1. Step 1: Set up your environment
Create a virtual environment and install the bare minimum packages instead of giant SDKs.

```python
pip install openai pydantic python-dotenv instructor
```

### 2. Step 2: Define your python tools
Write standard Python functions that your agent can execute when the LLM decides to call them.

```python
def calculate_tax(amount: float) -> float:
    return amount * 0.18
```

### 3. Step 3: Create the structured schema
Define a Pydantic model that forces the LLM to output its reasoning and the tool it wants to use.

```
class AgentDecision(BaseModel):
    thought: str
    tool_to_use: str
    tool_input: float
```

### 4. Step 4: Build the execution loop
Write the while loop that calls the LLM, parses the decision, runs the function, and feeds the result back.

```
while not task_completed:
    # Call LLM, parse with instructor, run tool, append to history
```

### 5. Step 5: Run and verify the agent
Execute the script with a query like 'Calculate tax for 500' and verify it calls your local function and prints the correct result.

```
python agent.py 'What is the tax on 500 dollars?'
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run in an infinite loop without a max_iteration safety cutoff. Fix this by adding a simple counter (max_loops = 5) inside your while loop to kill the process before it drains your API wallet.

## X / Twitter thread (copy-paste ready)

**1/** I stayed up until 2 AM fighting with bloated agent frameworks, so I built my own in 50 lines of pure Python.

**2/** Most tutorials make you install 10 different packages just to run a simple tool-use loop. It's absolute overkill.

**3/** Tip 1: Use `instructor` to force the LLM to output clean Pydantic models. No more broken JSON parsing regex nightmares.

**4/** Tip 2: Keep your tools as basic Python functions. If it takes more than 10 lines to define a tool, you're doing it wrong.

**5/** Tip 3: Always set a hard limit like `max_loops = 5`. An infinite LLM loop will eat your API budget in minutes.

**6/** Stop overcomplicating your stack. Write the loop yourself and actually understand how your agent thinks.

## LinkedIn version

I spent last night staring at a terminal at 1 AM, mildly annoyed at how overengineered the AI agent space has become. I just wanted a simple script to search the web and summarize a page—why did I need to import three different 'orchestrators' and write 200 lines of boilerplate?

So I deleted the bloated frameworks and started over with raw Python. Turns out, a real agent is just a simple while-loop, a system prompt, and some basic tool execution.

By using Pydantic to enforce structured JSON outputs and the 'instructor' library to wrap the OpenAI client, I got a working agent running in under 50 lines of code. No magic, no hidden abstractions—just clean, predictable Python that didn't break when I changed the prompt.

If you're trying to build your first agent, stop trying to learn complex orchestrator libraries. Build the execution loop yourself first so you actually understand how the LLM decides to call a function.

Your API wallet (and your sanity) will thank you.

#python #aiagents #automation #backend

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*