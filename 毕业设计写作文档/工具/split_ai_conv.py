import os, re

src = "/home/auv_user/auv_ws/AUV-Master-Project/毕业设计写作文档/AI对话记录——了解背景信息.md"
outdir = "/tmp/ai_conv_chunks"
os.makedirs(outdir, exist_ok=True)

with open(src, "r", encoding="utf-8", errors="replace") as fh:
    lines = fh.readlines()

n = len(lines)
size = os.path.getsize(src)

# Match headings like "# Q5", "## A16", "# Q123", possibly with trailing text
marker_re = re.compile(r"^(#{1,3})\s+([QA])(\d+)\b(.*)$")
heading_re = re.compile(r"^(#{1,4})\s+(.*)$")

markers = []      # (lineno, level, kind, num, rest)
all_head = []     # (lineno, level, text)
for i, ln in enumerate(lines, 1):
    m = marker_re.match(ln)
    if m:
        markers.append((i, len(m.group(1)), m.group(2), int(m.group(3)), m.group(4).strip()))
    h = heading_re.match(ln)
    if h:
        all_head.append((i, len(h.group(1)), h.group(2).strip()))

print(f"FILE lines={n} bytes={size}")
print(f"markers(Q/A)={len(markers)} headings(all)={len(all_head)}")

# summarize marker range
if markers:
    qs = [x for x in markers if x[2] == "Q"]
    as_ = [x for x in markers if x[2] == "A"]
    if qs:
        print(f"Q range: Q{min(q[3] for q in qs)}(L{qs[0][0]}) .. Q{max(q[3] for q in qs)}(L{qs[-1][0]})")
    if as_:
        print(f"A range: A{min(a[3] for a in as_)}(L{as_[0][0]}) .. A{max(a[3] for a in as_)}(L{as_[-1][0]})")

# Write full index file
idx = os.path.join(outdir, "_INDEX_markers.txt")
with open(idx, "w", encoding="utf-8") as fh:
    fh.write(f"# file={src}\n# lines={n} bytes={size}\n\n== Q/A markers ==\n")
    for (i, lvl, kind, num, rest) in markers:
        fh.write(f"L{i}\t{'#'*lvl} {kind}{num}\t{rest[:80]}\n")
    fh.write("\n== ALL headings ==\n")
    for (i, lvl, text) in all_head:
        fh.write(f"L{i}\t{'#'*lvl} {text[:90]}\n")
print("wrote index:", idx)

# Chunk the file at Q/A marker boundaries, ~40KB per chunk, aligned to markers
boundaries = [mk[0] for mk in markers] or [1]
# ensure start at 1
if boundaries[0] != 1:
    boundaries = [1] + boundaries
chunks = []
cur_start = boundaries[0]
cur_bytes = 0
def line_bytes(a, b):
    return sum(len(lines[k-1].encode("utf-8")) for k in range(a, b))

TARGET = 45000
seg_start = boundaries[0]
for bidx in range(1, len(boundaries)):
    b = boundaries[bidx]
    if line_bytes(seg_start, b) >= TARGET:
        chunks.append((seg_start, b-1))
        seg_start = b
chunks.append((seg_start, n))

manifest = os.path.join(outdir, "_MANIFEST.txt")
with open(manifest, "w", encoding="utf-8") as mf:
    for ci, (a, b) in enumerate(chunks):
        fn = os.path.join(outdir, f"chunk_{ci:02d}_L{a}-L{b}.md")
        with open(fn, "w", encoding="utf-8") as cf:
            cf.writelines(lines[a-1:b])
        kb = os.path.getsize(fn)//1024
        mf.write(f"chunk_{ci:02d}\tL{a}-L{b}\t{kb}KB\t{fn}\n")
        print(f"chunk_{ci:02d} L{a}-L{b} {kb}KB")
print("wrote manifest:", manifest)
