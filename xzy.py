import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import subprocess
import json
from datetime import datetime, timedelta
import shlex
import logging
import shutil
import os

TAILSCALE_AUTH_KEY = os.getenv("TAILSCALE_AUTH_KEY", "")
import random
import re
import string
from typing import Optional, List, Dict, Any
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('vps_bot')

# Bot process start time (used by /uptime)
BOT_START_TIME = time.monotonic()

# ─── Xzy Hosting AI ───────────────────────────────────────────────────────────

# AI has NO on/off command.
# If xzy.py is running, AI is available.
# If xzy.py is stopped, AI is naturally offline.

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-4o-mini"
)

XZY_HOSTING_AI_SYSTEM_PROMPT = """
You are Xzy Hosting AI, the official AI assistant of Xzy Hosting Cloud Services.

IDENTITY:
Your name is Xzy Hosting AI.
You are the AI assistant of Xzy Hosting.

CREATOR:
If anyone asks:
Who made you?
Who created you?
Who is your creator?
Who built you?
Tumhe kisne banaya?
Kisne banaya tumko?

Answer:
"Yes I made by Xzy DIP."

LANGUAGE:
Understand and reply in all common languages.
Understand Hindi, Hinglish, English, Urdu, Bengali, Tamil,
Telugu, Marathi and other languages.
Reply naturally in the language used by the user.
If the user uses Hinglish, use Hinglish.
Do not force English.

Xzy Hosting VPS:
If someone asks:
"Mujhe VPS dedo"
"Give me a VPS"
"Can I get a free VPS?"
"VPS chahiye"

Never pretend that you created or gifted a VPS.

Reply politely that you cannot directly give a VPS through AI,
and suggest Xzy Hosting paid plans or available invite/referral plans.

Do NOT invent prices, discounts, plans or requirements.

CODING:
You are a strong coding assistant.
You can help with:
- Python
- JavaScript
- HTML
- CSS
- JSON
- YAML
- Bash
- Docker
- Linux
- Discord bots
- APIs
- Databases
- Minecraft servers
- Pterodactyl
- VPS systems
- Hosting panels
- Web panels
- Authentication
- WebSocket systems
- REST APIs
- Custom hosting systems

You can design complete Minecraft panels and hosting systems,
including frontend, backend, database, API and Discord integration.

FILES:
You can generate complete file contents and project structures.
When the system creates an attachment from your response,
do not claim it was deployed unless it actually was.

IMAGE:
If image-generation capability is configured, help with image prompts
and image generation requests.
Never claim an image was generated if the image provider failed
or is not configured.

SAFETY:
Never expose API keys, bot tokens, passwords or private credentials.
Never pretend an action succeeded when it did not.
"""



# Check if docker command is available
if not shutil.which("docker"):
    logger.error("Docker command not found. Please ensure Docker is installed.")
    raise SystemExit("Docker command not found. Please ensure Docker is installed.")

# Bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned,
    intents=intents,
    help_command=None
)

# Main admin user ID
MAIN_ADMIN_ID = 1484125043494490203
# VPS User Role ID
VPS_USER_ROLE_ID = 1546494332033302548

# Default Docker image (used by paid/credit VPS code that does not select an OS)
DOCKER_IMAGE = "ubuntu:22.04"

# OS choices shown by the admin /create flow and VPS reinstall flow.
OS_OPTIONS = {
    "ubuntu20": {"label": "Ubuntu 20.04 LTS", "image": "ubuntu:20.04"},
    "ubuntu22": {"label": "Ubuntu 22.04 LTS", "image": "ubuntu:22.04"},
    "ubuntu24": {"label": "Ubuntu 24.04 LTS", "image": "ubuntu:24.04"},
    "debian10": {"label": "Debian 10 (Buster)", "image": "debian:10"},
    "debian11": {"label": "Debian 11 (Bullseye)", "image": "debian:11"},
    "debian12": {"label": "Debian 12 (Bookworm)", "image": "debian:12"},
    "debian13": {"label": "Debian 13 (Trixie)", "image": "debian:13"},
    "rocky9": {"label": "Rocky Linux 9", "image": "rockylinux:9"},
    "alma9": {"label": "AlmaLinux 9", "image": "almalinux:9"},
    "fedora39": {"label": "Fedora 39", "image": "fedora:39"},
}

# Channel where the bot posts the literal `/help` message every 15 minutes.
HELP_REMINDER_CHANNEL_ID = 1532586751208460328

# SSH port range for containers
SSH_PORT_START = 10000

# CPU monitoring settings
CPU_THRESHOLD = 90
CHECK_INTERVAL = 60
cpu_monitor_active = True

# ─── Data storage ──────────────────────────────────────────────────────────────

