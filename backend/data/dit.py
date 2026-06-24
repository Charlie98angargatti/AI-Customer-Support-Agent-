import duckdb

con = duckdb.connect("data/crm.duckdb")

rows = con.execute("SELECT * FROM orders").fetchall()

print("👤 Orders (row by row):\n")

for row in rows:
    print(row)