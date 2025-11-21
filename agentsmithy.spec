# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = []
hiddenimports = []
datas += collect_data_files('chromadb')
datas += collect_data_files('ddgs')
datas += collect_data_files('primp')
hiddenimports += collect_submodules('agentsmithy.tools')
hiddenimports += collect_submodules('agentsmithy.tools.builtin')
hiddenimports += collect_submodules('chromadb')
hiddenimports += collect_submodules('chromadb.telemetry.product')
hiddenimports += collect_submodules('tiktoken')
hiddenimports += collect_submodules('tiktoken_ext')
hiddenimports += collect_submodules('ddgs')
hiddenimports += collect_submodules('ddgs.engines')
hiddenimports += collect_submodules('primp')
# Ensure OpenAI model specs are included in frozen build (dynamic autodiscovery needs submodules bundled)
hiddenimports += collect_submodules('agentsmithy.llm.providers.openai')
hiddenimports += collect_submodules('agentsmithy.llm.providers.openai.models')
# Explicitly add model modules (collect_submodules may miss them)
hiddenimports += [
    'agentsmithy.llm.providers.openai.models.gpt4_1',
    'agentsmithy.llm.providers.openai.models.gpt5',
    'agentsmithy.llm.providers.openai.models.gpt5_mini',
    'agentsmithy.llm.providers.openai.models.gpt5_1',
    'agentsmithy.llm.providers.openai.models.gpt5_1_codex',
    'agentsmithy.llm.providers.openai.models.gpt5_1_codex_mini',
]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['rthooks/rthook_openai_models.py'],
    excludes=['pytest', 'pytest_asyncio', 'black', 'isort', 'mypy', 'ruff'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='agentsmithy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
