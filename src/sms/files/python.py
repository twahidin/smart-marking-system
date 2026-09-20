import ast


def render(data: bytes):
    try:
        src = data.decode("utf-8")
    except UnicodeDecodeError:
        src = data.decode("latin-1")
    lines = src.splitlines()
    try:
        ast.parse(src)  # parse only; never compiled or executed
        head, ok = "syntax: ok", "syntax ok"
    except SyntaxError as e:
        head, ok = f"syntax: error at line {e.lineno}: {e.msg}", f"syntax error at line {e.lineno}"
    body = "\n".join(f"{i:4d} | {l}" for i, l in enumerate(lines, 1))
    return head + "\n" + body + "\n", f"{len(lines)} lines, {ok}"
