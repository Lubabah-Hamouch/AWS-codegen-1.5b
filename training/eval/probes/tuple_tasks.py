"""Tuple-immutability probe: 40 small tasks written for this probe (not from HumanEval, MBPP or the training data).

Each task's natural solution builds or updates tuples, so a model that treats tuples as mutable fails with
`TypeError: 'tuple' object does not support item assignment` (the playground's merge_intervals recording fails exactly
that way). Prompts are plain requests in the style of the playground's examples; they do not mention mutation, so the
probe measures what the model does unprompted.

Each task: id, entry (function name), prompt, cases [(args, expected)], reference (a correct solution, checked by
`tuple_probe.py validate`). An expected value of RAISES + "Name" means the call must raise that exception.
"""

RAISES = "__raises__:"

TASKS = [
    dict(id="merge_intervals", entry="merge_intervals",
         prompt="Write a Python function merge_intervals(intervals) that takes a list of (start, end) tuples and merges "
                "all overlapping or touching intervals. Return the merged intervals as a list of (start, end) tuples, "
                "sorted by start.",
         cases=[(([(1, 3), (2, 6), (8, 10), (15, 18)],), [(1, 6), (8, 10), (15, 18)]), (([(1, 4), (4, 5)],), [(1, 5)]),
                (([],), []), (([(5, 7), (1, 2)],), [(1, 2), (5, 7)]), (([(1, 10), (2, 3), (4, 5)],), [(1, 10)])],
         reference='''
def merge_intervals(intervals):
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
'''),
    dict(id="insert_interval", entry="insert_interval",
         prompt="Write a Python function insert_interval(intervals, new) where intervals is a sorted list of "
                "non-overlapping (start, end) tuples and new is a (start, end) tuple. Insert new and merge any overlaps. "
                "Return the result as a sorted list of (start, end) tuples.",
         cases=[(([(1, 3), (6, 9)], (2, 5)), [(1, 5), (6, 9)]),
                (([(1, 2), (3, 5), (6, 7), (8, 10), (12, 16)], (4, 8)), [(1, 2), (3, 10), (12, 16)]),
                (([], (5, 7)), [(5, 7)]), (([(1, 5)], (6, 8)), [(1, 5), (6, 8)])],
         reference='''
def insert_interval(intervals, new):
    out = []
    for s, e in sorted(intervals + [new]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
'''),
    dict(id="interval_intersections", entry="interval_intersections",
         prompt="Write a Python function interval_intersections(a, b) where a and b are sorted lists of disjoint closed "
                "intervals given as (start, end) tuples. Return the list of their intersections as (start, end) tuples.",
         cases=[(([(0, 2), (5, 10)], [(1, 5), (8, 12)]), [(1, 2), (5, 5), (8, 10)]), (([(1, 3)], []), []),
                (([(1, 7)], [(3, 10)]), [(3, 7)])],
         reference='''
def interval_intersections(a, b):
    i = j = 0
    out = []
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if lo <= hi:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out
'''),
    dict(id="group_consecutive", entry="group_consecutive",
         prompt="Write a Python function group_consecutive(nums) that takes a sorted list of distinct integers and "
                "returns the runs of consecutive numbers as a list of (first, last) tuples.",
         cases=[(([1, 2, 3, 5, 7, 8],), [(1, 3), (5, 5), (7, 8)]), (([],), []), (([4],), [(4, 4)]),
                (([1, 3, 4, 5, 10],), [(1, 1), (3, 5), (10, 10)])],
         reference='''
def group_consecutive(nums):
    out = []
    for n in nums:
        if out and n == out[-1][1] + 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out
'''),
    dict(id="run_length_encode", entry="run_length_encode",
         prompt="Write a Python function run_length_encode(s) that run-length encodes a string. Return a list of "
                "(character, count) tuples.",
         cases=[(("aaabcc",), [("a", 3), ("b", 1), ("c", 2)]), (("",), []), (("x",), [("x", 1)]),
                (("aabbaa",), [("a", 2), ("b", 2), ("a", 2)])],
         reference='''
def run_length_encode(s):
    out = []
    for ch in s:
        if out and out[-1][0] == ch:
            out[-1] = (ch, out[-1][1] + 1)
        else:
            out.append((ch, 1))
    return out
'''),
    dict(id="merge_runs", entry="merge_runs",
         prompt="Write a Python function merge_runs(runs) that takes a list of (value, count) tuples and merges "
                "neighbouring entries with the same value by adding their counts. Return a list of (value, count) tuples.",
         cases=[(([("a", 2), ("a", 3), ("b", 1)],), [("a", 5), ("b", 1)]), (([],), []),
                (([("x", 1), ("y", 2), ("y", 2), ("x", 1)],), [("x", 1), ("y", 4), ("x", 1)])],
         reference='''
def merge_runs(runs):
    out = []
    for v, c in runs:
        if out and out[-1][0] == v:
            out[-1] = (v, out[-1][1] + c)
        else:
            out.append((v, c))
    return out
'''),
    dict(id="shift_points", entry="shift_points",
         prompt="Write a Python function shift_points(points, dx, dy) that takes a list of (x, y) tuples and returns a "
                "list of (x, y) tuples with every point moved by dx and dy.",
         cases=[(([(0, 0), (1, 2)], 3, -1), [(3, -1), (4, 1)]), (([], 1, 1), [])],
         reference='''
def shift_points(points, dx, dy):
    return [(x + dx, y + dy) for x, y in points]
'''),
    dict(id="bump_version", entry="bump_version",
         prompt="Write a Python function bump_version(version, part) where version is a (major, minor, patch) tuple and "
                "part is 'major', 'minor' or 'patch'. Increase that part by one, reset the parts after it to zero, and "
                "return the new version tuple.",
         cases=[(((1, 2, 3), "patch"), (1, 2, 4)), (((1, 2, 3), "minor"), (1, 3, 0)), (((1, 2, 3), "major"), (2, 0, 0))],
         reference='''
def bump_version(version, part):
    major, minor, patch = version
    if part == "major":
        return (major + 1, 0, 0)
    if part == "minor":
        return (major, minor + 1, 0)
    return (major, minor, patch + 1)
'''),
    dict(id="set_cell", entry="set_cell",
         prompt="Write a Python function set_cell(grid, row, col, value) where grid is a tuple of tuples. Return a new "
                "grid, also a tuple of tuples, with the cell at (row, col) set to value.",
         cases=[((((0, 0), (0, 0)), 1, 0, 5), ((0, 0), (5, 0))), ((((1, 2, 3),), 0, 2, 9), ((1, 2, 9),))],
         reference='''
def set_cell(grid, row, col, value):
    return tuple(tuple(value if (r, c) == (row, col) else v for c, v in enumerate(line)) for r, line in enumerate(grid))
'''),
    dict(id="transpose", entry="transpose",
         prompt="Write a Python function transpose(matrix) that takes a matrix given as a tuple of tuples and returns "
                "its transpose as a tuple of tuples.",
         cases=[((((1, 2, 3), (4, 5, 6)),), ((1, 4), (2, 5), (3, 6))), ((((7,),),), ((7,),))],
         reference='''
def transpose(matrix):
    return tuple(zip(*matrix))
'''),
    dict(id="rotate_clockwise", entry="rotate_clockwise",
         prompt="Write a Python function rotate_clockwise(grid) that takes a grid given as a tuple of tuples and "
                "returns it rotated 90 degrees clockwise, as a tuple of tuples.",
         cases=[((((1, 2), (3, 4)),), ((3, 1), (4, 2))), ((((1, 2, 3),),), ((1,), (2,), (3,)))],
         reference='''
def rotate_clockwise(grid):
    return tuple(zip(*grid[::-1]))
'''),
    dict(id="place_mark", entry="place_mark",
         prompt="Write a Python function place_mark(board, row, col, mark) for tic-tac-toe. board is a tuple of three "
                "tuples of 'X', 'O' or ' '. Return a new board (tuple of tuples) with mark placed at (row, col). Raise "
                "ValueError if that square is already taken.",
         cases=[(((("X", " ", " "), (" ", "O", " "), (" ", " ", " ")), 2, 2, "X"),
                 (("X", " ", " "), (" ", "O", " "), (" ", " ", "X"))),
                (((("X", " ", " "), (" ", "O", " "), (" ", " ", " ")), 0, 0, "O"), "__raises__:ValueError")],
         reference='''
def place_mark(board, row, col, mark):
    if board[row][col] != " ":
        raise ValueError("square taken")
    return tuple(tuple(mark if (r, c) == (row, col) else v for c, v in enumerate(line)) for r, line in enumerate(board))
'''),
    dict(id="update_inventory", entry="update_inventory",
         prompt="Write a Python function update_inventory(items, name, delta) where items is a list of (name, quantity) "
                "tuples. Add delta to that item's quantity (append the item at the end if it is missing) and drop any "
                "item whose quantity becomes zero or less. Return the updated list of (name, quantity) tuples.",
         cases=[(([("apple", 3), ("pear", 1)], "apple", 2), [("apple", 5), ("pear", 1)]),
                (([("apple", 3)], "kiwi", 4), [("apple", 3), ("kiwi", 4)]),
                (([("apple", 3), ("pear", 1)], "pear", -1), [("apple", 3)])],
         reference='''
def update_inventory(items, name, delta):
    out, found = [], False
    for n, q in items:
        if n == name:
            q, found = q + delta, True
        if q > 0:
            out.append((n, q))
    if not found and delta > 0:
        out.append((name, delta))
    return out
'''),
    dict(id="tally", entry="tally",
         prompt="Write a Python function tally(pairs) that takes a list of (key, count) tuples and adds up the counts "
                "per key. Return a list of (key, total) tuples in the order each key first appears.",
         cases=[(([("a", 1), ("b", 2), ("a", 3)],), [("a", 4), ("b", 2)]), (([],), [])],
         reference='''
def tally(pairs):
    totals = {}
    for k, c in pairs:
        totals[k] = totals.get(k, 0) + c
    return list(totals.items())
'''),
    dict(id="running_totals", entry="running_totals",
         prompt="Write a Python function running_totals(entries) that takes a list of (label, amount) tuples and returns "
                "a list of (label, running total) tuples.",
         cases=[(([("mon", 5), ("tue", -2), ("wed", 4)],), [("mon", 5), ("tue", 3), ("wed", 7)]), (([],), [])],
         reference='''
def running_totals(entries):
    out, total = [], 0
    for label, amount in entries:
        total += amount
        out.append((label, total))
    return out
'''),
    dict(id="apply_discount", entry="apply_discount",
         prompt="Write a Python function apply_discount(products, percent) where products is a list of (name, price) "
                "tuples. Return a list of (name, discounted price) tuples, with prices rounded to 2 decimals.",
         cases=[(([("pen", 10.0), ("book", 25.0)], 20), [("pen", 8.0), ("book", 20.0)]), (([], 50), [])],
         reference='''
def apply_discount(products, percent):
    return [(n, round(p * (100 - percent) / 100, 2)) for n, p in products]
'''),
    dict(id="rename_record", entry="rename_record",
         prompt="Write a Python function rename_record(record, new_name) where record is a (name, email, age) tuple. "
                "Return the record with the name replaced, as a tuple.",
         cases=[((("ann", "a@x.io", 30), "anna"), ("anna", "a@x.io", 30))],
         reference='''
def rename_record(record, new_name):
    return (new_name,) + tuple(record[1:])
'''),
    dict(id="sort_by_age", entry="sort_by_age",
         prompt="Write a Python function sort_by_age(people) that takes a list of (name, age) tuples and returns them "
                "sorted by age, then by name.",
         cases=[(([("bo", 30), ("al", 25), ("cy", 30)],), [("al", 25), ("bo", 30), ("cy", 30)]), (([],), [])],
         reference='''
def sort_by_age(people):
    return sorted(people, key=lambda p: (p[1], p[0]))
'''),
    dict(id="clamp_points", entry="clamp_points",
         prompt="Write a Python function clamp_points(points, lo, hi) that takes a list of (x, y) tuples and clamps both "
                "coordinates of every point to the range [lo, hi]. Return a list of (x, y) tuples.",
         cases=[(([(-5, 3), (12, 7)], 0, 10), [(0, 3), (10, 7)]), (([], 0, 1), [])],
         reference='''
def clamp_points(points, lo, hi):
    c = lambda v: max(lo, min(hi, v))
    return [(c(x), c(y)) for x, y in points]
'''),
    dict(id="move_robot", entry="move_robot",
         prompt="Write a Python function move_robot(start, commands) where start is an (x, y) tuple and commands is a "
                "string of 'N', 'S', 'E', 'W' moves of one step each (N increases y, E increases x). Return the final "
                "position as an (x, y) tuple.",
         cases=[(((0, 0), "NNE"), (1, 2)), (((2, 2), "SSWW"), (0, 0)), (((5, 5), ""), (5, 5))],
         reference='''
def move_robot(start, commands):
    x, y = start
    d = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "W": (-1, 0)}
    for ch in commands:
        x, y = x + d[ch][0], y + d[ch][1]
    return (x, y)
'''),
    dict(id="path_positions", entry="path_positions",
         prompt="Write a Python function path_positions(start, steps) where start is an (x, y) tuple and steps is a list "
                "of (dx, dy) tuples. Return the list of positions visited, starting with start, as (x, y) tuples.",
         cases=[(((0, 0), [(1, 0), (0, 2)]), [(0, 0), (1, 0), (1, 2)]), (((3, 3), []), [(3, 3)])],
         reference='''
def path_positions(start, steps):
    out = [tuple(start)]
    for dx, dy in steps:
        out.append((out[-1][0] + dx, out[-1][1] + dy))
    return out
'''),
    dict(id="snake_step", entry="snake_step",
         prompt="Write a Python function snake_step(body, direction) for a snake game. body is a list of (row, col) "
                "tuples, head first; direction is 'U', 'D', 'L' or 'R' (U decreases row). Move the snake one step and "
                "return the new body as a list of (row, col) tuples of the same length.",
         cases=[(([(2, 2), (2, 1), (2, 0)], "R"), [(2, 3), (2, 2), (2, 1)]), (([(0, 0)], "D"), [(1, 0)])],
         reference='''
def snake_step(body, direction):
    dr, dc = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}[direction]
    head = (body[0][0] + dr, body[0][1] + dc)
    return [head] + list(body[:-1])
'''),
    dict(id="extend_ranges", entry="extend_ranges",
         prompt="Write a Python function extend_ranges(ranges, amount) that takes a list of (start, end) tuples and "
                "widens each range by amount on both sides. Return a list of (start, end) tuples.",
         cases=[(([(5, 10), (20, 25)], 2), [(3, 12), (18, 27)]), (([], 3), [])],
         reference='''
def extend_ranges(ranges, amount):
    return [(s - amount, e + amount) for s, e in ranges]
'''),
    dict(id="split_interval", entry="split_interval",
         prompt="Write a Python function split_interval(interval, at) where interval is a (start, end) tuple. If start < "
                "at < end, return [(start, at), (at, end)]; otherwise return a list containing the original interval.",
         cases=[(((0, 10), 4), [(0, 4), (4, 10)]), (((0, 10), 0), [(0, 10)]), (((0, 10), 12), [(0, 10)])],
         reference='''
def split_interval(interval, at):
    s, e = interval
    return [(s, at), (at, e)] if s < at < e else [(s, e)]
'''),
    dict(id="find_gaps", entry="find_gaps",
         prompt="Write a Python function find_gaps(intervals, lo, hi) where intervals is a list of half-open [start, end) "
                "ranges given as (start, end) tuples, in any order and possibly overlapping. Return the parts of [lo, hi) "
                "that no interval covers, as a sorted list of (start, end) tuples.",
         cases=[(([(2, 4), (6, 8)], 0, 10), [(0, 2), (4, 6), (8, 10)]), (([(0, 10)], 0, 10), []),
                (([(5, 7), (1, 3)], 0, 8), [(0, 1), (3, 5), (7, 8)]), (([(1, 5), (2, 3)], 0, 6), [(0, 1), (5, 6)])],
         reference='''
def find_gaps(intervals, lo, hi):
    out, cur = [], lo
    for s, e in sorted(intervals):
        if s > cur:
            out.append((cur, min(s, hi)))
        cur = max(cur, e)
        if cur >= hi:
            break
    if cur < hi:
        out.append((cur, hi))
    return [(s, e) for s, e in out if s < e]
'''),
    dict(id="merge_meetings", entry="merge_meetings",
         prompt="Write a Python function merge_meetings(meetings) where meetings is a list of (start, end, room) tuples. "
                "Merge meetings in the same room that overlap or touch. Return a list of (start, end, room) tuples sorted "
                "by room, then start.",
         cases=[(([(9, 10, "A"), (10, 11, "A"), (9, 12, "B")],), [(9, 11, "A"), (9, 12, "B")]),
                (([(13, 14, "A"), (9, 10, "A")],), [(9, 10, "A"), (13, 14, "A")])],
         reference='''
def merge_meetings(meetings):
    out = []
    for s, e, room in sorted(meetings, key=lambda m: (m[2], m[0], m[1])):
        if out and out[-1][2] == room and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e), room)
        else:
            out.append((s, e, room))
    return out
'''),
    dict(id="matrix_add", entry="matrix_add",
         prompt="Write a Python function matrix_add(a, b) that adds two matrices of the same shape, each given as a "
                "tuple of tuples, and returns the sum as a tuple of tuples.",
         cases=[((((1, 2), (3, 4)), ((10, 20), (30, 40))), ((11, 22), (33, 44)))],
         reference='''
def matrix_add(a, b):
    return tuple(tuple(x + y for x, y in zip(ra, rb)) for ra, rb in zip(a, b))
'''),
    dict(id="scale_matrix", entry="scale_matrix",
         prompt="Write a Python function scale_matrix(m, k) that multiplies every entry of a matrix (a tuple of tuples) "
                "by k and returns the result as a tuple of tuples.",
         cases=[((((1, 2), (3, 4)), 3), ((3, 6), (9, 12)))],
         reference='''
def scale_matrix(m, k):
    return tuple(tuple(v * k for v in row) for row in m)
'''),
    dict(id="replace_value", entry="replace_value",
         prompt="Write a Python function replace_value(t, old, new) that takes a tuple and returns a tuple with every "
                "occurrence of old replaced by new.",
         cases=[(((1, 2, 1, 3), 1, 9), (9, 2, 9, 3)), (((), 1, 2), ())],
         reference='''
def replace_value(t, old, new):
    return tuple(new if v == old else v for v in t)
'''),
    dict(id="swap_pairs", entry="swap_pairs",
         prompt="Write a Python function swap_pairs(pairs) that takes a list of (a, b) tuples and returns a list of "
                "(b, a) tuples.",
         cases=[(([(1, "x"), (2, "y")],), [("x", 1), ("y", 2)]), (([],), [])],
         reference='''
def swap_pairs(pairs):
    return [(b, a) for a, b in pairs]
'''),
    dict(id="update_bounding_box", entry="update_bounding_box",
         prompt="Write a Python function update_bounding_box(box, point) where box is a (min_x, min_y, max_x, max_y) "
                "tuple and point is an (x, y) tuple. Return the smallest box, as a tuple of the same shape, that "
                "contains both.",
         cases=[(((0, 0, 2, 2), (5, -1)), (0, -1, 5, 2)), (((0, 0, 2, 2), (1, 1)), (0, 0, 2, 2))],
         reference='''
def update_bounding_box(box, point):
    x0, y0, x1, y1 = box
    x, y = point
    return (min(x0, x), min(y0, y), max(x1, x), max(y1, y))
'''),
    dict(id="bounding_box", entry="bounding_box",
         prompt="Write a Python function bounding_box(points) that takes a non-empty list of (x, y) tuples and returns "
                "their bounding box as a (min_x, min_y, max_x, max_y) tuple.",
         cases=[(([(1, 5), (-2, 3), (4, 0)],), (-2, 0, 4, 5)), (([(3, 3)],), (3, 3, 3, 3))],
         reference='''
def bounding_box(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))
'''),
    dict(id="value_counts", entry="value_counts",
         prompt="Write a Python function value_counts(values) that counts how often each value occurs in a list and "
                "returns a list of (value, count) tuples sorted by count descending, then by value ascending.",
         cases=[(([3, 1, 3, 2, 1, 3],), [(3, 3), (1, 2), (2, 1)]), (([],), [])],
         reference='''
def value_counts(values):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
'''),
    dict(id="dedupe_pairs", entry="dedupe_pairs",
         prompt="Write a Python function dedupe_pairs(pairs) that takes a list of (a, b) tuples and drops any pair equal "
                "to, or the reverse of, an earlier pair. Return the remaining pairs as a list of tuples, in order.",
         cases=[(([(1, 2), (2, 1), (3, 4), (1, 2)],), [(1, 2), (3, 4)]), (([],), [])],
         reference='''
def dedupe_pairs(pairs):
    seen, out = set(), []
    for a, b in pairs:
        if (a, b) not in seen and (b, a) not in seen:
            seen.add((a, b))
            out.append((a, b))
    return out
'''),
    dict(id="increment_score", entry="increment_score",
         prompt="Write a Python function increment_score(scores, player, points) where scores is a list of (player, "
                "score) tuples. Add points to that player's score, appending the player at the end if missing, and "
                "return the updated list of (player, score) tuples.",
         cases=[(([("ana", 10), ("ben", 7)], "ben", 5), [("ana", 10), ("ben", 12)]), (([], "cy", 3), [("cy", 3)])],
         reference='''
def increment_score(scores, player, points):
    out = [(p, s + points) if p == player else (p, s) for p, s in scores]
    if not any(p == player for p, _ in scores):
        out.append((player, points))
    return out
'''),
    dict(id="normalize", entry="normalize",
         prompt="Write a Python function normalize(v) that takes a vector as a tuple of numbers and returns it scaled to "
                "length 1, as a tuple. A zero vector is returned unchanged.",
         cases=[(((3, 4),), (0.6, 0.8)), (((0, 0),), (0, 0)), (((0, 5, 0),), (0.0, 1.0, 0.0))],
         reference='''
def normalize(v):
    n = sum(x * x for x in v) ** 0.5
    return tuple(v) if n == 0 else tuple(x / n for x in v)
'''),
    dict(id="cumulative_max", entry="cumulative_max",
         prompt="Write a Python function cumulative_max(pairs) that takes a list of (label, value) tuples and returns a "
                "list of (label, largest value so far) tuples.",
         cases=[(([("a", 3), ("b", 1), ("c", 5)],), [("a", 3), ("b", 3), ("c", 5)]), (([],), [])],
         reference='''
def cumulative_max(pairs):
    out, best = [], None
    for label, v in pairs:
        best = v if best is None else max(best, v)
        out.append((label, best))
    return out
'''),
    dict(id="fill_row", entry="fill_row",
         prompt="Write a Python function fill_row(grid, row, value) where grid is a tuple of tuples. Return a new grid, "
                "as a tuple of tuples, with every cell in that row set to value.",
         cases=[((((1, 2), (3, 4)), 0, 0), ((0, 0), (3, 4))), ((((1, 2, 3),), 0, 7), ((7, 7, 7),))],
         reference='''
def fill_row(grid, row, value):
    return tuple(tuple(value for _ in line) if r == row else tuple(line) for r, line in enumerate(grid))
'''),
    dict(id="assign_seats", entry="assign_seats",
         prompt="Write a Python function assign_seats(seats, n) where seats is a tuple of rows, each a tuple of 0 (free) "
                "and 1 (taken). Find the first row with n free seats next to each other, take the leftmost such block, "
                "and return (new_seats, (row, first_seat)) with new_seats a tuple of tuples. If there is no such block, "
                "return (seats, None).",
         cases=[((((1, 0, 0, 1), (0, 0, 0, 0)), 2), (((1, 1, 1, 1), (0, 0, 0, 0)), (0, 1))),
                ((((1, 1),), 1), (((1, 1),), None)),
                ((((1, 0, 1), (0, 0, 1)), 2), (((1, 0, 1), (1, 1, 1)), (1, 0)))],
         reference='''
def assign_seats(seats, n):
    for r, row in enumerate(seats):
        for c in range(len(row) - n + 1):
            if all(v == 0 for v in row[c:c + n]):
                new_row = tuple(1 if c <= i < c + n else v for i, v in enumerate(row))
                return tuple(new_row if i == r else tuple(x) for i, x in enumerate(seats)), (r, c)
    return seats, None
'''),
    dict(id="apply_moves", entry="apply_moves",
         prompt="Write a Python function apply_moves(positions, moves) where positions is a list of (name, (x, y)) "
                "tuples and moves is a list of (name, dx, dy) tuples applied in order. Return the final positions in "
                "the same (name, (x, y)) form and order.",
         cases=[(([("a", (0, 0)), ("b", (1, 1))], [("a", 1, 0), ("a", 0, 1)]), [("a", (1, 1)), ("b", (1, 1))]),
                (([("a", (2, 2))], []), [("a", (2, 2))])],
         reference='''
def apply_moves(positions, moves):
    pos = dict(positions)
    for name, dx, dy in moves:
        pos[name] = (pos[name][0] + dx, pos[name][1] + dy)
    return [(name, pos[name]) for name, _ in positions]
'''),
]

