# Larkin

Hermetic ultralight agents. 

- Ultralight hermetic sandbox via in-process Starlark interpreter gives power of code agents without the runtime overhead of Docker/VMs
- Opaque value system lets agent work with prompt-injection-risk text while ensuring agent can never see text

## Minimal example

```python
from larkin.agents import Agent
from larkin.models.google import GoogleModel

agent = Agent(model=GoogleModel("gemini-2.5-pro"))
agent.run(
    "Find the result of summarizing 452324562364, 124151435 ans 1242534 and then dividing that by 12"
)
```

## Longer description

This is experimental, not production ready, but fun!

This is a python library that lets you write "code agents" - agents that invoke tools by writing small scripts. 
This lets the agent do lots of complex work in each tool invocation, and avoid loading large amounts of text into its context window. 

The code is, essentially, Python, and is hermetically sandboxed in an in-process Starlark interpreter. 
This means Larkin doesn't need to start Docker containers or VMs, keeping its footprint light and security surface easier to audit. 

Larkin tools can declare the data they return as "opaque".
Opaque values can be manipulated by the agent in Starlark, but they cannot be *read* by the agent. 
Instead the agent needs to work with this "opaque" data by passing it to tools that accept opaque values - for instance, tools that answer questions about the opaque data and respond with fixed categories. 

Heavily inspired by [smolagents](https://github.com/huggingface/smolagents).

## Hacking

```
# Testing, typechecks, lints
uv run pytest
uv run ruff check
uv run ruff format
uv run ty check
```

## Contributing 

Please don't open huge PRs, or anything other than minimal obvious micro-fixes, without first starting a discussion; it sucks if you spend a ton of effort on something that we then find we can't merge because it doesn't fit the project.

Please don't send vibe-coded PRs that you *haven't yourself read and take responsibility for*; doing that is just a complicated way to write a feature request and filter it through a bunch of code - if you want a feature and don't understand how to implement it, write the feature request and a maintainer can write the prompt.

## License

MIT
