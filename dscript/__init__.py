"""DesmosScript Compiler"""
import re
import regex
import shlex
import json
import random
import abc
import os
import sys


STANDARD_LIBRARY = {
    "split": [
        r"s_{plita}\left(a,t_{emp}\right)=\sum_{n=t_{emp}}^{t_{emp}}a\left[n+1\right]",
        r"s_{plitb}\left(a,t_{emp}\right)=\sum_{n=t_{emp}}^{t_{emp}}a\left[n+2\right]",
        r"s_{plitc}\left(a,t_{emp}\right)=\left(s_{plita}\left(a,t_{emp}\right),s_{plitb}\left(a,t_{emp}\right)\right)",
        r"s_{plit}\left(a\right)=s_{plitc}\left(a,\left[0,2,...,\operatorname{floor}\left(\frac{\operatorname{length}\left(a\right)}{2}\right)\right]\right)",
    ],
    "concat": [
        r"c_{oncata}\left(a,b,t_{emp}\right)=\sum_{n=t_{emp}}^{t_{emp}}\left\{n\le\operatorname{length}\left(a\right):a\left[n\right],b\left[n-\operatorname{length}\left(a\right)\right]\right\}",
        r"c_{oncat}\left(a,b\right)=c_{oncata}\left(a,b,\left[1,...,\operatorname{length}\left(a\right)+\operatorname{length}\left(b\right)\right]\right)",
    ],
    "slice": [
        r"s_{licea}\left(a,t_{emp},s_{tart}\right)=\sum_{n=t_{emp}}^{t_{emp}}a\left[n+s_{tart}-1\right]",
        r"s_{liceb}\left(a,s_{tart},e_{nd}\right)=s_{licea}\left(a,\left[1,...,e_{nd}-s_{tart}+1\right],s_{tart}\right)",
        r"s_{lice}\left(a,s_{tart},e_{nd}\right)=s_{liceb}\left(a,\left\{s_{tart}<0:\operatorname{length}\left(a\right)+s_{tart}+1,s_{tart}\right\},\left\{e_{nd}<0:\operatorname{length}\left(a\right)+e_{nd}+1,e_{nd}\right\}\right)",
    ],
    "fill": [
        r"f_{illa}\left(r_{angefill},v_{fill}\right)=\sum_{n=r_{angefill}}^{r_{angefill}}v_{fill}",
        r"f_{ill}\left(l_{enfill},v_{fill}\right)=f_{illa}\left(\left[1,...l_{enfill}\right],v_{fill}\right)",
    ],
    "assign": [
        r"a_{ssigna}\left(l_{asn},i_{asn},v_{asn},t_{asn}\right)=\sum_{n=t_{asn}}^{t_{asn}}\left\{i_{asn}=n:v_{asn},l_{asn}\left[n\right]\right\}"
        r"a_{ssign}\left(l_{asn},i_{asn},v_{asn}\right)=a_{ssigna}\left(l_{asn},i_{asn},v_{asn},\left[1,...,\operatorname{length}\left(l_{asn}\right)\right]\right)",
    ],
}


def make_cond(cond, trueres, falseres):
    falseres = ',' + falseres if falseres else ''
    return "{" + cond + ":" + trueres + falseres + "}"


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
    # format fractions
    st = re.sub(r"frac\((.+?),(.+?)\)", r"\\frac{\1}{\2}", st)
    # format multi-letter variables but ignores latex \words and builtin functions
    st = re.sub(
        r"(?:(\\[a-zA-Z]+)|(polygon|sin|cos|tan|csc|sec|cot|arcsin|arccos|arctan|arccsc|arcsec|arccot|sinh|cosh|tanh|csch|sech|coth|total|min|max|length|mean|median|quantile|stdev|stdevp|mad|var|cov|corr|nCr|nPr|lcm|gcd|mod|floor|ceil|round|abs|sign|nthroot|exp|ln|log|log_a)|(?:([a-zA-Z])([a-zA-Z0-9]+)))",
        (
            lambda m: m.group(3) + "_{" + m.group(4) + "}"
            if m.group(4)
            else (m.group(1) or r"\operatorname{" + m.group(2) + "}")
        ),
        st,
    )

    return (
        st.replace("(", r"\left(")
        .replace(" ", "")
        .replace(")", r"\right)")
        .replace("[", r"\left[")
        .replace("]", r"\right]")
        .replace("<=", r"\le ")
        .replace(">=", r"\ge ")
        .replace("polygon", r"\operatorname{polygon}")
    )


