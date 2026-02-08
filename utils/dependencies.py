"""Dependency installation utilities"""
import sys
import subprocess


def ensure_dependency(package_name, import_names=None, pip_packages=None):
    """
    Ensures a dependency is installed, installing it if necessary.
    
    Args:
        package_name: Human-readable name for the package
        import_names: List of module names to try importing
        pip_packages: List of package names to install via pip
    """
    if import_names is None:
        import_names = [package_name]
    if pip_packages is None:
        pip_packages = [package_name]
    
    try:
        for name in import_names:
            __import__(name)
    except ImportError:
        print(f"Installing missing dependency: {package_name}")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + pip_packages)


def install_all_dependencies():
    """Install all required dependencies for the bot"""
    ensure_dependency("python-dotenv", ["dotenv"], ["python-dotenv"])
    ensure_dependency("discord.py", ["discord"], ["discord.py", "discord-ext-voice-recv"])
    ensure_dependency("psutil", ["psutil"], ["psutil"])
    ensure_dependency("numpy", ["numpy"], ["numpy"])
    ensure_dependency("faster-whisper", 
                     ["faster_whisper", "ctranslate2", "hf_transfer"],
                     ["faster-whisper", "hf-transfer", "ctranslate2"])
    ensure_dependency("LLM Summarizer", 
                     ["transformers", "accelerate", "bitsandbytes", "torch", "sentencepiece"],
                     ["transformers", "accelerate", "bitsandbytes", "torch", "sentencepiece"])
