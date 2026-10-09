"""Request-phrase helpers: requested-column extraction (inference + training) and paraphrasing (training)."""
import re
from .retrieve import toks, name_alts, hit, all_fks, GENERIC_COLS

CONN = r"\b(?:with their|with its|along with|alongside|including|plus|together with|as well as|with)\b"
BLOCK = {"at", "least", "more", "than", "over", "under", "less", "only", "between", "greater", "fewer"}
CONN_CHOICES = ["with their", "along with", "alongside", "including", "plus", "together with", "as well as", "with"]

def requested_columns(question, know, tables):
    """Columns the user asked to see ('... with country and email'). A known data value means it is a filter instead."""
    parts = re.split(CONN, question, flags=re.I)
    if len(parts) < 2:
        return []
    seg = parts[-1]
    if re.search(r"\d", seg) or BLOCK & set(seg.lower().split()):
        return []
    q = set(toks(seg))
    if not q:
        return []
    for vals in know.get("values", {}).values():
        for v in vals:
            vt = set(toks(v))
            if vt and vt <= q:
                return []
    out = []
    for t in tables:
        meta = know["tables"][t]
        skip = {c for fk in all_fks(meta) for c in fk["cols"]} | set(meta["pk"])
        alts_t = name_alts(t)
        tname = set().union(*alts_t) if alts_t else set()
        for col in meta["columns"]:
            alts = [a for a in name_alts(col) if not (a & GENERIC_COLS)]
            if not alts or col in skip or set().union(*alts) <= tname:
                continue
            if hit(alts, q) and col not in out:
                out.append(col)
    return out

WORD_SWAPS = {"total": ["total", "overall"], "average": ["average", "mean"], "highest": ["highest", "largest", "biggest"],
              "lowest": ["lowest", "smallest"], "per": ["per", "for each"], "Top": ["Top", "Best"],
              "give": ["give", "show", "list"], "Number": ["Number", "Count"]}

def paraphrase(q, rng, extra=False):
    for k, opts in WORD_SWAPS.items():
        if re.search(rf"\b{k}\b", q) and rng.random() < 0.4:
            q = re.sub(rf"\b{k}\b", rng.choice(opts), q, count=1)
    if extra and rng.random() < 0.8:
        q = re.sub(CONN, rng.choice(CONN_CHOICES), q, count=1, flags=re.I)
    return q

def typo(q, rng, p=0.06):
    """Light real-world noise: drop or swap one letter in a long word."""
    if rng.random() > p:
        return q
    ws = q.split(" ")
    idx = [i for i, w in enumerate(ws) if len(w) >= 6 and w.isalpha()]
    if not idx:
        return q
    i = rng.choice(idx); w = ws[i]; j = rng.randrange(1, len(w) - 2)
    ws[i] = w[:j] + w[j + 1:] if rng.random() < 0.5 else w[:j] + w[j + 1] + w[j] + w[j + 2:]
    return " ".join(ws)
