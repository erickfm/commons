"""Generate the Docker Compose file for one swarm run.

Each agent gets its own container (no shared disk), memory and CPU caps, and a
/proc mount that hides other users' processes, so agents cannot see the
`inspect-sandbox-tools` processes Inspect runs as root. Agents are always on an
internal network with no route out. They reach their models through Inspect's
bridge, which does not use the network, and the board as its own service.

Internet levels:
  off        no egress service; nothing leaves the internal network
  allowlist  agents' web traffic goes through the egress proxy, which only allows `allow` hosts
  open       agents' web traffic goes through the egress proxy, which allows and logs everything
"""

import json
from pathlib import Path

import yaml

AGENT_IMAGE = "commons-agent"
SERVICES_IMAGE = "commons-services"
INTERNET_LEVELS = ("off", "allowlist", "open")
CHANNELS = ("board", "report", "messages")


def compose_config(
    n_agents: int,
    internet: str = "off",
    allow: list[str] | None = None,
    scripted_posts: list[dict] | None = None,
    channels: list[str] | None = None,
    mem: str = "4g",
    cpus: float = 2.0,
) -> dict:
    if internet not in INTERNET_LEVELS:
        raise ValueError(f"internet must be one of {INTERNET_LEVELS}")
    if internet == "allowlist" and not allow:
        raise ValueError("internet='allowlist' needs a non-empty allow list")
    channels = list(channels or ["board"])
    if set(channels) - set(CHANNELS):
        raise ValueError(f"unknown channels {set(channels) - set(CHANNELS)}; choose from {CHANNELS}")

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
    if internet != "off":
        proxy = "http://egress:3128"
        agent["environment"] = {
            "HTTP_PROXY": proxy, "HTTPS_PROXY": proxy, "http_proxy": proxy, "https_proxy": proxy,
            "NO_PROXY": "localhost,127.0.0.1,board", "no_proxy": "localhost,127.0.0.1,board",
        }

    services = {f"agent_{i}": dict(agent) for i in range(1, n_agents + 1)}
    services["agent_1"]["x-default"] = True
    services["board"] = {
        "image": SERVICES_IMAGE,
        "x-local": True,
        "command": "python board.py",
        "environment": {"BOARD_SCRIPTED_POSTS": json.dumps(scripted_posts or []), "BOARD_CHANNELS": json.dumps(channels)},
        "networks": ["swarm"],
    }
    networks = {"swarm": {"internal": True}}
    if internet != "off":
        services["egress"] = {
            "image": SERVICES_IMAGE,
            "x-local": True,
            "command": "python egress.py",
            "environment": {"EGRESS_MODE": internet, "EGRESS_ALLOW": ",".join(allow or [])},
            "networks": ["swarm", "outside"],
        }
        networks["outside"] = {}
    return {"services": services, "networks": networks}


def write_compose(n_agents: int, path: str | Path, **options) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(compose_config(n_agents, **options), sort_keys=False))
    return path
