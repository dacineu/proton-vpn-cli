# Proton VPN CLI

Copyright (c) 2025 Proton AG

This repository holds the Proton VPN CLI.
For licensing information see [COPYING](COPYING.md) and [LICENSE](LICENSE).
For contribution policy see [CONTRIBUTING](CONTRIBUTING.md).

## Description

### Early access release

The official [Proton VPN](https://protonvpn.com) CLI is here. This early access release delivers core VPN functionality now, and we'll build out additional features based on your feedback and priorities.

Current functionality:
- Connect and disconnect from VPN servers
- Select servers by country, city, or server ID
- WireGuard protocol support
- List available servers with filtering (`protonvpn servers list`)
- Free tier can select servers by country or city

Current limitations:
- No advanced features (NetShield, kill switch, split tunneling, port forwarding)
- Cannot run alongside the Proton VPN GUI app

We're actively developing additional features. Report issues and request features through https://protonvpn.com/support-form

Have fun on your terminal.


### Cloning

Once you've cloned this repo, run:

> git submodule update --init --recursive

to clone the necessary submodule.

### Installation

You can find the latest beta release and installation instructions on our [Proton VPN official website](https://protonvpn.com/support/linux-cli).

### Dependencies

For development purposes (within a virtual environment) see the required packages in the setup.py file, under `install_requires` and `extra_require`. As of now these packages will not be available on pypi. Also see [Virtual environment](#virtual-environment) below.

### Daemon Service

The Proton VPN CLI requires the `protonvpn` systemd service (daemon) to be running for connection operations. The daemon is provided by the `proton-vpn-local-agent` package (installed automatically as a dependency).

To check if the daemon is active and enable it:

```shell
# Check status
systemctl status protonvpn.service

# If not running, start it
sudo systemctl start protonvpn.service

# Enable on boot
sudo systemctl enable protonvpn.service
```

The CLI will display an error if the daemon is not running when attempting to connect or disconnect.

### Non-root operation

The CLI is designed to run without superuser privileges. All privileged operations are handled by the daemon via D-Bus. The current user must be authorized to communicate with the daemon (this is typically handled automatically by the package installation via Polkit rules).

### Arch Linux

For Arch Linux users, community-maintained PKGBUILD files are available in the `packaging/arch/` directory of this repository.

To build and install:

1. Ensure you have the required dependencies:
   ```bash
   sudo pacman -S --needed base-devel python python-pip
   ```

2. Navigate to the packaging directory:
   ```bash
   cd packaging/arch
   ```

3. Update the SHA256 checksum (optional if you use the provided script):
   ```bash
   ./update_checksums.sh
   ```

4. Build and install:
   ```bash
   makepkg -si
   ```

The package will:
- Install the CLI and Python module
- Install and enable the `protonvpn.service` daemon automatically
- Set up documentation in `/usr/share/doc/proton-vpn-cli/`

**Note**: The package depends on `proton-vpn-api-core`, `proton-keyring-linux`, and `proton-vpn-local-agent` which may need to be built from AUR if not available in official repositories.

For more details on Arch packaging, see `packaging/arch/ARCH_LINUX_PACKAGING.md`.


### Virtual environment

If you didn't do it yet, to be able to pip install Proton VPN components you'll
need to set up our internal Python package registry. You can do so running the
command below, after replacing `{GITLAB_TOKEN`} with your
[personal access token](https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html)
with the scope set to `api`.

```shell
pip config set global.index-url https://__token__:{GITLAB_TOKEN}@{GITLAB_INSTANCE}/api/v4/groups/{GROUP_ID}/-/packages/pypi/simple
```

You can create the virtual environment and install the rest of dependencies as
follows:

```shell
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### CLI misc.

CLI logs are stored under `~/.cache/Proton/VPN/logs/` directory.

User settings are under `~/.config/Proton/VPN/` directory.

## Folder structure

### Folder "debian"

Contains all debian related data, for easy package compilation.

### Folder "rpmbuild"

Contains all rpm/fedora related data, for easy package compilation.

### Folder "proton/vpn/cli"

This folder contains the CLI source code.

### Folder "tests"

This folder contains unit test code.

You can run the tests with:

```shell
pytest
```


## Versioning
Version matches format: `[major][minor][patch]`

We automate the versioning of the debian and rpm files.
All versions of the application are recorded in versions.yml.
To bump the version, add the following text to the top of versions.yml

```
version: <latest version>
time: <date> <time>
author: <your name>
email: <your email address>
urgency: low
stability: unstable
description:
- <A description of the changes this new version contains>
---
```

Make sure you have the '---' dashes at the end of your block of text.
You can use the previous entries as an example.

Finally run `scripts/build_packages.py`. This will generate a new package.spec
file for rpmbuild and a new changelog file for debian.

That's it.

