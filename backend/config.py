"""
config.py
=========
Configuration loader for AI Support Agent.
Reads configuration from config.yaml file.
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent

CONFIG_FILE = PROJECT_ROOT / "config.yaml"

_config_cache: Optional[Dict[str, Any]] = None


def load_config() -> Dict[str, Any]:
    """
    Load configuration from config.yaml
    Cached after first load for performance.
    """
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {CONFIG_FILE}\n"
            f"Please create config.yaml in the project root directory"
        )
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            _config_cache = yaml.safe_load(f)
        return _config_cache
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in config.yaml: {e}")


def get_model_config() -> Dict[str, Any]:
    """Get model configuration section"""
    config = load_config()
    return config.get("model", {})


def get_app_config() -> Dict[str, Any]:
    """Get application configuration section"""
    config = load_config()
    return config.get("app", {})


def get_gpu_config() -> Dict[str, Any]:
    """Get GPU configuration section"""
    config = load_config()
    return config.get("gpu", {})


def get_logging_config() -> Dict[str, Any]:
    """Get logging configuration section"""
    config = load_config()
    return config.get("logging", {})


def get_model_name() -> str:
    """Get HuggingFace model name"""
    config = get_model_config()
    return config.get("name", "Qwen/Qwen2.5-1.5B-Instruct")


def get_hf_token() -> Optional[str]:
    """Get HuggingFace API token"""
    config = get_model_config()
    token = config.get("hf_token", "")
    
    # Remove placeholder if not set
    if token.startswith("hf_YOUR_HUGGINGFACE"):
        return None
    
    return token if token else None


def get_admin_token() -> str:
    """Get admin secret token"""
    config = get_app_config()
    return config.get("admin_secret_token", "shopease-admin-dev-token-2025")


def get_app_host() -> str:
    """Get application host"""
    config = get_app_config()
    return config.get("host", "0.0.0.0")


def get_app_port() -> int:
    """Get application port"""
    config = get_app_config()
    return config.get("port", 8000)


def get_gpu_device_id() -> int:
    """Get GPU device ID"""
    config = get_gpu_config()
    return config.get("device_id", 0)


def is_use_fp16() -> bool:
    """Check if should use float16 precision"""
    config = get_gpu_config()
    return config.get("use_fp16", True)


def is_use_openai() -> bool:
    """Check if should use OpenAI API"""
    config = get_model_config()
    return config.get("use_openai", False)


def is_use_ollama() -> bool:
    """Check if should use Ollama"""
    config = get_model_config()
    return config.get("use_ollama", False)


if __name__ == "__main__":
    # Test configuration loading
    print("Loading configuration...")
    config = load_config()
    print(yaml.dump(config, default_flow_style=False))
