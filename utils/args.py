"""Command-line argument parsing"""
import argparse


def parse_arguments():
    """Parse command-line arguments for the bot"""
    parser = argparse.ArgumentParser(description="Meeting Bot Standalone Entry")
    parser.add_argument("--cpu", action="store_true", help="Force CPU mode")
    parser.add_argument("--gpu", action="store_true", help="Force GPU (CUDA) mode")
    parser.add_argument("--model", type=str, help="Specific Whisper model to use (e.g., base, small, medium, large-v3)")
    parser.add_argument("--cuda-path", type=str, help="Path to CUDA toolkit installation")
    parser.add_argument("--cache-dir", type=str, help="Custom directory for huggingface cache")
    
    return parser.parse_args()
