import asyncio, random, threading
from .gossip import Gossip
from .node import Node

def start_node_thread(node, stop_event):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(node.run(stop_event))
    except asyncio.CancelledError:
        pass
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        for task in asyncio.all_tasks(loop):
            task.cancel()
        try:
            loop.run_until_complete(asyncio.gather(*asyncio.all_tasks(loop), return_exceptions=True))
        except:
            pass
        loop.close()


def main():
    net = Gossip()
    nodes_info = [("A", 2), ("B", 1), ("C", 1), ("D", 1)]
    for pid, _ in nodes_info:
        net.register(pid)

    power = {pid: vp for pid, vp in nodes_info}
    nodes = [Node(pid, vp, net, [p for p, _ in nodes_info], power) for pid, vp in nodes_info]

    stop_event = threading.Event()
    threads = []
    for node in nodes:
        t = threading.Thread(target=start_node_thread, args=(node, stop_event), daemon=True)
        t.start()
        threads.append(t)

    try:
        asyncio.run(asyncio.sleep(10))
    finally:
        stop_event.set()  # signal za graceful shutdown
        print("\n=== Simulation finished ===")
        for t in threads:
            t.join(timeout=1)

if __name__ == "__main__":
    main()