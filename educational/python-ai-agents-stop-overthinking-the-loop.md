# Python AI Agents: Stop Overthinking the Loop

_An agent is just an LLM sitting in a while-loop with tool definitions—stop using 800-page frameworks._

## Scroll-stopping hooks

**Hook 1.** Spent four hours debugging LangChain imports at 1am just to realize an AI agent is literally a while-loop and an if-statement.

**Hook 2.** Most devs give up on building AI agents because tutorials immediately dump 15 abstract wrapper classes on them.

**Hook 3.** You don't need a massive orchestration framework to build your first working agent in Python—just vanilla code and the official SDK.

**Hook 4.** The moment you stop treating 'agents' like magic and start treating them like recursive function callers, everything clicks.

**Hook 5.** Every 'autonomous agent' pitch is hiding the exact same 30-line while-loop under the hood. Here it is without the fluff.

## 7 tips that actually move the needle

### Tip 1. Use the official openai library's client.chat.completions.create directly instead of wrapper frameworks.
_Why it matters:_ It keeps your call stack transparent so you can actually read the raw payload errors.

```
response = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
```

### Tip 2. Define your tools as plain Python dictionaries adhering to the JSON schema spec.
_Why it matters:_ It eliminates third-party schema parser bugs and runs everywhere.

```
tools = [{'type': 'function', 'function': {'name': 'get_weather', 'parameters': {'type': 'object', 'properties': {'city': {'type': 'string'}}}}}]
```

### Tip 3. Map function names to callable references using an explicit dictionary registry.
_Why it matters:_ It completely prevents dangerous eval() calls when running agent-selected tools.

```
TOOL_MAP = {'get_weather': get_weather}
result = TOOL_MAP[tool_call.function.name](**json.loads(tool_call.function.arguments))
```

### Tip 4. Always hard-cap your agent's execution loop with a max_turns guard variable.
_Why it matters:_ It stops the model from burning your entire API credit balance when it gets stuck in an argument loop.

```
for _ in range(5):
    # loop logic here
    if not tool_calls: break
```

### Tip 5. Append the tool execution result back to the messages array with role 'tool' and the matching tool_call_id.
_Why it matters:_ The API rejects the request immediately if the output message cannot be matched to the calling step.

```
messages.append({'role': 'tool', 'tool_call_id': tool_call.id, 'content': json.dumps(result)})
```

### Tip 6. Use pydantic's BaseModel.model_json_schema() to generate tool schemas automatically.
_Why it matters:_ Writing raw nested JSON schemas by hand at 1am guarantees missing brackets.

```python
from pydantic import BaseModel
class Query(BaseModel): city: str
schema = Query.model_json_schema()
```

### Tip 7. Enable python-dotenv to isolate your keys before running ad-hoc agent scripts.
_Why it matters:_ It saves you from accidentally committing live OpenAI tokens inside scratchpad test scripts.

```python
from dotenv import load_dotenv
load_dotenv()
```

## Step-by-step procedure

### 1. Install the core client and load environment variables
Keep dependencies dead minimal. You only need the official OpenAI client library and python-dotenv to get going.

```python
pip install openai python-dotenv
```

### 2. Define a plain Python function and its JSON schema
Write the function you want the agent to use, then create the metadata schema that tells the model when and how to call it.

```python
def get_stock(symbol: str):
    return {'symbol': symbol, 'price': 142.50}

tools = [{'type': 'function', 'function': {'name': 'get_stock', 'description': 'Get live price', 'parameters': {'type': 'object', 'properties': {'symbol': {'type': 'string'}}, 'required': ['symbol']}}}]
```

### 3. Create the dispatch dictionary
Map the string name from your schema directly to your local Python function so you can execute it safely.

```
available_tools = {'get_stock': get_stock}
```

### 4. Implement the conversational execution loop
Send messages to the model, inspect tool_calls, run matching functions, and feed results back into the array.

```python
import json
messages = [{'role': 'user', 'content': 'What is the stock price of AAPL?'}]
for _ in range(3):
    res = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: break
    for call in msg.tool_calls:
        fn = available_tools[call.function.name]
        out = fn(**json.loads(call.function.arguments))
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': json.dumps(out)})
```

### 5. Print the final output to verify execution
Once the model finishes its tool calls, it synthesizes the final natural language answer into the message list.

```python
print(messages[-1].content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to append the assistant's intermediate response (the one containing tool_calls) before appending the tool results, which triggers a 400 InvalidRequestError. Always push response.choices[0].message to messages first.

## X / Twitter thread (copy-paste ready)

**1/** Most tutorials make building your first Python AI agent 10x harder than it actually is.

**2/** Stripped of heavy frameworks, an agent is just an LLM inside a while-loop that executes functions based on tool_calls.

**3/** Step 1: Define a normal Python function and map it in a dictionary. Never use eval() on LLM string responses.

**4/** Step 2: Pass that function's schema to client.chat.completions.create using the standard OpenAI tools parameter.

**5/** Step 3: Run the returned function call, feed the output back with role: 'tool', and loop until tool_calls is empty.

**6/** That is the whole core pattern. Build this natively once before you ever touch a bloated agent framework.

## LinkedIn version

It was 1am and I was down an absolute rabbit hole trying to get a basic agent to query an API.

Every tutorial I opened pointed me to massive orchestrators, custom abstractions, and 300-line documentation pages. I spent an hour debugging import errors and wrapper syntax before stepping back and asking: what is this actually doing under the hood?

Turns out, an agent is not mystical tech. It is literally just an API call, an array of message objects, and a simple loop.

The LLM returns a structured JSON payload saying 'run this function with these inputs'. You run your local Python function, push the output back into the message history, and invoke the model one more time to explain the answer. That is the entire architecture.

Once you build this loop from scratch with 30 lines of standard Python, you suddenly understand what every agent framework is doing—and when you actually don't need one.

#python #ai #softwareengineering #developers

_Tags: python, aiagents, coding, automation_

---
*By Suman Giri — built with the CoderFact engine.*