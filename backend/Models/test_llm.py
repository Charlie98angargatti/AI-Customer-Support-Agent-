print("STEP 0")

try:
    print("STEP 1")

    from llm import get_llm
    
    print("STEP 2")

    llm = get_llm()

    print("STEP 3")

    response = llm.invoke(
        "What is machine learning? Explain in 3 lines."
    )

    print("STEP 4")

    print(response)

except Exception as e:
    import traceback

    print("\nERROR OCCURRED\n")
    traceback.print_exc()

input("\nPress Enter to exit...")


