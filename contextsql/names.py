"""Name helpers: abbreviation expansion + simple singularization."""
FULL2ABBR = {"customer": "cust", "quantity": "qty", "amount": "amt", "employee": "emp", "department": "dept",
             "number": "no", "description": "descr", "address": "addr", "date": "dt", "price": "prc",
             "order": "ord", "product": "prod", "invoice": "inv", "account": "acct", "transaction": "txn",
             "patient": "pat", "doctor": "doc", "appointment": "appt", "student": "stud", "course": "crs",
             "shipment": "shp", "warehouse": "wh", "subscription": "sub", "ticket": "tkt", "property": "prop",
             "listing": "lst", "member": "mem", "book": "bk", "room": "rm", "booking": "bkg", "salary": "sal",
             "category": "cat", "status": "sts", "created": "crt", "supplier": "supp", "manager": "mgr"}
ABBR2FULL = {v: k for k, v in FULL2ABBR.items()}
ABBR2FULL.update({"cus": "customer", "acc": "account", "desc": "description", "trx": "transaction",
                  "tx": "transaction", "nbr": "number", "amnt": "amount", "num": "number", "qnty": "quantity",
                  "emp": "employee", "dpt": "department", "cust": "customer", "prd": "product", "ord": "order"})
PREFIXES = {"tbl", "t", "tb"}

def singular(w):
    if w.endswith("ies") and len(w) > 4: return w[:-3] + "y"
    if w.endswith("sses"): return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3: return w[:-1]
    return w
