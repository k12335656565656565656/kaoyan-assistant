# SQLite Migration Skill

- Do not drop existing tables.
- Do not delete user data.
- Add columns and tables safely with backward compatibility in mind.
- Keep old rows readable even when new fields are introduced later.
- Centralize database read and write logic in repository files instead of scattered page code.
