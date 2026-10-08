from llama_cpp import Llama
llm = Llama(model_path="models/contextsql-q4_k_m.gguf", n_ctx=2048, verbose=False)
prompt = """### Schema
CREATE TABLE customers (customer_id INT, name VARCHAR(100), country VARCHAR(50));

### Business context
(none)

### Question
How many customers are in India?

### SQL
"""
out = llm(prompt, max_tokens=100, temperature=0, stop=[";"])
print(out["choices"][0]["text"].strip() + ";")