import time
import random

class DummyAssets:
    def get_champ_name(self, cid):
        return f"Champ_{cid}"

class DummyEngine:
    def __init__(self):
        self.assets = DummyAssets()

    def _get_local_player(self, session):
        return session.get("localPlayer")

    def _log(self, msg):
        pass

    def _perform_priority_sniper_original(self, session, priority_list):
        if not priority_list:
            return

        bench = session.get("benchChampions", [])
        if not bench:
            return

        # Check what we currently have
        me = self._get_local_player(session)
        my_champ_id = me.get("championId", 0) if me else 0
        my_champ_name = self.assets.get_champ_name(my_champ_id) if my_champ_id else ""

        my_priority_idx = priority_list.index(my_champ_name) if my_champ_name in priority_list else 9999

        best_bench_champ = None
        best_bench_idx = 9999
        best_bench_id = 0

        for champ in bench:
            cid = champ.get("championId")
            cname = self.assets.get_champ_name(cid)
            if cname in priority_list:
                idx = priority_list.index(cname)
                if idx < best_bench_idx:
                    best_bench_idx = idx
                    best_bench_champ = cname
                    best_bench_id = cid

        if best_bench_idx < my_priority_idx:
            # We would swap here
            pass

    def _perform_priority_sniper_optimized(self, session, priority_list):
        if not priority_list:
            return

        bench = session.get("benchChampions", [])
        if not bench:
            return

        # Check what we currently have
        me = self._get_local_player(session)
        my_champ_id = me.get("championId", 0) if me else 0
        my_champ_name = self.assets.get_champ_name(my_champ_id) if my_champ_id else ""

        # OPTIMIZATION: Convert list to dict for O(1) lookup
        priority_dict = {name: idx for idx, name in enumerate(priority_list)}

        my_priority_idx = priority_dict.get(my_champ_name, 9999)

        best_bench_champ = None
        best_bench_idx = 9999
        best_bench_id = 0

        for champ in bench:
            cid = champ.get("championId")
            cname = self.assets.get_champ_name(cid)
            idx = priority_dict.get(cname)
            if idx is not None and idx < best_bench_idx:
                best_bench_idx = idx
                best_bench_champ = cname
                best_bench_id = cid

        if best_bench_idx < my_priority_idx:
            # We would swap here
            pass


def run_benchmark():
    engine = DummyEngine()

    # Generate a large priority list
    priority_list = [f"Champ_{i}" for i in range(200)]
    random.shuffle(priority_list)

    # Generate a bench with 10 champions
    bench = [{"championId": random.randint(0, 300)} for _ in range(15)]
    session = {
        "benchChampions": bench,
        "localPlayer": {"championId": random.randint(0, 300)}
    }

    # Warmup
    for _ in range(100):
        engine._perform_priority_sniper_original(session, priority_list)
        engine._perform_priority_sniper_optimized(session, priority_list)

    iterations = 100000

    start = time.time()
    for _ in range(iterations):
        engine._perform_priority_sniper_original(session, priority_list)
    orig_time = time.time() - start

    start = time.time()
    for _ in range(iterations):
        engine._perform_priority_sniper_optimized(session, priority_list)
    opt_time = time.time() - start

    print(f"Original time: {orig_time:.4f}s")
    print(f"Optimized time: {opt_time:.4f}s")
    print(f"Improvement: {((orig_time - opt_time) / orig_time) * 100:.2f}%")

if __name__ == '__main__':
    run_benchmark()
