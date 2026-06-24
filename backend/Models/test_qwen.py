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


# from Models.llm import get_llm

# print("Loading model...")

# llm = get_llm()

# print("Model loaded successfully!")

# response = llm.invoke(
#     "What is machine learning? Explain in 3 lines."
# )

# print("\nResponse:")
# print(response)