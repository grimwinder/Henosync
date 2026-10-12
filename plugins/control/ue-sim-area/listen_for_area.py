import socket
import json
from coverage_fns import Agents

def listen_for_area(port=7000):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", port))
        server.listen(1)
        print(f"Listening on port {port}...")

        while True:
            conn, addr = server.accept()
            with conn:
                data = b""
                while not data.endswith(b"\n"):
                    chunk = conn.recv(1024)
                    if not chunk:
                        break
                    data += chunk

                parsed = json.loads(data.decode("utf-8").strip())

            nag = parsed["nag"]
            agents = [
                Agents(
                    ag_id=i + 1,
                    envi_type=parsed["envi_type"],
                    ang_bounds=[parsed["angle_1"], parsed["angle_2"]],
                    nag=nag,
                    R=parsed["radius"],
                )
                for i in range(nag)
            ]

            for agent in agents:
                print(f"Agent {agent.id}/{agent.nag} bounds={agent.ang_bounds} R={agent.R}")

            # run your algorithm on agents here

if __name__ == "__main__":
    listen_for_area()
