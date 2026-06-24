from transformers import AutoTokenizer, AutoModelForCausalLM

print("Loading tokenizer")

tokenizer = AutoTokenizer.from_pretrained(
    "Qwen/Qwen2.5-1.5B-Instruct"
)

print("Tokenizer loaded")

print("Loading model")

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-1.5B-Instruct"
)

print("Model loaded successfully")
