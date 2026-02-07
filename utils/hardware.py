"""Hardware detection and model selection utilities"""
import subprocess
from pathlib import Path


def get_system_info():
    """Detects CPU RAM and GPU VRAM if available."""
    import psutil
    import ctranslate2
    
    info = {
        "ram_gb": psutil.virtual_memory().total / (1024**3),
        "gpu_available": False,
        "vram_gb": 0,
        "cuda_version": None
    }
    
    # Check CUDA availability via ctranslate2
    try:
        if ctranslate2.get_cuda_device_count() > 0:
            info["gpu_available"] = True
            # Note: ctranslate2 doesn't give VRAM easily, normally we'd use nvidia-smi or torch
            # We'll use a fallback check for VRAM if we really need it, but for now we assume 
            # if CUDA is there, we can try at least 'medium'
            info["vram_gb"] = 4  # Default assumption if CUDA exists
    except:
        pass
        
    return info


def select_best_model(info):
    """Selects the best whisper model based on hardware."""
    if info["gpu_available"]:
        if info["vram_gb"] >= 8:
            return "large-v3", "cuda", "float16"
        elif info["vram_gb"] >= 4:
            return "medium", "cuda", "float16"
        else:
            return "small", "cuda", "int8_float16"
    else:
        # CPU path
        if info["ram_gb"] >= 16:
            return "medium", "cpu", "int8"
        elif info["ram_gb"] >= 8:
            return "small", "cpu", "int8"
        else:
            return "base", "cpu", "int8"


def verify_gpu_availability(sys_info):
    """
    Verifies GPU is available when requested.
    Returns True if GPU is available, raises SystemExit if not.
    """
    import sys
    
    # Check for NVIDIA drivers
    try:
        subprocess.check_output(["nvidia-smi"])
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: '--gpu' flag was given, but NVIDIA drivers or 'nvidia-smi' were not found.")
        print("Please install the latest NVIDIA drivers: https://www.nvidia.com/Download/index.aspx")
        sys.exit(1)
        
    if not sys_info["gpu_available"]:
        print("ERROR: GPU mode requested. Drivers found, but CUDA is not accessible by ctranslate2.")
        print("You may need to install the CUDA Toolkit or ensure cuBLAS/cuDNN DLLs are in your PATH.")
        import os
        print(f"Current PATH: {os.environ['PATH'][:200]}...")
        sys.exit(1)
    
    return True


def setup_cuda_env(cuda_path=None):
    """Sets up CUDA environment variables."""
    import os
    
    if cuda_path:
        cuda_path = Path(cuda_path)
        if cuda_path.exists():
            print(f"Adding {cuda_path} to PATH and CUDA_PATH")
            os.environ["CUDA_PATH"] = str(cuda_path)
            os.environ["PATH"] = str(cuda_path / "bin") + os.pathsep + os.environ["PATH"]
        else:
            print(f"Warning: Provided CUDA path {cuda_path} does not exist.")
