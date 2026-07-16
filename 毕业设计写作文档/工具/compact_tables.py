#!/usr/bin/env python3
"""Convert pandoc-exported longtable+minipage blocks into compact booktabs tables.

Rules (Batch A of thesis compression):
- Proportional p{...} specs (pandoc) -> tabularx with L/R/C (X) columns preserving
  the raggedright / raggedleft / centering alignment encoded by pandoc.
- Letter specs (ll, lrrrr, ...) -> plain tabular, spec preserved verbatim.
- Header minipage cells collapsed to single-line text.
- Duplicate \\endfirsthead header removed; \\endhead/\\endlastfoot dropped.
- Wrap in table[htbp] + \\centering; caption kept with its \\label.
- Tables in the KEEP_LONGTABLE set stay as (compact) longtable because they span pages.

Only the SOURCE-OF-TRUTH .tex files are edited. Prints one line per converted table.
"""
import re
import sys

# Labels that must remain longtable (genuinely span > 1 page).
KEEP_LONGTABLE = {
    "tab:ch05-evidence-inventory",
    "tab:ch05-negative-results",
    "tab:ch05-eskf-robustness",
    "tab:ch05-r22-native-factorial",
    "tab:ch02-hardware",
    "tab:ch05-simulation-implementation",
}

LT_RE = re.compile(r"\\begin\{longtable\}(.*?)\\end\{longtable\}", re.DOTALL)


def strip_minipage(cell: str) -> str:
    """Return the plain inner text of a (possibly minipage-wrapped) header cell."""
    m = re.search(
        r"\\begin\{minipage\}\[[bt]\]\{[^}]*\}\s*(?:\\raggedright|\\raggedleft|\\centering)?\s*(.*?)\s*\\end\{minipage\}",
        cell,
        re.DOTALL,
    )
    text = m.group(1) if m else cell
    return " ".join(text.split())


def split_top_cells(header_block: str):
    """Split a header row on top-level & (all & here are top level after minipage removal)."""
    # Header block spans multiple minipage cells separated by ' & '. Extract each minipage.
    cells = re.findall(
        r"\\begin\{minipage\}.*?\\end\{minipage\}", header_block, re.DOTALL
    )
    if cells:
        return [strip_minipage(c) for c in cells]
    # Fallback: plain '&'-separated single-line header. Drop the row terminator
    # (\\ and any \tabularnewline) so the caller can re-append exactly one.
    line = " ".join(header_block.split())
    line = re.sub(r"\\tabularnewline\s*$", "", line)
    line = re.sub(r"\\\\\s*$", "", line).strip()
    return [c.strip() for c in line.split("&")]


