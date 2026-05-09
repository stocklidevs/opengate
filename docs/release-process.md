# Release Process

Open Gate keeps the version in three places:

- `VERSION`
- `pyproject.toml`
- `open_gate/version.py`

Before tagging a release:

1. Update all three version values.
2. Add a `CHANGELOG.md` entry with user-visible changes.
3. Run:

```powershell
python -m unittest discover -s tests
python -m open_gate.regression --pretty
```

4. Run at least one live Codex smoke in `repair` mode.
5. For benchmark claims, publish the report files under `runs\`.

The README badges should reflect the latest released version and current proxy mode support.
