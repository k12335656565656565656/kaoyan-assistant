# Windows PowerShell Skill

- Prefer Windows PowerShell commands for local development and project automation.
- Project paths may contain spaces and should be quoted in commands and scripts.
- Use `.\.venv\Scripts\Activate.ps1` to activate the local virtual environment.
- Avoid Linux-only commands such as `rm -rf` or `source venv/bin/activate`.
- Do not expose API keys, tokens, or secrets in terminal commands, scripts, or copied logs.