def map_colspec(raw: str):
    """Return (mode, spec). mode in {'X','plain'}. raw is content between the outer braces."""
    raw = raw.strip()
    if "\\linewidth" in raw and "\\real" in raw:
        # proportional pandoc spec -> tabularx X columns preserving alignment
        aligns = re.findall(r"\\(raggedright|raggedleft|centering)\b", raw)
        colmap = {"raggedright": r">{\raggedright\arraybackslash}X",
                  "raggedleft": r">{\raggedleft\arraybackslash}X",
                  "centering": r">{\centering\arraybackslash}X"}
        spec = "@{}" + "".join(colmap[a] for a in aligns) + "@{}"
        return "X", spec, len(aligns)
    # letter or fixed-p spec: keep verbatim, count columns
    inner = raw
    # count columns: letters l/r/c or p{...} groups or X
    tmp = re.sub(r"p\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "P", inner)
    tmp = re.sub(r">\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", tmp)
    tmp = tmp.replace("@{}", "").replace("\\arraybackslash", "")
    ncol = len(re.findall(r"[lrcPX]", tmp))
    return "plain", inner, ncol


def convert_block(block: str) -> str:
    body = block  # includes \begin{longtable}...\end{longtable}
    # 1. column spec: everything between \begin{longtable}[]{ ... } up to the
    #    caption line. The spec may span multiple lines and contain nested braces,
    #    so match up to the first "\caption" which always follows the spec.
    m = re.search(r"\\begin\{longtable\}\[\]\{(.*?)\}\s*\\caption", body, re.DOTALL)
    if not m:
        return block
    raw_spec = " ".join(m.group(1).split())  # original pandoc spec, normalized whitespace
    mode, spec, ncol = map_colspec(m.group(1))

    # 2. caption + label
    cm = re.search(r"\\caption\{(.*?)\}(\\label\{[^}]*\})?\\tabularnewline", body, re.DOTALL)
    if not cm:
        return block
    caption = cm.group(1)
    label = cm.group(2) or ""
    label_name = re.search(r"\\label\{([^}]*)\}", label)
    label_name = label_name.group(1) if label_name else ""

    # 3. header: between first \toprule after caption and \midrule...\endfirsthead
    hm = re.search(
        r"\\tabularnewline\s*\n\\toprule\\noalign\{\}\s*\n(.*?)\\midrule\\noalign\{\}\s*\n\\endfirsthead",
        body,
        re.DOTALL,
    )
    if hm:
        header_cells = split_top_cells(hm.group(1))
    else:
        # header without \endfirsthead duplication (plain longtable)
        hm2 = re.search(
            r"\\tabularnewline\s*\n\\toprule\\noalign\{\}\s*\n(.*?)\\midrule\\noalign\{\}\s*\n\\endhead",
            body,
            re.DOTALL,
        )
        if not hm2:
            return block
        header_cells = split_top_cells(hm2.group(1))
    header_line = " & ".join(header_cells) + r" \\"

    # 4. body rows: after \endlastfoot up to \end{longtable}
    bm = re.search(r"\\endlastfoot\s*\n(.*?)\\end\{longtable\}", body, re.DOTALL)
    if not bm:
        return block
    body_rows = bm.group(1).strip("\n")

    # Every table stays an INLINE longtable (flows exactly where it sits in the
    # text, like the original pandoc output). Converting to a table[htbp] float
    # lets it reposition and washes out the vertical savings. The deterministic
    # win comes from (a) collapsing tall minipage header cells to a single line
    # and (b) dropping the duplicated \endfirsthead header copy. The original
    # pandoc column spec is preserved verbatim (proportional p{...} works here;
    # tabularx X does not).
    keep_lt = True

    if keep_lt:
        # Genuinely multi-page: stay longtable. Keep the ORIGINAL pandoc column
        # spec verbatim (proportional p{...\real{}} widths work in longtable;
        # tabularx X columns do not). Only collapse the minipage headers and
        # drop the duplicated \endfirsthead copy.
        env_open = "\\begin{longtable}[]{%s}" % raw_spec
        out = []
        out.append(env_open)
        out.append(r"\caption{%s}%s\tabularnewline" % (caption, label))
        out.append(r"\toprule\noalign{}")
        out.append(header_line)
        out.append(r"\midrule\noalign{}")
        out.append(r"\endhead")
        out.append(r"\bottomrule\noalign{}")
        out.append(r"\endlastfoot")
        out.append(body_rows)
        out.append(r"\end{longtable}")
        return "\n".join(out)

    # single-page: table + (tabularx | tabular)
    out = []
    out.append(r"\begin{table}[htbp]")
    out.append(r"\centering")
    out.append(r"\caption{%s}%s" % (caption, label))
    if mode == "X":
        out.append(r"\begin{tabularx}{\linewidth}{%s}" % spec)
    else:
        out.append(r"\begin{tabular}{@{}%s@{}}" % spec if not spec.startswith("@{}") else r"\begin{tabular}{%s}" % spec)
    out.append(r"\toprule")
    out.append(header_line)
    out.append(r"\midrule")
    out.append(body_rows)
    out.append(r"\bottomrule")
    out.append(r"\end{tabularx}" if mode == "X" else r"\end{tabular}")
    out.append(r"\end{table}")
    return "\n".join(out)


def process(path: str):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    count = [0]

    def repl(mm):
        block = mm.group(0)
        new = convert_block(block)
        if new != block:
            count[0] += 1
            lab = re.search(r"\\label\{([^}]*)\}", block)
            print("  converted:", lab.group(1) if lab else "(nolabel)")
        return new

    new_text = LT_RE.sub(repl, text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    print(f"{path}: {count[0]} tables converted")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        process(p)
