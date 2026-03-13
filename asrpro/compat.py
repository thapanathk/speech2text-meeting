"""
Compatibility patches for legacy library APIs removed in newer versions.
Import this module at the very top of manage.py / wsgi.py / asgi.py.
"""
import sys
import types
import importlib.metadata as _importlib_metadata
import os as _os

# ── Set environment ──────────────────────────────────────────────────────
_os.environ.setdefault("TRANSFORMERS_OFFLINE", "0")  # Allow model downloads

# ── Mock torchcodec before transformers tries to import it ─────────────────
# transformers 4.57.1+ checks for torchcodec but doesn't use it at runtime.
# TorchCodec fails if FFmpeg DLLs can't be found, so we stub it out early.
class _TorchCodecMock:
    """Mock torchcodec to prevent FFmpeg DLL loading errors."""
    __version__ = "0.10.0"
    __path__ = []
    def __getattr__(self, name):
        # Return a mock module for any attribute access
        return types.ModuleType(name)

def _create_mock_module(name):
    """Create a mock module that returns other mock modules on attribute access."""
    mod = types.ModuleType(name)
    mod.__path__ = []
    mod.__spec__ = None
    return mod

if "torchcodec" not in sys.modules:
    tc_mock = _TorchCodecMock()
    sys.modules["torchcodec"] = tc_mock
    # Pre-create the most likely imports
    sys.modules["torchcodec._core"] = _create_mock_module("torchcodec._core")
    sys.modules["torchcodec._core.ops"] = _create_mock_module("torchcodec._core.ops")
    sys.modules["torchcodec.decoders"] = _create_mock_module("torchcodec.decoders")
    sys.modules["torchcodec.decoders._video_decoder"] = _create_mock_module("torchcodec.decoders._video_decoder")

    class _AudioDecoder:
        pass

    sys.modules["torchcodec.decoders"].AudioDecoder = _AudioDecoder
    tc_mock.decoders = sys.modules["torchcodec.decoders"]
    tc_mock._core = sys.modules["torchcodec._core"]

# Install a custom import hook to handle any torchcodec submodules on-demand
class _TorchCodecImportHook:
    """Automatically create mock modules for any torchcodec submodule."""
    def find_module(self, fullname, path=None):
        if fullname.startswith("torchcodec"):
            return self
        return None
    
    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        mod = _create_mock_module(fullname)
        sys.modules[fullname] = mod
        return mod

sys.meta_path.insert(0, _TorchCodecImportHook())

# ── optree: might not be installed, handle gracefully ────────────────────
_original_from_name = _importlib_metadata.Distribution.from_name
_FAKE_PACKAGE_VERSIONS = {
    "optree": "0.0.0",
    "torchcodec": "0.10.0",
}

@classmethod
def _patched_from_name(cls, name):
    if name in _FAKE_PACKAGE_VERSIONS:
        class FakeDistribution:
            version = _FAKE_PACKAGE_VERSIONS[name]
        return FakeDistribution()
    return _original_from_name.__func__(cls, name)

_importlib_metadata.Distribution.from_name = _patched_from_name

# Also patch version() to be forgiving
_original_version = _importlib_metadata.version

def _patched_version(name):
    try:
        return _original_version(name)
    except _importlib_metadata.PackageNotFoundError:
        if name in _FAKE_PACKAGE_VERSIONS:
            return _FAKE_PACKAGE_VERSIONS[name]
        raise

_importlib_metadata.version = _patched_version

# ── NumPy 2.0: removed np.NaN ─────────────────────────────────────────────
import numpy as np
if not hasattr(np, "NaN"):
    np.NaN = np.nan
if not hasattr(np, "NAN"):
     np.NAN = np.nan
if not hasattr(np, "NAN"):
    np.NAN = np.nan
if not hasattr(np, "bool"):
    np.bool = np.bool_
if not hasattr(np, "int"):
    np.int = np.int_
if not hasattr(np, "float"):
    np.float = np.float64
if not hasattr(np, "complex"):
    np.complex = np.complex128

# ── PyTorch & torch.load ─────────────────────────────────────────────────
import torch
import torch.serialization
import torch.torch_version

# PyTorch 2.6+: weights_only=True by default; allowlist TorchVersion
try:
    torch.serialization.add_safe_globals([torch.torch_version.TorchVersion])
except Exception:
    pass

# pyannote.audio classes stored inside model checkpoints
try:
    from pyannote.audio.core.task import Specifications, Problem, Resolution
    from pyannote.core import SlidingWindow
    torch.serialization.add_safe_globals([Specifications, Problem, Resolution, SlidingWindow])
except Exception:
    pass

# Patch torch.load to use weights_only=False by default for pyannote/speechbrain
# model checkpoints (these are trusted local HuggingFace cache files).
_original_torch_load = torch.load

def _patched_torch_load(f, *args, **kwargs):
    kwargs["weights_only"] = False
    return _original_torch_load(f, *args, **kwargs)

torch.load = _patched_torch_load

# ── torchaudio: removed backend API ──────────────────────────────────────
import torchaudio

# top-level functions removed since 2.1
if not hasattr(torchaudio, "set_audio_backend"):
    torchaudio.set_audio_backend = lambda *a, **kw: None
if not hasattr(torchaudio, "get_audio_backend"):
    torchaudio.get_audio_backend = lambda: "default"
if not hasattr(torchaudio, "list_audio_backends"):
    torchaudio.list_audio_backends = lambda: ["default"]
if not hasattr(torchaudio, "get_audio_backend_options"):
    torchaudio.get_audio_backend_options = lambda *a, **kw: {}

# torchaudio.AudioMetaData moved; provide shim at top level
if not hasattr(torchaudio, "AudioMetaData"):
    try:
        from torchaudio._torchaudio import AudioMetaData as _AMD
        torchaudio.AudioMetaData = _AMD
    except Exception:
        class _AudioMetaData:
            def __init__(self, sample_rate=0, num_frames=0, num_channels=0,
                         bits_per_sample=0, encoding=""):
                self.sample_rate = sample_rate
                self.num_frames = num_frames
                self.num_channels = num_channels
                self.bits_per_sample = bits_per_sample
                self.encoding = encoding
        torchaudio.AudioMetaData = _AudioMetaData

# stub out the entire torchaudio.backend sub-package (used by speechbrain)
def _make_backend_stub(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod

_backend      = _make_backend_stub("torchaudio.backend")
_common       = _make_backend_stub("torchaudio.backend.common")
_sox          = _make_backend_stub("torchaudio.backend.sox_io_backend")
_soundfile    = _make_backend_stub("torchaudio.backend.soundfile_backend")
_no_backend   = _make_backend_stub("torchaudio.backend.no_backend")

# AudioMetaData is the most-imported symbol from torchaudio.backend.common
_common.AudioMetaData = torchaudio.AudioMetaData

# load / save / info stubs (speechbrain may import these from backend modules)
def _load_stub(filepath, *a, **kw):
    return torchaudio.load(filepath, *a, **kw)

def _save_stub(filepath, src, sample_rate, *a, **kw):
    return torchaudio.save(filepath, src, sample_rate, *a, **kw)

def _info_stub(filepath, *a, **kw):
    return torchaudio.info(filepath, *a, **kw)

for _mod in (_sox, _soundfile):
    _mod.load = _load_stub
    _mod.save = _save_stub
    _mod.info = _info_stub

# attach sub-modules as attributes on the parent
torchaudio.backend = _backend
_backend.common = _common
_backend.sox_io_backend = _sox
_backend.soundfile_backend = _soundfile
_backend.no_backend = _no_backend
