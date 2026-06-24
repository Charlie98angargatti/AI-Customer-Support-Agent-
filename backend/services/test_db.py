# from Services.db_service import execute_query
# from Services.db_service import execute_query
# # from db_service import execute_query

# result = execute_query("SELECT * FROM customers LIMIT 3")
# print(result)

print("1. Starting")

from Services.db_service import execute_query

print("2. Import successful")

result = execute_query("SELECT * FROM customers LIMIT 3")

print("3. Query finished")
print(result)