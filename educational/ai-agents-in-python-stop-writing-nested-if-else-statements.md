# AI Agents in Python: Stop writing nested if-else statements

_Build a dead-simple, self-correcting Python agent using raw code in under 10 minutes without the enterprise bloat._

## Scroll-stopping hooks

**Hook 1.** I wasted three hours last night trying to get a basic LangChain agent to stop looping infinitely, only to realize a 20-line raw Python loop does it better.

**Hook 2.** Most 'AI Agent' tutorials are just wrappers around expensive API calls that break the second your prompt has a typo.

**Hook 3.** You don't need a heavy enterprise framework to build an agent—just a simple state machine, a system prompt, and a while-loop.

**Hook 4.** Spent my 1 AM debugging why my LLM agent refused to call the calculator tool, and the fix was literally changing a single function docstring.

**Hook 5.** Stop overcomplicating AI agents; if your code can't run a basic tool-calling loop in standard Python, adding LangChain won't save you.

## 7 tips that actually move the needle

### Tip 1. Tool binding with Pydantic
_Why it matters:_ Forces the LLM to output structured JSON matching your function arguments instead of raw text.

```python
from pydantic import BaseModel
class Search(BaseModel):
    query: str
```

### Tip 2. Use the instructor library instead of raw OpenAI SDK
_Why it matters:_ It handles retry logic and parsing errors automatically so your agent doesn't crash on bad JSON.

```python
import instructor
client = instructor.from_openai(OpenAI())
```

### Tip 3. Strict system prompts for loop termination
_Why it matters:_ Prevent infinite runs by forcing the model to emit a specific end token like [FINISHED].

```
prompt = 'If done, write [FINISHED] and stop.'
```

### Tip 4. Track state using a native Python dict
_Why it matters:_ Heavy state managers add unnecessary complexity when a simple dictionary passed to your steps works fine.

```
state = {'messages': [], 'steps': 0}
```

### Tip 5. Set a hard recursion limit
_Why it matters:_ Protect your wallet from runaway agent loops that spam the API 50 times in 3 seconds.

```
if state['steps'] > 5: break
```

### Tip 6. Use docstrings as tool descriptions
_Why it matters:_ LLMs use your Python function docstrings to decide which tool to call, so make them incredibly literal.

```python
def add(a, b):
    '''Adds two integers. Use this for math.'''
```

### Tip 7. Log raw LLM inputs and outputs with LangSmith
_Why it matters:_ Debugging agents is impossible without seeing the exact prompt and JSON response that triggered a failure.

```
export LANGCHAIN_TRACING_V2='true'
```

## Step-by-step procedure

### 1. Step 1: Initialize the environment
Install the bare essentials—no bloated frameworks, just the core OpenAI and Pydantic libraries.

```python
pip install openai pydantic
```

### 2. Step 2: Define your agent's tools
Write a standard Python function and use Pydantic to define its schema so the LLM knows what arguments it expects.

```
class Calculate(BaseModel):
    expression: str
```

### 3. Step 3: Write the system prompt
Tell the model exactly what tools it has, how to format its thoughts, and how to signal when it is finished.

```
prompt = 'You have tools. Finish with [DONE].'
```

### 4. Step 4: Create the execution loop
Write a simple while loop that takes the LLM's response, checks if a tool call was requested, runs the local function, and feeds the result back.

```
while step < 5:
    # Call LLM and run tool
```

### 5. Step 5: Run the agent and verify
Pass a query that requires the tool and print out each step of the loop to watch the agent reason and self-correct.

```
response = run_agent('What is 45 * 82?')
```

### 6. Step 6: Add the panic switch
Implement a step counter inside the loop to automatically terminate the execution if the agent takes more than 5 steps.

```
if step_count > 5: raise Exception('Max steps reached')
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run without a hard execution cap. If the LLM gets confused, it will loop infinitely, calling your API and draining your balance. Fix it by wrapping your main agent loop in a strict 'for i in range(max_turns)' block instead of a raw 'while True'.

## X / Twitter thread (copy-paste ready)

**1/** AI Agents in Python: Stop writing nested if-else statements.

**2/** Spent last night debugging an agent loop that ran 40 times because of a bad prompt—here is how to build a simple, safe one in 20 lines of Python.

**3/** Tip 1: Use Pydantic to strictly define your tools so the LLM doesn't hallucinate invalid arguments.

**4/** Tip 2: Ditch the heavy frameworks; a standard Python while loop with a hard step limit of 5 is all you need to start.

**5/** Tip 3: Write explicit docstrings on your tool functions—the LLM reads these to decide what to call.

**6/** Try this setup today and stop burning your API budget on infinite loops. Full guide on CoderFact.

## LinkedIn version

It was 1 AM, and my terminal was scrolling faster than a matrix screensaver. I had built a "simple" AI agent using a popular framework, but a minor prompt typo sent it into a doom loop—spamming my API key and racking up a $15 bill in minutes.

That is when I realized we have overcomplicated agents. You do not need massive enterprise frameworks or hundreds of abstractions to build something useful. You just need a standard Python loop, a structured output tool, and a hard exit condition.

I stripped out all the bloat and rebuilt it using raw Python and Pydantic. By defining tools as clean Python functions with explicit docstrings, the LLM knew exactly when and how to call them. No magic, just standard code.

The secret sauce is the loop control. I added a simple iteration counter that kills the process if it takes more than 5 steps. Suddenly, debugging became trivial, and my wallet was safe.

If you are trying to build your first agent, step away from the heavy SDKs. Write a simple loop, bind your functions, and watch it work without the headache.

python automation coderfact softwareengineering

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*