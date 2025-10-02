# Ensure OpenAI chat model modules are imported at runtime in the frozen binary
# This avoids relying on pkgutil/pkg_resources discovery that fails in PyInstaller onefile.
# Keep this list in sync with available model modules.
from importlib import import_module

MODULES = [
    "agentsmithy_server.core.providers.openai.models.gpt4_1",
    "agentsmithy_server.core.providers.openai.models.gpt5",
    "agentsmithy_server.core.providers.openai.models.gpt5_mini",
]

for m in MODULES:
    try:
        import_module(m)
    except Exception:
        # Do not crash app startup due to a single model; log is not available here.
        # Failures will surface later when selecting that model.
        pass
