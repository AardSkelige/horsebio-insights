def money(v):
    try:
        return f"{v:.2f}р"
    except Exception:
        return str(v)