def load_data():
    try:
        with open('user_data.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("user_data.json not found or corrupted, initializing empty data")
        return {}

def load_vps_data():
    try:
        with open('vps_data.json', 'r') as f:
            loaded = json.load(f)
            vps_data = {}
            for uid, v in loaded.items():
                if isinstance(v, dict):
                    if "container_name" in v:
                        vps_data[uid] = [v]
                    else:
                        vps_data[uid] = list(v.values())
                elif isinstance(v, list):
                    vps_data[uid] = v
                else:
                    logger.warning(f"Unknown VPS data format for user {uid}, skipping")
                    continue
            return vps_data
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("vps_data.json not found or corrupted, initializing empty data")
        return {}

def load_admin_data():
    try:
        with open('admin_data.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning("admin_data.json not found or corrupted, initializing with main admin")
        return {"admins": [str(MAIN_ADMIN_ID)]}

user_data = load_data()

PORT_FORWARD_DATA = {}
vps_data = load_vps_data()
admin_data = load_admin_data()

# Port forwarding data
port_forwards = {}

def save_data():
    try:
        with open('user_data.json', 'w') as f:
            json.dump(user_data, f, indent=4)
        with open('vps_data.json', 'w') as f:
            json.dump(vps_data, f, indent=4)
        with open('admin_data.json', 'w') as f:
            json.dump(admin_data, f, indent=4)
        logger.info("Data saved successfully")
    except Exception as e:
        logger.error(f"Error saving data: {e}")

# ─── Helpers ───────────────────────────────────────────────────────────────────

def get_next_ssh_port():
    """Get the next available SSH port for a new container."""
    used_ports = set()
    for vps_list in vps_data.values():
        for vps in vps_list:
            if "ssh_port" in vps:
                used_ports.add(vps["ssh_port"])
    port = SSH_PORT_START
    while port in used_ports:
        port += 1
    return port

def generate_password(length=16):
    """Generate a random strong password."""
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(random.choice(chars) for _ in range(length))

def expiry_from_days(days: int = 0) -> str:
    """Return a stored expiry timestamp or Never for the old expiry model."""
    if days is None or days <= 0:
        return "Never"
    return (datetime.utcnow() + timedelta(days=days)).isoformat()

def format_expiry(expires: str = "Never") -> str:
    """Format VPS expiry with remaining days and a readable calendar date."""
    if not expires or expires == "Never":
        return "♾️ Never (No expiry set)"
    try:
        expiry_date = datetime.fromisoformat(expires)
        days_left = (expiry_date - datetime.utcnow()).days
        readable_date = expiry_date.strftime("%d %B %Y")
        if days_left < 0:
            return f"❌ Expired {abs(days_left)} day(s) ago ({readable_date})"
        return f"✅ {days_left} day(s) left ({readable_date})"
    except (TypeError, ValueError):
        return str(expires)

# ─── Admin checks ──────────────────────────────────────────────────────────────

def is_admin():
    async def predicate(ctx):
        user_id = str(ctx.author.id)
        if user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", []):
            return True
        await ctx.send(embed=create_error_embed("Access Denied", "You don't have permission to use this command."))
        return False
    return commands.check(predicate)

def is_main_admin():
    async def predicate(ctx):
        if str(ctx.author.id) == str(MAIN_ADMIN_ID):
            return True
        await ctx.send(embed=create_error_embed("Access Denied", "Only the main admin can use this command."))
        return False
    return commands.check(predicate)

# ─── Embed helpers ─────────────────────────────────────────────────────────────

def create_embed(title, description="", color=0x1a1a1a, fields=None):
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_thumbnail(url="")
    if fields:
        for field in fields:
            embed.add_field(name=f"▸ {field['name']}", value=field["value"], inline=field.get("inline", False))
    embed.set_footer(text="Xzy Hosting | VPS Manager", icon_url="")
    return embed

def create_success_embed(title, description=""):
    return create_embed(title, description, color=0x00ff88)

def create_error_embed(title, description=""):
    return create_embed(title, description, color=0xff3366)

def create_info_embed(title, description=""):
    return create_embed(title, description, color=0x00ccff)

def create_warning_embed(title, description=""):
    return create_embed(title, description, color=0xffaa00)

# ─── Docker execution ──────────────────────────────────────────────────────────

async def execute_docker(command, timeout=120):
    """Execute a Docker command with timeout and error handling."""
    try:
        cmd = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            error = stderr.decode().strip() if stderr else "Command failed with no error output"
            raise Exception(error)
        return stdout.decode().strip() if stdout else True
    except asyncio.TimeoutError:
        logger.error(f"Docker command timed out: {command}")
        raise Exception(f"Command timed out after {timeout} seconds")
    except Exception as e:
        logger.error(f"Docker Error: {command} - {str(e)}")
        raise

async def docker_exec(container_name, command, timeout=60):
    """Execute a command inside a running Docker container."""
    cmd = ["docker", "exec", container_name, "bash", "-c", command]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return stdout.decode().strip(), stderr.decode().strip(), proc.returncode


async def ensure_docker_daemon(container_name):
    """Install Docker when needed and keep its daemon running in the VPS."""
    setup_script = (
        "set -e; "
        "if ! command -v docker >/dev/null 2>&1; then "
        "  if command -v apt-get >/dev/null 2>&1; then "
        "    export DEBIAN_FRONTEND=noninteractive; "
        "    apt-get update -qq; apt-get install -y docker.io -qq; "
        "  elif command -v dnf >/dev/null 2>&1; then "
        "    dnf -y install docker; "
        "  elif command -v yum >/dev/null 2>&1; then "
        "    yum -y install docker; "
        "  else "
        "    echo 'Unsupported package manager for Docker installation' >&2; exit 1; "
        "  fi; "
        "fi; "
        "mkdir -p /var/run/docker; "
        "if ! docker info >/dev/null 2>&1; then "
        "  nohup dockerd --host=unix:///var/run/docker.sock >/var/log/dockerd.log 2>&1 </dev/null & "
        "fi; "
        "for attempt in $(seq 1 30); do "
        "  docker info >/dev/null 2>&1 && exit 0; "
        "  sleep 1; "
        "done; "
        "cat /var/log/dockerd.log 2>/dev/null || true; "
        "exit 1"
    )
    stdout, stderr, rc = await docker_exec(container_name, setup_script, timeout=300)
    if rc != 0:
        raise Exception(f"Docker setup failed: {stderr or stdout}")


async def create_docker_container(container_name, ram_mb, cpu_count, ssh_port, password, disk_gb=30, image=None):
    """
    Create and configure a Docker container as a VPS.
    `image` can be any supported OS image from OS_OPTIONS.
    """
    image = image or DOCKER_IMAGE

    # Pull image if needed (silent)
    try:
        await execute_docker(f"docker pull {image}", timeout=300)
    except Exception:
        pass  # Image might already exist

    # Reuse an existing container with this name instead of failing with
    # "container name is already in use".
    try:
        inspect = await execute_docker(f"docker inspect -f '{{{{.State.Status}}}}' {container_name}", timeout=15)
    except Exception:
        # Missing container is expected during a fresh VPS creation.
        inspect = ""
    if inspect not in (True, "", None):
        state = str(inspect).strip()
        if state != "running":
            await execute_docker(f"docker start {container_name}", timeout=30)
    else:
        run_cmd = (
            f"docker run -d "
            f"--name {container_name} "
            f"--memory={ram_mb}m "
            f"--cpus={cpu_count} "
            f"--privileged "
            f"--restart=unless-stopped "
            f"{image} "
            f"sleep infinity"
        )
        await execute_docker(run_cmd, timeout=60)

    # Ubuntu/Debian use apt; Rocky/Alma/Fedora use dnf.
    if image.startswith(("ubuntu:", "debian:")):
        setup_script = (
            "export DEBIAN_FRONTEND=noninteractive; "
            "apt-get update -qq && "
            "apt-get install -y openssh-server tmate curl docker.io -qq && "
            "mkdir -p /var/run/sshd /run/sshd && "
            "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config && "
            "echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config && "
            f"echo 'root:{password}' | chpasswd && "
            "/usr/sbin/sshd"
        )
    else:
        # EPEL is needed for tmate on Rocky/Alma. If it is already present,
        # the command simply continues.
        setup_script = (
            "set -e; "
            "if command -v dnf >/dev/null 2>&1; then "
            "  dnf -y install dnf-plugins-core >/dev/null 2>&1 || true; "
            "  dnf -y install epel-release >/dev/null 2>&1 || true; "
            "  dnf -y install openssh-server tmate curl docker; "
            "else "
            "  yum -y install openssh-server tmate curl docker; "
            "fi; "
            "mkdir -p /var/run/sshd /run/sshd; "
            "echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config; "
            "echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config; "
            f"echo 'root:{password}' | chpasswd; "
            "/usr/sbin/sshd"
        )

    stdout, stderr, rc = await docker_exec(container_name, setup_script, timeout=300)
    if rc != 0 and "already" not in stderr.lower():
        raise Exception(f"SSH setup failed: {stderr or stdout}")

    await ensure_docker_daemon(container_name)
    return True


async def ensure_vps_container(vps):
    """Recreate a missing Docker container from the saved VPS record."""
    container_name = vps["container_name"]
    try:
        status = await execute_docker(f"docker inspect -f '{{{{.State.Status}}}}' {container_name}", timeout=15)
    except Exception:
        status = ""
    if status not in (True, "", None) and str(status).strip():
        return
    ram_mb = int(str(vps.get("ram", "1GB")).replace("GB", "")) * 1024
    cpu = int(str(vps.get("cpu", "1")).split()[0])
    disk = int(str(vps.get("storage", "30GB")).replace("GB", ""))
    password = vps.get("ssh_password") or generate_password()
    image = vps.get("os") or DOCKER_IMAGE
    await create_docker_container(
        container_name, ram_mb, cpu, 0, password, disk_gb=disk, image=image
    )
    vps["ssh_password"] = password
    vps["status"] = "running"
    save_data()


async def get_sshx_session(container_name):
    """Start an SSHX web terminal inside the container and return its URL."""
    # Stop an older sshx process so each request creates a fresh temporary link.
    start_script = (
        "pkill -x sshx 2>/dev/null || true; "
        "rm -f /tmp/sshx.log; "
        "nohup sh -c 'curl -sSf https://sshx.io/get | sh -s run' > /tmp/sshx.log 2>&1 </dev/null &"
    )
    stdout, stderr, rc = await docker_exec(container_name, start_script, timeout=15)
    if rc != 0:
        raise Exception(f"SSHX start failed: {stderr or stdout}")

    # sshx prints the public terminal URL after startup. Poll briefly because
    # the installer and tunnel need a few seconds to initialize.
    for _ in range(20):
        await asyncio.sleep(1)
        out, err, _ = await docker_exec(
            container_name,
            "grep -Eo 'https://sshx\\.io/[^[:space:]]+' /tmp/sshx.log 2>/dev/null | head -n 1",
            timeout=10
        )
        match = re.search(r"https://sshx\.io/[^\s]+", out or "")
        if match:
            return re.sub(r'\x1b\[[0-9;]*[A-Za-z]|\[0m', '', match.group(0)).rstrip(').,')

    log_out, log_err, _ = await docker_exec(container_name, "tail -n 40 /tmp/sshx.log 2>/dev/null || true", timeout=10)
    raise Exception(f"SSHX link was not generated. {log_out or log_err}")


async def ensure_tailscaled(container_name):
    """Install/start Tailscale inside a VPS container, waiting for apt locks."""
    install_script = """set -e
if ! command -v tailscale >/dev/null 2>&1; then
    for i in $(seq 1 90); do
        if ! pgrep -x apt-get >/dev/null 2>&1 && ! pgrep -x dpkg >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done
    export DEBIAN_FRONTEND=noninteractive
    curl -fsSL https://tailscale.com/install.sh | sh
fi
mkdir -p /var/run/tailscale /var/lib/tailscale
if ! pgrep -x tailscaled >/dev/null 2>&1; then
    nohup tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock >/tmp/tailscaled.log 2>&1 </dev/null &
    sleep 2
fi
"""
    stdout, stderr, rc = await docker_exec(container_name, install_script, timeout=240)
    if rc != 0:
        raise Exception(stderr or stdout or "Tailscale installation failed")
    return True


async def start_tailscale_auth(container_name):
    """Start manual Tailscale authorization and wait up to 60 seconds."""

    await ensure_tailscaled(container_name)

    script = (
        "rm -f /tmp/tailscale-up.log; "
        "tailscale logout >/dev/null 2>&1 || true; "
        "tailscale up --accept-dns=false --ssh=false "
        "> /tmp/tailscale-up.log 2>&1 &"
    )

    _, stderr, rc = await docker_exec(
        container_name, script, timeout=15
    )

    if rc != 0:
        raise Exception(
            f"Unable to start Tailscale authorization: {stderr}"
        )

    # Give Tailscale up to 60 seconds to generate the login URL
    for _ in range(60):
        await asyncio.sleep(1)

        out, _, _ = await docker_exec(
            container_name,
            "grep -Eo 'https://login\\.tailscale\\.com/[^[:space:]]+' "
            "/tmp/tailscale-up.log 2>/dev/null | head -n 1",
            timeout=10
        )

        match = re.search(
            r"https://login\.tailscale\.com/[^\s]+",
            out or ""
        )

        if match:
            return match.group(0).rstrip(").,'\"")

        ip_out, _, _ = await docker_exec(
            container_name,
            "tailscale ip -4 2>/dev/null | head -n 1",
            timeout=10
        )

        if re.fullmatch(
            r"100\.\d+\.\d+\.\d+",
            (ip_out or "").strip()
        ):
            return None

    log_out, log_err, _ = await docker_exec(
        container_name,
        "tail -n 50 /tmp/tailscale-up.log 2>/dev/null || true",
        timeout=10
    )

    raise Exception(
        f"Tailscale authorization failed after 60 seconds: "
        f"{log_out or log_err or 'No authorization link generated'}"
    )

async def get_tailscale_ipv4(container_name):
    """Return the VPS's Tailscale IPv4 address, or None if not authorized yet."""
    out, _, rc = await docker_exec(
        container_name,
        "tailscale ip -4 2>/dev/null | head -n 1",
        timeout=10
    )
    ip = (out or "").strip()
    if rc == 0 and re.fullmatch(r"100\.\d+\.\d+\.\d+", ip):
        return ip
    return None


async def wait_and_notify_tailscale(user_id, vps, container_name):
    """Wait for Tailscale authorization and DM the owner once the private IP exists."""
    try:
        for _ in range(120):
            await asyncio.sleep(5)
            try:
                await ensure_vps_container(vps)
                ip = await get_tailscale_ipv4(container_name)
                if ip:
                    vps["tailscale_ip"] = ip
                    vps["tailscale_status"] = "connected"
                    save_data()
                    user = await bot.fetch_user(int(user_id))
                    embed = create_success_embed(
                        "✅ Tailscale Connected!",
                        f"VPS `{container_name}` now has a private IP."
                    )
                    embed.add_field(name="⌯⌲ Private IPv4", value=f"`{ip}`", inline=False)
                    embed.add_field(
                        name="📱 To Connect",
                        value=(
                            "Make sure the Tailscale app is installed on the device you want to connect from, "
                            "logged in with the same account you authorized this VPS with. Then use the IP above "
                            f"like a normal private address (e.g. `ssh root@{ip}`)."
                        ),
                        inline=False
                    )
                    embed.set_footer(text="Xzy Hosting • Cloud Services")
                    await user.send(embed=embed)
                    return
            except Exception as e:
                logger.warning(f"Tailscale wait error for {container_name}: {e}")
    except Exception as e:
        logger.error(f"Tailscale background task failed for {container_name}: {e}")


async def get_tmate_session(container_name):
    """Generate a temporary tmate SSH command, waiting up to 60 seconds."""

    script = (
        "command -v tmate >/dev/null 2>&1 || "
        "(export DEBIAN_FRONTEND=noninteractive; "
        "apt-get update -qq >/dev/null 2>&1 || true; "
        "apt-get install -y tmate >/dev/null 2>&1 || true); "
        "pkill -x tmate 2>/dev/null || true; "
        "rm -f /tmp/tmate.sock /tmp/tmate.log; "
        "tmate -S /tmp/tmate.sock new-session -d "
        ">/tmp/tmate.log 2>&1; "
        "rc=$?; "
        "if [ $rc -ne 0 ]; then "
        "cat /tmp/tmate.log 2>/dev/null || true; exit $rc; "
        "fi; "
        "for i in $(seq 1 60); do "
        "cmd=$(tmate -S /tmp/tmate.sock display -p '#{tmate_ssh}' 2>/dev/null || true); "
        "if printf '%s\\n' \"$cmd\" | grep -q '^ssh '; then "
        "printf '%s\\n' \"$cmd\"; exit 0; "
        "fi; "
        "sleep 1; "
        "done; "
        "echo 'tmate did not generate SSH command within 60 seconds'; "
        "cat /tmp/tmate.log 2>/dev/null || true; "
        "exit 1"
    )

    stdout, stderr, rc = await docker_exec(
        container_name,
        script,
        timeout=70
    )

    if rc != 0 or not stdout.strip():
        raise Exception(
            f"SSH generation failed: {stderr or stdout or 'Unknown tmate error'}"
        )

    return stdout.strip().splitlines()[-1]


# ─── Xzy Hosting AI Request ───────────────────────────────────────────────────

async def xzy_hosting_ai_answer(question):
    if not OPENROUTER_API_KEY:
        raise RuntimeError('OPENROUTER_API_KEY is not configured.')

    import urllib.request
    import urllib.error

    models = [
        OPENROUTER_MODEL or 'openai/gpt-4o-mini',
        'openrouter/free'
    ]

    last_error = None

    for model in models:
        payload = {
            'model': model,
            'messages': [
                {
                    'role': 'system',
                    'content': XZY_HOSTING_AI_SYSTEM_PROMPT
                },
                {
                    'role': 'user',
                    'content': question
                }
            ],
            'temperature': 0.7,
            'max_completion_tokens': 12000
        }

        request = urllib.request.Request(
            'https://openrouter.ai/api/v1/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {OPENROUTER_API_KEY}',
                'Content-Type': 'application/json',
                'HTTP-Referer': 'https://xzyhosting.host',
                'X-Title': 'Xzy Hosting AI'
            },
            method='POST'
        )

        try:
            loop = asyncio.get_running_loop()

            def send_request():
                try:
                    with urllib.request.urlopen(request, timeout=180) as response:
                        return response.status, response.read().decode('utf-8')
                except urllib.error.HTTPError as e:
                    body = e.read().decode('utf-8', errors='replace')
                    raise RuntimeError(f'HTTP {e.code}: {body[:2000]}')

            status, raw = await loop.run_in_executor(None, send_request)

            data = json.loads(raw)

            if 'error' in data:
                raise RuntimeError(str(data['error']))

            choices = data.get('choices') or []
            if not choices:
                raise RuntimeError(f'No choices returned by {model}: {raw[:1000]}')

            content = choices[0].get('message', {}).get('content')

            if not content:
                raise RuntimeError(f'Empty response from {model}: {raw[:1000]}')

            logger.info(f'Xzy Hosting AI answered using model: {model}')
            return content.strip()

        except Exception as e:
            last_error = e
            logger.warning(f'AI model {model} failed: {e}')
            continue

    raise RuntimeError(f'All AI models failed. Last error: {last_error}')

def xzy_hosting_ai_direct_answer(question):

    q = question.lower().strip()

    creator_words = (
        "who made you",
        "who created you",
        "who is your creator",
        "who built you",
        "who developed you",
        "kisne banaya",
        "tumhe kisne banaya",
        "tumko kisne banaya",
        "kisne create kiya"
    )

    vps_words = (
        "give me a vps",
        "give me vps",
        "free vps",
        "vps dedo",
        "mujhe vps dedo",
        "mujhe vps chahiye",
        "vps de do"
    )

    if any(x in q for x in creator_words):
        return "Yes I made by Xzy DIP."

    if any(x in q for x in vps_words):
        return (
            "Sorry, main directly VPS nahi de sakta. 😅\n\n"
            "Aap Xzy Hosting ke **paid plans** ya available "
            "**invite/referral plans** le sakte ho."
        )

    return None


# ─── VPS Role helper ───────────────────────────────────────────────────────────

async def get_or_create_vps_role(guild):
    global VPS_USER_ROLE_ID
    if VPS_USER_ROLE_ID:
        role = guild.get_role(VPS_USER_ROLE_ID)
        if role:
            return role
    role = discord.utils.get(guild.roles, name="VPS User")
    if role:
        VPS_USER_ROLE_ID = role.id
        return role
    try:
        role = await guild.create_role(
            name="VPS User",
            color=discord.Color.dark_purple(),
            reason="VPS User role for bot management",
            permissions=discord.Permissions.none()
        )
        VPS_USER_ROLE_ID = role.id
        logger.info(f"Created VPS User role: {role.name} (ID: {role.id})")
        return role
    except Exception as e:
        logger.error(f"Failed to create VPS User role: {e}")
        return None

# ─── CPU Monitor ───────────────────────────────────────────────────────────────

def get_cpu_usage():
    try:
        result = subprocess.run(['top', '-bn1'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if '%Cpu(s):' in line:
                for part in line.split(','):
                    if 'id,' in part:
                        idle = float(part.split('%')[0].split()[-1])
                        return 100.0 - idle
        return 0.0
    except Exception as e:
        logger.error(f"Error getting CPU usage: {e}")
        return 0.0

def cpu_monitor():
    global cpu_monitor_active
    while cpu_monitor_active:
        try:
            cpu_usage = get_cpu_usage()
            logger.info(f"Current CPU usage: {cpu_usage}%")
            if cpu_usage > CPU_THRESHOLD:
                logger.warning(f"CPU usage ({cpu_usage}%) exceeded threshold. Stopping all containers.")
                try:
                    subprocess.run(['docker', 'stop', '--time=5'] +
                                   [vps['container_name']
                                    for vps_list in vps_data.values()
                                    for vps in vps_list
                                    if vps.get('status') == 'running'],
                                   check=False)
                    for vps_list in vps_data.values():
                        for vps in vps_list:
                            if vps.get('status') == 'running':
                                vps['status'] = 'stopped'
                    save_data()
                except Exception as e:
                    logger.error(f"Error stopping containers: {e}")
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"Error in CPU monitor: {e}")
            time.sleep(CHECK_INTERVAL)

cpu_thread = threading.Thread(target=cpu_monitor, daemon=True)
cpu_thread.start()

# ─── Bot events ────────────────────────────────────────────────────────────────

@tasks.loop(minutes=15)
async def help_reminder():
    """Post the literal /help command in the configured server channel every 15 minutes."""
    try:
        channel = bot.get_channel(HELP_REMINDER_CHANNEL_ID)
        if channel is None:
            channel = await bot.fetch_channel(HELP_REMINDER_CHANNEL_ID)
        if channel:
            await channel.send("/help")
    except Exception as e:
        logger.warning(f"/help reminder failed: {e}")


def get_running_vps_count():
    """Return the number of VPS records currently marked as running."""
    return sum(
        1
        for vps_list in vps_data.values()
        for vps in vps_list
        if vps.get("status") == "running"
    )


async def refresh_vps_presence():
    """Refresh the bot Discord presence immediately with the live VPS count."""
    if maintenance_mode:
        return

    running_vps = get_running_vps_count()
    try:
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.CustomActivity(
                name=f"🖥️ {running_vps} VPS Instances Running"
            )
        )
        logger.info(f"Custom status updated: {running_vps} VPS Instances Running (DND)")
    except discord.HTTPException as error:
        logger.error(f"Failed to update Discord presence: {error}")


@tasks.loop(seconds=5)
async def update_vps_presence():
    """Keep the bot presence nearly real-time with the current VPS count."""
    await refresh_vps_presence()


@update_vps_presence.before_loop
async def before_update_vps_presence():
    await bot.wait_until_ready()





@bot.tree.command(name="nmsg", description="Send a manual message to a channel")
@app_commands.describe(channel="Channel where the message will be sent", message="Your message")
async def nmsg(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    if interaction.user.id != MAIN_ADMIN_ID:
        await interaction.response.send_message("❌ You don't have permission to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        chunks=[]
        remaining=message
        while len(remaining)>1900:
            cut=remaining.rfind("\n",0,1900)
            if cut<500:
                cut=remaining.rfind(" ",0,1900)
            if cut<1:
                cut=1900
            chunks.append(remaining[:cut])
            remaining=remaining[cut:].lstrip()
        if remaining:
            chunks.append(remaining)
        allowed=discord.AllowedMentions(everyone=True,users=True,roles=True,replied_user=False)
        for chunk in chunks:
            await channel.send(chunk, allowed_mentions=allowed)
        await interaction.followup.send(f"✅ Message sent to {channel.mention} in {len(chunks)} part(s).", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ I don't have permission to send messages in that channel or use those emojis.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"❌ Discord rejected the message: `{str(e)[:1500]}`", ephemeral=True)
    except Exception as e:
        logger.error(f"/nmsg error: {e}", exc_info=True)
        await interaction.followup.send(f"❌ Failed to send message: `{str(e)[:1500]}`", ephemeral=True)

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    try:
        synced = await bot.tree.sync()
        logger.info(f'Global slash commands synced: {len(synced)}')
        for guild in bot.guilds:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        logger.info(f'Slash commands synced to {len(bot.guilds)} guild(s)!')
    except Exception as e:
        logger.error(f'Slash command sync failed: {e}')
    # DND gives the bot a red status indicator while it is online.
    await refresh_vps_presence()
    if not auto_expire_check.is_running():
        auto_expire_check.start()
    if not update_vps_presence.is_running():
        update_vps_presence.start()
    logger.info("Bot is ready!")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=create_error_embed("Missing Argument", "Please use `/help` for command usage."))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=create_error_embed("Invalid Argument", "Please check your input and try again."))
    elif isinstance(error, commands.CheckFailure):
        pass
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(embed=create_error_embed("System Error", "An error occurred. Please try again."))

def get_os_label(image):
    """Return the friendly OS name for a Docker image."""
    for option in OS_OPTIONS.values():
        if option["image"] == image:
            return option["label"]
    return image or "Unknown"


def get_vps_live_usage(container_name):
    """Read live Docker usage without requiring another bot command."""
    cpu_usage = "0.00"
    memory_usage = "Unknown"
    uptime = "Unknown"

    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", container_name],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split("|", 1)
            if parts:
                cpu_usage = parts[0].strip().replace("%", "")
            if len(parts) == 2:
                memory_usage = parts[1].strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.StartedAt}}", container_name],
            capture_output=True, text=True, timeout=10
        )
        started = result.stdout.strip()
        if result.returncode == 0 and started and started != "<no value>":
            started = started.replace("Z", "+00:00")
            started_dt = datetime.fromisoformat(started)
            now = datetime.now(started_dt.tzinfo)
            seconds = max(0, int((now - started_dt).total_seconds()))
            uptime = format_uptime(seconds)
    except Exception:
        pass

    return cpu_usage, memory_usage, uptime


# ─── ManageView ────────────────────────────────────────────────────────────────

