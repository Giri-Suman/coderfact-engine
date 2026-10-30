# AI Agent in Python: Stop overcomplicating the loop

_You don't need a heavy framework to build an agent that actually runs code and fixes itself._

## Scroll-stopping hooks

**Hook 1.** I spent three hours debugging LangChain abstractions last night before trashing the whole repo and writing a 40-line while-loop instead.

**Hook 2.** Most tutorials make AI agents sound like rocket science, but an agent is literally just an LLM outputting a tool call inside a while loop.

**Hook 3.** If your agent needs 12 wrapper classes just to search Google and parse a string, you're not building software—you're building bloat.

**Hook 4.** Wasted my entire evening yesterday fighting agent framework docs until I realized the native OpenAI client does 90% of the heavy lifting.

**Hook 5.** Stop installing massive agent libraries until you've written the raw while-loop version by hand at least once.

## 7 tips that actually move the needle

### Tip 1. Use pydantic to define your tool arguments instead of messy JSON schemas.
_Why it matters:_ It handles the schema generation, type validation, and error serialization in one shot.

```
class SearchQuery(BaseModel):
    query: str = Field(description='Search terms')
    max_results: int = 3
```

### Tip 2. Bind native tool schemas directly with client.chat.completions.create using tools parameter.
_Why it matters:_ Modern LLMs are explicitly trained on tool-calling tokens, so manual prompt parsing is dead.

```
tools = [{'type': 'function', 'function': {'name': 'calc', 'parameters': Schema.model_json_schema()}}]
```

### Tip 3. Enforce a hard max_iterations counter in your while loop.
_Why it matters:_ Without a circuit breaker, a hallucinating model will burn your entire API balance on a recursive mistake.

```
for _ in range(MAX_STEPS):
    if response.choices[0].finish_reason != 'tool_calls': break
```

### Tip 4. Route tool execution using a plain Python dict dispatch table.
_Why it matters:_ Avoids fragile eval() calls or massive, hard-to-maintain if-elif chains.

```
TOOL_MAP = {'fetch_weather': fetch_weather, 'run_sql': run_sql}
result = TOOL_MAP[fn_name](**fn_args)
```

### Tip 5. Append tool results right back into the message history with role: 'tool'.
_Why it matters:_ The model needs to see the tool call ID match its own request to resolve the output context.

```
history.append({'role': 'tool', 'tool_call_id': call.id, 'content': str(output)})
```

### Tip 6. Run python -m pip install litellm if you want multi-provider support without rewrites.
_Why it matters:_ It gives you the exact same OpenAI tool-calling syntax across Anthropic, Ollama, and Bedrock.

```python
from litellm import completion
res = completion(model='claude-3-5-sonnet', messages=history, tools=tools)
```

### Tip 7. Feed execution tracebacks straight back to the LLM when your Python tools fail.
_Why it matters:_ Models are surprisingly good at self-correcting their bad inputs if you hand them the raw exception.

```
except Exception as err:
    history.append({'role': 'tool', 'tool_call_id': call.id, 'content': f'Error: {err}'})
```

## Step-by-step procedure

### 1. Install the official OpenAI package
Keep dependencies dead simple. Just install the base client—no external agent libraries required.

```python
pip install openai pydantic
```

### 2. Define a standalone Python function
Write the actual logic you want your model to execute, like reading a file or hitting an API.

```python
def get_site_status(url: str) -> str:
    import urllib.request
    return str(urllib.request.urlopen(url).getcode())
```

### 3. Declare the function schema for the model
Tell the LLM what your function is called, what it does, and the parameters it accepts.

```
tools = [{'type': 'function', 'function': {'name': 'get_site_status', 'description': 'Check HTTP status', 'parameters': {'type': 'object', 'properties': {'url': {'type': 'string'}}, 'required': ['url']}}}]
```

### 4. Build the core execution loop
Send the prompt, inspect the response, run the requested tool, and feed the answer back.

```
messages = [{'role': 'user', 'content': 'Is coderfact.com up?'}]
while True:
    res = client.chat.completions.create(model='gpt-4o-mini', messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: break
    for call in msg.tool_calls:
        out = get_site_status(**json.loads(call.function.arguments))
        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': out})
```

### 5. Verify the final agent output
Print the last assistant message—it should clearly synthesize the tool execution output.

```python
print(messages[-1].content)
```

## The mistake almost everyone makes

> ⚠️  Forgetting to feed both the assistant message (containing tool_calls) AND the tool execution results back to the message history. If you omit the assistant's initial tool call message, the API returns a 400 error complaining that a tool response exists without a matching request.

## X / Twitter thread (copy-paste ready)

**1/** Building your first Python AI agent is way simpler than framework docs make it look. Here is the blueprint.

**2/** Most devs get stuck because they try to learn three orchestration libraries at once. Don't bother. An agent is just a tool loop.

**3/** Step 1: Define plain Python functions and format their schemas with Pydantic. No magic wrappers needed.

**4/** Step 2: Pass them into the standard client.chat.completions API using the tools argument.

**5/** Step 3: Run a while-loop. If the model triggers a tool call, run the function, append the result, and call the API again.

**6/** That is the entire secret. Once you understand the loop, you can build anything without bloat. What tool are you running first?

## LinkedIn version

At 1am last night, I almost threw my laptop across the room trying to debug a broken dependency graph inside an agent orchestration framework.

All I wanted was a quick Python script that pinged an API, inspected the output, and summarized the status. Instead, I had five layers of abstraction and zero visibility into what was failing.

So I nuked the repo and rebuilt the whole concept with nothing but the base OpenAI client, a simple dictionary lookup, and a 20-line while-loop. It worked on the very first run.

We need to stop pretending AI agents are mysterious black boxes. At its core, an agent is just an LLM outputting structured JSON arguments, a Python runner executing those arguments, and a loop feeding the output right back to the model until it finishes the task.

Build the raw loop yourself before reaching for a third-party framework. You'll understand the moving parts—and your scripts won't break every time an abstraction library bumps its minor version.

#python #ai #softwareengineering #automation

_Tags: python, aiagents, programming, automation_

---
*By Suman Giri — built with the CoderFact engine.*