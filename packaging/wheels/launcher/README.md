# Launcher offline wheels

Bundled wheels for dev launcher when system proxy blocks pip (e.g. `127.0.0.1:10808`).

Required for offline install:
- `pywebview-*.whl`
- `bottle-*.whl`
- `typing_extensions-*.whl`
- `pythonnet-*.whl`
- `proxy_tools-0.1.0/` or `proxy_tools-0.1.0.tar.gz`

Optional (editable install fallback):
- `setuptools-*.whl`
- `wheel-*.whl`
- `clr_loader-*.whl`

Refresh wheels (maintainers):

```bash
py -3.11 scripts/ensure_launcher_deps.py
```