class Statement(abc.ABC):
    @staticmethod
    @abc.abstractmethod
    def parse(graph, l):
        """Return True if line parsed, False if parser should try next statement"""
        return False


class PrefixedStatement(Statement):
    @classmethod
    def parse(cls, graph, l):
        if l.startswith(cls.PREFIX):
            return cls.process(graph, l)

    @staticmethod
    @abc.abstractmethod
    def process(graph, l):
        return True


class Comment(PrefixedStatement):
    PREFIX = "#"

    @staticmethod
    def process(graph, l):
        # do nothing
        return True


class Note(PrefixedStatement):
    PREFIX = '" '

    @staticmethod
    def process(graph, l):
        folder_data = {"folderId": graph.folder} if graph.folder else {}
        graph.add_exp({"type": "text", "text": l[2:], **folder_data})
        return True


class Color(PrefixedStatement):
    PREFIX = "color "

    @staticmethod
    def is_valid_color(colorhex):
        """Validates that a color is in the format #<6 hex digits>"""
        return all([i in "0123456789abcdef" for i in colorhex[1:]])

    @classmethod
    def process(cls, graph, l):
        _, _, newcolor = l.partition(" ")
        if (
            not newcolor.startswith("#")
            or len(newcolor) != 7
            or not cls.is_valid_color(newcolor)
        ):
            graph.warn(f"Invalid color statement {l!r}")
        else:
            graph.color = newcolor
        return True


class Bounds(Statement):
    @classmethod
    def parse(cls, graph, l):
        if l.startswith("xbounds ") or l.startswith("ybounds "):
            return cls.process(graph, l)

    @staticmethod
    def process(graph, l):
        args = l.split(" ")
        axe = l[0]  # x or y
        bounds = ' '.join(args[1:])
        newviewport = graph.viewport.copy()
        try:
            vmin, vmax = bounds.split(",")
            newviewport[axe + "min"] = float(vmin)
            newviewport[axe + "max"] = float(vmax)
        except ValueError:
            graph.warn(f"Syntax Error: Invalid bound statement: {l!r}")
        graph.viewport = newviewport
        return True


class Slider(PrefixedStatement):
    PREFIX = "slider "

    LOOP_DIRECTIONS = {
        "back_and_forth": None,
        "fwd": ("loopMode", "LOOP_FORWARD"),
        "once": ("newLoopMode", "PLAY_ONCE"),
    }

    @classmethod
    def process(cls, graph, l):
        if len(graph.explist) < 1 or graph.explist[-1]["type"] != "expression":
            graph.warn(f"Syntax Error: slider statement must follow an expression")
        args = l.split(" ")
        if len(args) < 4 or args[2] != "to":
            graph.warn(
                f"Syntax Error: slider statement should be in the form of "
                "'slider x to x'"
            )
            return True
        last = graph.explist[-1]
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
                        graph.warn(
                            f"Syntax Error: Expected a step after 'step' in "
                            "slider statement"
                        )
                        return True
                    i += 1
                elif arg in cls.LOOP_DIRECTIONS:
                    # ignore None values
                    if cls.LOOP_DIRECTIONS[arg]:
                        k, v = cls.LOOP_DIRECTIONS[arg]
                        last["slider"][k] = v
                elif arg == "playing":
                    last["slider"]["isPlaying"] = True
                else:
                    graph.warn(f"Ignoring unrecognized slider arg {arg}")
                i += 1
        return True