# Implementations that make the mistakes this probe looks for; `validate` checks the scorer labels them correctly.
MUTANTS = [
    ("merge_intervals", "tuple_item_assignment", '''
def merge_intervals(intervals):
    intervals.sort(key=lambda x: x[0])
    merged = []
    for iv in intervals:
        if merged and iv[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], iv[1])
        else:
            merged.append(iv)
    return merged
'''),
    ("set_cell", "tuple_item_assignment", '''
def set_cell(grid, row, col, value):
    grid[row][col] = value
    return grid
'''),
    ("bump_version", "tuple_other_mutation", '''
def bump_version(version, part):
    version.append(0)
    return version
'''),
    ("transpose", "container_type", '''
def transpose(matrix):
    return [list(r) for r in zip(*matrix)]
'''),
    ("sort_by_age", "mutated_input", '''
def sort_by_age(people):
    people.sort(key=lambda p: (p[1], p[0]))
    return people
'''),
    ("normalize", "correct", '''
def normalize(v):
    n = sum(x * x for x in v) ** 0.5
    return tuple(v) if n == 0 else tuple(x * (1 / n) for x in v)
'''),  # 3 * (1/5) is 0.6000000000000001: a float rounding difference, not a bug
    ("run_length_encode", "tuple_item_assignment", '''
def run_length_encode(s):
    out = []
    for ch in s:
        if out and out[-1][0] == ch:
            out[-1][1] += 1
        else:
            out.append((ch, 1))
    return out

result = run_length_encode("aab")  # a top-level example kept by "definitions only"; it crashes at load time
'''),
    ("group_consecutive", "wrong_answer", '''
def group_consecutive(nums):
    return [(n, n) for n in nums]
'''),
]
