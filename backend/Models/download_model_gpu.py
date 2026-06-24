"""
download_model_gpu.py
====================
Downloads and initializes Qwen2.5-1.5B-Instruct on GPU device 0
Optimized for HPC GPU servers with multiple A100 GPUs

Usage:
    python download_model_gpu.py

For use on HPC with SLURM:
    srun python download_model_gpu.py
    or
    python -m torch.distributed.launch --nproc_per_node=1 download_model_gpu.py
"""

import os
import torch
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_cuda_setup():
    """Check CUDA and GPU configuration"""
    print("=" * 60)
    print("CUDA & GPU CONFIGURATION CHECK")
    print("=" * 60)
    
    print(f"PyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"CUDA version: {torch.version.cuda if torch.cuda.is_available() else 'N/A'}")
    
    if torch.cuda.is_available():
        print(f"Number of GPUs: {torch.cuda.device_count()}")
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            print(f"\n  GPU {i}:")
            print(f"    Name: {props.name}")
            print(f"    Memory: {props.total_memory / 1e9:.2f} GB")
            print(f"    Compute Capability: {props.major}.{props.minor}")
    else:
        print("WARNING: No CUDA GPUs detected!")
        return False
    
    print("\n" + "=" * 60)
    return True


def download_model_on_device_0():
    """Download and initialize model on GPU device 0"""
    
    # Verify GPU availability
    if not torch.cuda.is_available():
        print("ERROR: CUDA not available!")
        sys.exit(1)
    
    device_id = 0
    device = torch.device(f"cuda:{device_id}")
    print(f"\n{'='*60}")
    print(f"DOWNLOADING MODEL TO GPU {device_id}")
    print(f"{'='*60}")
    
    device_props = torch.cuda.get_device_properties(device_id)
    print(f"Target GPU: {device_props.name}")
    print(f"Available Memory: {torch.cuda.get_device_properties(device_id).total_memory / 1e9:.2f} GB")
    
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
    except ImportError:
        print("ERROR: transformers not installed")
        print("Run: pip install transformers accelerate")
        sys.exit(1)
    
    print(f"\nModel: {model_name}")
    print("Step 1/3: Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    print("✓ Tokenizer loaded")
    
    print("Step 2/3: Loading model on GPU device 0...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,  # Use float16 for efficiency on A100
        device_map={"": device_id},  # Map all weights to device 0
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    print("✓ Model loaded on GPU")
    
    model.eval()  # Set to eval mode
    print("Step 3/3: Model set to eval mode")
    
    # Verify model is on correct device
    model_device = next(model.parameters()).device
    print(f"\n✓ Model device: {model_device}")
    
    print("\n" + "=" * 60)
    print("SUCCESS: Model ready on GPU device 0")
    print("=" * 60)
    
    # Test inference
    print("\nTesting inference on GPU device 0...")
    test_prompt = "Hello, I am"
    
    inputs = tokenizer(test_prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=50,
            do_sample=False,
            temperature=None,
            pad_token_id=tokenizer.eos_token_id
        )
    
    result = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"\nTest prompt: {test_prompt}")
    print(f"Test result: {result}")
    print("\n✓ GPU inference test successful!")
    
    return model, tokenizer


if __name__ == "__main__":
    # Check CUDA setup
    if not check_cuda_setup():
        sys.exit(1)
    
    # Download and test model on GPU device 0
    try:
        model, tokenizer = download_model_on_device_0()
        print("\n✓ All systems ready for HPC deployment!")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
