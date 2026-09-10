PAID IP BOT
===========

Ubuntu Installation & Setup Guide
---------------------------------

This guide explains how to install and run Paid IP Bot on an Ubuntu VPS.

REQUIREMENTS
------------

- Ubuntu VPS
- Git
- Python 3
- pip
- Discord Bot Token
- Tailscale Auth Key
- OpenRouter API Key


1. UPDATE UBUNTU
----------------

apt update
apt upgrade -y


2. INSTALL GIT
--------------

apt install git -y


3. INSTALL NANO
---------------

apt install nano -y


4. CLONE THE REPOSITORY
-----------------------

git clone https://github.com/xzydip/xzy

cd xzy


5. INSTALL PYTHON AND PIP
-------------------------

apt install python3 -y
apt install python3-pip -y


6. INSTALL BOT DEPENDENCIES
---------------------------

If the repository contains a requirements.txt file, run:

pip3 install -r requirements.txt

If there is no requirements.txt file, install the Python packages required by xzy.py manually.


7. Dowload Discord
-------------------

pip install discord


7. CONFIGURE XZY.PY
-------------------

Open the bot file:

nano xzy.py

Press:

CTRL + W

Search for:

token

Enter the required Discord Bot Token.

After editing:

CTRL + O
ENTER
CTRL + X

IMPORTANT:
Do NOT paste your Discord Bot Token into a public GitHub repository.

If your xzy.py already reads the token from an environment variable, use that method instead of putting the token directly inside the source code.


8. SET TAILSCALE AUTH KEY
-------------------------

Set your Tailscale authentication key:

export TS_AUTHKEY="YOUR_TAILSCALE_AUTH_KEY"

Replace:

YOUR_TAILSCALE_AUTH_KEY

with your actual Tailscale auth key.

IMPORTANT:
Never put the real auth key inside xzy.py, README.txt, GitHub commits, screenshots, or any other public file.


9. SET OPENROUTER API KEY
-------------------------

Set your OpenRouter API key:

export OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"

Replace:

YOUR_OPENROUTER_API_KEY

with your actual OpenRouter API key.

IMPORTANT:
Never upload your real OpenRouter API key to GitHub.


10. RUN THE BOT
---------------

Start the bot with:

python3 xzy.py


11. CHECK FOR ERRORS
--------------------

If the bot does not start, run:

python3 xzy.py

Read the error shown in the terminal and fix the missing package, configuration, or environment variable.

You can also check your Python version:

python3 --version

And pip:

pip3 --version


12. RUN BOT IN BACKGROUND
-------------------------

For a simple background process, you can use:

nohup python3 xzy.py > bot.log 2>&1 &

To view the bot log:

tail -f bot.log

To stop a bot started with nohup, find its process:

ps aux | grep xzy.py

Then stop the correct process:

kill PID

Replace PID with the process ID of your bot.


13. USING SCREEN
----------------

Install screen:

apt install screen -y

Create a screen session:

screen -S paid-ip-bot

Run:

python3 xzy.py

Detach from the screen:

CTRL + A
then press D

Re-enter the session:

screen -r paid-ip-bot


14. IMPORTANT GITHUB SECURITY
----------------------------

This repository may be public.

NEVER upload:

- Discord Bot Tokens
- Tailscale Auth Keys
- OpenRouter API Keys
- Passwords
- SSH Private Keys
- Database Passwords
- Webhook URLs containing sensitive credentials
- Other private secrets


15. IF A TOKEN WAS LEAKED
-------------------------

If you accidentally uploaded a Discord Bot Token:

1. Open the Discord Developer Portal.
2. Reset/regenerate the bot token.
3. Replace the old token in your VPS configuration.
4. Remove the leaked token from the repository history if necessary.

If a Tailscale Auth Key was exposed:

1. Revoke the exposed key.
2. Create a new auth key.
3. Update the VPS environment variable.

If an OpenRouter API key was exposed:

1. Revoke the exposed key.
2. Create a new API key.
3. Update the VPS environment variable.


16. ENVIRONMENT VARIABLES
-------------------------

Recommended variables:

TS_AUTHKEY="YOUR_TAILSCALE_AUTH_KEY"
OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"

Do not commit files containing real values.

For local testing, you can set them temporarily with:

export TS_AUTHKEY="YOUR_TAILSCALE_AUTH_KEY"
export OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"


17. BASIC COMMAND SUMMARY
-------------------------

apt update
apt upgrade -y
apt install git -y
apt install nano -y
apt install python3 -y
apt install python3-pip -y

git clone https://github.com/xzydip/xzy-vps-bot.git
cd Paid-ip-bot

pip3 install -r requirements.txt

nano xzy.py

export TS_AUTHKEY="YOUR_TAILSCALE_AUTH_KEY"
export OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY"

python3 xzy.py


18. TROUBLESHOOTING
-------------------

BOT DOES NOT START
------------------

Run:

python3 xzy.py

Check the error message.

MODULE NOT FOUND
----------------

If you see:

ModuleNotFoundError

Install the missing Python package with:

pip3 install PACKAGE_NAME

Or, if requirements.txt exists:

pip3 install -r requirements.txt


PERMISSION ERROR
----------------

Make sure you are inside the bot directory:

cd Paid-ip-bot

Then run:

python3 xzy.py


ENVIRONMENT VARIABLE NOT FOUND
------------------------------

Check whether the variable exists:

echo $TS_AUTHKEY
echo $OPENROUTER_API_KEY

Do not share the output publicly because it may contain secret credentials.


19. PROJECT STRUCTURE
---------------------

A typical project may look like:

Paid-ip-bot/
|
|-- xzy.py
|-- requirements.txt
|-- README.txt
|-- other project files
|
|-- DO NOT STORE REAL SECRETS HERE


20. DISCLAIMER
--------------

Use this software only on systems and accounts that you own or are authorized to manage.

The user is responsible for securing their Discord bot, VPS, Tailscale credentials, API keys, and other private information.

Do not use this project to access systems without permission.


PAID IP BOT
===========

GitHub:
https://github.com/xzydip/xzy-vps-bot/

End of README
