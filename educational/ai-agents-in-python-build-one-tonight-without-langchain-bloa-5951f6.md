# AI Agents in Python: Build One Tonight Without LangChain Bloat

_Stop overcomplicating state machines—here is how a while loop and tool calls actually work._

## Scroll-stopping hooks

**Hook 1.** I spent three hours debugging a framework abstraction just to realize an AI agent is literally a while loop with tool calls.

**Hook 2.** You do not need a 50MB framework to build an AI agent—you just need Python, a system prompt, and a loop.

**Hook 3.** Most AI agent tutorials sell you complex DAG abstractions before you even understand how a model decides to execute a function.

**Hook 4.** If your agent crashes every time it gets a bad JSON response, your prompt isn't the problem—your loop is.

**Hook 5.** Wrote an AI agent at 1am last night using zero agent frameworks. It works better than the bloatware I was using last week.

## 7 tips that actually move the needle

### Tip 1. Use the official `google-genai` SDK over heavy wrapper libraries.
_Why it matters:_ Wrapper frameworks hide the raw API response structure, making function-call debugging an absolute nightmare.

```python
from google import genai
client = genai.Client()
response = client.models.generate_content(model='gemini-2.5-flash', contents='Hi')
```

### Tip 2. Define tools with strict Python type hints and explicit docstrings.
_Why it matters:_ Gemini reads your function's docstring and type annotations to figure out when and how to invoke it.

```python
def get_user_orders(user_id: str) -> list:
    """Fetches active order IDs for a given user UUID."""
    return ["ord_123", "ord_456"]
```

### Tip 3. Pass Python functions directly inside the `tools` config parameter.
_Why it matters:_ The SDK automatically converts raw functions into OpenAPI-compliant JSON schemas for the model.

```
config = {'tools': [get_user_orders]}
response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt, config=config)
```

### Tip 4. Inspect `response.candidates[0].function_calls` to catch execution requests.
_Why it matters:_ Models don't run code—they return execution requests that your Python code must evaluate.

```python
if response.function_calls:
    call = response.function_calls[0]
    print(call.name, call.args)
```

### Tip 5. Map function names to actual callables using a dictionary lookup.
_Why it matters:_ It avoids dangerous `eval()` calls and makes tool routing completely explicit.

```
TOOL_MAP = {'get_user_orders': get_user_orders}
result = TOOL_MAP[call.name](**call.args)
```

### Tip 6. Append tool execution responses back into the conversation history.
_Why it matters:_ The model needs to see the tool's output to formulate its final natural language answer.

```
history.append({'role': 'tool', 'parts': [result]})
```

### Tip 7. Cap your execution loop with an explicit `max_iters` safe stop.
_Why it matters:_ Prevents infinite loops and drained API credits when a tool continuously returns unexpected output.

```
for _ in range(MAX_ITERS):
    # run agent loop
    break
```

## Step-by-step procedure

### 1. Step 1: Install the native SDK and set environment keys
Grab the latest SDK via pip and export your key so the client picks it up automatically.

```python
pip install google-genai
export GEMINI_API_KEY="your_key_here"
```

### 2. Step 2: Define your core Python tools
Write clean standard functions with clear type hints—these act as the agent's hands.

```python
def fetch_weather(city: str) -> str:
    """Returns current weather for a city."""
    return f"Sunny, 28C in {city}"
```

### 3. Step 3: Instantiate the client and register tools
Pass the Python functions directly to the generation config.

```python
from google import genai
client = genai.Client()
tools = [fetch_weather]
```

### 4. Step 4: Build the execution loop
Handle the back-and-forth loop between model tool calls and local Python execution.

```python
def run_agent(prompt):
    messages = [prompt]
    while True:
        res = client.models.generate_content(model='gemini-2.5-flash', contents=messages, config={'tools': tools})
        if not res.function_calls:
            return res.text
        for call in res.function_calls:
            out = fetch_weather(**call.args)
            messages.append({'role': 'tool', 'parts': [out]})
```

### 5. Step 5: Execute an end-to-end multi-step task
Ask a query that requires tool use and print the final computed output.

```python
print(run_agent("What is the weather in Kolkata right now?"))
```

## The mistake almost everyone makes

> ⚠️  Writing docstrings without detailing parameter formats. If your docstring just says 'gets data', Gemini will guess argument formats and pass dirty inputs. Fix it by documenting what each argument expects directly inside the docstring.

## X / Twitter thread (copy-paste ready)

**1/** Building your first AI agent doesn't require a 50MB orchestration framework.

**2/** At its core, an AI agent is just a model inside a loop that decides when to trigger standard Python functions.

**3/** First, write plain Python functions with type hints and explicit docstrings. Gemini reads these docstrings as its tool specs.

**4/** Pass those functions directly to `client.models.generate_content(..., config={'tools': [my_func]})` using the google-genai SDK.

**5/** Catch `res.function_calls`, execute the function locally in Python, and append the result back to your chat history.

**6/** Stop over-engineering your tools. Write a basic loop tonight and save yourself hours of framework debugging.

## LinkedIn version

I stayed up until 1am last night trying to debug a simple AI agent task.

The framework I was using had wrapped everything in so many layers of abstractions, state graphs, and custom schemas that I couldn't even see the raw API requests anymore. It took me two hours to realize the model was just returning a malformed tool call that the framework was silently dropping.

I scrapped the whole setup, opened a clean file, and wrote a raw agent using just the standard SDK and Python's built-in control flow. 

Turns out, an AI agent isn't magic—it's a while loop. You pass your Python functions into the model call, check if the model requested a tool call, run the function locally with those arguments, and feed the output back to the model until it gives you a final string response.

Stop reaching for heavy frameworks before you build one from scratch. You'll save hours of debugging and actually understand what your code is doing under the hood.

#python #ai #developer #automation #coding

_Tags: python, tutorial, ai, developer_

---
*By Suman Giri — built with the CoderFact engine.*