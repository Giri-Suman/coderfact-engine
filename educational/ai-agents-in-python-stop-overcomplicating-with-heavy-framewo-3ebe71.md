# AI agents in Python: Stop overcomplicating with heavy frameworks

_Build a working, self-correcting agent in under 50 lines of raw Python without the LangChain bloat._

## Scroll-stopping hooks

**Hook 1.** Spent last night fighting a 400-line framework abstraction just to make a simple API call. Stripped it all out for raw Python at 2 AM, and guess what—it actually works now.

**Hook 2.** Everyone is selling you complex agentic libraries when all you actually need is a simple while-loop and a structured system prompt.

**Hook 3.** I stayed up until 1:30 AM trying to debug an AI agent that kept looping infinitely. The fix wasn't a fancier library—it was a basic Python list acting as short-term memory.

**Hook 4.** Stop installing massive SDKs for simple AI tasks. If your Python agent needs three wrapper libraries just to run a bash command, you're doing it wrong.

**Hook 5.** I built a quick automation tool for CoderFact yesterday and realized most agent tutorials are needlessly complex. Here is the dead-simple Python pattern I actually ended up using.

## 7 tips that actually move the needle

### Tip 1. Use litellm instead of native provider SDKs
_Why it matters:_ It standardizes inputs and outputs across Anthropic, OpenAI, and local Ollama models with a single unified format.

```python
from litellm import completion
res = completion(model='gpt-4o-mini', messages=[{'role': 'user', 'content': 'Hi'}])
```

### Tip 2. Enforce structured outputs with Pydantic's BaseModel
_Why it matters:_ It forces the LLM to return valid JSON that maps directly to Python objects, preventing parsing errors.

```python
from pydantic import BaseModel
class ToolCall(BaseModel):
    name: str
    args: dict
```

### Tip 3. Control execution with a simple while loop and counter
_Why it matters:_ Avoid complex state machines—a basic loop with a max iteration limit prevents infinite run bills.

```
max_steps = 5
for step in range(max_steps):
    # agent logic here
```

### Tip 4. Clean LLM output with a basic markdown strip utility
_Why it matters:_ LLMs occasionally hallucinate markdown blocks around JSON, so you need a fallback parser to avoid JSONDecodeError.

```
raw_json = raw_text.strip().removeprefix('```json').removesuffix('```').strip()
```

### Tip 5. Run local system commands safely using subprocess.run
_Why it matters:_ Let your agent execute local shell tools by capturing stdout and stderr to feed back into the prompt.

```python
import subprocess
res = subprocess.run(['ping', '-c', '1', 'google.com'], capture_output=True, text=True)
```

### Tip 6. Track agent state changes using the rich console library
_Why it matters:_ When your agent is thinking, printing colored terminal outputs helps you trace exactly where its logic breaks at 1 AM.

```python
from rich import print
print(f'[bold red]Tool Executed:[/bold red] {tool_name}')
```

### Tip 7. Manage API keys cleanly with python-dotenv
_Why it matters:_ Keeps your Anthropic and OpenAI keys out of your git commits without hardcoding strings.

```python
from dotenv import load_dotenv
import os
load_dotenv()
```

## Step-by-step procedure

### 1. Step 1: Install clean dependencies
Install litellm and python-dotenv to handle API calls and environment variables without heavy framework overhead.

```python
pip install litellm python-dotenv pydantic rich
```

### 2. Step 2: Define your system instructions
Write a clear system prompt telling the LLM it has access to specific tools and must respond in a strict JSON format.

```
SYSTEM_PROMPT = "You are an assistant with access to tools. Respond ONLY with JSON: {'tool': 'name', 'args': {}}"
```

### 3. Step 3: Create the tool registry
Map tool names as strings directly to real Python functions using a standard dictionary.

```python
def get_weather(city): return f'Sunny in {city}'
tools = {'get_weather': get_weather}
```

### 4. Step 4: Build the execution loop
Write a loop that sends messages to the LLM, parses the JSON tool call, runs the local function, and appends the result back to the message history.

```
messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
# Add loop logic here to run tools and feed results back
```

### 5. Step 5: Run and verify the output
Ask the agent to check the weather in Kolkata and print the conversation history to verify it successfully called the tool and gave the final answer.

```
messages.append({'role': 'user', 'content': 'Is it raining in Kolkata?'})
# Run your loop and watch the terminal print the tool execution
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run without an iteration cap, which leads to infinite loops and massive API bills when the LLM gets confused. Fix this by hardcoding a max_iterations limit in your loop.

## X / Twitter thread (copy-paste ready)

**1/** Python agents don't need 10,000 lines of framework code—I built one in 50 lines last night.

**2/** I was tired of fighting bloated abstractions at 1 AM, so I stripped everything down to a simple while-loop and litellm.

**3/** First rule: Use Pydantic to force structured JSON outputs so your parser doesn't break on the first API call.

**4/** Second rule: Write a simple dictionary map to connect the LLM's JSON tool requests to actual Python functions.

**5/** Third rule: Hardcode a max limit of 5 iterations. If the agent can't solve it by then, it's looping and burning your money.

**6/** Here is the clean pattern I'm using to build lightweight automations over at CoderFact. Try it yourself tonight.

## LinkedIn version

It was 1 AM last night, and I was staring at a stack trace from a popular "agentic" framework. All I wanted was to build a simple helper tool for CoderFact that checks a database and sends an alert. Instead, I was deep in nested abstractions, trying to figure out why a simple prompt was throwing a validation error three libraries deep.

So I deleted the package. I started a clean Python file, imported litellm, and wrote a basic while loop.

No complex state graphs. No enterprise-grade cognitive architectures. Just a system prompt telling the model to return JSON, a parser, and a dictionary mapping tool names to actual Python functions. By 1:45 AM, the agent was running, calling local tools, and self-correcting when a tool returned an error.

We have overcomplicated AI development. You do not need a massive framework to build an agent—you need a solid understanding of loops, structured outputs, and basic error handling.

If you are tired of fighting black-box libraries, try building your next agent from scratch. It takes less than 50 lines of pure Python, and you will actually understand how your code works when it breaks.

#python #aiagents #automation #backenddev

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*