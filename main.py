import os
from getpass import getpass

import dscript
from client import DesmosClient


def shell():
    while True:
        c = input(">> ")
        g = dscript.DesmosScript()
        g.parse(c)
        print("\n".join(g.get_latex_statements()))


def process(script):
    with open(script, "r") as f:
        code = f.read()

    print("Compiling...")
    data = dscript.desmos_compile(code)
    if len(sys.argv) > 2:
        graph_hash = sys.argv[2]
    else:
        graph_hash = input(
            "Enter graph hash to upload to (can be passed on command line as 3rd arg): "
        )
    username = os.getenv("DESMOS_USER") or input(
        "Desmos Username (can be passed in DESMOS_USER environment variable): "
    )
    password = os.getenv("DESMOS_PASS") or getpass(
        "Desmos Password (can be passed in DESMOS_PASS environment variable): "
    )
    print("Logging in...")
    c = DesmosClient()
    c.login(username, password)
    c.save_graph(data, graph_hash)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Running dscript shell. Pass a filename to compile from file.")
        shell()
    else:
        process(sys.argv[1])
