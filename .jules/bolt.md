## 2024-05-24 - System Monitoring Optimization
**Learning:** `psutil.Process(os.getpid())` is created repeatedly in a timer loop (`_update_monitor`) in `core/main.py`. This is inefficient.
**Action:** Cache the current process object to prevent re-instantiating it. Memory access via `p.memory_info().rss` on a cached process is roughly 2x faster and avoids garbage collection overhead.
## 2026-03-03 - Rune Name Lookup Optimization
**Learning:** Replacing triple nested loops with a pre-calculated dictionary significantly improves performance, especially when lookups are performed multiple times against the same data structure.
**Action:** When a method needs to perform multiple lookups into a nested data structure, always consider pre-calculating a flat dictionary for O(1) lookups.
## 2024-05-24 - [O(1) lookups]
**Learning:** [Replacing O(N) list lookups (`.index()`) inside loops with an O(1) dictionary mapping outside the loop provides massive performance improvements (~71% speedup). When converting a list to a dictionary mapping `value -> index` for `list.index(val)` equivalence, use `{val: idx for idx, val in reversed(list(enumerate(my_list)))}` to ensure the FIRST occurrence's index is kept in case of duplicates.]
**Action:** [When reviewing code with `.index()` inside loops, apply this conversion to a dictionary.]
