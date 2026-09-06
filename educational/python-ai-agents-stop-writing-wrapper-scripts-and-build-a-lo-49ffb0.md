# Python AI Agents: Stop writing wrapper scripts and build a loop

_How I finally got an LLM to stop hallucinating and actually run local bash commands for me._

## Scroll-stopping hooks

**Hook 1.** Spent until 2 AM trying to make an LLM write files to my disk, only for it to hallucinate library imports that don't exist. Here is how you actually build an autonomous agent that works.

**Hook 2.** Most 'AI agents' you see on Twitter are just glorified while-loops with a prompt that costs $4 a run. Let's build a real one that actually uses tools.

**Hook 3.** I got tired of manually copying API responses into my frontend code, so I built a Python agent to do it—and it only took 40 lines of code once I stopped using bloated frameworks.

**Hook 4.** You don't need LangChain or CrewAI to build your first agent. In fact, starting there is why you're confused.

**Hook 5.** The secret to AI agents isn't the model's size; it's how you parse the tool calls. Here's the raw Python setup I used to automate my CoderFact asset pipeline.

## 7 tips that actually move the needle

### Tip 1. Use instructor for structured JSON outputs
_Why it matters:_ It uses Pydantic to force the LLM to return exactly the schema you defined, saving you from writing fragile regex parsers.

```python
from pydantic import BaseModel
import instructor
from openai import OpenAI
client = instructor.from_openai(OpenAI())
```

### Tip 2. Debug agent loops visually with loguru
_Why it matters:_ It color-codes your agent's thought process, tool calls, and errors automatically so you can see where the loop broke.

```python
from loguru import logger
logger.info("Agent initialized")
logger.success("Tool executed successfully")
```

### Tip 3. Use subprocess.run with capture_output=True to run CLI tools
_Why it matters:_ It allows the agent to execute shell commands safely and read the stdout/stderr to self-correct its mistakes.

```python
import subprocess
result = subprocess.run(["git", "status"], capture_output=True, text=True)
print(result.stdout)
```

### Tip 4. Keep your API keys safe using python-dotenv
_Why it matters:_ Hardcoding keys in agent scripts is the fastest way to get your OpenAI account drained on GitHub.

```python
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
```

### Tip 5. Limit agent executions with a strict counter loop
_Why it matters:_ If your agent gets stuck in an error loop, it will happily burn through $50 of API credits in three minutes.

```python
max_iterations = 5
for i in range(max_iterations):
    print(f"Loop {i}")
```

### Tip 6. Mock expensive API calls during development using unittest.mock
_Why it matters:_ You don't need to pay OpenAI 2 cents every single time you test if your python parser works.

```python
from unittest.mock import Mock
mock_client = Mock()
mock_client.chat.completions.create.return_value = "Mocked response"
```

### Tip 7. Use rich to print beautiful terminal markdowns of decisions
_Why it matters:_ Reading raw JSON strings in a black terminal at 1 AM is how you ruin your eyesight.

```python
from rich import print
from rich.panel import Panel
print(Panel("[bold green]Agent Action:[/bold green] Running test script"))
```

## Step-by-step procedure

### 1. Step 1 Set up your environment
Install the bare essentials—no bloated frameworks, just the OpenAI SDK and Pydantic.

```python
pip install openai pydantic python-dotenv
```

### 2. Step 2 Define the tools your agent can use
Write standard Python functions that the model can invoke, like a basic file writer.

```python
def write_file(filename: str, content: str):
    with open(filename, "w") as f:
        f.write(content)
    return f"Saved to {filename}"
```

### 3. Step 3 Create the system prompt
Tell the LLM exactly how to format its thoughts and when to call your tools.

```
prompt = "You are an assistant. You can write files using the write_file tool. Respond with: TOOL: write_file | filename | content"
```

### 4. Step 4 Write the execution loop
Call the OpenAI API, parse the response, and if it asks to use a tool, run your local Python function.

```
response = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "Create a file named hello.txt with the text 'Hi Suman'"}])
```

### 5. Step 5 Handle tool execution and feedback
Run the Python function, capture the output, and send it back to the model so it knows it succeeded.

```
tool_output = write_file("hello.txt", "Hi Suman")
# Feed tool_output back to LLM in the next message turn
```

### 6. Step 6 Run the agent and verify
Execute your script and check your local directory to see if the file was created with the correct content.

```python
import os
assert os.path.exists("hello.txt")
print("Agent successfully created the file!")
```

## The mistake almost everyone makes

> ⚠️  Letting the agent run in an infinite loop without a hard stop. If the LLM hallucinates a tool name, it will fail, catch its own failure, try the exact same hallucinated tool again, and repeat this cycle until your API quota is completely blown. Fix: Always wrap your agent execution in a strict `for i in range(max_runs)` loop and hard-crash the script if it exceeds the limit.

## X / Twitter thread (copy-paste ready)

**1/** I spent last night until 2 AM trying to build a simple Python agent. I fell into the framework trap before realizing you only need 40 lines of clean Python. Here is how to build one without the bloat.

**2/** The industry wants you to think you need complex agentic frameworks. You don't. An agent is just an LLM in a while-loop that knows how to output structured text and trigger local functions.

**3/** Step 1: Use Pydantic to define your tools. Don't rely on raw system prompts to get JSON. Use the `instructor` library to force the LLM to output valid arguments for your local Python functions.

**4/** Step 2: Write your execution loop. Never let an agent run indefinitely. Wrap it in a strict `for i in range(5)` loop. If it doesn't solve the task in 5 steps, break and log the error.

**5/** Step 3: Feed the tool results back. When your local function runs (e.g., writing a file), append the output to the chat history as a 'tool' role. The LLM needs this context to decide its next move.

**6/** Stop overcomplicating your automation pipeline. Build the loop yourself, inspect the raw API calls, and keep it simple. I wrote a quick guide to get you started.

## LinkedIn version

It was 1:30 AM last night, and I was staring at a terminal full of infinite recursion errors.

I was trying to use a popular 'agentic framework' to automate a simple file-generation task for CoderFact. The framework had hundreds of stars on GitHub, promised 'autonomous magic,' and yet it kept failing to parse its own outputs, burning through my OpenAI credits while doing absolutely nothing.

That is when I closed the tab, deleted the virtual environment, and decided to write a raw Python loop instead.

Here is the truth: you do not need bloated frameworks to build your first AI agent. An agent is just an LLM in a loop. It looks at a task, decides to call a function, gets the result of that function, and decides what to do next. When you write this loop yourself using basic Python and Pydantic, the magic disappears—and is replaced by actual control.

Next time you want to build an agent, skip the wrapper libraries. Write a simple execution loop, cap it at 5 iterations so it doesn't drain your wallet, and parse the tool outputs yourself. Your code will be faster, easier to debug, and you will actually understand why it works.

#python #aiagents #softwareengineering #buildinpublic #backend

_Tags: python, aiagents, automation, backend_

---
*By Suman Giri — built with the CoderFact engine.*