class Draggable(PrefixedStatement):
    PREFIX = "draggable"

    VALID_TYPES = ["X", "Y", "XY", "NONE"]

    @classmethod
    def process(cls, graph, l):
        args = l.split(" ")
        if len(args) < 2:
            graph.warn("Expected draggable type")
        drag_mode = args[1]
        if drag_mode not in cls.VALID_TYPES:
            graph.warn(
                f"Invalid draggable type, must be one of {', '.join(cls.VALID_TYPES)}"
            )
        # TODO: check if last is a point, maybe separate point expression that contains the default drag mode (NONE)
        graph.explist[-1]["dragMode"] = drag_mode
        return True


class Hidden(PrefixedStatement):
    PREFIX = "hidden"

    @staticmethod
    def process(graph, l):
        graph.explist[-1]["hidden"] = True
        return True


class Label(PrefixedStatement):
    PREFIX = "label "

    @staticmethod
    def process(graph, l):
        args = l.split(" ")
        if len(args) < 2:
            graph.warn("Expected label value")
        graph.explist[-1]["showLabel"] = True
        graph.explist[-1]["label"] = ' '.join(args[1:])
        return True


class LabelOptions(PrefixedStatement):
    PREFIX = "labelopts "

    OPTIONS = {
      d: ("labelOrientation", d) for d in ["left", "right", "above", "below"]
    }

    @classmethod
    def process(cls, graph, l):
        args = l.split(" ")
        for a in args[1:]:
            if a in cls.OPTIONS:
                k, v = cls.OPTIONS[a]
                graph.explist[-1][k] = v
            else:
                graph.warn(f"Unrecognized label option {a}, ignoring")
        return True


class Folder(PrefixedStatement):
    PREFIX = "folder"

    @classmethod
    def process(cls, graph, l):
        if l.startswith("folder-closed "):
            extra = {"collapsed": True}
        elif l.startswith("folder "):
            extra = {}
        else:
            graph.warn(
                f"Syntax Error: 'folder' statement must start with 'folder '"
                " or 'folder-closed ', ignoring"
            )
            return True

        _, _, folder_title = l.partition(" ")
        if not folder_title:
            print(
                f"WARN: Syntax Error: Expected folder title in 'folder' statement, ignoring"
            )
            return True

        graph.add_exp({"type": "folder", "title": folder_title, **extra})
        graph.folder = str(graph.exp_id)
        return True


class EndFolder(PrefixedStatement):
    PREFIX = "endfolder"

    @staticmethod
    def process(graph, l):
        graph.folder = None
        return True


class Include(PrefixedStatement):
    PREFIX = "include"

    @staticmethod
    def load_pkg(graph, name):
        if name in STANDARD_LIBRARY:
            return STANDARD_LIBRARY[name]
        elif os.path.exists(name + ".dscript"):
            g = graph.make_child_graph(name + ".dscript")
            with open(name + ".dscript", "r") as f:
                g.parse(f.read())
            return g.get_latex_statements()
        print("bruh")

    @classmethod
    def process(cls, graph, l):
        args = shlex.split(l)
        if len(args) < 2:
            graph.warn("Ignoring invalid include statement")
            return True
        pkgname = args[1]
        pkg = cls.load_pkg(graph, pkgname)
        if pkg is None:
            graph.warn(f"Unable to find package {pkgname!r}")
            return True

        folder_data = {"folderId": graph.folder} if graph.folder else {}
        for s in pkg:
            graph.add_exp(
                {"type": "expression", "color": graph.color, "latex": s, **folder_data}
            )

        return True


class Expression(Statement):
    @staticmethod
    def parse(graph, l):
        did_match = True
        sub = lambda s: regex.sub(
            r"\|if(?: ?)\((.+?)\)(?: ?)then(?: ?)(?:((?R))|(.+?))(?:(?: else )(?:((?R))|(.+)))?\|",
            replace_ifs,
            s,
        )

        while did_match:
            did_match = False
            # print("subbing", l)

            def replace_ifs(m):
                nonlocal did_match
                did_match = True
                cond, truerecurse, trueres, falserecurse, falseres = m.groups()

                if truerecurse:
                    trueres = sub(truerecurse)
                if falserecurse:
                    falseres = sub(falserecurse)

                res = cond_replacer(cond, trueres, falseres)
                # print("result:", res)
                return res

            l = sub(l)

        folder_data = {"folderId": graph.folder} if graph.folder else {}
        graph.add_exp(
            {
                "type": "expression",
                "color": graph.color,
                "latex": convert_to_latex(l),
                **folder_data,
            }
        )


