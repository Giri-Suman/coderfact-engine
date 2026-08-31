# AI Agents in Python: Stop writing wrapper scripts and build a loop

_How I finally stopped overcomplicating agent frameworks and built a working agent in 30 lines of raw Python._

## Scroll-stopping hooks

**Hook 1.** Spent until 2 AM fighting with a bloated framework's abstractions just to make an LLM call a local math function. Ended up throwing it all away and writing a basic while-loop in 20 lines of raw Python.

**Hook 2.** Most AI agent tutorials are just wrappers around 500MB of dependencies you don't need. You don't need a framework to build an agent—you just need a while-loop and a system prompt.

**Hook 3.** I wasted my entire evening trying to get an 'out-of-the-box' agent framework to stop hallucinating tool arguments. Here is how you write a deterministic tool executor yourself without the bloat.

**Hook 4.** If your AI agent needs a 4-step setup process and three custom environment variables just to print 'Hello World', you are doing it wrong. Let's build one using nothing but the official SDK.

**Hook 5.** The secret to AI agents isn't some complex cognitive architecture. It is literally just formatting JSON in a loop until the LLM decides it is done.

## 7 tips that actually move the needle

### Tip 1. Use pydantic for structured outputs instead of raw text parsing
_Why it matters:_ It forces the LLM to return valid JSON that maps directly to your Python objects without regex nightmares.

```
class ToolCall(BaseModel):
  name: str
  args: dict
```

### Tip 2. Bind tools directly using openai.pydantic_function_tool
_Why it matters:_ It automatically handles schema generation so you don't have to write manual JSON schemas.

```
tools = [openai.pydantic_function_tool(MyPydanticClass)]
```

### Tip 3. Keep a hard limit on your execution loop with a simple counter
_Why it matters:_ If your agent gets stuck in an infinite loop, it will drain your API credits before you finish your coffee.

```
for _ in range(max_iterations):
```

### Tip 4. Use tenacity to handle rate limits and transient API errors
_Why it matters:_ LLM APIs fail constantly, and a simple retry decorator keeps your agent from crashing mid-task.

```
@retry(stop=stop_after_attempt(3))
```

### Tip 5. Log the raw LLM prompts using rich instead of standard print statements
_Why it matters:_ It makes debugging the back-and-forth tool calls actually readable in your terminal.

```python
from rich import print_json
print_json(data=response)
```

### Tip 6. Use python-dotenv to load your API keys from a .env file
_Why it matters:_ Hardcoding keys in your agent script is the fastest way to get your account drained on GitHub.

```python
from dotenv import load_dotenv
load_dotenv()
```

### Tip 7. Use pytest with unittest.mock to test your tool execution logic
_Why it matters:_ It saves you money and lets you verify your agent's routing logic instantly without hitting the live API.

```
mock_agent.return_value = expected_json
```

## Step-by-step procedure

### 1. Step 1: Install the bare essentials
Avoid heavy frameworks and install just the OpenAI SDK and Pydantic to keep your environment clean.

```python
pip install openai pydantic python-dotenv
```

### 2. Step 2: Define your agent's tools
Create a standard Python function and define its input schema using Pydantic so the LLM knows how to call it.

```
class GetWeather(BaseModel):
    location: str
```

### 3. Step 3: Set up the system prompt
Tell the LLM exactly what tools it has access to and force it to output tool calls when it needs information.

```
system_prompt = "You are an assistant with access to tools. Use them."
```

### 4. Step 4: Write the execution loop
Write a simple while-loop that sends messages to the LLM, checks if it wants to call a tool, runs the tool, and feeds the result back.

```
while steps < max_steps:
    # call LLM, run tool, append to messages
```

### 5. Step 5: Run and verify the agent
Ask your agent a question that requires the tool and watch it execute the local function and return the final answer.

```python
response = run_agent("What is the weather in Kolkata?")
print(response)
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run without a token budget or iteration cap. Fix: Always wrap your agent's execution loop in a strict 'for i in range(max_turns)' block and track token usage via the API response metadata to avoid surprise bills.

## X / Twitter thread (copy-paste ready)

**1/** I wasted my entire evening fighting a bloated AI framework just to call a local Python function.

**2/** Turns out, you don't need 10 dependencies to build an AI agent. You just need 30 lines of raw Python, a while-loop, and Pydantic.

**3/** Tip 1: Use Pydantic to define your tools. The OpenAI SDK can convert these schemas automatically—no manual JSON writing required.

**4/** Tip 2: Cap your loops. If you don't put a strict 'max_iterations = 5' on your agent loop, a small hallucination will drain your wallet in minutes.

**5/** Tip 3: Feed the tool output back into the message history. The LLM needs to see the result of its own action to make the next decision.

**6/** Stop overcomplicating your stack. Write the loop yourself and keep it simple. Full code at CoderFact.

## LinkedIn version

It was 1 AM, and I was staring at a stack trace that looked like a novel.

All I wanted was to build a simple AI agent that could check a local database and send an email. But instead, I was fighting with a massive framework's 'agent executor' that refused to parse its own generated output. It was bloated, confusing, and completely unnecessary.

So I deleted the directory, opened a blank Python file, and went back to basics. No frameworks. Just the raw OpenAI SDK, Pydantic, and a simple while-loop.

Here is the secret: an AI agent is just a loop. You send a prompt, the LLM decides if it needs to call a tool, you run that tool locally, and you feed the result back to the LLM. That is it. You do not need five layers of abstractions to do this. You just need clean schemas and a strict iteration cap so your wallet doesn't get destroyed by an infinite loop.

Stop overcomplicating your AI stack. Build the loop yourself first so you actually understand what is happening under the hood.

#python #aiagents #softwareengineering #coderfact

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*