# Python AI agents: Stop writing nested if-else chains for LLMs

_Build a self-correcting agent in 50 lines of Python without heavy, over-engineered frameworks._

## Scroll-stopping hooks

**Hook 1.** I spent three hours last night trying to make an LLM output clean JSON, only for it to hallucinate a trailing comma and break my parser. The fix wasn't a better prompt—it was a 10-line Python loop that lets the model debug its own syntax.

**Hook 2.** You don't need LangChain's massive dependency tree to build an AI agent. A simple while-loop, a system prompt, and a basic tool-calling schema in raw Python will outperform most bloated frameworks anyway.

**Hook 3.** Most 'AI agents' I see online are just expensive wrappers around a single API call. If your agent doesn't have a feedback loop to inspect its own output and run local code, you just built a chatbot with a fancy name.

**Hook 4.** It's 1 AM, your API credits are draining, and your agent is stuck in an infinite loop calling the same broken tool. Here is the exact control-loop pattern I built for CoderFact to stop agents from burning cash.

**Hook 5.** We need to talk about tool-calling in Python. Stop manually parsing strings with regex—OpenAI and Anthropic literally accept JSON schemas for functions, and matching them is just a dictionary lookup.

## 7 tips that actually move the needle

### Tip 1. pydantic for structured output validation
_Why it matters:_ It forces the LLM to conform to a strict schema before your code even attempts to run the arguments.

```python
from pydantic import BaseModel
class ToolCall(BaseModel):
    name: str
    args: dict
```

### Tip 2. instructor library for type-safe API calls
_Why it matters:_ It patches the OpenAI client to return validated Pydantic objects directly instead of raw, untyped JSON strings.

```python
import instructor
client = instructor.from_openai(OpenAI())
resp = client.chat.completions.create(response_model=ToolCall)
```

### Tip 3. sys.executable subprocess pattern
_Why it matters:_ Running agent-generated Python code locally requires executing it safely inside your current environment's virtualenv.

```python
import sys, subprocess
subprocess.run([sys.executable, "-c", code], capture_output=True)
```

### Tip 4. Hardcount iteration limits on execution loops
_Why it matters:_ It acts as a circuit breaker to prevent your agent from running infinitely and draining your API budget on a single run.

```
for step in range(MAX_STEPS):
    if task_completed: break
```

### Tip 5. System prompt injection with jinja2
_Why it matters:_ Dynamically inserting tool definitions and historical state into your prompts is cleaner and less error-prone than messy f-strings.

```python
from jinja2 import Template
Template("Tools: {{tools}}").render(tools=my_tools)
```

### Tip 6. Local execution testing with litellm
_Why it matters:_ You can swap your backend to a local Llama 3 model with a single line of code to test your agent's logic for free.

```python
import litellm
litellm.completion(model="ollama/llama3", messages=msgs)
```

### Tip 7. Single-file state tracking with a dataclass
_Why it matters:_ Keeping your agent's history, tool outputs, and execution steps in a simple typed object makes debugging late-night runs trivial.

```
@dataclass
class AgentState:
    history: list
    steps: int
```

## Step-by-step procedure

### 1. Step 1: Define your Python tools
Write standard Python functions and describe them using docstrings or simple JSON schemas so the LLM knows what arguments they accept.

```python
def get_weather(city: str) -> str:
    return f"22C in {city}"
```

### 2. Step 2: Set up the ReAct system prompt
Explain the Reason-Act-Observe loop to the LLM so it knows how to think before calling a tool.

```
SYSTEM_PROMPT = "You can use tools. Format: Thought, Action, Observation."
```

### 3. Step 3: Initialize the OpenAI client
Set up a standard client to send the prompt, history, and available tool definitions to the model.

```python
from openai import OpenAI
client = OpenAI()
```

### 4. Step 4: Build the execution loop
Write a loop that parses the model's tool calls, runs the corresponding Python functions, and appends the result to the messages.

```
while not finished:
    res = call_llm(messages)
    run_tool(res.tool_name)
```

### 5. Step 5: Run and verify the agent
Execute a script where the agent must use your tools to solve a query, and print the final execution trace to verify it made the right decisions.

```
agent.run("What is the weather in Kolkata?")
```

### 6. Step 6: Add the execution circuit breaker
Prevent infinite loops by raising an error if the agent exceeds 5 steps without returning a final answer.

```
if steps > 5:
    raise Exception("Agent loop limit exceeded")
```

## The mistake almost everyone makes

> ⚠️  Letting the agent call tools without validating the arguments first. The LLM will inevitably hallucinate arguments that don't match your Python function signatures. The fix is to use Pydantic to validate the arguments, catch the validation error, and feed the error message back to the LLM so it can correct its own mistake on the next turn.

## X / Twitter thread (copy-paste ready)

**1/** Python AI agents don't need massive frameworks—you can build a self-correcting agent in 50 lines of raw code.

**2/** I spent last night debugging an agent that ran into an infinite loop and ate $10 of API credits. Frameworks hide this logic; writing it yourself teaches you how to control the flow.

**3/** Tip 1: Use Pydantic to define your tools. Don't parse raw text with regex—let the model output structured JSON that maps directly to your Python functions.

**4/** Tip 2: Build a strict while-loop with a hard limit of 5 iterations. If the agent doesn't solve the task by then, kill the process. Your wallet will thank you.

**5/** Tip 3: Feed Python execution errors back into the LLM. If its code crashes, write a handler that sends the traceback back as a user message so it can self-correct.

**6/** I put together the minimal template I use for CoderFact tools. Try building one tonight—it's way simpler than you think.

## LinkedIn version

It was 1 AM last night, and I was staring at a terminal screen filled with API timeout errors. I was trying to build a simple automation helper for CoderFact using one of those massive, trending AI agent frameworks. But between the nested abstractions, undocumented breaking changes, and the fact that it took three imports just to run a print statement, I had enough. I pip uninstalled the library and decided to build it from scratch.

It turns out, an AI agent is just a while-loop with a system prompt and some structured data validation. You don't need hundreds of files of boilerplate. You just need a model that can output JSON, a validator like Pydantic to make sure the arguments are real, and a basic error handler to catch bugs.

When you strip away the hype, the core pattern is simple: the model thinks, it decides to call a Python function, your code runs that function, and you feed the result back to the model. If the function crashes, you don't panic—you just send the traceback back to the LLM and let it write a fix.

Once I wrote this loop myself, the agent actually started working. No magic, no over-engineered wrappers, just standard Python. Plus, I can actually debug it now when things go wrong at midnight.

Stop overcomplicating your AI stack. Write the loop yourself first, understand the execution flow, and only pull in heavy frameworks when you genuinely hit their limits.

#python #aiagents #automation #backenddevelopment

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*