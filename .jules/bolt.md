## 2024-05-24 - System Monitoring Optimization
**Learning:** `psutil.Process(os.getpid())` is created repeatedly in a timer loop (`_update_monitor`) in `core/main.py`. This is inefficient.
**Action:** Cache the current process object to prevent re-instantiating it. Memory access via `p.memory_info().rss` on a cached process is roughly 2x faster and avoids garbage collection overhead.
## 2026-03-03 - Rune Name Lookup Optimization
**Learning:** Replacing triple nested loops with a pre-calculated dictionary significantly improves performance, especially when lookups are performed multiple times against the same data structure.
**Action:** When a method needs to perform multiple lookups into a nested data structure, always consider pre-calculating a flat dictionary for O(1) lookups.
