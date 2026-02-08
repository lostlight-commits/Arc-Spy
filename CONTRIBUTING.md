# Contributing to ARC SPY

Thanks for your interest in contributing! Here are some guidelines:

## How to Contribute

1. **Fork the repository** and create a new branch for your feature/bugfix
2. **Make your changes** with clear, descriptive commit messages
3. **Test your changes** locally before submitting
4. **Run code quality checks** (see below)
5. **Submit a Pull Request** with a clear description of what you changed and why

## Code Quality

Before submitting a PR, please run:

```bash
# Install development dependencies
pip install ruff mypy

# Lint check
ruff check .

# Format check (or auto-format with: ruff format .)
ruff format --check .

# Type check (optional but recommended)
mypy . --ignore-missing-imports
```

## Pull Request Guidelines

- Keep PRs focused on a single feature/fix
- Update documentation if you're adding new features
- Add comments for complex logic
- Test with a real Discord bot if possible

## Questions?

Feel free to open an issue for discussion before starting major changes!

## Support

If you want to support the project financially:
- Patreon: https://patreon.com/connorbotboi?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink
