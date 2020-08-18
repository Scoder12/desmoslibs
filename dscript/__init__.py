"""DesmosScript Compiler"""
import re
import regex
import json
import sys
import random


def make_cond(cond, trueres, falseres):
    return "{" + cond + ":" + trueres + "," + falseres + "}"


def make_and_exp(conda, condb, trueres, falseres):
    return make_cond(conda, make_cond(condb, trueres, falseres), falseres)


def make_or_exp(conda, condb, trueres, falseres):
    return make_cond(conda, trueres, make_cond(condb, trueres, falseres))


def cond_replacer(cond, trueres, falseres):
    for op, op_f in {"and": make_and_exp, "or": make_or_exp}.items():
        split = cond.split(f" {op} ")
        if len(split) != 2:
            continue
        conda, condb = split
        res = op_f(conda, condb, trueres, falseres)
        return res
    return make_cond(cond, trueres, falseres)

    # re.sub(r'\((.*?)\)', lambda cm: operation_replacer(cm.group(1)), cond)


def convert_to_latex(st):
    st = (
        st.replace("{", r"\left\{")
        .replace("}", r"\right\}")
        .replace("*", r"\cdot")
        .replace(" ", "")
    )
    # format multi-letter variables but ignores latex \words and function(s
    # (regex and lambda black magic)
    st = re.sub(
        r"(?:(\\[a-zA-Z]+)|([a-zA-Z]+\()|(?:([a-zA-Z])([a-zA-Z0-9]+)))",
        (
            lambda m: print(m.groups(), m.group(2))
            or m.group(3) + "_{" + m.group(4) + "}"
            if m.group(4)
            else (m.group(1) or m.group(2))
        ),
        st,
    )

    # format multi-letter variables
    # must be followed by = or ~ to be replaced
    # st = re.sub(r'([a-zA-Z0-9])([a-zA-Z0-9]+)(?==|~)', r'\1_{\2}', st)

    return (
        st.replace("(", r"\left(")
        .replace(")", r"\right)")
        .replace("<=", r"\le")
        .replace(">=", r"\ge")
        .replace(" ", "")
    )


LOOP_DIRECTIONS = {
    "back_and_forth": None,
    "fwd": ("loopMod", "LOOP_FORWARD"),
    "once": ("newLoopMode", "PLAY_ONCE"),
}


def desmos_compile(data, randseed=None):
    # change line expansions to be on a single line
    data = re.sub(r"\\(?: +)?\n(?: +)?", "", data)

    explist = []
    lno = 1  # idk why but it starts at 2
    color = "#000000"
    folder = None
    viewport = {"xmin": -10, "ymin": -10, "xmax": 10, "ymax": 10}
    for l in data.split("\n"):
        l = l.strip()
        if not l or l.startswith("#"):
            continue

        if l.startswith("color "):
            newcolor = l[len("color ") :]
            if (
                not newcolor.startswith("#")
                or len(newcolor) != 7
                or not all([i in "0123456789abcdef" for i in newcolor[1:]])
            ):
                print(f"Warn: Invalid color statement {l!r}", file=sys.stderr)
            else:
                color = newcolor
            continue

        if l.startswith("xbounds ") or l.startswith("ybounds"):
            axe = l[0]  # x or y
            bounds = l[len("*bounds ") :]
            newviewport = viewport.copy()
            try:
                vmin, vmax = bounds.split(",")
                newviewport[axe + "min"] = float(vmin)
                newviewport[axe + "max"] = float(vmax)
            except ValueError:
                print(
                    f"WARN: Syntax Error: Invalid bound statement: {l!r}",
                    file=sys.stderr,
                )
            viewport = newviewport
            continue

        if l.startswith("slider "):
            if len(explist) < 1 or explist[-1]["type"] != "expression":
                print(
                    f"WARN: Syntax Error: slider statement must follow an expression",
                    file=sys.stderr,
                )
            args = l.split(" ")
            if len(args) < 4 or args[2] != "to":
                print(
                    f"WARN: Syntax Error: slider statement should be in the form of "
                    "'slider x to x'",
                    file=sys.stderr,
                )
                continue
            last = explist[-1]
            last["slider"] = {
                "hardMin": True,
                "hardMax": True,
                "min": convert_to_latex(args[1]),
                "max": convert_to_latex(args[3]),
            }
            if len(args) >= 5:
                i = 4
                while i < len(args):
                    arg = args[i]
                    if arg.startswith("@") and arg.endswith("x"):
                        speed = float(arg[1:-1])
                        last["slider"]["animationPeriod"] = 4000 / speed
                    elif arg == "step":
                        try:
                            last["slider"]["step"] = args[i + 1]
                        except IndexError:
                            print(
                                f"WARN: Syntax Error: Expected a step after 'step' in "
                                "slider statement",
                                file=sys.stderr,
                            )
                            continue
                        i += 1
                    elif arg in LOOP_DIRECTIONS:
                        if LOOP_DIRECTIONS[arg]:
                            k, v = LOOP_DIRECTIONS[arg]
                            last["slider"][k] = v
                    elif arg == "playing":
                        last["slider"]["isPlaying"] = True
                    else:
                        print(
                            f"WARN: Ignoring unrecognized slider arg {arg}",
                            file=sys.stderr,
                        )
                    i += 1
            continue

        if l.startswith("folder"):
            if l.startswith("folder-closed "):
                folder_title = l[len("folder-closed ") :]
                extra = {"collapsed": True}
            elif l.startswith("folder "):
                folder_title = l[len("folder ") :]
                extra = {}
            else:
                print(
                    f"WARN: Syntax Error: 'folder' statement must start with 'folder '"
                    " or 'folder closed ', ignoring",
                    file=sys.stderr,
                )
                continue

            if not folder_title:
                print(
                    f"WARN: Syntax Error: Expected folder title in 'folder' statement, ignoring",
                    file=sys.stderr,
                )
                continue
            explist.append(
                {"type": "folder", "id": str(lno), "title": folder_title, **extra}
            )
            folder = str(lno)
            continue

        if l.startswith("endfolder"):
            folder = None
            continue

        lno += 1
        folder_data = {"folderId": folder} if folder else {}
        if l.startswith('" '):
            explist.append(
                {"type": "text", "id": str(lno), "text": l[2:], **folder_data}
            )
        else:
            did_match = True
            sub = lambda s: regex.sub(
                r"\(if(?: ?)\((.+?)\)(?: ?)then(?: ?)(?:((?R))|(.+?))(?: else )(?:((?R))|(.+?))\)",
                replace_ifs,
                s,
            )

            while did_match:
                did_match = False
                print("subbing", l)

                def replace_ifs(m):
                    nonlocal did_match
                    did_match = True

                    cond, truerecurse, trueres, falserecurse, falseres = m.groups()
                    print("GROUPS:", *(f"\n{repr(i)}" for i in m.groups()))
                    if truerecurse:
                        trueres = sub(truerecurse)
                        print(f"subbed truerecurse, now {trueres!r}")
                    if falserecurse:
                        falseres = sub(falserecurse)
                        print(f"subbed falserecurse, now {falseres!r}")
                    return cond_replacer(cond, trueres, falseres)

                l = sub(l)
            print("RES:", repr(l))

            explist.append(
                {
                    "type": "expression",
                    "id": str(lno),
                    "color": color,
                    "latex": convert_to_latex(l),
                    **folder_data,
                }
            )

    if randseed is None:
        randseed = "%030x" % random.randrange(16 ** 32)

    return {
        "version": 7,
        "graph": {"viewport": viewport},
        "randomSeed": randseed,
        "expressions": {"list": explist},
    }


def compile_file(inf, outf, write_tex=False):
    with open(inf, "r") as f:
        data = f.read()
    out = desmos_compile(data)

    with open(outf, "w+") as f:
        f.write(json.dumps(out))

    with open(outf + ".tex", "w+") as f:
        f.write(
            "\n".join(
                [
                    i["latex"]
                    for i in out["expressions"]["list"]
                    if i["type"] == "expression"
                ]
            )
        )


if __name__ == "__main__":
    compile_file("test.dscript", "test.djson")
