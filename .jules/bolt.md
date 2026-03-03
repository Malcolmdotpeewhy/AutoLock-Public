## 2024-05-24 - System Monitoring Optimization
**Learning:** `psutil.Process(os.getpid())` is created repeatedly in a timer loop (`_update_monitor`) in `core/main.py`. This is inefficient.
**Action:** Cache the current process object to prevent re-instantiating it. Memory access via `p.memory_info().rss` on a cached process is roughly 2x faster and avoids garbage collection overhead.
