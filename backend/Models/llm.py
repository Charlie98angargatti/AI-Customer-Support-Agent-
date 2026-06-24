"""
models/llm.py  (FIXED)
======================
Provides get_llm() — a LangChain-compatible LLM that LangGraph
can call .bind_tools() and .invoke() on.

YOUR SETUP: Qwen 2.5 1.5B Instruct via HuggingFace transformers
"""

import os
from dotenv import load_dotenv

load_dotenv()

_llm_instance = None


def get_llm(temperature: float = 0.0):
    """
    Returns a LangChain-compatible LLM instance (Ollama only).
    Singleton: loads once and reuses.
    """
    global _llm_instance

    if _llm_instance is not None:
        return _llm_instance

    use_ollama = os.getenv("USE_OLLAMA", "true").lower() == "true"

    if not use_ollama:
        raise ValueError(
            "This setup is Ollama-only. Set USE_OLLAMA=true in .env"
        )

    _llm_instance = _load_ollama(temperature)
    return _llm_instance


def _load_ollama(temperature: float):
    """
    Connects to local Ollama server.
    Make sure: ollama serve is running
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        raise ImportError(
            "Missing dependency.\n"
            "Run: pip install langchain-ollama"
        )

    model_name = os.getenv("OLLAMA_MODEL", "mistral")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    print("===================================")
    print(f"🔗 Connecting to Ollama")
    print(f"🧠 Model: {model_name}")
    print(f"🌐 URL: {base_url}")
    print("===================================")

    return ChatOllama(
        model=model_name,
        base_url=base_url,
        temperature=temperature
    )


# Optional test run
if __name__ == "__main__":
    llm = get_llm()
    print("LLM loaded successfully!")



# import os
# import torch
# from dotenv import load_dotenv

# load_dotenv()

# _llm_instance = None


# def get_llm(temperature: float = 0.0):
#     """
#     Returns a LangChain-compatible LLM instance.
#     Singleton: model loads from disk only once, then reused.
#     """
#     global _llm_instance
#     if _llm_instance is not None:
#         return _llm_instance

#     use_openai = os.getenv("USE_OPENAI", "false").lower() == "true"
#     use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"

#     if use_openai:
#         _llm_instance = _load_openai(temperature)
#     elif use_ollama:
#         _llm_instance = _load_ollama(temperature)
#     else:
#         _llm_instance = _load_huggingface(temperature)

#     return _llm_instance


# def _load_huggingface(temperature: float):
#     print("Loading Qwen2.5-1.5B-Instruct (15-60 seconds on first run)...")

#     try:
#         from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
#         from langchain_huggingface import HuggingFacePipeline, ChatHuggingFace
#     except ImportError:
#         raise ImportError(
#             "Missing packages. Run:\n"
#             "  pip install langchain-huggingface transformers accelerate"
#         )

#     model_name = os.getenv("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")

#     if torch.cuda.is_available():
#         device_map = "auto"
#         torch_dtype = torch.float16
#         print(f"  GPU detected: {torch.cuda.get_device_name(0)}")
#     else:
#         device_map = "cpu"
#         torch_dtype = torch.float32
#         print("  No GPU — running on CPU (expect 30-90s per response)")

#     print("STEP 1: Loading tokenizer")

#     tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
#     if tokenizer.pad_token is None:
#         tokenizer.pad_token = tokenizer.eos_token
#     print("STEP 2: Tokenizer loaded")

#     print("STEP 3: Loading model")

    # model = AutoModelForCausalLM.from_pretrained(
    #     model_name,
    #     torch_dtype=torch_dtype,
    #     device_map="cpu",
    #     low_cpu_mem_usage=True,
    #     trust_remote_code=True,
    # )  

#     model = AutoModelForCausalLM.from_pretrained(
#     model_name,
#     torch_dtype=torch.float32,
#     trust_remote_code=True,
# )

#     print("STEP 4: Model loaded")

#     model.eval()

#     print("STEP 5: Creating pipeline")

    # pipe = pipeline(
    #     "text-generation",
    #     model=model,
    #     tokenizer=tokenizer,
    #     max_new_tokens=1024,
    #     do_sample=(temperature > 0),
    #     temperature=temperature if temperature > 0 else None,
    #     return_full_text=False,
    #     pad_token_id=tokenizer.eos_token_id,
    # )

#     pipe = pipeline(
#     "text-generation",
#     model=model,
#     tokenizer=tokenizer,
#     max_new_tokens=512,
#     do_sample=False,
#     return_full_text=False,
#     pad_token_id=tokenizer.eos_token_id,
# )

#     print("STEP 6: Pipeline created")

#     hf_pipeline = HuggingFacePipeline(pipeline=pipe)

#     print("STEP 7: HF Pipeline created")

#     chat_model = ChatHuggingFace(llm=hf_pipeline, tokenizer=tokenizer)

#     print("STEP 8: Chat model created")
   
#     print(f"Model loaded: {model_name}")
#     return chat_model


# def _load_ollama(temperature: float):
#     try:
#         from langchain_ollama import ChatOllama
#     except ImportError:
#         raise ImportError("Run: pip install langchain-ollama")

#     model_name = os.getenv("OLLAMA_MODEL", "mistral:7b-instruct-q4_K_M")
#     base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
#     print(f"Connecting to Ollama: {model_name} at {base_url}")
#     return ChatOllama(model=model_name, base_url=base_url, temperature=temperature)


# def _load_openai(temperature: float):
#     try:
#         from langchain_openai import ChatOpenAI
#     except ImportError:
#         raise ImportError("Run: pip install langchain-openai")

#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         raise ValueError("OPENAI_API_KEY not set in .env")
#     return ChatOpenAI(model="gpt-4o-mini", temperature=temperature, api_key=api_key)

# if __name__ == "__main__":
#     llm = get_llm()
#     print("LLM loaded successfully!")

# from transformers import AutoTokenizer, AutoModelForCausalLM

# tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B")
# model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-1.5B")
# messages = [
#     {"role": "user", "content": "Who are you?"},
# ]	
# inputs = tokenizer.apply_chat_template(
# 	messages,
# 	add_generation_prompt=True,
# 	tokenize=True,
# 	return_dict=True,
# 	return_tensors="pt",
# ).to(model.device)

# outputs = model.generate(**inputs, max_new_tokens=40)
# print(tokenizer.decode(outputs[0][inputs["input_ids"].shape[-1]:]))