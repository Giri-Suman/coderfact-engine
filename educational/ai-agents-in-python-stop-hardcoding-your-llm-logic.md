# AI Agents in Python: Stop Hardcoding Your LLM Logic

_Build a self-correcting Python script that actually does work, not just chats._

## Scroll-stopping hooks

**Hook 1.** I spent 3 hours last night debugging an LLM loop just to realize my agent was arguing with itself in JSON. Here is how to actually build one that works.

**Hook 2.** Stop chaining 15 prompt templates together. An AI agent is literally just a standard Python while-loop with tool access.

**Hook 3.** Your LLM app isn't an agent until it can execute functions and fix its own syntax errors without you pressing retry.

**Hook 4.** Most dev tutorials for AI agents overcomplicate LangChain. You can write a fully functional agent in 40 lines of pure Python.

**Hook 5.** If your script can't handle a failed API call on its own, it's just a glorified chatbot. Let's build a real agent.

## 7 tips that actually move the needle

### Tip 1. Use litellm for model routing
_Why it matters:_ It normalizes OpenAI, Anthropic, and local Ollama interfaces so your agent code stays identical across providers.

```python
from litellm import completion
res = completion(model="gpt-4o-mini", messages=messages, tools=tools)
```

### Tip 2. Define tools with Pydantic schemas
_Why it matters:_ Generates rock-solid JSON schemas for function calling without hand-writing schema dictionaries.

```
class FetchUrl(BaseModel):
    url: str = Field(description="Target URL to scrape")
```

### Tip 3. Inject execution results directly back into history
_Why it matters:_ Agents need to see the exact raw output of their tools to decide the next step.

```
messages.append({"role": "tool", "tool_call_id": call.id, "content": str(output)})
```

### Tip 4. Cap your loop iterations with a max_steps counter
_Why it matters:_ Prevents infinite reasoning loops that drain your API credit balance at 2am.

```
if step_count > 5: raise RuntimeError("Agent stuck in loop")
```

### Tip 5. Use SystemMessage to enforce tool-first outputs
_Why it matters:_ LLMs love to chat; forcing tool calls cuts out conversational filler before execution.

```
system_prompt = "Only respond with tool calls until you have the final answer."
```

### Tip 6. Log raw function arguments using rich
_Why it matters:_ Helps you instantly spot hallucinated function parameters in your terminal.

```python
from rich import print
print(f"[bold blue]Tool Call:[/bold blue] {call.function.name}")
```

### Tip 7. Sanitize return strings from local shell tools
_Why it matters:_ Raw terminal output can overflow model context windows if not truncated early.

```
output = result.stdout[:2000] # truncate long shell output
```

## Step-by-step procedure

### 1. Step 1: Set up the environment and LiteLLM
Install litellm and pydantic. Set up your environment variables for local or remote LLMs.

```python
pip install litellm pydantic
export OPENAI_API_KEY="your-key"
```

### 2. Step 2: Define your python tools
Write the actual Python functions your agent will execute when requested by the model.

```python
def get_system_time():
    import datetime
    return str(datetime.datetime.now())
```

### 3. Step 3: Register tools using JSON schema format
Map your Python functions to structural descriptions so the LLM knows when to invoke them.

```
tools = [{
    "type": "function",
    "function": {
        "name": "get_system_time",
        "description": "Returns the current server time"
    }
}]
```

### 4. Step 4: Build the execution while-loop
Create a loop that passes message history to the model, checks for tool calls, and executes them.

```
messages = [{"role": "user", "content": "What time is it?"}]
while True:
    res = completion(model="gpt-4o-mini", messages=messages, tools=tools)
    msg = res.choices[0].message
    messages.append(msg)
    if not msg.tool_calls: break
```

### 5. Step 5: Run the tool and feed results back
Parse the tool call name, call the real function, and append the payload back into the conversation.

```
for call in msg.tool_calls:
    if call.function.name == "get_system_time":
        out = get_system_time()
        messages.append({"role": "tool", "tool_call_id": call.id, "content": out})
```

### 6. Step 6: Run end-to-end and verify stdout
Ask a query requiring the tool and confirm the agent calls the function before returning a final text answer.

```python
final_res = completion(model="gpt-4o-mini", messages=messages)
print(final_res.choices[0].message.content)
```

## The mistake almost everyone makes

> ⚠️  Passing tool results back as standard 'user' or 'system' messages. The LLM loses context of which execution call produced which data—always use the official 'tool' role along with the exact tool_call_id.

## X / Twitter thread (copy-paste ready)

**1/** Stop overcomplicating AI agents. You don't need heavy frameworks—it's just a Python while-loop with tool bindings.

**2/** Most devs get stuck because they try to force an LLM to follow rigid chain logic. Let the model pick the function instead.

**3/** Tip 1: Use Pydantic to build tool schemas effortlessly. Hand-writing nested JSON schemas at 1am is a nightmare.

**4/** Tip 2: Never trust a loop without an exit guard. Always set a hard max_steps limit so a confused agent doesn't blow up your API billing.

**5/** Tip 3: Pass tool outputs back under the 'tool' role with the original 'tool_call_id'. If you pass it as a user message, the agent loses track.

**6/** Full Python implementation built for CoderFact is live. Stop building chatbots—start building scripts that do real work.

## LinkedIn version

I lost almost three hours last night debugging an AI agent framework. The agent got caught in an infinite loop, arguing with itself over an invalid JSON response format. 

At 1am, I stripped everything out and rebuilt the whole pipeline in raw Python. Turns out, an AI agent isn't magic—it's just a while-loop, an API call, and execution handlers for local functions.

Here is how simple it actually is: you pass a user prompt and a list of functions (tools) to an LLM. If the model determines it needs data, it skips sending text and returns a function call request. You run that function locally, pass the output back into the array, and let the model finish its thought.

If you want to build one today, skip the bloated abstractions first. Write the loop by hand using `litellm` and `pydantic`. You'll understand error handling far better when you see the tool payloads moving through your own code.

Once your script can self-correct from a failed function execution without crashing, you officially have an agent.

#python #aiengineering #softwaredevelopment #coderfact

_Tags: python, aiagents, llm, automation_

---
*By Suman Giri — built with the CoderFact engine.*