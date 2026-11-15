# AI Agents in Python: Stop Loop-Prompting, Use a Loop Instead

_How I finally got an LLM to stop hallucinating and actually run local Python tools at 1 AM._

## Scroll-stopping hooks

**Hook 1.** Most 'AI agent' tutorials are just 200 lines of string formatting around an API call. Here is what an actual agent looks like.

**Hook 2.** I spent three hours debugging why my LLM kept lying about executing code, only to realize I was missing a 5-line while-loop.

**Hook 3.** You don't need LangChain or heavy frameworks to build a working AI agent. Plain Python and the OpenAI SDK are enough.

**Hook 4.** Stop passing full conversation histories back and forth manually—let JSON function schemas handle tool calls properly.

**Hook 5.** If your AI script can't decide when to stop calling tools, your control loop is broken. Let's fix it.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to auto-generate JSON schemas for your tools instead of writing raw dictionaries
_Why it matters:_ Manual JSON schemas break the moment you rename a argument or change a type.

```python
from pydantic import TypeAdapter
schema = TypeAdapter(MyToolArgs).json_schema()
```

### Tip 2. Bind native Python functions to OpenAI's tools parameter directly
_Why it matters:_ It forces the model to return structured argument payloads instead of messy Markdown code blocks.

```
response = client.chat.completions.create(model='gpt-4o', messages=msgs, tools=my_tools)
```

### Tip 3. Wrap the tool execution logic in a explicit while-loop that breaks on message.content
_Why it matters:_ If you don't loop until tool_calls is empty, the agent stops halfway through complex multi-step tasks.

```
while response.choices[0].finish_reason == 'tool_calls':
    execute_tools(response)
    response = call_api()
```

### Tip 4. Append tool results back into the context using the 'tool' role and matching tool_call_id
_Why it matters:_ The API will crash with a 400 error if your response context drops the ID mapping.

```
messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(result)})
```

### Tip 5. Set a hard cap on iteration count using a maximum step counter in your execution loop
_Why it matters:_ An unconstrained agent loop will burn through your API credits in 60 seconds if it gets stuck.

```
if step_count > 5:
    raise TimeoutError('Agent exceeded maximum allowed tool steps')
```

### Tip 6. Log raw API requests with httpx debugging enabled to see actual tool call payloads
_Why it matters:_ Silent schema mismatches fail softly inside the model without throwing python exceptions.

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Tip 7. Use docstrings as tool descriptions—the LLM reads them to pick the right function
_Why it matters:_ Vague docstrings cause the model to pick the wrong tool or guess arguments incorrectly.

```python
def fetch_weather(city: str):
    """Fetches live temperature in Celsius for a given city name."""
```

## Step-by-step procedure

### 1. Install dependencies and setup OpenAI client
Grab the official openai SDK and pydantic for schema parsing.

```python
pip install openai pydantic
```

### 2. Define a concrete Python function for the agent to execute
Create a real tool, like a local file reader or system command, complete with type hints.

```python
def read_file(filepath: str) -> str:
    with open(filepath, 'r') as f:
        return f.read()
```

### 3. Declare the function schema array
Structure the function definition so the OpenAI API understands its parameter requirements.

```
tools = [{'type': 'function', 'function': {'name': 'read_file', 'description': 'Reads local text file', 'parameters': {'type': 'object', 'properties': {'filepath': {'type': 'string'}}, 'required': ['filepath']}}}]
```

### 4. Build the main execution loop
Handle model responses, call the local Python function when requested, and push the output back to context.

```python
messages = [{'role': 'user', 'content': 'What is inside demo.txt?'}]
while True:
    res = client.chat.completions.create(model='gpt-4o', messages=messages, tools=tools)
    msg = res.choices[0].message
    if not msg.tool_calls:
        print('Final Answer:', msg.content)
        break
    messages.append(msg)
    for call in msg.tool_calls:
        out = read_file(**json.loads(call.function.arguments))
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': out})
```

### 5. Verify end-to-end execution
Create a local file 'demo.txt' and run the script—it should inspect the file automatically and report the contents.

```
python agent.py
```

## The mistake almost everyone makes

> ⚠️  Forgetting to push the original assistant message containing tool_calls back to the messages list before pushing the tool result. The API requires the sequence to be User -> Assistant (tool request) -> Tool (result). Fix: append the entire response.choices[0].message object before adding the tool execution output.

## X / Twitter thread (copy-paste ready)

**1/** Most 'AI Agent' frameworks hide the simple reality of how tool calls work.

**2/** At 1 AM today, I got fed up with heavy agent libraries hiding simple API errors. Here is how tool loops actually work in plain Python.

**3/** Step 1: Define a normal Python function with explicit types and docstrings.

**4/** Step 2: Pass the function JSON schema to OpenAI's tool parameter.

**5/** Step 3: Run a while-loop. If finish_reason is 'tool_calls', run your Python code local and feed the string output back into messages[].

**6/** No black magic—just a message list and a control loop. Build it yourself before grabbing a heavy framework.

## LinkedIn version

I spent half of last night trying to figure out why an agent library kept hanging on a basic file-read task. After diving through layers of abstractions, I deleted the framework and rewrote the agent in 30 lines of plain Python.

Here is the truth about AI agents: they are just standard API calls wrapped in a while-loop. The model doesn't run your code. It just inspects your schema, pauses, and tells your Python runtime—'Hey, execute this function name with these JSON arguments.'

Your code executes the function, appends the output to the conversation array as a 'tool' role message, and sends it back to the API. The loop continues until the model has enough context to spit out a plain text response.

Once you build this mechanism manually once using just the official OpenAI client and standard Python, the hype clears up. You realize you don't need giant third-party libraries for basic automation toolkits.

Start small: write one local function, expose it to the client via JSON schema, and manage the execution loop yourself. You'll save hours of debugging generic framework tracebacks.

#python #aiengineering #softwaredevelopment #automation #coding

_Tags: python, aiagents, openai, backend_

---
*By Suman Giri — built with the CoderFact engine.*