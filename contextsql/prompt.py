"""Prompt format - MUST match the format the model was fine-tuned on."""

def build_prompt(schema, ctx_lines, question):
    ctx = "\n".join(ctx_lines) if ctx_lines else "(none)"
    return f"### Schema\n{schema}\n\n### Business context\n{ctx}\n\n### Question\n{question}\n\n### SQL\n"
