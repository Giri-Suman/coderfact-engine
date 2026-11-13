# AI Agents in Python: Stop Loop-Prompting, Start Function Calling

_How I finally got a Python script to do actual work instead of just hallucinating text at 1 AM._

## Scroll-stopping hooks

**Hook 1.** Most 'AI agents' on GitHub are just infinite while-loops wrapping an OpenAI API call. Here is how you build a real one that actually runs tools.

**Hook 2.** I spent three hours debugging why my AI agent kept inventing fake shell commands. The fix took four lines of function-calling code.

**Hook 3.** If your Python AI script can't touch your local filesystem or call an external API safely, it isn't an agent—it's just an expensive chatbot.

**Hook 4.** Stop using massive, black-box agent frameworks until you've written a basic tool-calling loop in raw Python first.

**Hook 5.** Built my first actual working AI agent last night at 1 AM. It didn't require LangChain, AutoGPT, or 50 dependencies—just standard Python and `pydantic`.

## 7 tips that actually move the needle

### Tip 1. Use `pydantic` to declare your agent's tool schemas instead of writing raw JSON schemas by hand.
_Why it matters:_ It prevents runtime type errors and automatically generates strict JSON schemas that LLMs actually respect.

```python
from pydantic import BaseModel, Field
class FetchUrl(BaseModel):
    url: str = Field(description='The full HTTP URL to scrape')
```

### Tip 2. Pass function definitions directly inside the OpenAI `tools` array using `model_dump()`.
_Why it matters:_ It keeps your code clean and ensures your schema stays perfectly synced with your Python functions.

```
tools = [{'type': 'function', 'function': {'name': 'fetch', 'parameters': FetchUrl.model_json_schema()}}]
```

### Tip 3. Set `tool_choice='auto'` and inspect `response.choices[0].message.tool_calls` before executing anything.
_Why it matters:_ The model will tell you *which* tool to run and hand you the validated arguments ready to parse.

```
if message.tool_calls:
    tool_call = message.tool_calls[0]
    args = json.loads(tool_call.function.arguments)
```

### Tip 4. Execute the matching local Python function using a mapping dictionary instead of dangerous `eval()` calls.
_Why it matters:_ Using `eval()` on LLM outputs is how you accidentally delete your home directory.

```
TOOL_MAP = {'fetch': run_fetch_logic}
result = TOOL_MAP[tool_call.function.name](**args)
```

### Tip 5. Append the tool's execution result back to the conversation history as a message with `role='tool'`.
_Why it matters:_ The LLM needs to see the tool's output to process the next step or answer your prompt.

```
messages.append({'role': 'tool', 'tool_call_id': tool_call.id, 'content': str(result)})
```

### Tip 6. Cap your main Execution Loop with `max_iterations = 5` to avoid burning API credits on infinite loops.
_Why it matters:_ If an agent gets confused, it will happily ping OpenAI 500 times in 30 seconds unless you stop it.

```
for _ in range(5):
    response = client.chat.completions.create(...)
    if not response.choices[0].message.tool_calls: break
```

### Tip 7. Log raw LLM responses to a local `.log` file or use `rich.console` for colored terminal outputs.
_Why it matters:_ When an agent fails silently, you need to see whether it chose the wrong tool or failed to parse the arguments.

```python
from rich import print
print(f'[bold green]Agent chose tool:[/bold green] {tool_call.function.name}')
```

## Step-by-step procedure

### 1. Step 1: Set up dependencies
Install the lightweight official client and Pydantic. Avoid heavy agent frameworks until you understand the underlying loop.

```python
pip install openai pydantic
```

### 2. Step 2: Define your executable tool
Write a plain Python function that does real work—like checking a file size or fetching data—and annotate its parameters using Pydantic.

```python
import os
from pydantic import BaseModel, Field

class ReadFile(BaseModel):
    filepath: str = Field(description='Path to local file')

def read_file(filepath: str) -> str:
    return open(filepath).read() if os.path.exists(filepath) else 'File not found'
```

### 3. Step 3: Register tools with the LLM API
Construct the OpenAI payloads so the model knows what tools exist and what inputs they expect.

```
tools = [{
    'type': 'function',
    'function': {
        'name': 'read_file',
        'description': 'Reads local file contents',
        'parameters': ReadFile.model_json_schema()
    }
}]
```

### 4. Step 4: Implement the execution loop
Call the model, check if it wants to invoke a tool, execute the function locally, and feed the result back to the model.

```
messages = [{'role': 'user', 'content': 'What is in requirements.txt?'}]
response = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
if response.choices[0].message.tool_calls:
    # Route to local function and append result
    pass
```

### 5. Step 5: Run and verify local file access
Execute the full script against a real local file and confirm the agent successfully reads the file without hallucinating content.

```
python agent.py
# Output: 'The requirements.txt file contains: openai, pydantic.'
```

## The mistake almost everyone makes

> ⚠️  Passing raw LLM strings straight into python's `eval()` or `exec()` to execute generated code. If the model hallucinates a bad shell command, it can wipe local files. Fix: Use strict Pydantic parsing and map function names explicitly to pre-written, safe local Python functions.

## X / Twitter thread (copy-paste ready)

**1/** Most 'AI agent' tutorials overcomplicate things with 10 abstractions you don't need.

**2/** Last night at 1 AM, I got fed up with bloated frameworks and built a clean agent loop in raw Python using function calling. Here's how it works.

**3/** 1/ Use Pydantic to build tool schemas instead of manually writing JSON. It guarantees types match your Python functions.

**4/** 2/ Send tool schemas via `tools` array. Check `message.tool_calls`—if present, don't return text yet. Route to your local python functions.

**5/** 3/ Pass the execution output back into the message history with `role='tool'`. Let the model digest the real data and print the final answer.

**6/** Build it natively once so you actually understand what's happening under the hood. Full step-by-step breakdown coming to CoderFact!

## LinkedIn version

I spent half of last night fighting with an AI agent framework that kept hiding errors under five layers of abstractions.

At 1 AM, I wiped the project, opened a clean file, and wrote a simple Python loop using native tool calling and Pydantic schemas instead.

Turns out, a real agent only needs three core pieces: a Pydantic schema so the model knows what parameters to send, a dispatcher map that routes function names to local code safely, and a simple while-loop that feeds tool outputs back to the model until it finishes the task.

No magic. No massive dependency tree. Just predictable Python code that executes when the model asks it to.

If you want to build automation tools that actually work, build the loop manually first before pulling in heavy frameworks. You'll save hours of debugging runtime hallucinations.

#python #aiengineering #backenddev #automation #coderfact

_Tags: python, aiagents, pydantic, automation_

---
*By Suman Giri — built with the CoderFact engine.*