# Python AI Agents: Build One Tonight Without Massive Frameworks

_Stop overcomplicating LangChain. Write a clean ReAct loop in under 40 lines of Python._

## Scroll-stopping hooks

**Hook 1.** Spent four hours debugging an agent framework last night before realizing the whole pattern is literally just a while loop and a function map.

**Hook 2.** Most tutorials hand you a 400-page framework to build an AI agent that searches Google. You can write the entire loop in standard Python.

**Hook 3.** If your AI agent framework requires 12 abstractions just to run a basic math function, you're not building an agent—you're building technical debt.

**Hook 4.** I stayed up till 2am rewriting my agent loop from scratch because the library I used broke its own tool-calling syntax again.

**Hook 5.** An AI agent isn't magic. It's an LLM trapped in a while-loop with permission to run your Python functions until it gets the answer.

## 7 tips that actually move the needle

### Tip 1. Use standard Python type hints to generate function schemas automatically
_Why it matters:_ It avoids handwriting messy JSON schemas for every custom tool your model calls.

```python
def get_stock(symbol: str) -> float:
    """Fetches latest price for a stock symbol."""
    return 150.25
```

### Tip 2. Enforce strict JSON schema responses using pydantic models
_Why it matters:_ Models love hallucinating tool arguments unless you validate them at the boundary.

```python
from pydantic import BaseModel
class SearchArgs(BaseModel):
    query: str
```

### Tip 3. Cap your execution loop with an explicit max_iterations counter
_Why it matters:_ Unchecked agents will happily burn through your API credits in an infinite retry loop.

```
for _ in range(5):
    response = client.chat.completions.create(...)
    if not response.choices[0].message.tool_calls: break
```

### Tip 4. Inspect the raw payload with the official openai Python client
_Why it matters:_ Framework abstractions hide the actual tool-call messages being passed back into context.

```python
from openai import OpenAI
client = OpenAI()
print(client.chat.completions.create(model='gpt-4o-mini', messages=history))
```

### Tip 5. Return structured error strings from tools directly into the message history
_Why it matters:_ The LLM can read the exact Python traceback and fix its own input arguments on the next step.

```
except Exception as e:
    return f"Tool failed with error: {str(e)}"
```

### Tip 6. Use litellm to test local models without changing tool syntax
_Why it matters:_ It gives you a drop-in OpenAI-compatible interface for Ollama and local models.

```python
import litellm
res = litellm.completion(model='ollama/llama3.1', messages=msgs, tools=tools)
```

### Tip 7. Maintain conversation context as a single flat list of standard dictionaries
_Why it matters:_ It makes debugging painless because you can print the full state with simple json.dumps.

```
messages = [{"role": "user", "content": "What is 42 * 8?"}]
# Just append tool outputs directly
```

## Step-by-step procedure

### 1. Install the official OpenAI package
Keep dependencies to a bare minimum so you actually understand where errors originate.

```python
pip install openai
```

### 2. Define a plain Python tool function
Write the exact logic you want the agent to execute when needed.

```python
def calculate(expression: str) -> str:
    return str(eval(expression))
```

### 3. Declare the tool schema for the model
Tell the model what the function is called and what arguments it accepts.

```
tools = [{
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Evaluates a math string",
        "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}
    }
}]
```

### 4. Map function names to actual Python callables
Use a basic dictionary lookup to route tool execution safely.

```
available_tools = {"calculate": calculate}
```

### 5. Run the execution while-loop
Send the prompt, check for tool calls, execute the mapped function, and append the result back to messages.

```
messages = [{"role": "user", "content": "What is 1337 * 42?"}]
while True:
    res = client.chat.completions.create(model="gpt-4o-mini", messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: break
    for call in msg.tool_calls:
        args = json.loads(call.function.arguments)
        result = available_tools[call.function.name](**args)
        messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
```

### 6. Print the final output and verify execution
Check the last message in your context to confirm the agent used the tool and gave the right answer.

```python
print(messages[-1].content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to send the assistant's initial message containing the tool_calls array back to the API alongside the tool result. The API will reject your request with a 400 error unless the assistant message precedes the tool role response.

## X / Twitter thread (copy-paste ready)

**1/** You don't need a massive framework to build an AI agent in Python. Here's how the pattern actually works.

**2/** Spent half the night wrestling multi-layered agent libraries before realizing the core loop is just a 30-line while-loop.

**3/** First: Define a plain Python function and pass its JSON schema into the OpenAI chat completions API using the tools argument.

**4/** Next: Map the function names in a dictionary. When the model responds with tool_calls, parse the JSON args and call your function directly.

**5/** Then: Append the tool output with role='tool' and the matching tool_call_id right back to your message list, then loop again.

**6/** Build it once with zero abstractions so you understand the raw loop. Grab the snippet above and test it on your local machine.

## LinkedIn version

At 1:00 AM last night, I found myself debugging an agent library that wrapped an API call inside five layers of classes, decorators, and custom handlers. All I wanted was to let a model run a basic Python math function.

After digging through cryptic stack traces for two hours, I wiped the script and went back to bare Python. 

Here's the reality: an AI agent isn't complex magic. It's a while-loop. The model decides if it needs data, emits a tool name with arguments, your script executes the function, appends the output to the message history, and asks the model again.

Frameworks are fine once you hit enterprise orchestration, but jumping straight into heavy abstractions means you miss how simple tool calling actually is under the hood. 

Build your first agent from scratch with raw API calls. Once you understand how messages and tool IDs stitch together, you can debug anything.

#python #aiagents #softwareengineering #coding #developers

_Tags: python, aiagents, llm, automation_

---
*By Suman Giri — built with the CoderFact engine.*