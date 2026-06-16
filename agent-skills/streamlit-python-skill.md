# Streamlit Python Skill

- Keep Streamlit UI code thin and move business logic into service modules.
- Avoid repeatedly initializing database connections, API clients, or heavy resources during reruns.
- Use `st.session_state` carefully and intentionally, especially for multi-step confirmation flows.
- Avoid putting large prompts, extraction logic, or database write logic directly inside page code.
- Prefer stable helper functions and schemas over ad hoc state dictionaries.
