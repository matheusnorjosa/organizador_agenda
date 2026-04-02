## Git Workflow
- Do not include "Claude Code" in commit messages
- Use conventional commits (be brief and descriptive)
- Commit messages should explain what was changed and why

## Important Concepts
Focus on these principles in all code:
- error monitoring/observability
- automated tests
- readability/maintainability

## Coding Guidelines (Python)
- Use type hints where they add clarity
- Prefer async/await for I/O operations
- Unused variables should not exist. Prefix with `_` if necessary
- Avoid abbreviations. Names should be descriptive
- Use early returns instead of long if-else chains
- Follow conventions: SNAKE_CAPS for constants, snake_case for variables and functions

## Software Engineering
- No premature optimization. Optimize only when performance is measured
- Prioritize observability and security. These are not optional
- Comments should explain why, not what

## Testing
- Test behavior, not implementation details
- Every bug fix must be accompanied by a regression test
- Test names should describe outcomes: "returns_error_when_unauthorized"

## Writing
- Be concise. Do not waste the reader's time
- Prefer active voice
- Keep sentences short. One idea per sentence
- Lead with the result, then explain supporting details
