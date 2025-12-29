# My Project

A Python project using Hatch and uv.

## Development

```bash
# Install dependencies
hatch env create

# Build the project
hatch build

# Run the example
export GITHUB_TOKEN={YOUR_READONLY_TOKEN}
hatch run python run.py

# Run linting
hatch run lint

# Format code
hatch run format

# Type checking
hatch run type-check

# Run tests
hatch run test

# Run all checks
hatch run check
```