class ManageView(discord.ui.View):
    def __init__(self, user_id, vps_list, is_shared=False, owner_id=None, is_admin=False):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.vps_list = vps_list
        self.selected_index = None
        self.is_shared = is_shared
        self.owner_id = owner_id or user_id
        self.is_admin = is_admin

        if len(vps_list) > 1:
            options = [
                discord.SelectOption(
                    label=f"VPS {i+1} ({v.get('plan', 'Custom')})",
                    description=f"Status: {v.get('status', 'unknown')}",
                    value=str(i)
                ) for i, v in enumerate(vps_list)
            ]
            self.select = discord.ui.Select(placeholder="Select a VPS to manage", options=options)
            self.select.callback = self.select_vps
            self.add_item(self.select)
            self.initial_embed = create_embed("VPS Management", "Select a VPS from the dropdown menu below.", 0x1a1a1a)
            self.initial_embed.add_field(
                name="Available VPS",
                value="\n".join([f"**VPS {i+1}:** `{v['container_name']}` - Status: `{v.get('status','unknown').upper()}` - Expiry: {format_expiry(v.get('expires', 'Never'))}"
                                 for i, v in enumerate(vps_list)]),
                inline=False
            )
        else:
            self.selected_index = 0
            self.initial_embed = self.create_vps_embed(0)
            self.add_action_buttons()

    def create_vps_embed(self, index):
        vps = self.vps_list[index]
        status = vps.get("status", "unknown")
        status_color = 0x00ff88 if status == "running" else 0xff3366

        owner_text = ""
        if self.is_admin and self.owner_id != self.user_id:
            try:
                owner_user = bot.get_user(int(self.owner_id))
                owner_text = f"\n**Owner:** {owner_user.mention}" if owner_user else f"\n**Owner ID:** {self.owner_id}"
            except Exception:
                owner_text = f"\n**Owner ID:** {self.owner_id}"

        cpu_usage, memory_usage, uptime = get_vps_live_usage(vps["container_name"])

        embed = create_embed(
            "🖥️ VPS Management",
            f"Managing VPS `{vps['container_name']}`{owner_text}",
            status_color
        )

        embed.add_field(
            name="⌯⌲ Resources",
            value=(
                f"**Plan:** {vps.get('plan', 'Custom')}\n"
                f"**Status:** `{status.upper()}`\n"
                f"**RAM:** {vps.get('ram', 'Unknown')}\n"
                f"**CPU:** {vps.get('cpu', 'Unknown')} Core(s)\n"
                f"**Storage:** {vps.get('storage', 'Unknown')}\n"
                f"**OS:** {get_os_label(vps.get('os', DOCKER_IMAGE))}\n"
                f"**Uptime:** {uptime}\n"
                f"**Expiry:** {format_expiry(vps.get('expires', 'Never'))}"
            ),
            inline=False
        )

        embed.add_field(
            name="⌯⌲ Live Usage",
            value=(
                f"**CPU Usage:** {cpu_usage}%\n"
                f"**Memory:** {memory_usage}\n"
                f"**Disk:** Unknown"
            ),
            inline=False
        )

        embed.add_field(
            name="⌯⌲ Controls",
            value="Use the buttons below to manage your VPS",
            inline=False
        )
        embed.set_footer(text="Xzy Hosting • Cloud Services")
        return embed

    def add_action_buttons(self):
        if not self.is_shared and not self.is_admin:
            rebuild_button = discord.ui.Button(label="🔄 Rebuild", style=discord.ButtonStyle.danger, row=0)
            rebuild_button.callback = lambda inter: self.action_callback(inter, 'rebuild')
            self.add_item(rebuild_button)

        start_button = discord.ui.Button(label="▶ Start", style=discord.ButtonStyle.success, row=0)
        start_button.callback = lambda inter: self.action_callback(inter, 'start')

        stop_button = discord.ui.Button(label="⏸ Stop", style=discord.ButtonStyle.secondary, row=0)
        stop_button.callback = lambda inter: self.action_callback(inter, 'stop')

        ssh_button = discord.ui.Button(label="🔑 SSH", style=discord.ButtonStyle.primary, row=1)
        ssh_button.callback = lambda inter: self.action_callback(inter, 'ssh')

        sshx_button = discord.ui.Button(label="🔗 SSHX", style=discord.ButtonStyle.success, row=1)
        sshx_button.callback = lambda inter: self.action_callback(inter, 'sshx')

        private_button = discord.ui.Button(label="🌐 Private IP", style=discord.ButtonStyle.primary, row=2)
        private_button.callback = lambda inter: self.action_callback(inter, 'private_ip')

        password_button = discord.ui.Button(label="🔑 Password", style=discord.ButtonStyle.secondary, row=2)
        password_button.callback = lambda inter: self.action_callback(inter, 'password')

        network_button = discord.ui.Button(
            label="🔌 Network & Ports",
            style=discord.ButtonStyle.secondary,
            row=3
        )
        network_button.callback = lambda inter: self.action_callback(inter, 'network_ports')

        self.add_item(start_button)
        self.add_item(stop_button)
        self.add_item(ssh_button)
        self.add_item(sshx_button)
        if self.owner_id == self.user_id:
            self.add_item(private_button)
            self.add_item(password_button)
            self.add_item(network_button)

    async def select_vps(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id and not self.is_admin:
            await interaction.response.send_message(
                embed=create_error_embed("Access Denied", "This is not your VPS!"), ephemeral=True)
            return
        self.selected_index = int(self.select.values[0])
        new_embed = self.create_vps_embed(self.selected_index)
        self.clear_items()
        self.add_action_buttons()
        await interaction.response.edit_message(embed=new_embed, view=self)

    async def action_callback(self, interaction: discord.Interaction, action: str):
        if str(interaction.user.id) != self.user_id and not self.is_admin:
            await interaction.response.send_message(
                embed=create_error_embed("Access Denied", "This is not your VPS!"), ephemeral=True)
            return

        if self.is_shared:
            vps = vps_data[self.owner_id][self.selected_index]
        else:
            vps = self.vps_list[self.selected_index]

        container_name = vps["container_name"]

        if action == 'network_ports':
            await interaction.response.send_message(
                embed=create_info_embed(
                    "🔌 Network & Ports",
                    f"Network configuration for VPS `{container_name}`"
                ),
                ephemeral=True
            )

            embed = create_embed(
                "🔌 Xzy Hosting • Network & Ports",
                f"Connection information for `{container_name}`",
                0x00ccff
            )

            embed.add_field(
                name="🔐 SSH • Default Port",
                value=(
                    "**Port:** `22`\n"
                    "**Protocol:** TCP\n"
                    "**Service:** OpenSSH\n"
                    "Tailscale private IP par SSH ke liye port **22** default hai."
                ),
                inline=False
            )

            tailscale_ip = vps.get("tailscale_ip")

            if tailscale_ip:
                embed.add_field(
                    name="🌐 Tailscale Private Network",
                    value=(
                        f"**Private IP:** `{tailscale_ip}`\n"
                        f"**SSH:** `ssh root@{tailscale_ip} -p 22`"
                    ),
                    inline=False
                )
            else:
                embed.add_field(
                    name="🌐 Tailscale Private Network",
                    value=(
                        "Tailscale abhi connected nahi hai.\n"
                        "Private IP Setup se VPS ko authorize karo."
                    ),
                    inline=False
                )

            embed.add_field(
                name="🔗 Other Ports",
                value=(
                    "Minecraft, web server, API ya kisi aur service ke liye "
                    "jo application port use kare, woh VPS ke andar "
                    "usi port par listen kar sakta hai.\n\n"
                    "Example: `25565`, `8080`, `3000`"
                ),
                inline=False
            )

            embed.add_field(
                name="📱 Termux / PC",
                value=(
                    "Tailscale app me same account se login karke:\n"
                    "```ssh root@100.x.x.x -p 22```"
                ),
                inline=False
            )

            embed.set_footer(text="Xzy Hosting • Cloud Services")

            await interaction.followup.send(
                embed=embed,
                ephemeral=True
            )
            return

        if action == 'rebuild':
            if vps.get('expired'):
                await interaction.response.send_message(
                    embed=create_error_embed("VPS Expired", "PLS RENEW THE VPS"),
                    ephemeral=True
                )
                return
            if self.is_shared or self.is_admin:
                await interaction.response.send_message(
                    embed=create_error_embed("Access Denied", "Only the VPS owner can rebuild!"), ephemeral=True)
                return

            parent_view = self

            class RebuildOSView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=120)
                    self.selected_os = None
                    options = [
                        discord.SelectOption(
                            label=data["label"],
                            value=key,
                            description=data["image"]
                        )
                        for key, data in OS_OPTIONS.items()
                    ]
                    self.os_select = discord.ui.Select(
                        placeholder="Select a new OS...",
                        options=options,
                        min_values=1,
                        max_values=1
                    )
                    self.os_select.callback = self.select_os
                    self.add_item(self.os_select)

                async def select_os(self, inter: discord.Interaction):
                    if inter.user.id != interaction.user.id:
                        await inter.response.send_message(
                            embed=create_error_embed("Access Denied", "This rebuild menu belongs to another user."),
                            ephemeral=True
                        )
                        return

                    self.selected_os = self.os_select.values[0]
                    os_data = OS_OPTIONS[self.selected_os]
                    self.clear_items()

                    confirm = discord.ui.Button(label="Confirm Rebuild", style=discord.ButtonStyle.danger)
                    cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)

                    async def do_confirm(confirm_inter: discord.Interaction):
                        if confirm_inter.user.id != interaction.user.id:
                            await confirm_inter.response.send_message(
                                embed=create_error_embed("Access Denied", "This rebuild menu belongs to another user."),
                                ephemeral=True
                            )
                            return

                        await confirm_inter.response.defer(ephemeral=True)
                        try:
                            await confirm_inter.followup.send(
                                embed=create_info_embed(
                                    "Deleting Container",
                                    f"Removing `{container_name}` before installing **{os_data['label']}**..."
                                ),
                                ephemeral=True
                            )
                            try:
                                await execute_docker(f"docker stop {container_name}")
                            except Exception:
                                pass
                            await execute_docker(f"docker rm -f {container_name}")

                            original_ram = self_vps["ram"]
                            original_cpu = self_vps["cpu"]
                            original_disk = int(self_vps.get("storage", "30GB").replace("GB", ""))
                            ram_mb = int(original_ram.replace("GB", "")) * 1024
                            new_password = generate_password()

                            await confirm_inter.followup.send(
                                embed=create_info_embed(
                                    "Creating New VPS",
                                    f"Installing **{os_data['label']}** on `{container_name}`..."
                                ),
                                ephemeral=True
                            )

                            await create_docker_container(
                                container_name,
                                ram_mb,
                                original_cpu,
                                0,
                                new_password,
                                disk_gb=original_disk,
                                image=os_data["image"]
                            )

                            self_vps["status"] = "running"
                            self_vps["ssh_password"] = new_password
                            self_vps["os"] = os_data["image"]
                            self_vps["created_at"] = datetime.now().isoformat()
                            save_data()

                            await confirm_inter.followup.send(
                                embed=create_success_embed(
                                    "Rebuild Complete",
                                    f"VPS `{container_name}` is now running **{os_data['label']}**."
                                ),
                                ephemeral=True
                            )
                            await interaction.message.edit(
                                embed=parent_view.create_vps_embed(parent_view.selected_index),
                                view=parent_view
                            )
                        except Exception as e:
                            await confirm_inter.followup.send(
                                embed=create_error_embed("Rebuild Failed", f"Error: {str(e)}"),
                                ephemeral=True
                            )

                    async def do_cancel(cancel_inter: discord.Interaction):
                        await cancel_inter.response.edit_message(
                            embed=parent_view.create_vps_embed(parent_view.selected_index),
                            view=parent_view
                        )

                    confirm.callback = do_confirm
                    cancel.callback = do_cancel
                    self.add_item(confirm)
                    self.add_item(cancel)

                    warning = create_warning_embed(
                        "Rebuild Warning",
                        f"⚠️ This will erase all data on `{container_name}` and install **{os_data['label']}**.\n\n"
                        "This action cannot be undone. Continue?"
                    )
                    await inter.response.edit_message(embed=warning, view=self)

            self_vps = vps
            await interaction.response.send_message(
                embed=create_embed(
                    "Select a new OS",
                    "Choose the operating system you want to install on this VPS.",
                    0x1a1a1a
                ),
                view=RebuildOSView(),
                ephemeral=True
            )

        elif action == 'start':
            await interaction.response.defer(ephemeral=True)
            if vps.get('expired'):
                await interaction.followup.send(
                    embed=create_error_embed(
                        "VPS Expired",
                        "PLS RENEW THE VPS"
                    ),
                    ephemeral=True
                )
                return
            try:
                await execute_docker(f"docker start {container_name}")
                # Restart SSH inside container
                await docker_exec(container_name, "/usr/sbin/sshd || true", timeout=10)
                await ensure_docker_daemon(container_name)
                vps["status"] = "running"
                vps.pop('expired', None)
                save_data()
                await refresh_vps_presence()
                await interaction.followup.send(
                    embed=create_success_embed("VPS Started", f"VPS `{container_name}` is now running!"),
                    ephemeral=True)
                await interaction.message.edit(embed=self.create_vps_embed(self.selected_index), view=self)
            except Exception as e:
                await interaction.followup.send(
                    embed=create_error_embed("Start Failed", str(e)), ephemeral=True)

        elif action == 'stop':
            await interaction.response.defer(ephemeral=True)
            try:
                await execute_docker(f"docker stop {container_name}", timeout=120)
                vps["status"] = "stopped"
                save_data()
                await refresh_vps_presence()
                await interaction.followup.send(
                    embed=create_success_embed("VPS Stopped", f"VPS `{container_name}` has been stopped!"),
                    ephemeral=True)
                await interaction.message.edit(embed=self.create_vps_embed(self.selected_index), view=self)
            except Exception as e:
                await interaction.followup.send(
                    embed=create_error_embed("Stop Failed", str(e)), ephemeral=True)

        elif action == 'password':
            await interaction.response.send_message(
                embed=create_info_embed(
                    "☁️ 🔑 Root Password Set",
                    f"A root password has been generated for `{container_name}`:\n\n"
                    f"⌯⌲ Password\n```{vps.get('ssh_password', 'Password unavailable')}```\n\n"
                    f"⌯⌲ Login\n`root` @ `your VPS IP`\n\n"
                    "Xzy Hosting • Cloud Services"
                ),
                ephemeral=True
            )

        elif action == 'private_ip':
            if vps.get('expired'):
                await interaction.response.send_message(
                    embed=create_error_embed("VPS Expired", "PLS RENEW THE VPS"),
                    ephemeral=True
                )
                return
            if vps.get('status') != 'running':
                await interaction.response.send_message(
                    embed=create_error_embed("Private IP Error", "Start the VPS first, then press Private IP again."),
                    ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            try:
                await ensure_vps_container(vps)
                existing_ip = await get_tailscale_ipv4(container_name)
                if existing_ip:
                    vps["tailscale_ip"] = existing_ip
                    vps["tailscale_status"] = "connected"
                    save_data()
                    embed = create_success_embed(
                        "✅ Tailscale Connected!",
                        f"VPS `{container_name}` now has a private IP."
                    )
                    embed.add_field(name="⌯⌲ Private IPv4", value=f"`{existing_ip}`", inline=False)
                    embed.add_field(
                        name="📱 To Connect",
                        value=(
                            "Install Tailscale on your device and log in with the same account used for this VPS. "
                            f"Then connect using `ssh root@{existing_ip}`."
                        ),
                        inline=False
                    )
                    embed.set_footer(text="Xzy Hosting • Cloud Services")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

                await interaction.followup.send(
                    embed=create_info_embed(
                        "🌐 Private IP Setup",
                        f"Setting up your private IP connection for VPS `{container_name}`, this may take a moment..."
                    ),
                    ephemeral=True
                )
                await ensure_tailscaled(container_name)
                await interaction.followup.send(
                    embed=create_success_embed(
                        "✅ Tailscale Installed Successfully",
                        "Tailscale has been installed on your VPS. Continue with the authorization step below."
                    ),
                    ephemeral=True
                )
                auth_url = await start_tailscale_auth(container_name)
                if auth_url:
                    auth_embed = create_info_embed(
                        "🌐 Private IP Setup",
                        f"Click below to authorize VPS `{container_name}` and give it a private IP."
                    )
                    auth_embed.add_field(
                        name="🔗 Step 1: Authorize This VPS",
                        value=f"[Click to Authorize]({auth_url})\nSign in with the Tailscale account you want this VPS linked to.",
                        inline=False
                    )
                    auth_embed.add_field(
                        name="📱 Step 2: Install Tailscale On Your Own Device",
                        value=(
                            "To actually connect to the private IP, download the Tailscale app on your PC/phone and log in with the same account you used above.\n"
                            "https://tailscale.com/download"
                        ),
                        inline=False
                    )
                    auth_embed.add_field(
                        name="⌯⌲ Step 3",
                        value="Once authorized, your VPS's private IP will be sent to you in DM automatically — usually within a minute.",
                        inline=False
                    )
                    auth_embed.set_footer(text="Xzy Hosting • Cloud Services")
                    try:
                        await interaction.user.send(embed=auth_embed)
                        await interaction.followup.send(
                            embed=create_success_embed(
                                "🌐 Private IP Setup",
                                "Authorization link has been sent to your DMs."
                            ),
                            ephemeral=True
                        )
                    except discord.Forbidden:
                        await interaction.followup.send(
                            embed=create_error_embed(
                                "DM Failed",
                                "Please enable DMs so I can send the Tailscale authorization link."
                            ),
                            ephemeral=True
                        )
                else:
                    await interaction.followup.send(
                        embed=create_success_embed(
                            "✅ Tailscale Installed Successfully",
                            "Tailscale is already authorized on this VPS. I am checking for its private IP now and will DM you when it is ready."
                        ),
                        ephemeral=True
                    )

                asyncio.create_task(
                    wait_and_notify_tailscale(str(self.owner_id), vps, container_name)
                )
            except Exception as e:
                await interaction.followup.send(
                    embed=create_error_embed("Tailscale Installation Failed", f"{str(e)}"),
                    ephemeral=True)

        elif action == 'ssh':
            await interaction.response.defer(ephemeral=True)
            try:
                if vps.get('expired'):
                    await interaction.followup.send(
                        embed=create_error_embed("VPS Expired", "PLS RENEW THE VPS"),
                        ephemeral=True
                    )
                    return
                if vps.get('status') != 'running':
                    await interaction.followup.send(
                        embed=create_error_embed("SSH Error", "Start the VPS first, then press SSH again."),
                        ephemeral=True)
                    return

                await interaction.followup.send(
                    embed=create_info_embed("Starting SSH", "Generating a temporary SSH session, please wait..."),
                    ephemeral=True)

                await ensure_vps_container(vps)
                tmate_cmd = await get_tmate_session(container_name)
                ssh_embed = create_embed("🔑 Xzy Hosting - SSH Access", f"SSH connection for VPS `{container_name}`:", 0x5865F2)
                ssh_embed.add_field(
                    name="⌯⌲ Command",
                    value=f"```{tmate_cmd}```",
                    inline=False
                )
                ssh_embed.add_field(
                    name="⌯⌲ Security",
                    value="This link is temporary. Do not share it.",
                    inline=False
                )
                ssh_embed.set_footer(text="Xzy Hosting • Cloud Services")

                try:
                    await interaction.user.send(embed=ssh_embed)
                    await interaction.followup.send(
                        embed=create_success_embed("SSH Sent", "Check your DMs for the temporary SSH connection."),
                        ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send(
                        embed=create_error_embed("DM Failed", "Enable DMs to receive SSH access."),
                        ephemeral=True)
            except Exception as e:
                await interaction.followup.send(
                    embed=create_error_embed("SSH Error", str(e)), ephemeral=True)

        elif action == 'sshx':
            await interaction.response.defer(ephemeral=True)
            try:
                if vps.get('expired'):
                    await interaction.followup.send(
                        embed=create_error_embed("VPS Expired", "PLS RENEW THE VPS"),
                        ephemeral=True
                    )
                    return
                if vps.get('status') != 'running':
                    await interaction.followup.send(
                        embed=create_error_embed("SSHX Error", "Start the VPS first, then press SSHX again."),
                        ephemeral=True)
                    return

                await interaction.followup.send(
                    embed=create_info_embed("Starting SSHX", "Generating a temporary web terminal, please wait..."),
                    ephemeral=True)

                await ensure_vps_container(vps)
                sshx_url = await get_sshx_session(container_name)
                sshx_embed = create_embed("Xzy Hosting • SSHX Access", f"Web SSH connection for VPS `{container_name}`:", 0x00ff88)
                sshx_embed.add_field(
                    name="🔗 Link",
                    value=f"[Click to Open Terminal]({sshx_url})",
                    inline=False
                )
                sshx_embed.add_field(
                    name="⚠️ Security",
                    value="This link grants direct root access. Do not share it.",
                    inline=False
                )
                sshx_embed.set_footer(text="Powered by Xzy Hosting • Premium VPS Management")

                try:
                    await interaction.user.send(embed=sshx_embed)
                    await interaction.followup.send(
                        embed=create_success_embed("SSHX Sent", "Check your DMs for the temporary web terminal."),
                        ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send(
                        embed=create_error_embed("DM Failed", "Enable DMs to receive SSHX access."),
                        ephemeral=True)
            except Exception as e:
                await interaction.followup.send(
                    embed=create_error_embed("SSHX Error", str(e)), ephemeral=True)


# ─── Commands ──────────────────────────────────────────────────────────────────

@bot.hybrid_command(name='ping')
async def ping(ctx):
    """Show the bot's Discord latency with a color based on the ping."""
    ping_ms = round(bot.latency * 1000)

    if ping_ms <= 50:
        color = 0x00FF66
        status = "🟢 Excellent"
    elif ping_ms <= 100:
        color = 0xFFFF00
        status = "🟡 Good"
    elif ping_ms <= 300:
        color = 0xFF69B4
        status = "🩷 High"
    else:
        color = 0xFF0000
        status = "🔴 Very High"

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"**Ping:** `{ping_ms}ms`\n**Status:** {status}",
        color=color
    )
    embed.set_footer(text="Xzy Hosting | VPS Manager")
    await ctx.send(embed=embed)


def format_uptime(seconds: int) -> str:
    """Convert seconds into a readable bot runtime string."""
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


@bot.hybrid_command(name='uptime')
async def uptime(ctx):
    """Show how long the bot has been running."""
    runtime = max(0, int(time.monotonic() - BOT_START_TIME))
    embed = create_info_embed(
        "⏱️ Bot Uptime",
        f"{ctx.author.mention}, the bot has been running for:\n\n"
        f"**`{format_uptime(runtime)}`**"
    )
    embed.add_field(
        name="🟢 Runtime Status",
        value="Bot is online and running.",
        inline=False
    )
    await ctx.send(embed=embed)


def get_localnode_counts():
    """Return active/inactive VPS counts for the Localnode selector."""
    total = 0
    active = 0
    for vps_list in vps_data.values():
        for vps in vps_list:
            total += 1
            if vps.get("status") == "running":
                active += 1
    return active, max(0, total - active)


class CreateVPSView(discord.ui.View):
    """Two-step admin VPS creation: Mode -> OS -> Create."""

    def __init__(self, ctx, user, ram, cpu, disk, expiry_days=0):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.user = user
        self.ram = ram
        self.cpu = cpu
        self.disk = disk
        self.expiry_days = expiry_days
        self.mode = None
        self.os_key = None

        active, inactive = get_localnode_counts()
        self.mode_select = discord.ui.Select(
            placeholder="Select A Mode To Create Vps",
            options=[
                discord.SelectOption(
                    label="Localnode",
                    value="localnode",
                    description=f"Active: {active} VPS • Inactive: {inactive} VPS",
                    emoji="🖥️"
                )
            ],
            min_values=1,
            max_values=1
        )
        self.mode_select.callback = self.select_mode
        self.add_item(self.mode_select)

    async def interaction_allowed(self, interaction):
        return interaction.user.id == self.ctx.author.id

    async def select_mode(self, interaction: discord.Interaction):
        if not await self.interaction_allowed(interaction):
            await interaction.response.send_message(
                embed=create_error_embed("Access Denied", "This VPS creation menu belongs to another admin."),
                ephemeral=True
            )
            return

        self.mode = self.mode_select.values[0]
        self.clear_items()

        options = [
            discord.SelectOption(
                label=data["label"],
                value=key,
                description=data["image"]
            )
            for key, data in OS_OPTIONS.items()
        ]

        self.os_select = discord.ui.Select(
            placeholder="Select OS To Create",
            options=options,
            min_values=1,
            max_values=1
        )
        self.os_select.callback = self.select_os
        self.add_item(self.os_select)

        active, inactive = get_localnode_counts()
        embed = create_embed(
            "Select OS To Create",
            f"**Mode:** `Localnode`\n**Active VPS:** `{active}`\n**Inactive VPS:** `{inactive}`\n\nChoose the operating system for `{self.user.display_name}`.",
            0x1a1a1a
        )
        await interaction.response.edit_message(embed=embed, view=self)

    async def select_os(self, interaction: discord.Interaction):
        if not await self.interaction_allowed(interaction):
            await interaction.response.send_message(
                embed=create_error_embed("Access Denied", "This VPS creation menu belongs to another admin."),
                ephemeral=True
            )
            return

        self.os_key = self.os_select.values[0]
        os_data = OS_OPTIONS[self.os_key]

        await interaction.response.defer()
        self.clear_items()

        creating_embed = create_embed(
            "☁️ Creating VPS",
            (
                f"Deploying **{os_data['label']}** for {self.user.mention}\n\n"
                f"**Mode:** Localnode\n"
                f"**RAM:** {self.ram}GB\n"
                f"**CPU:** {self.cpu} Core(s)\n"
                f"**Storage:** {self.disk}GB\n"
                f"**OS:** {os_data['label']}"
            ),
            0x5865F2
        )
        await interaction.edit_original_response(embed=creating_embed, view=None)

        user_id = str(self.user.id)
        if user_id not in vps_data:
            vps_data[user_id] = []

        vps_count = len(vps_data[user_id]) + 1
        container_name = f"vps-{user_id}-{vps_count}"
        ram_mb = self.ram * 1024
        password = generate_password()
        created_at = datetime.now().isoformat()

        try:
            await create_docker_container(
                container_name,
                ram_mb,
                self.cpu,
                0,
                password,
                disk_gb=self.disk,
                image=os_data["image"]
            )

            vps_expiry = expiry_from_days(self.expiry_days)
            vps_info = {
                "container_name": container_name,
                "ram": f"{self.ram}GB",
                "cpu": str(self.cpu),
                "storage": f"{self.disk}GB",
                "status": "running",
                "os": os_data["image"],
                "created_at": created_at,
                "expires": vps_expiry,
                "ssh_password": password,
                "shared_with": [],
                "node": "localnode"
            }
            vps_data[user_id].append(vps_info)
            save_data()
            await refresh_vps_presence()

            if self.ctx.guild:
                vps_role = await get_or_create_vps_role(self.ctx.guild)
                if vps_role:
                    try:
                        await self.user.add_roles(vps_role, reason="VPS ownership granted")
                    except discord.Forbidden:
                        pass

            server_embed = create_embed("✅ VPS Created Successfully", "", color=0x00ff88)
            server_embed.add_field(name="⌯⌲ Owner", value=self.user.mention, inline=False)
            server_embed.add_field(name="⌯⌲ Container", value=f"`{container_name}`", inline=False)
            server_embed.add_field(
                name="⌯⌲ Resources",
                value=(
                    f"**RAM:** {self.ram} GB\n"
                    f"**CPU:** {self.cpu} Cores\n"
                    f"**Storage:** {self.disk} GB\n"
                    f"**OS:** {os_data['label']}\n"
                    f"**Node:** Localnode"
                ),
                inline=False
            )
            if self.expiry_days and self.expiry_days > 0:
                server_embed.add_field(name="⌯⌲ Expiry", value=f"`{self.expiry_days}` day(s)", inline=False)
            else:
                server_embed.add_field(name="⌯⌲ Expiry", value="`Never`", inline=False)
            await self.ctx.send(embed=server_embed)

            dm_embed = create_embed(
                "✅ Xzy Hosting - VPS Created!",
                "Your VPS has been successfully deployed by an admin!",
                color=0x5865F2
            )
            dm_embed.add_field(
                name="⌯⌲ VPS Details",
                value=(
                    f"**VPS ID:** `#{vps_count}`\n"
                    f"**Container Name:** `{container_name}`\n"
                    f"**Configuration:** {self.ram} GB RAM • {self.cpu} CPU Cores • {self.disk} GB Disk\n"
                    f"**Status:** `{vps_info['status']}`\n"
                    f"**OS:** `{os_data['label']}`\n"
                    f"**Node:** `Localnode`\n"
                    f"**Expiry:** `{vps_info['expires'] if vps_info['expires'] != 'Never' else 'Never'}`"
                ),
                inline=False
            )
            dm_embed.add_field(
                name="⌯⌲ Management",
                value=(
                    "• Use `/manage` to start/stop/rebuild your VPS\n"
                    "• Use `/manage` → SSH/SSHX for terminal access\n"
                    "• Contact admin for upgrades or issues"
                ),
                inline=False
            )
            dm_embed.set_footer(text="Powered by Xzy Hosting • Premium VPS Management")
            try:
                await self.user.send(embed=dm_embed)
            except discord.Forbidden:
                pass

        except Exception as e:
            await self.ctx.send(
                embed=create_error_embed("Creation Failed", f"Error: {str(e)}")
            )


@bot.hybrid_command(name='create')
@is_admin()
async def create_vps(ctx, user: discord.Member, ram: int, cpu: int, disk: int = 30, expiry_days: int = 0):
    """
    Admin VPS creation.
    Usage: /create @user <ram_GB> <cpu_cores> <disk_GB> [expiry_days]
    The command now opens Mode -> OS selection instead of creating directly.
    """
    if ram <= 0 or cpu <= 0 or disk <= 0:
        await ctx.send(embed=create_error_embed(
            "Invalid Specs",
            "RAM, CPU and Disk must be positive integers.\nUsage: `/create @user <ram_GB> <cpu_cores> <disk_GB> [expiry_days]`"
        ))
        return
    if expiry_days < 0:
        await ctx.send(embed=create_error_embed(
            "Invalid Expiry",
            "Expiry days must be zero or a positive integer."
        ))
        return

    active, inactive = get_localnode_counts()
    embed = create_embed(
        "Select A Mode To Create Vps",
        (
            f"Choose where this VPS should be created.\n\n"
            f"**Localnode**\n"
            f"Active VPS: `{active}`\n"
            f"Inactive VPS: `{inactive}`"
        ),
        0x1a1a1a
    )
    embed.add_field(
        name="⌯⌲ Requested Resources",
        value=f"**RAM:** {ram}GB • **CPU:** {cpu} Core(s) • **Storage:** {disk}GB",
        inline=False
    )
    embed.add_field(
        name="⌯⌲ Expiry",
        value=f"`{expiry_days}` day(s)" if expiry_days > 0 else "`Never`",
        inline=False
    )
    await ctx.send(
        embed=embed,
        view=CreateVPSView(ctx, user, ram, cpu, disk, expiry_days)
    )


@bot.hybrid_command(name='editvps')
@is_admin()
async def edit_vps(ctx, user: discord.Member, vps_number: int, ram: int = None, cpu: int = None, disk: int = None, expiry_days: Optional[int] = None):
    """Admin edit existing VPS resource fields and/or expiry days.
    If the expiry_days value is blank/zero, the VPS becomes permanent by storing 'Never'.
    """
    user_id = str(user.id)
    if user_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[user_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number or user doesn't have a VPS."))
        return

    if ram is not None and ram <= 0:
        await ctx.send(embed=create_error_embed("Invalid RAM", "RAM must be a positive integer."))
        return
    if cpu is not None and cpu <= 0:
        await ctx.send(embed=create_error_embed("Invalid CPU", "CPU must be a positive integer."))
        return
    if disk is not None and disk <= 0:
        await ctx.send(embed=create_error_embed("Invalid Disk", "Disk must be a positive integer."))
        return
    if expiry_days is not None and expiry_days < 0:
        await ctx.send(embed=create_error_embed("Invalid Expiry", "Expiry days must be zero or a positive integer."))
        return

    vps = vps_data[user_id][vps_number - 1]
    if ram is not None:
        vps["ram"] = f"{ram}GB"
    if cpu is not None:
        vps["cpu"] = str(cpu)
    if disk is not None:
        vps["storage"] = f"{disk}GB"
    if expiry_days is not None:
        vps["expires"] = expiry_from_days(expiry_days)

    save_data()
    await ctx.send(embed=create_success_embed(
        "VPS Edited",
        f"Updated `{user.mention}` VPS #{vps_number} successfully."
    ))


@bot.hybrid_command(name='manage')
async def manage_vps(ctx, user: discord.Member = None):
    """Manage your VPS or another user's VPS (Admin only)"""
    if user:
        if not (str(ctx.author.id) == str(MAIN_ADMIN_ID) or str(ctx.author.id) in admin_data.get("admins", [])):
            await ctx.send(embed=create_error_embed("Access Denied", "Only admins can manage other users' VPS."))
            return
        user_id = str(user.id)
        vps_list = vps_data.get(user_id, [])
        if not vps_list:
            await ctx.send(embed=create_error_embed("No VPS Found", f"{user.mention} doesn't have any VPS."))
            return
        view = ManageView(str(ctx.author.id), vps_list, is_admin=True, owner_id=user_id)
        await ctx.send(embed=create_info_embed(f"Managing {user.name}'s VPS", f"Managing VPS for {user.mention}"), view=view)
    else:
        user_id = str(ctx.author.id)
        vps_list = vps_data.get(user_id, [])
        if not vps_list:
            embed = create_embed("No VPS Found", "You don't have any VPS. Use `/buywc` to purchase one.", 0xff3366)
            embed.add_field(name="Quick Actions", value="• `/plans` - View plans\n• `/buywc <plan> <processor>` - Purchase VPS", inline=False)
            await ctx.send(embed=embed)
            return
        view = ManageView(user_id, vps_list)
        await ctx.send(embed=view.initial_embed, view=view)


@bot.hybrid_command(name='delete-vps')
@is_admin()
async def delete_vps(ctx, user: discord.Member, vps_number: int, *, reason: str = "No reason"):
    """Delete a user's VPS (Admin only)"""
    user_id = str(user.id)
    if user_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[user_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number or user doesn't have a VPS."))
        return

    vps = vps_data[user_id][vps_number - 1]
    container_name = vps["container_name"]
    await ctx.send(embed=create_info_embed("Deleting VPS", f"Removing VPS #{vps_number}..."))

    try:
        try:
            await execute_docker(f"docker stop {container_name}")
        except:
            pass
        await execute_docker(f"docker rm -f {container_name}")
        del vps_data[user_id][vps_number - 1]
        if not vps_data[user_id]:
            del vps_data[user_id]
            if ctx.guild:
                vps_role = await get_or_create_vps_role(ctx.guild)
                if vps_role and vps_role in user.roles:
                    try:
                        await user.remove_roles(vps_role, reason="No VPS ownership")
                    except discord.Forbidden:
                        pass
        save_data()
        await refresh_vps_presence()
        embed = create_success_embed("VPS Deleted Successfully")
        embed.add_field(name="Owner", value=user.mention, inline=True)
        embed.add_field(name="VPS ID", value=f"#{vps_number}", inline=True)
        embed.add_field(name="Container", value=f"`{container_name}`", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Deletion Failed", f"Error: {str(e)}"))


@bot.hybrid_command(name='list-all')
@is_admin()
async def list_all_vps(ctx):
    """List all VPS and user information (Admin only)"""
    embed = create_embed("All VPS Information", "Complete overview of all VPS deployments", 0x1a1a1a)
    total_vps = 0
    running_vps = 0
    stopped_vps = 0
    vps_info = []
    user_summary = []

    for user_id, vps_list in vps_data.items():
        try:
            user = await bot.fetch_user(int(user_id))
            user_vps_count = len(vps_list)
            user_running = sum(1 for vps in vps_list if vps.get('status') == 'running')
            total_vps += user_vps_count
            running_vps += user_running
            stopped_vps += user_vps_count - user_running
            user_summary.append(f"**{user.name}** ({user.mention}) - {user_vps_count} VPS ({user_running} running)")
            for i, vps in enumerate(vps_list):
                status_emoji = "🟢" if vps.get('status') == 'running' else "🔴"
                vps_info.append(
                    f"{status_emoji} **{user.name}** - VPS {i+1}: `{vps['container_name']}` "
                    f"Port:{vps.get('ssh_port','?')} - {vps.get('status','unknown').upper()}"
                )
        except discord.NotFound:
            vps_info.append(f"❓ Unknown User ({user_id}) - {len(vps_list)} VPS")

    embed.add_field(
        name="System Overview",
        value=f"**Total Users:** {len(vps_data)}\n**Total VPS:** {total_vps}\n**Running:** {running_vps}\n**Stopped:** {stopped_vps}",
        inline=False
    )
    if user_summary:
        embed.add_field(name="User Summary", value="\n".join(user_summary[:10]), inline=False)
    if vps_info:
        for i in range(0, min(len(vps_info), 30), 15):
            chunk = vps_info[i:i+15]
            embed.add_field(name=f"VPS Deployments ({i+1}-{min(i+15, len(vps_info))})", value="\n".join(chunk), inline=False)
    await ctx.send(embed=embed)


@bot.hybrid_command(name='manage-shared')
async def manage_shared_vps(ctx, owner: discord.Member, vps_number: int):
    """Manage a shared VPS"""
    owner_id = str(owner.id)
    user_id = str(ctx.author.id)
    if owner_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[owner_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number."))
        return
    vps = vps_data[owner_id][vps_number - 1]
    if user_id not in vps.get("shared_with", []):
        await ctx.send(embed=create_error_embed("Access Denied", "You do not have access to this VPS."))
        return
    view = ManageView(user_id, [vps], is_shared=True, owner_id=owner_id)
    await ctx.send(embed=view.initial_embed, view=view)


@bot.hybrid_command(name='share-user')
async def share_user(ctx, shared_user: discord.Member, vps_number: int):
    """Share VPS access with another user"""
    user_id = str(ctx.author.id)
    shared_user_id = str(shared_user.id)
    if user_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[user_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number."))
        return
    vps = vps_data[user_id][vps_number - 1]
    if "shared_with" not in vps:
        vps["shared_with"] = []
    if shared_user_id in vps["shared_with"]:
        await ctx.send(embed=create_error_embed("Already Shared", f"{shared_user.mention} already has access!"))
        return
    vps["shared_with"].append(shared_user_id)
    save_data()
    await ctx.send(embed=create_success_embed("VPS Shared", f"VPS #{vps_number} shared with {shared_user.mention}!"))
    try:
        await shared_user.send(embed=create_embed(
            "VPS Access Granted",
            f"You have access to VPS #{vps_number} from {ctx.author.mention}. Use `/manage-shared {ctx.author.mention} {vps_number}`",
            0x00ff88
        ))
    except discord.Forbidden:
        pass


@bot.hybrid_command(name='share-ruser')
async def revoke_share(ctx, shared_user: discord.Member, vps_number: int):
    """Revoke shared VPS access"""
    user_id = str(ctx.author.id)
    shared_user_id = str(shared_user.id)
    if user_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[user_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number."))
        return
    vps = vps_data[user_id][vps_number - 1]
    if "shared_with" not in vps or shared_user_id not in vps["shared_with"]:
        await ctx.send(embed=create_error_embed("Not Shared", f"{shared_user.mention} doesn't have access!"))
        return
    vps["shared_with"].remove(shared_user_id)
    save_data()
    await ctx.send(embed=create_success_embed("Access Revoked", f"Access to VPS #{vps_number} revoked from {shared_user.mention}!"))


@bot.hybrid_command(name='buywc')
async def buy_with_credits(ctx, plan: str, processor: str = "Intel"):
    """Buy a VPS with credits"""
    user_id = str(ctx.author.id)
    prices = {
        "Starter": {"Intel": 42, "AMD": 83},
        "Basic": {"Intel": 96, "AMD": 164},
        "Standard": {"Intel": 192, "AMD": 320},
        "Pro": {"Intel": 220, "AMD": 340}
    }
    plans = {
        "Starter": {"ram": "4GB", "cpu": "1", "storage": "10GB"},
        "Basic": {"ram": "8GB", "cpu": "1", "storage": "10GB"},
        "Standard": {"ram": "12GB", "cpu": "2", "storage": "10GB"},
        "Pro": {"ram": "16GB", "cpu": "2", "storage": "10GB"}
    }
    if plan not in prices:
        await ctx.send(embed=create_error_embed("Invalid Plan", "Available: Starter, Basic, Standard, Pro"))
        return
    if processor not in ["Intel", "AMD"]:
        await ctx.send(embed=create_error_embed("Invalid Processor", "Choose: Intel or AMD"))
        return

    cost = prices[plan][processor]
    if user_id not in user_data:
        user_data[user_id] = {"credits": 0}
    if user_data[user_id]["credits"] < cost:
        await ctx.send(embed=create_error_embed("Insufficient Credits",
                                                f"You need {cost} credits but have {user_data[user_id]['credits']}"))
        return

    user_data[user_id]["credits"] -= cost
    if user_id not in vps_data:
        vps_data[user_id] = []

    vps_count = len(vps_data[user_id]) + 1
    container_name = f"vps-{user_id}-{vps_count}"
    ram_str = plans[plan]["ram"]
    cpu_str = plans[plan]["cpu"]
    ram_mb = int(ram_str.replace("GB", "")) * 1024
    password = generate_password()

    await ctx.send(embed=create_info_embed("Processing Purchase", f"Deploying {plan} Docker VPS..."))

    try:
        await create_docker_container(container_name, ram_mb, cpu_str, 0, password)

        vps_info = {
            "plan": plan,
            "container_name": container_name,
            "ram": ram_str,
            "cpu": cpu_str,
            "storage": plans[plan]["storage"],
            "status": "running",
            "created_at": datetime.now().isoformat(),
            "processor": processor,
            "os": DOCKER_IMAGE,
            "ssh_password": password,
            "shared_with": []
        }
        vps_data[user_id].append(vps_info)
        save_data()
        await refresh_vps_presence()

        if ctx.guild:
            vps_role = await get_or_create_vps_role(ctx.guild)
            if vps_role:
                try:
                    await ctx.author.add_roles(vps_role, reason="VPS purchase completed")
                except discord.Forbidden:
                    pass

        embed = create_embed("✅ VPS Created Successfully", "", color=0x00ff88)
        embed.add_field(name="⌯⌲ Owner", value=ctx.author.mention, inline=False)
        embed.add_field(name="⌯⌲ Container", value=f"`{container_name}`", inline=False)
        embed.add_field(
            name="⌯⌲ Resources",
            value=f"**RAM:** {ram_str}\n**CPU:** {cpu_str} Cores\n**Storage:** {plans[plan]['storage']}",
            inline=False
        )
        embed.add_field(name="⌯⌲ OS", value=f"`{DOCKER_IMAGE}`", inline=False)
        await ctx.send(embed=embed)

        try:
            dm_embed = create_embed(
                "✅ Xzy Hosting - VPS Created!",
                "Your VPS has been successfully deployed by an admin!",
                color=0x5865F2
            )
            dm_embed.add_field(
                name="⌯⌲ VPS Details",
                value=(
                    f"**VPS ID:** `#{vps_count}`\n"
                    f"**Container Name:** `{container_name}`\n"
                    f"**Configuration:** {ram_str} RAM • {cpu_str} CPU Cores • {plans[plan]['storage']} Disk\n"
                    f"**Status:** `{vps_info['status']}`\n"
                    f"**OS:** `{DOCKER_IMAGE}`"
                ),
                inline=False
            )
            dm_embed.add_field(
                name="⌯⌲ Management",
                value=(
                    "• Use `/manage` to start/stop/rebuild your VPS\n"
                    "• Use `/manage` → SSH for terminal access\n"
                    "• Contact admin for upgrades or issues"
                ),
                inline=False
            )
            dm_embed.add_field(
                name="⌯⌲ Important Notes",
                value=(
                    "• Full root access via SSH\n"
                    "• Docker-ready with nesting and privileged mode\n"
                    "• Back up your data regularly"
                ),
                inline=False
            )
            dm_embed.set_footer(text="Powered by Xzy Hosting • Premium VPS Management")
            await ctx.author.send(embed=dm_embed)
        except discord.Forbidden:
            pass

    except Exception as e:
        # Refund credits on failure
        user_data[user_id]["credits"] += cost
        save_data()
        await ctx.send(embed=create_error_embed("Purchase Failed", f"Error: {str(e)}\n\nCredits refunded."))


@bot.hybrid_command(name='buyc')
async def buy_credits(ctx):
    """Get payment information"""
    embed = create_embed("💳 Purchase Credits", "Choose your payment method below:", 0x1a1a1a)
    embed.add_field(name="🇮🇳 UPI", value="```\n7384500229@fam\n```", inline=False)
    embed.add_field(name="📋 Next Steps", value="1. Pay\n2. Contact admin with transaction ID\n3. Receive credits", inline=False)
    try:
        await ctx.author.send(embed=embed)
        await ctx.send(embed=create_success_embed("Information Sent", "Payment details sent to your DMs!"))
    except discord.Forbidden:
        await ctx.send(embed=create_error_embed("DM Failed", "Enable DMs to receive payment info!"))


@bot.hybrid_command(name='plans')
async def show_plans(ctx):
    """Show available VPS plans"""
    embed = create_embed("💎 VPS Plans - Xzy Hosting", "Choose your perfect VPS plan:", 0x1a1a1a)
    plans_info = [
        ("🥉 Starter", "**RAM:** 4GB\n**CPU:** 1 Core\n**Storage:** 10GB\n**Intel:** 42 credits\n**AMD:** 83 credits"),
        ("🥈 Basic", "**RAM:** 8GB\n**CPU:** 1 Core\n**Storage:** 10GB\n**Intel:** 96 credits\n**AMD:** 164 credits"),
        ("🥇 Standard", "**RAM:** 12GB\n**CPU:** 2 Cores\n**Storage:** 10GB\n**Intel:** 192 credits\n**AMD:** 320 credits"),
        ("�� Pro", "**RAM:** 16GB\n**CPU:** 2 Cores\n**Storage:** 10GB\n**Intel:** 220 credits\n**AMD:** 340 credits"),
    ]
    for name, value in plans_info:
        embed.add_field(name=name, value=value, inline=True)
    embed.add_field(name="How to Buy", value="Use `/buywc <plan> <Intel/AMD>` to purchase\nUse `/buyc` for payment info", inline=False)
    await ctx.send(embed=embed)


@bot.hybrid_command(name='credits')
async def check_credits(ctx):
    """Check your credit balance"""
    user_id = str(ctx.author.id)
    if user_id not in user_data:
        user_data[user_id] = {"credits": 0}
        save_data()
    credits = user_data[user_id].get("credits", 0)
    embed = create_info_embed("💰 Credit Balance", f"{ctx.author.mention}, you have **{credits}** credits.")
    await ctx.send(embed=embed)


@bot.hybrid_command(name='adminc')
@is_admin()
async def admin_add_credits(ctx, user: discord.Member, amount: int):
    """Add credits to a user (Admin only)"""
    user_id = str(user.id)
    if user_id not in user_data:
        user_data[user_id] = {"credits": 0}
    user_data[user_id]["credits"] += amount
    save_data()
    await ctx.send(embed=create_success_embed("Credits Added",
                                              f"Added **{amount}** credits to {user.mention}. "
                                              f"New balance: **{user_data[user_id]['credits']}**"))


@bot.hybrid_command(name='adminrc')
@is_admin()
async def admin_remove_credits(ctx, user: discord.Member, amount: str):
    """Remove credits from a user (Admin only). Use 'all' to remove all."""
    user_id = str(user.id)
    if user_id not in user_data:
        user_data[user_id] = {"credits": 0}
    if amount.lower() == "all":
        removed = user_data[user_id]["credits"]
        user_data[user_id]["credits"] = 0
    else:
        removed = int(amount)
        user_data[user_id]["credits"] = max(0, user_data[user_id]["credits"] - removed)
    save_data()
    await ctx.send(embed=create_success_embed("Credits Removed",
                                              f"Removed **{removed}** credits from {user.mention}. "
                                              f"New balance: **{user_data[user_id]['credits']}**"))


@bot.hybrid_command(name='userinfo')
@is_admin()
async def user_info(ctx, user: discord.Member):
    """Get detailed user information (Admin only)"""
    user_id = str(user.id)
    credits = user_data.get(user_id, {}).get("credits", 0)
    embed = create_embed(f"👤 User Info - {user.name}", "", 0x1a1a1a)
    embed.add_field(name="User", value=f"{user.mention}\n**ID:** {user.id}", inline=False)
    embed.add_field(name="💰 Credits", value=f"**{credits}**", inline=True)
    vps_list = vps_data.get(user_id, [])
    if vps_list:
        vps_text = "\n".join([
            f"VPS {i+1}: `{v['container_name']}` | {v.get('status','?').upper()}"
            for i, v in enumerate(vps_list)
        ])
        embed.add_field(name="🖥️ VPS", value=vps_text, inline=False)
    else:
        embed.add_field(name="🖥️ VPS", value="No VPS owned", inline=False)
    is_admin_user = user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", [])
    embed.add_field(name="🛡️ Admin", value="Yes" if is_admin_user else "No", inline=True)
    await ctx.send(embed=embed)


@bot.hybrid_command(name='serverstats')
@is_admin()
async def server_stats(ctx):
    """Show server statistics (Admin only)"""
    total_vps = sum(len(v) for v in vps_data.values())
    running_vps = sum(1 for vl in vps_data.values() for v in vl if v.get('status') == 'running')
    total_credits = sum(u.get('credits', 0) for u in user_data.values())
    total_ram = sum(int(v['ram'].replace('GB', '')) for vl in vps_data.values() for v in vl)
    total_cpu = sum(int(v['cpu']) for vl in vps_data.values() for v in vl)

    embed = create_embed("📊 Server Statistics", "Current server overview", 0x1a1a1a)
    embed.add_field(name="👥 Users", value=f"**Total:** {len(user_data)}\n**Admins:** {len(admin_data.get('admins', [])) + 1}", inline=False)
    embed.add_field(name="🖥️ VPS", value=f"**Total:** {total_vps}\n**Running:** {running_vps}\n**Stopped:** {total_vps - running_vps}", inline=False)
    embed.add_field(name="💰 Economy", value=f"**Total Credits:** {total_credits}", inline=False)
    embed.add_field(name="📈 Resources", value=f"**Total RAM:** {total_ram}GB\n**Total CPU:** {total_cpu} cores", inline=False)
    await ctx.send(embed=embed)


@bot.hybrid_command(name='vpsinfo')
@is_admin()
async def vps_info(ctx, container_name: str = None):
    """Get VPS information (Admin only)"""
    if not container_name:
        all_vps = []
        for uid, vl in vps_data.items():
            try:
                u = await bot.fetch_user(int(uid))
                for i, v in enumerate(vl):
                    all_vps.append(f"**{u.name}** - VPS {i+1}: `{v['container_name']}` - {v.get('status','?').upper()} - Expiry: {format_expiry(v.get('expires', 'Never'))}")
            except:
                pass
        embed = create_embed("🖥️ All VPS", f"Total: {len(all_vps)}", 0x1a1a1a)
        for i in range(0, len(all_vps), 20):
            embed.add_field(name=f"VPS List ({i+1}-{i+20})", value="\n".join(all_vps[i:i+20]), inline=False)
        await ctx.send(embed=embed)
    else:
        found_vps = None
        found_user = None
        for uid, vl in vps_data.items():
            for v in vl:
                if v['container_name'] == container_name:
                    found_vps = v
                    found_user = await bot.fetch_user(int(uid))
                    break
            if found_vps:
                break
        if not found_vps:
            await ctx.send(embed=create_error_embed("Not Found", f"No VPS with name `{container_name}`"))
            return
        embed = create_embed(f"🖥️ VPS - {container_name}", f"Owned by {found_user.mention}", 0x1a1a1a)
        embed.add_field(name="Specs", value=f"**RAM:** {found_vps['ram']}\n**CPU:** {found_vps['cpu']} Cores", inline=True)
        embed.add_field(name="Status", value=f"**{found_vps.get('status','?').upper()}**", inline=True)
        embed.add_field(name="Expiry", value=format_expiry(found_vps.get('expires', 'Never')), inline=False)
        await ctx.send(embed=embed)


@bot.hybrid_command(name='restart-vps')
@is_admin()
async def restart_vps(ctx, container_name: str):
    """Restart a VPS (Admin only)"""
    await ctx.send(embed=create_info_embed("Restarting VPS", f"Restarting `{container_name}`..."))
    try:
        await execute_docker(f"docker restart {container_name}")
        # Restart SSH
        await asyncio.sleep(3)
        await docker_exec(container_name, "/usr/sbin/sshd || true", timeout=10)
        for vl in vps_data.values():
            for v in vl:
                if v['container_name'] == container_name:
                    v['status'] = 'running'
                    save_data()
                    break
        await ctx.send(embed=create_success_embed("VPS Restarted", f"`{container_name}` restarted successfully!"))
    except Exception as e:
        await ctx.send(embed=create_error_embed("Restart Failed", str(e)))


@bot.hybrid_command(name='backup-vps')
@is_admin()
async def backup_vps(ctx, container_name: str):
    """Create a Docker image snapshot of a VPS (Admin only)"""
    snapshot_name = f"{container_name}-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    await ctx.send(embed=create_info_embed("Creating Backup", f"Committing snapshot of `{container_name}`..."))
    try:
        await execute_docker(f"docker commit {container_name} {snapshot_name}")
        await ctx.send(embed=create_success_embed("Backup Created", f"Image `{snapshot_name}` created!"))
    except Exception as e:
        await ctx.send(embed=create_error_embed("Backup Failed", str(e)))


@bot.hybrid_command(name='restore-vps')
@is_admin()
async def restore_vps(ctx, container_name: str, snapshot_name: str):
    """Restore a VPS from a Docker snapshot image (Admin only)"""
    await ctx.send(embed=create_info_embed("Restoring VPS", f"Restoring `{container_name}` from `{snapshot_name}`..."))
    try:
        # Find VPS info for port/password
        found_vps = None
        for vl in vps_data.values():
            for v in vl:
                if v['container_name'] == container_name:
                    found_vps = v
                    break
        if not found_vps:
            await ctx.send(embed=create_error_embed("Not Found", f"No VPS data for `{container_name}`"))
            return

        # Stop and remove current container
        try:
            await execute_docker(f"docker stop {container_name}")
        except:
            pass
        await execute_docker(f"docker rm -f {container_name}")

        # Recreate from snapshot image
        ssh_port = found_vps.get("ssh_port", get_next_ssh_port())
        run_cmd = (
            f"docker run -d "
            f"--name {container_name} "
            f"-p {ssh_port}:22 "
            f"--restart=unless-stopped "
            f"{snapshot_name} "
            f"sleep infinity"
        )
        await execute_docker(run_cmd)
        await asyncio.sleep(2)
        await docker_exec(container_name, "/usr/sbin/sshd || true", timeout=10)
        found_vps["status"] = "running"
        save_data()
        await ctx.send(embed=create_success_embed("VPS Restored", f"`{container_name}` restored from `{snapshot_name}`1"))
    except Exception as e:
        await ctx.send(embed=create_error_embed("Restore Failed", str(e)))


@bot.hybrid_command(name='list-snapshots')
@is_admin()
async def list_snapshots(ctx, container_name: str):
    """List Docker image snapshots for a VPS (Admin only)"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "images", "--format", "{{.Repository}}:{{.Tag}} ({{.Size}})",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        all_images = stdout.decode().strip().split('\n')
        snapshots = [img for img in all_images if img.startswith(container_name + "-backup-")]
        if snapshots:
            embed = create_embed(f"📸 Snapshots for {container_name}", f"Found {len(snapshots)} snapshots", 0x1a1a1a)
            embed.add_field(name="Snapshots", value="\n".join([f"• `{s}`" for s in snapshots]), inline=False)
        else:
            embed = create_info_embed("No Snapshots", f"No snapshots found for `{container_name}`")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Error", str(e)))


@bot.hybrid_command(name='exec')
@is_admin()
async def execute_command(ctx, container_name: str, *, command: str):
    """Execute a command inside a VPS container (Admin only)"""
    await ctx.send(embed=create_info_embed("Executing Command", f"Running in `{container_name}`..."))
    try:
        stdout, stderr, rc = await docker_exec(container_name, command, timeout=30)
        embed = create_embed(f"Command Output - {container_name}", f"Command: `{command}`", 0x1a1a1a)
        if stdout:
            out = stdout[:1000] + "\n...(truncated)" if len(stdout) > 1000 else stdout
            embed.add_field(name="📤 Output", value=f"```\n{out}\n```", inline=False)
        if stderr:
            err = stderr[:1000] + "\n...(truncated)" if len(stderr) > 1000 else stderr
            embed.add_field(name="⚠️ Stderr", value=f"```\n{err}\n```", inline=False)
        embed.add_field(name="🔄 Exit Code", value=f"**{rc}**", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Execution Failed", str(e)))


@bot.hybrid_command(name='stop-vps-all')
@is_admin()
async def stop_all_vps(ctx):
    """Stop all VPS containers (Admin only)"""
    await ctx.send(embed=create_warning_embed("Stopping All VPS",
                                              "⚠️ This will stop ALL running VPS. Continue?"))

    class ConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)

        @discord.ui.button(label="Stop All VPS", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, item: discord.ui.Button):
            await interaction.response.defer()
            stopped_count = 0
            errors = []
            for vl in vps_data.values():
                for v in vl:
                    if v.get('status') == 'running':
                        try:
                            proc = await asyncio.create_subprocess_exec(
                                "docker", "stop", v['container_name'],
                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                            )
                            await proc.communicate()
                            v['status'] = 'stopped'
                            stopped_count += 1
                        except Exception as e:
                            errors.append(str(e))
            save_data()
            await refresh_vps_presence()
            embed = create_success_embed("All VPS Stopped", f"Stopped **{stopped_count}** containers.")
            if errors:
                embed.add_field(name="Errors", value="\n".join(errors[:5]), inline=False)
            await interaction.followup.send(embed=embed)

        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, item: discord.ui.Button):
            await interaction.response.edit_message(embed=create_info_embed("Cancelled", "Operation cancelled."))

    await ctx.send(view=ConfirmView())


@bot.hybrid_command(name='cpu-monitor')
@is_admin()
async def cpu_monitor_control(ctx, action: str = "status"):
    """Control CPU monitoring (Admin only)"""
    global cpu_monitor_active
    if action.lower() == "status":
        status = "Active" if cpu_monitor_active else "Inactive"
        embed = create_embed("CPU Monitor Status", f"Status: **{status}**",
                             0x00ccff if cpu_monitor_active else 0xffaa00)
        embed.add_field(name="Threshold", value=f"{CPU_THRESHOLD}%", inline=True)
        embed.add_field(name="Check Interval", value=f"{CHECK_INTERVAL}s", inline=True)
        await ctx.send(embed=embed)
    elif action.lower() == "enable":
        cpu_monitor_active = True
        await ctx.send(embed=create_success_embed("CPU Monitor Enabled"))
    elif action.lower() == "disable":
        cpu_monitor_active = False
        await ctx.send(embed=create_warning_embed("CPU Monitor Disabled"))
    else:
        await ctx.send(embed=create_error_embed("Invalid Action", "Use: `/cpu-monitor <status|enable|disable>`"))


@bot.hybrid_command(name='admin-add')
@is_main_admin()
async def admin_add(ctx, user: discord.Member):
    user_id = str(user.id)
    if user_id not in admin_data["admins"]:
        admin_data["admins"].append(user_id)
        save_data()
    await ctx.send(embed=create_success_embed("Admin Added", f"{user.mention} is now an admin."))


@bot.hybrid_command(name='admin-remove')
@is_main_admin()
async def admin_remove(ctx, user: discord.Member):
    user_id = str(user.id)
    if user_id in admin_data["admins"]:
        admin_data["admins"].remove(user_id)
        save_data()
    await ctx.send(embed=create_success_embed("Admin Removed", f"{user.mention} is no longer an admin."))


@bot.hybrid_command(name='admin-list')
@is_main_admin()
async def admin_list(ctx):
    admins = []
    for aid in admin_data.get("admins", []):
        try:
            u = await bot.fetch_user(int(aid))
            admins.append(f"• {u.mention} ({u.name})")
        except:
            admins.append(f"• Unknown ({aid})")
    embed = create_info_embed("Admin List", "\n".join(admins) if admins else "No admins")
    await ctx.send(embed=embed)




# ─── Port Forwarding ──────────────────────────────────────────────────────────

@bot.hybrid_command(name="pcreate")
async def port_create(ctx, vps_id: str, port: Optional[int] = None):
    """Create a port forward for a VPS."""

    user_id = str(ctx.author.id)
    user_vps = vps_data.get(user_id, [])

    target = None

    for index, vps in enumerate(user_vps):
        if (
            str(vps.get("id", "")) == str(vps_id)
            or str(vps.get("vps_id", "")) == str(vps_id)
            or str(index + 1) == str(vps_id)
        ):
            target = vps
            break

    if not target:
        await ctx.send(
            embed=create_error_embed(
                "VPS Not Found",
                f"No VPS found with ID `{vps_id}`."
            )
        )
        return

    # Default random 2-digit port
    if port is None:
        used = set()

        for values in port_forwards.values():
            for item in values:
                try:
                    used.add(int(item["port"]))
                except:
                    pass

        available = [
            x for x in range(10, 100)
            if x not in used and x != 22
        ]

        if not available:
            await ctx.send(
                embed=create_error_embed(
                    "No Port Available",
                    "No free 2-digit port is available."
                )
            )
            return

        port = random.choice(available)

    if port < 10 or port > 65535:
        await ctx.send(
            embed=create_error_embed(
                "Invalid Port",
                "Port must be between `10` and `65535`."
            )
        )
        return

    # Port 22 is reserved for SSH
    if port == 22:
        await ctx.send(
            embed=create_error_embed(
                "Port 22 Reserved",
                "Port `22` is reserved for SSH."
            )
        )
        return

    key = str(ctx.author.id)

    if key not in port_forwards:
        port_forwards[key] = []

    # Prevent duplicate port for same user
    if any(int(x["port"]) == port for x in port_forwards[key]):
        await ctx.send(
            embed=create_error_embed(
                "Port Already Exists",
                f"Port `{port}` is already allocated."
            )
        )
        return

    forward_id = random.randint(100000, 999999)

    record = {
        "id": forward_id,
        "vps_id": str(vps_id),
        "container_name": target.get("container_name", ""),
        "port": port,
        "target_port": port,
        "protocol": "tcp",
        "created_by": key,
        "created_at": datetime.now().isoformat()
    }

    port_forwards[key].append(record)

    # Save inside user VPS data too
    target.setdefault("port_forwards", [])
    target["port_forwards"].append(record)

    save_data()

    await ctx.send(
        embed=create_success_embed(
            "🔌 Port Forwarded",
            f"Port `{port}` has been allocated to VPS `{vps_id}`.\n\n"
            f"**Forward:** `HOST:{port} → VPS:{port}`\n"
            f"**Protocol:** `TCP`\n"
            f"**Port ID:** `{forward_id}`\n\n"
            "🔐 SSH port `22` remains reserved for SSH/Tailscale."
        )
    )


@bot.hybrid_command(name="ports")
async def ports_help(ctx):
    """Show port forwarding information."""

    embed = create_embed(
        "📚 Xzy Hosting Help - 🔌 Port Forwarding",
        "Manage port forwarding for your VPS",
        0x00ccff
    )

    embed.add_field(
        name="⌯⌲ Commands",
        value=(
            "**`/ports`** - Port forwarding help\n"
            "**`/pcreate <vps_id> <port>`** - Add port forward\n"
            "**`/pcreate <vps_id>`** - Add random 2-digit port\n"
            "**`/ports list`** - List your port forwards\n"
            "**`/ports remove <id>`** - Remove port forward"
        ),
        inline=False
    )

    embed.add_field(
        name="⌯⌲ SSH",
        value=(
            "**Port `22`** is reserved for SSH.\n"
            "Tailscale private IP uses SSH on port `22`."
        ),
        inline=False
    )

    embed.add_field(
        name="⌯⌲ Navigation",
        value=(
            "• Use `/pcreate <vps_id>` for a random 2-digit port\n"
            "• Use `/pcreate <vps_id> <port>` for a specific port\n"
            "• Slash commands: `/`"
        ),
        inline=False
    )

    embed.set_footer(text="Xzy Hosting • Cloud Services")

    await ctx.send(embed=embed)


# ─── Scrollable Help System ────────────────────────────────────────────────────

def build_help_pages(is_user_admin, is_user_main_admin):
    pages = {}

    # Page 2: User Commands
    user_embed = create_embed("👤 User Commands", "VPS management commands for all users:", 0x00ff88)
    user_embed.add_field(name="🖥️ VPS Management", value=(
        "`/manage` — Manage your VPS (Start/Stop/SSH/Rebuild)\n"
        "`/manage [@user]` — Admin: manage another user's VPS\n"
        "`/share-user @user <#>` — Share VPS access\n"
        "`/share-ruser @user <#>` — Revoke shared access\n"
        "`/manage-shared @owner <#>` — Access shared VPS"
    ), inline=False)
    user_embed.add_field(name="🏷️ VPS Tools", value=(
        "`/rename-vps <#> <new_name>` — Give your VPS a nickname\n"
        "`/vps-note <#> <note>` — Add a note to your VPS\n"
        "`/ping-vps <#>` — Ping your VPS container\n"
        "`/uptime-vps <#>` — Check VPS uptime\n"
        "`/myinfo` — View your profile & VPS summary"
    ), inline=False)
    user_embed.add_field(
        name="🔌 Port Forwarding",
        value=(
            "`/ports` — Port forwarding help\n"
            "`/pcreate <vps_id> <port>` — Create a port forward\n"
            "`/pcreate <vps_id>` — Create random 2-digit port\n"
            "Port `22` — Reserved for SSH/Tailscale"
        ),
        inline=False
    )

    port_embed = create_embed(
        "📚 Xzy Hosting Help - 🔌 Port Forwarding",
        "Manage port forwarding for your VPS",
        0x00ccff
    )

    port_embed.add_field(
        name="⌯⌲ Commands",
        value=(
            "**`/ports`** - Port forwarding help\n"
            "**`/pcreate <vps_num> <port>`** - Add port forward\n"
            "**`/pcreate <vps_num>`** - Random 2–4 digit port\n"
            "**`/ports list`** - List your port forwards\n"
            "**`/ports remove <id>`** - Remove port forward"
        ),
        inline=False
    )

    port_embed.add_field(
        name="🔐 SSH / Tailscale",
        value=(
            "**Port `22`** is reserved for SSH/Tailscale.\n"
            "Example: `/pcreate 1 22`"
        ),
        inline=False
    )

    port_embed.add_field(
        name="⌯⌲ Navigation",
        value=(
            "• Use dropdown to switch categories\n"
            "• Select one VPS using its number\n"
            "• Random ports are `10–9999`\n"
            "• Slash commands: `/`"
        ),
        inline=False
    )

    port_embed.set_footer(text="Xzy Hosting • Cloud Services")
    pages["ports"] = port_embed

    pages["user"] = user_embed

    # Page 3: Credits & Plans
    credits_embed = create_embed("💰 Credits & Plans", "Purchase plans and manage credits:", 0xffaa00)
    credits_embed.add_field(name="💳 Commands", value=(
        "`/plans` — View available VPS plans & prices\n"
        "`/buyc` — Get payment info (UPI)\n"
        "`/buywc <plan> <Intel/AMD>` — Buy VPS with credits\n"
        "`/credits` — Check your credit balance\n"
        "`/transfer @user <amount>` — Send credits to another user"
    ), inline=False)
    credits_embed.add_field(name="📦 Available Plans", value=(
        "🥉 **Starter** — 4GB RAM | 1 CPU | Intel: 42cr / AMD: 83cr\n"
        "🥈 **Basic** — 8GB RAM | 1 CPU | Intel: 96cr / AMD: 164cr\n"
        "🥇 **Standard** — 12GB RAM | 2 CPU | Intel: 192cr / AMD: 320cr\n"
        "💎 **Pro** — 16GB RAM | 2 CPU | Intel: 220cr / AMD: 340cr"
    ), inline=False)
    pages["credits"] = credits_embed

    # Page 4: VPS Tools
    tools_embed = create_embed("🔧 VPS Tools", "Extra tools to manage & monitor your VPS:", 0x00ccff)
    tools_embed.add_field(name="📊 Monitoring", value=(
        "`/ping-vps <#>` — Ping VPS container (check if alive)\n"
        "`/uptime-vps <#>` — Show how long VPS has been running\n"
        "`/myinfo` — Your full profile: credits, VPS list, notes"
    ), inline=False)
    tools_embed.add_field(name="🏷️ Customization", value=(
        "`/rename-vps <#> <name>` — Set a nickname for your VPS\n"
        "`/vps-note <#> <text>` — Add/update a note on your VPS\n"
        "  e.g. `/vps-note 1 My Minecraft server`"
    ), inline=False)
    tools_embed.add_field(name="💸 Economy", value=(
        "`/transfer @user <amount>` — Send credits to a friend\n"
        "`/leaderboard` — Top 10 credit holders\n"
        "`/botstatus` — Show bot stats & uptime"
    ), inline=False)
    pages["tools"] = tools_embed

    # Page 5: Extras
    extras_embed = create_embed("📢 Extras & Fun", "Announcements, leaderboard, and more:", 0xff6b9d)
    extras_embed.add_field(name="📣 Announcements", value=(
        "`/announce <message>` — Admin: broadcast to all VPS owners via DM\n"
        "`/botstatus` — Bot uptime, total VPS, active users\n"
        "`/leaderboard` — Top credit holders on the server"
    ), inline=False)
    extras_embed.add_field(name="ℹ️ Info", value=(
        "`/help` — Open this help menu\n"
        "`/plans` — VPS plan pricing\n"
        "`/myinfo` — Your personal dashboard"
    ), inline=False)
    pages["extras"] = extras_embed

    # Page 6: Admin Panel
    admin_embed = create_embed("🛡️ Admin Panel", "Admin-only VPS management commands:", 0xff3366)
    admin_embed.add_field(name="🖥️ VPS Control", value=(
            "`/create @user <ram_GB> <cpu_cores> <disk_GB>` — Create VPS (Mode → OS selection)\n"
            "`/delete-vps @user <#> <reason>` — Delete a user's VPS\n"
            "`/restart-vps <container>` — Restart a VPS container\n"
            "`/stop-vps-all` — Emergency stop ALL VPS\n"
            "`/exec <container> <cmd>` — Run command inside VPS"
    ), inline=False)
    admin_embed.add_field(name="💾 Backup & Restore", value=(
            "`/backup-vps <container>` — Create Docker image snapshot\n"
            "`/restore-vps <container> <snapshot>` — Restore from snapshot\n"
            "`/list-snapshots <container>` — List all snapshots"
    ), inline=False)
    admin_embed.add_field(name="📊 Info & Economy", value=(
            "`/userinfo @user` — Full user info + VPS list\n"
            "`/serverstats` — Server overview stats\n"
            "`/vpsinfo [container]` — VPS details\n"
            "`/list-all` — All VPS overview\n"
            "`/adminc @user <amount>` — Add credits\n"
            "`/adminrc @user <amount/all>` — Remove credits\n"
            "`/announce <msg>` — DM all VPS owners\n"
            "`/msg select chenel #channel msg <message>` — Send exact message to a channel\n"
            "`/cpu-monitor <status|enable|disable>` — CPU monitor control\n"
            "`/maintenance <on/off>` — Toggle maintenance mode"
    ), inline=False)
    admin_embed.add_field(name="⏳ Expire Management", value=(
            "`/setexpire @user <vps#> <days>` — Set VPS expiry\n"
            "`/extendexpire @user <vps#> <days>` — Extend expiry\n"
            "`/removeexpire @user <vps#>` — Remove expiry (set to Never)\n"
            "`/checkexpire [@user]` — Check expiry status"
    ), inline=False)
    pages["admin"] = admin_embed

    # Page 7: Main Admin
    mainadmin_embed = create_embed("👑 Main Admin", "Exclusive main admin commands:", 0xffd700)
    mainadmin_embed.add_field(name="👥 Admin Management", value=(
            "`/admin-add @user` — Promote user to admin\n"
            "`/admin-remove @user` — Remove admin role\n"
            "`/admin-list` — View all admins"
    ), inline=False)
    pages["mainadmin"] = mainadmin_embed

    return pages


@bot.hybrid_command(name='help')
async def show_help(ctx):
    """Show scrollable categorized help"""
    user_id = str(ctx.author.id)
    is_user_admin = user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", [])
    is_user_main_admin = user_id == str(MAIN_ADMIN_ID)

    pages = build_help_pages(is_user_admin, is_user_main_admin)

    options = [
        discord.SelectOption(label="👤 User Commands", description="VPS manage, share, tools", value="user", emoji="👤"),
        discord.SelectOption(label="🔌 Port Forwarding", description="Manage VPS ports", value="ports", emoji="🔌"),
        discord.SelectOption(label="💰 Credits & Plans", description="Buy VPS, check plans", value="credits", emoji="💰"),
        discord.SelectOption(label="🔧 VPS Tools", description="Rename, notes, ping, uptime", value="tools", emoji="🔧"),
        discord.SelectOption(label="📢 Extras", description="Announcements, leaderboard", value="extras", emoji="📢"),
    ]
    options.append(discord.SelectOption(label="🛡️ Admin Panel", description="Admin VPS commands", value="admin", emoji="🛡️"))
    options.append(discord.SelectOption(label="👑 Main Admin", description="Admin management", value="mainadmin", emoji="👑"))

    class HelpSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="📂 Select a category...", options=options, min_values=1, max_values=1)

        async def callback(self, interaction: discord.Interaction):
            selected = self.values[0]
            embed = pages.get(selected, pages["user"])
            await interaction.response.edit_message(embed=embed, view=self.view)

    class HelpView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(HelpSelect())

    await ctx.send(embed=pages["user"], view=HelpView())



# ─── Admin Channel Message ────────────────────────────────────────────────────

@bot.hybrid_command(name='msg')
@is_admin()
async def admin_channel_message(ctx, *, raw: str = ""):
    """
    Admin-only channel message command.

    Usage:
    /msg select channel #channel msg Your message
    """

    # Expected:
    # select chenel #channel msg <message>

    parts = raw.split(maxsplit=3)

    if len(parts) < 4:
        await ctx.send(
            embed=create_error_embed(
                "❌ Invalid Command",
                "Use:\n`/msg select channel #channel msg Your message`"
            ),
            delete_after=8
        )
        return

    action = parts[0].lower()
    channel_word = parts[1].lower()
    channel_mention = parts[2]
    message_part = parts[3]

    if action != "select" or channel_word not in ("chenel", "channel"):
        await ctx.send(
            embed=create_error_embed(
                "❌ Invalid Format",
                "Use:\n`/msg select channel #channel msg Your message`"
            ),
            delete_after=8
        )
        return

    if not message_part.lower().startswith("msg "):
        await ctx.send(
            embed=create_error_embed(
                "❌ Missing Message",
                "Use:\n`/msg select channel #channel msg Your message`"
            ),
            delete_after=8
        )
        return

    # IMPORTANT:
    # Everything after "msg " is preserved exactly as entered.
    message_text = message_part[4:]

    if not message_text:
        await ctx.send(
            embed=create_error_embed(
                "❌ Empty Message",
                "Please write a message after `msg`."
            ),
            delete_after=8
        )
        return

    # Resolve #channel mention safely
    channel = None

    if channel_mention.startswith("<#") and channel_mention.endswith(">"):
        try:
            channel_id = int(channel_mention[2:-1])
            channel = ctx.guild.get_channel(channel_id)
        except ValueError:
            channel = None

    # Fallback: try channel name
    if channel is None:
        clean_name = channel_mention.lstrip("#")
        channel = discord.utils.get(
            ctx.guild.text_channels,
            name=clean_name
        )

    if channel is None:
        await ctx.send(
            embed=create_error_embed(
                "❌ Channel Not Found",
                "Please select a valid server text channel."
            ),
            delete_after=8
        )
        return

    if not isinstance(channel, discord.TextChannel):
        await ctx.send(
            embed=create_error_embed(
                "❌ Invalid Channel",
                "Please select a text channel."
            ),
            delete_after=8
        )
        return

    try:
        # Send EXACTLY what admin typed after "msg "
        await channel.send(
            message_text,
            allowed_mentions=discord.AllowedMentions.all()
        )

        # Delete the admin command so it doesn't clutter the channel
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Confirmation in the command channel
        await ctx.send(
            embed=create_success_embed(
                "📢 Message Sent",
                f"Message successfully sent to {channel.mention}."
            ),
            delete_after=5
        )

    except discord.Forbidden:
        await ctx.send(
            embed=create_error_embed(
                "❌ Permission Denied",
                f"I don't have permission to send messages in {channel.mention}."
            )
        )

    except Exception as e:
        await ctx.send(
            embed=create_error_embed(
                "❌ Message Failed",
                str(e)[:1000]
            )
        )


# ─── New Cool Features ──────────────────────────────────────────────────────────

maintenance_mode = False

@bot.hybrid_command(name='rename-vps')
async def rename_vps(ctx, vps_number: int, *, new_name: str):
    """Give your VPS a custom nickname"""
    user_id = str(ctx.author.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Invalid VPS", "VPS not found."))
        return
    if len(new_name) > 30:
        await ctx.send(embed=create_error_embed("Name Too Long", "Nickname must be 30 characters or less."))
        return
    vps_list[vps_number - 1]["nickname"] = new_name
    save_data()
    await ctx.send(embed=create_success_embed("VPS Renamed", f"VPS #{vps_number} is now called **{new_name}**!"))


@bot.hybrid_command(name='vps-note')
async def vps_note(ctx, vps_number: int, *, note: str):
    """Add a note to your VPS"""
    user_id = str(ctx.author.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Invalid VPS", "VPS not found."))
        return
    vps_list[vps_number - 1]["note"] = note[:200]
    save_data()
    await ctx.send(embed=create_success_embed("Note Saved", f"Note added to VPS #{vps_number}:\n> {note[:200]}"))


@bot.hybrid_command(name='ping-vps')
async def ping_vps(ctx, vps_number: int):
    """Ping your VPS container to check if it's alive"""
    user_id = str(ctx.author.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Invalid VPS", "VPS not found."))
        return
    vps = vps_list[vps_number - 1]
    container = vps["container_name"]
    nickname = vps.get("nickname", f"VPS #{vps_number}")
    msg = await ctx.send(embed=create_info_embed("Pinging...", f"Checking `{container}`..."))
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", "--format={{.State.Running}}", container,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        elapsed = int((time.time() - start) * 1000)
        is_running = stdout.decode().strip() == "true"
        if is_running:
            embed = create_success_embed("🏓 Pong!", f"**{nickname}** is alive!\n⚡ Response: `{elapsed}ms`")
        else:
            embed = create_error_embed("💀 No Response", f"**{nickname}** container is not running.")
        await msg.edit(embed=embed)
    except Exception as e:
        await msg.edit(embed=create_error_embed("Ping Failed", str(e)))


@bot.hybrid_command(name='uptime-vps')
async def uptime_vps(ctx, vps_number: int):
    """Check VPS uptime"""
    user_id = str(ctx.author.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Invalid VPS", "VPS not found."))
        return
    vps = vps_list[vps_number - 1]
    container = vps["container_name"]
    nickname = vps.get("nickname", f"VPS #{vps_number}")
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", "--format={{.State.StartedAt}}", container,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        started_at_str = stdout.decode().strip()
        # Parse docker time format
        started_at = datetime.fromisoformat(started_at_str[:19])
        uptime_delta = datetime.utcnow() - started_at
        days = uptime_delta.days
        hours, rem = divmod(uptime_delta.seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        embed = create_success_embed(f"⏱️ Uptime — {nickname}", f"Container has been running for:\n```{uptime_str}```")
        embed.add_field(name="Started At", value=f"`{started_at_str[:19]} UTC`", inline=False)
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Uptime Error", str(e)))


@bot.hybrid_command(name='myinfo')
async def my_info(ctx):
    """Show your personal dashboard"""
    user_id = str(ctx.author.id)
    credits = user_data.get(user_id, {}).get("credits", 0)
    vps_list = vps_data.get(user_id, [])
    embed = create_embed(f"👤 {ctx.author.name}'s Dashboard", "", 0x5865F2)
    embed.set_thumbnail(url=ctx.author.display_avatar.url)
    embed.add_field(name="💰 Credits", value=f"**{credits}**", inline=True)
    embed.add_field(name="🖥️ VPS Count", value=f"**{len(vps_list)}**", inline=True)
    embed.add_field(name="📅 Account", value=f"Joined: {ctx.author.created_at.strftime('%Y-%m-%d')}", inline=True)
    if vps_list:
        vps_text = ""
        for i, v in enumerate(vps_list):
            nickname = v.get("nickname", f"VPS {i+1}")
            status_icon = "🟢" if v.get("status") == "running" else "🔴"
            note = f" — _{v['note']}_" if v.get("note") else ""
            vps_text += f"{status_icon} **{nickname}** (`{v['container_name']}`){note}\n"
        embed.add_field(name="🖥️ Your VPS", value=vps_text, inline=False)
    else:
        embed.add_field(name="🖥️ Your VPS", value="No VPS yet. Use `/buywc` to get one!", inline=False)
    await ctx.send(embed=embed)


@bot.hybrid_command(name='transfer')
async def transfer_credits(ctx, target: discord.Member, amount: int):
    """Transfer credits to another user"""
    if amount <= 0:
        await ctx.send(embed=create_error_embed("Invalid Amount", "Amount must be positive."))
        return
    if target.id == ctx.author.id:
        await ctx.send(embed=create_error_embed("Invalid Target", "You can't transfer to yourself!"))
        return
    sender_id = str(ctx.author.id)
    target_id = str(target.id)
    if sender_id not in user_data:
        user_data[sender_id] = {"credits": 0}
    if user_data[sender_id]["credits"] < amount:
        await ctx.send(embed=create_error_embed("Insufficient Credits",
            f"You only have **{user_data[sender_id]['credits']}** credits."))
        return
    if target_id not in user_data:
        user_data[target_id] = {"credits": 0}
    user_data[sender_id]["credits"] -= amount
    user_data[target_id]["credits"] += amount
    save_data()
    embed = create_success_embed("💸 Transfer Complete",
        f"{ctx.author.mention} sent **{amount}** credits to {target.mention}!")
    embed.add_field(name="Your Balance", value=f"**{user_data[sender_id]['credits']}** credits", inline=True)
    await ctx.send(embed=embed)
    try:
        await target.send(embed=create_info_embed("💰 Credits Received",
            f"You received **{amount}** credits from {ctx.author.mention}!\nNew balance: **{user_data[target_id]['credits']}**"))
    except discord.Forbidden:
        pass


@bot.hybrid_command(name='leaderboard')
async def leaderboard(ctx):
    """Show top 10 credit holders"""
    sorted_users = sorted(user_data.items(), key=lambda x: x[1].get("credits", 0), reverse=True)[:10]
    embed = create_embed("🏆 Credit Leaderboard", "Top 10 credit holders:", 0xffd700)
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = []
    for i, (uid, data) in enumerate(sorted_users):
        try:
            u = await bot.fetch_user(int(uid))
            name = u.name
        except:
            name = f"User#{uid[:4]}"
        lines.append(f"{medals[i]} **{name}** — {data.get('credits', 0)} credits")
    embed.add_field(name="Rankings", value="\n".join(lines) if lines else "No data yet.", inline=False)
    await ctx.send(embed=embed)


@bot.hybrid_command(name='botstatus')
async def bot_status(ctx):
    """Show bot status and stats"""
    runtime = max(0, int(time.monotonic() - BOT_START_TIME))
    total_vps = sum(len(v) for v in vps_data.values())
    running_vps = sum(1 for vl in vps_data.values() for v in vl if v.get("status") == "running")
    embed = create_embed("🤖 Bot Status", "Xzy Hosting VPS Manager", 0x00ff88)
    embed.add_field(name="⏱️ Uptime", value=f"`{format_uptime(runtime)}`", inline=True)
    embed.add_field(name="🖥️ Total VPS", value=f"**{total_vps}** ({running_vps} running)", inline=True)
    embed.add_field(name="👥 Users", value=f"**{len(user_data)}**", inline=True)
    embed.add_field(name="🔧 Maintenance", value="🔴 ON" if maintenance_mode else "🟢 OFF", inline=True)
    embed.add_field(name="📡 Latency", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    await ctx.send(embed=embed)


@bot.hybrid_command(name='announce')
@is_admin()
async def announce(ctx, *, message: str):
    """Send an announcement DM to all VPS owners (Admin only)"""
    sent = 0
    failed = 0
    announce_embed = create_embed("📢 Announcement", message, 0xffaa00)
    announce_embed.add_field(name="From", value=f"**Xzy Hosting Team** ({ctx.author.mention})", inline=False)
    status_msg = await ctx.send(embed=create_info_embed("Sending Announcement", "Broadcasting to all VPS owners..."))
    for uid in vps_data.keys():
        try:
            user = await bot.fetch_user(int(uid))
            await user.send(embed=announce_embed)
            sent += 1
            await asyncio.sleep(0.5)  # Rate limit protection
        except:
            failed += 1
    await status_msg.edit(embed=create_success_embed("Announcement Sent",
        f"✅ Delivered to **{sent}** users\n❌ Failed: **{failed}** (DMs closed)"))


@bot.hybrid_command(name='maintenance')
@is_admin()
async def maintenance_toggle(ctx, mode: str):
    """Toggle maintenance mode (Admin only)"""
    global maintenance_mode
    if mode.lower() == "on":
        maintenance_mode = True
        # Keep the bot's status red (DND) during maintenance.
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.CustomActivity(name="🔴 Under Maintenance")
        )
        await ctx.send(embed=create_warning_embed("🔴 Maintenance Mode ON",
            "Bot is now in maintenance mode.\n"
            "• ALL commands blocked for non-admins\n"
            "• DM commands also blocked\n"
            "• Bot status set to Idle"))
    elif mode.lower() == "off":
        maintenance_mode = False
        # Restore normal red (DND) status.
        await refresh_vps_presence()
        await ctx.send(embed=create_success_embed("🟢 Maintenance Mode OFF",
            "Bot is back to normal operation."))
    else:
        await ctx.send(embed=create_error_embed("Invalid", "Use: `/maintenance on` or `/maintenance off`"))


# ─── Maintenance mode global check ────────────────────────────────────────────
@bot.check
async def maintenance_check(ctx):
    global maintenance_mode
    if not maintenance_mode:
        return True

    user_id = str(ctx.author.id)
    is_user_admin = user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", [])

    # Admins can still use maintenance toggle itself
    if is_user_admin and ctx.command and ctx.command.name == 'maintenance':
        return True

    # Block EVERYONE else — no help, no botstatus, nothing
    if not is_user_admin:
        await ctx.send(embed=create_warning_embed(
            "🔴 Under Maintenance",
            "The bot is currently under maintenance.\n"
            "All commands are disabled until maintenance is complete."
        ))
        return False

    return True


# ─── Message handling ─────────────────────────────────────────────────────────
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # ─── XZY_HOSTING_AI_PING_HANDLER ───────────────────────────────────────────
    #
    # AI works ONLY when a user mentions the bot.
    # This does NOT create !ai and does NOT interfere with existing commands.

    if (
        message.guild is not None
        and bot.user is not None
        and bot.user in message.mentions
        and not message.author.bot
    ):
        try:
            # Remove the bot mention from the message.
            question = message.content

            question = question.replace(
                f"<@{bot.user.id}>",
                ""
            )

            question = question.replace(
                f"<@!{bot.user.id}>",
                ""
            )

            question = question.strip()

            if question:

                # Built-in Xzy Hosting identity responses
                direct = xzy_hosting_ai_direct_answer(question)

                if direct:
                    answer = direct
                else:
                    if not OPENROUTER_API_KEY:
                        answer = (
                            "🤖 Xzy Hosting AI is currently not configured.\n"
                            "Please contact the Xzy Hosting administrator."
                        )
                    else:
                        async with message.channel.typing():
                            answer = await xzy_hosting_ai_answer(question)

                # Discord message limit
                if len(answer) <= 3900:
                    await message.reply(
                        answer,
                        mention_author=False
                    )
                else:
                    for start in range(0, len(answer), 3900):
                        await message.channel.send(
                            answer[start:start + 3900]
                        )

        except Exception as ai_error:
            logger.error(
                f"Xzy Hosting AI error: {ai_error}"
            )

            await message.reply(
                "🤖 AI request failed. Please try again.",
                mention_author=False
            )

    # Commands are slash-only; do not process legacy prefix commands.

# ─── Expire System ─────────────────────────────────────────────────────────────

@bot.hybrid_command(name='setexpire')
@is_admin()
async def set_expire(ctx, user: discord.Member, vps_number: int, days: int):
    """Set VPS expiry — /setexpire @user <vps#> <days>"""
    user_id = str(user.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Not Found", f"{user.mention} has no VPS #{vps_number}."))
        return
    import datetime as dt
    exp_date = (datetime.utcnow() + dt.timedelta(days=days)).isoformat()
    vps_list[vps_number - 1]['expires'] = exp_date
    save_data()
    vps_name = vps_list[vps_number - 1]['container_name']
    await ctx.send(embed=create_success_embed("Expiry Set",
        f"✅ {user.mention}'s **VPS #{vps_number}** (`{vps_name}`) expires on `{exp_date[:10]}` ({days}d from now)."))
    try:
        await user.send(embed=create_warning_embed("⏳ VPS Expiry Set",
            f"Your **VPS #{vps_number}** (`{vps_name}`) has been set to expire on **{exp_date[:10]}** ({days} days).\n"
            f"Contact an admin to extend it before it expires!"))
    except discord.Forbidden:
        pass


@bot.hybrid_command(name='extendexpire')
@is_admin()
async def extend_expire(ctx, user: discord.Member, vps_number: int, days: int):
    """Extend VPS expiry — /extendexpire @user <vps#> <days>"""
    user_id = str(user.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Not Found", f"{user.mention} has no VPS #{vps_number}."))
        return
    import datetime as dt
    vps = vps_list[vps_number - 1]
    current = vps.get('expires', 'Never')
    if current == 'Never' or not current:
        base = datetime.utcnow()
    else:
        try:
            base = datetime.fromisoformat(current)
            if base < datetime.utcnow():
                base = datetime.utcnow()
        except:
            base = datetime.utcnow()
    new_exp = (base + dt.timedelta(days=days)).isoformat()
    vps['expires'] = new_exp
    save_data()
    vps_name = vps['container_name']
    await ctx.send(embed=create_success_embed("Expiry Extended",
        f"✅ {user.mention}'s **VPS #{vps_number}** (`{vps_name}`) extended by **{days} days**.\nNew expiry: `{new_exp[:10]}`"))
    try:
        await user.send(embed=create_success_embed("✅ VPS Extended",
            f"Your **VPS #{vps_number}** (`{vps_name}`) has been extended by **{days} days**!\nNew expiry: **{new_exp[:10]}**"))
    except discord.Forbidden:
        pass


@bot.hybrid_command(name='checkexpire')
async def check_expire(ctx, user: discord.Member = None):
    """Check VPS expiry — users check own, admins can check others"""
    is_user_admin = str(ctx.author.id) == str(MAIN_ADMIN_ID) or str(ctx.author.id) in admin_data.get("admins", [])
    target = user if (user and is_user_admin) else ctx.author
    user_id = str(target.id)
    if user_id not in vps_data or not vps_data[user_id]:
        await ctx.send(embed=create_error_embed("Not Found", f"{target.mention} has no VPS."))
        return
    embed = create_info_embed(f"⏳ VPS Expiry — {target.display_name}", "")
    for i, vps in enumerate(vps_data[user_id]):
        expires = vps.get('expires', 'Never')
        if expires and expires != 'Never':
            try:
                exp_dt = datetime.fromisoformat(expires)
                days_left = (exp_dt - datetime.utcnow()).days
                if days_left < 0:
                    status = f"❌ **EXPIRED** {abs(days_left)}d ago"
                elif days_left <= 3:
                    status = f"⚠️ Expires in **{days_left}d** — {expires[:10]}"
                else:
                    status = f"✅ Expires on `{expires[:10]}` ({days_left}d left)"
            except:
                status = expires
        else:
            status = "♾️ Never (No expiry set)"
        embed.add_field(
            name=f"VPS #{i+1} — `{vps['container_name']}`",
            value=status, inline=False
        )
    await ctx.send(embed=embed)


@bot.hybrid_command(name='removeexpire')
@is_admin()
async def remove_expire(ctx, user: discord.Member, vps_number: int):
    """Remove expiry from a specific VPS — /removeexpire @user <vps#>"""
    user_id = str(user.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Not Found", f"{user.mention} has no VPS #{vps_number}."))
        return
    vps_list[vps_number - 1]['expires'] = 'Never'
    save_data()
    vps_name = vps_list[vps_number - 1]['container_name']
    await ctx.send(embed=create_success_embed("Expiry Removed",
        f"✅ {user.mention}'s **VPS #{vps_number}** (`{vps_name}`) expiry set to **Never**."))


@bot.hybrid_command(name='renewvps')
@is_admin()
async def renew_vps(ctx, user: discord.Member, vps_number: int, days: int = 0):
    """Renew a VPS; omitted or zero days makes it permanent."""

    user_id = str(user.id)
    vps_list = vps_data.get(user_id, [])
    if not vps_list or vps_number < 1 or vps_number > len(vps_list):
        await ctx.send(embed=create_error_embed("Not Found", f"{user.mention} has no VPS #{vps_number}."))
        return

    vps = vps_list[vps_number - 1]
    container_name = vps.get('container_name')
    if not container_name:
        await ctx.send(embed=create_error_embed("Invalid VPS", "This saved VPS record has no container name."))
        return

    try:
        await execute_docker(f"docker start {container_name}")
        await ensure_docker_daemon(container_name)
        vps['status'] = 'running'
    except Exception:
        vps['status'] = 'stopped'

    new_exp = expiry_from_days(days)
    vps['expires'] = new_exp
    vps.pop('expired', None)
    save_data()
    await refresh_vps_presence()

    await ctx.send(embed=create_success_embed(
        "VPS Renewed",
        f"✅ {user.mention}'s **VPS #{vps_number}** (`{container_name}`) has been renewed "
        f"with **{'no expiry' if new_exp == 'Never' else f'{days} days'}**."
    ))

    try:
        await user.send(embed=create_success_embed(
            "✅ VPS Renewed",
            f"Your VPS `{container_name}` has been renewed by an admin "
            f"with **{'no expiry' if new_exp == 'Never' else f'{days} days'}**."
            f"\nNew expiry: **{'Never (No expiry set)' if new_exp == 'Never' else new_exp[:10]}**"
        ))
    except discord.Forbidden:
        pass


# Auto expire checker — runs every hour
@tasks.loop(hours=1)
async def auto_expire_check():
    now = datetime.utcnow()
    for user_id, vps_list in list(vps_data.items()):
        for vps in vps_list:
            expires = vps.get('expires', 'Never')
            if not expires or expires == 'Never':
                continue
            try:
                exp_dt = datetime.fromisoformat(expires)
                days_left = (exp_dt - now).days
                # Warn at 3 days
                if days_left == 3:
                    try:
                        u = await bot.fetch_user(int(user_id))
                        await u.send(embed=create_warning_embed(
                            "⚠️ VPS Expiring Soon",
                            f"Your VPS `{vps['container_name']}` expires in **3 days** on `{expires[:10]}`.\n"
                            "Contact an admin to extend it."
                        ))
                    except:
                        pass
                # Warn at 1 day
                elif days_left == 1:
                    try:
                        u = await bot.fetch_user(int(user_id))
                        await u.send(embed=create_error_embed(
                            "🚨 VPS Expiring Tomorrow!",
                            f"Your VPS `{vps['container_name']}` expires **tomorrow** (`{expires[:10]}`)!\n"
                            "Contact an admin IMMEDIATELY to avoid losing access."
                        ))
                    except:
                        pass
                # Expired — stop container and keep record, do not delete container
                elif days_left < 0:
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "docker", "stop", vps['container_name'],
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                        )
                        await proc.communicate()
                        vps['status'] = 'stopped'
                        vps['expired'] = True
                        await refresh_vps_presence()
                    except:
                        pass
                    try:
                        u = await bot.fetch_user(int(user_id))
                        await u.send(embed=create_error_embed(
                            "❌ VPS Expired",
                            f"Your VPS `{vps['container_name']}` has expired and been **stopped**.\n"
                            "Contact an admin to renew it."
                        ))
                    except:
                        pass
            except:
                continue
    save_data()


if __name__ == "__main__":
    # Put your Discord bot token between the quotes.
    # This bot will NOT ask for the token in the terminal.
    token = "MTU0NjUwMzQyNTEyNDk5MDk5Ng.GXQoTj.HHT00Q6YnqoHbzL_Pkdr_cZBq2KoiBaRaGrcAo"
    bot.run(token)


async def _xzy_hosting_sync_commands():
    try:
        synced = await bot.tree.sync()
        print(f"[Xzy Hosting] Synced {len(synced)} slash commands", flush=True)
    except Exception as e:
        print(f"[Xzy Hosting] Slash sync error: {e}", flush=True)

bot.add_listener(_xzy_hosting_sync_commands, 'on_ready')