class CircularDependencyError(Exception):
    pass


class DesmosScript:
    STATEMENTS = [
        Comment,
        Note,
        Color,
        Bounds,
        Slider,
        Draggable,
        Hidden,
        Label,
        LabelOptions,
        Folder,
        EndFolder,
        Include,
        Expression,
    ]

    def __init__(self, randseed=None, callstack=[], name="<root>"):
        if randseed is None:
            randseed = "%030x" % random.randrange(16 ** 32)
        self.randseed = randseed
        self.explist = []
        self.lineno = 0
        self.exp_id = 1  # idk why but it starts at 2
        self.color = "#000000"
        self.folder = None
        self.viewport = {"xmin": -10, "ymin": -10, "xmax": 10, "ymax": 10}
        self.callstack = callstack + [(name, None)]

    def add_exp(self, data):
        self.exp_id += 1
        data["id"] = str(self.exp_id)
        # print("Adding exp:", data)
        self.explist.append(data)

    def warn(self, *msgs):
        print("WARN:", *msgs, "\n" + self.get_trace(), file=sys.stderr)

    def parse_line(self, l):
        l = l.strip()
        if not l:
            return
        # print("parsing", l)

        for s in self.STATEMENTS:
            r = s.parse(self, l)
            if r:
                break

    def parse(self, data):
        # Make line extensions be on the same line
        # data = re.sub(r'\\(?: +)?\n(?: +)?', '', data)

        last = ""
        for ln, l in enumerate(data.split("\n")):
            self.lineno = ln + 1
            l = l.split("#")[0].strip()
            if l.endswith("\\"):
                last += l[:-1]
                # print("last:", last)
                continue

            self.parse_line(last + l)

            last = ""

    def update_callstack(self):
        """Update the last frame of the traceback's (the current one) to have to current line number. """
        self.callstack[-1] = (self.callstack[-1][0], self.lineno)

    def get_trace(self):
        self.update_callstack()
        lines = []
        for f, line in reversed(self.callstack):
            l = f"    file {f}"

            if line is not None:
                l += f" line {line}"
            lines.append(l)
        return "\n".join(lines)

    def make_child_graph(self, name):
        if name in set([i[0] for i in self.callstack]):
            raise CircularDependencyError(
                f"Attempt to import from {name!r} when it is in the call stack\n{self.get_trace()}"
            )
        self.update_callstack()
        return DesmosScript(
            randseed=self.randseed, callstack=self.callstack.copy(), name=name
        )

    def get_latex_statements(self):
        return [i["latex"] for i in self.explist if i["type"] == "expression"]

    def json(self):
        return {
            "version": 7,
            "graph": {"viewport": self.viewport},
            "randomSeed": self.randseed,
            "expressions": {"list": self.explist},
        }


def desmos_compile(data, randseed=None):
    g = DesmosScript(randseed=randseed)
    g.parse(data)
    return g.json()


def compile_file(inf, outf, write_tex=False, randseed=None):
    with open(inf, "r") as f:
        data = f.read()
    g = DesmosScript(randseed=randseed, name=inf)
    g.parse(data)
    out = g.json()

    with open(outf, "w+") as f:
        f.write(json.dumps(out))

    with open(outf + ".tex", "w+") as f:
        f.write("\n".join(g.get_latex_statements()))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <infile> [outfile]")
    inf = sys.argv[1]
    if len(sys.argv) > 2:
        out = sys.argv[2]
    else:
        parts = inf.split(".")
        out = ".".join(parts[:-1] if len(parts) > 1 else parts) + ".djson"
    compile_file(inf, outf)
