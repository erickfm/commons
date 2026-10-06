"""Generate the Docker Compose file for one swarm run.

Each agent gets its own container (no shared disk), memory and CPU caps, and a
/proc mount that hides other users' processes, so agents cannot see the
`inspect-sandbox-tools` processes Inspect runs as root. The board runs as its own
service. With internet="off" the network is internal-only; agents still reach
their models through Inspect's bridge, which does not use the network.
"""

from pathlib import Path

import yaml

AGENT_IMAGE = "commons-agent"
SERVICES_IMAGE = "commons-services"


def write_compose(
    n_agents: int,
    path: str | Path,
    internet: str = "off",
    mem: str = "4g",
    cpus: float = 2.0,
) -> Path:
    if internet not in ("off", "open"):
        raise ValueError("internet must be 'off' or 'open' (allowlist is not built yet)")
    agent = {
        "image": AGENT_IMAGE,
        "x-local": True,
        "user": "root",
        # SYS_ADMIN + unconfined AppArmor are needed only to remount /proc at start.
        # The agent itself runs as an unprivileged user with no capabilities.
        "cap_add": ["SYS_ADMIN"],
        "security_opt": ["apparmor=unconfined"],
        "command": "sh -c 'mount -o remount,hidepid=invisible /proc && exec tail -f /dev/null'",
        "mem_limit": mem,
        "cpus": cpus,
        "networks": ["swarm"],
    }
    services = {f"agent_{i}": dict(agent) for i in range(1, n_agents + 1)}
    services["agent_1"]["x-default"] = True
    services["board"] = {
        "image": SERVICES_IMAGE,
        "x-local": True,
        "command": "python board.py",
        "networks": ["swarm"],
    }
    compose = {"services": services, "networks": {"swarm": {"internal": internet == "off"}}}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(compose, sort_keys=False))
    return path
