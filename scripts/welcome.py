#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (C) 2015 GNS3 Technologies Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import locale
import os
import sys
import time
import subprocess
import configparser
import urllib.request
import json
from dialog import Dialog, PythonDialogBug

try:
    locale.setlocale(locale.LC_ALL, '')
except locale.Error:
    # Not supported via SSH
    pass


def get_ip():
    """
    Returns eth0 IP address.
    """

    my_ip = subprocess.Popen([r"ip addr show eth0 | awk '/inet / {print $2}' | cut -d/ -f1"],
                             stdout=subprocess.PIPE,
                             shell=True)

    (IP, errors) = my_ip.communicate()
    my_ip.stdout.close()
    if len(IP) == 0:
        return None
    return IP.decode().strip()


def get_config():
    """
    Returns the server config.
    """

    config = configparser.RawConfigParser()
    path = os.path.expanduser("~/.config/GNS3/gns3_server.conf")
    config.read([path], encoding="utf-8")
    return config


def write_config(config):
    """
    Writes the server config.
    """

    with open(os.path.expanduser("~/.config/GNS3/gns3_server.conf"), 'w') as f:
        config.write(f)


def gns3_version():
    """
    Returns the GNS3 server version.
    """

    try:
        return subprocess.check_output(["gns3server", "--version"]).strip().decode()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def gns3vm_version():
    """
    Returns the GNS3 VM version.
    """
    with open('/home/gns3/.config/GNS3/gns3vm_version') as f:
        return f.read().strip()


d = Dialog(dialog="dialog", autowidgetsize=True)
if gns3_version() is None:
    d.set_background_title("GNS3")
else:
    d.set_background_title("GNS3 {}".format(gns3_version()))


def mode():
    """
    Selects the GNS3 version to run.
    """

    if d.yesno("This feature is for testers only. You may break your GNS3 installation. Are you REALLY sure you want to continue?", yes_label="Exit (Safe option)", no_label="Continue") == d.OK:
        return
    code, tag = d.menu("Select the GNS3 release channel",
                       choices=[("2.1", "Current stable release (RECOMMENDED)"),
                                ("2.1dev", "Next stable release, development version"),
                                ("2.2dev", "Totally unstable version")])
    d.clear()
    if code == Dialog.OK:
        os.makedirs(os.path.expanduser("~/.config/GNS3"), exist_ok=True)
        with open(os.path.expanduser("~/.config/GNS3/gns3_release_channel"), "w+") as f:
            f.write(tag)
        update(force=True)


def get_release_channel():
    """
    Returns the current release channel.
    """

    try:
        with open(os.path.expanduser("~/.config/GNS3/gns3_release_channel")) as f:
            content = f.read()
            return content
    except OSError:
        return "2.2"


def get_all_releases(release_channel):
    """
    Returns all releases for a corresponding release channel (e.g. 2.1, 2.2 etc.)
    Excludes alphas, betas, RCs and development releases.
    """

    releases = []
    try:
        tags_url = urllib.request.urlopen("https://api.github.com/repos/GNS3/gns3-server/tags")
        raw_data = tags_url.read()
    except urllib.request.URLError as e:
        d.infobox("Cannot connect to GitHub to get the GNS3 versions: {}".format(str(e)))
        return None
    encoding = tags_url.info().get_content_charset("utf-8")
    try:
        json_data = json.loads(raw_data.decode(encoding))
    except ValueError as e:
        d.infobox("Invalid JSON data received: {}".format(str(e)))
        return None
    for tag in json_data:
        release = tag.get("name")
        if release and release[1:].startswith(release_channel) and not re.search("dev|a|rc|b", release):
            releases.append(release)

    def atoi(text):
        return int(text) if text.isdigit() else text

    def natural_keys(text):
        return [atoi(c) for c in re.split(r"(\d+)", text)]

    return sorted(releases, key=natural_keys, reverse=True)


def update(force=False):
    """
    Updates the GNS3 VM.
    """

    if not force:
        if d.yesno("PLEASE SNAPSHOT THE VM BEFORE RUNNING THE UPDATE IN CASE OF FAILURE. The server will reboot at the end of the update process. Continue?") != d.OK:
            return

    release_channel = get_release_channel()
    match = re.search("dev|a|rc|b", release_channel)
    if match:
        # development release (unstable), download and execute update script from the unstable branch on GitHub
        ret = os.system("curl https://raw.githubusercontent.com/GNS3/gns3-vm/bionic-unstable/scripts/update_{}.sh > /tmp/update.sh && bash -x /tmp/update.sh".format(release_channel))
    else:
        releases = get_all_releases(release_channel)
        if len(releases) > 1:
            # only show the menu if more than 1 release
            choices = []
            for release_tag in releases:
                choices.append((release_tag, "Release {}".format(release_tag)))
            code, gns3_version = d.menu("Select a GNS3 version",
                               choices=choices)
            d.clear()
            if code == Dialog.OK:
                # current release (stable), download and execute update script from the stable branch on GitHub and pass the GNS3 version we want
                ret = os.system("curl https://raw.githubusercontent.com/GNS3/gns3-vm/bionic-stable/scripts/update_{}.sh > /tmp/update.sh && bash -x /tmp/update.sh {}".format(release_channel, gns3_version))
            else:
                return
        else:
            # current release (stable), download and execute update script from the stable branch on GitHub
            ret = os.system("curl https://raw.githubusercontent.com/GNS3/gns3-vm/bionic-stable/scripts/update_{}.sh > /tmp/update.sh && bash -x /tmp/update.sh".format(release_channel))
    if ret != 0:
        print("ERROR DURING THE UPDATE PROCESS PLEASE, TAKE A SCREENSHOT IF YOU NEED SUPPORT")
        time.sleep(30)


def shrink_disk():
    """
    Shrinks the VM disk.
    """

    ret = os.system("lspci | grep -i vmware")
    if ret != 0:
        d.msgbox("Shrinking the disk is only supported when running the GNS3 VM with VMware")
        return

    if d.yesno("Would you like to shrink the VM disk? The VM will reboot at the end of the process. Continue?") != d.OK:
        return

    os.system("sudo service gns3 stop")
    os.system("sudo service docker stop")
    os.system("sudo vmware-toolbox-cmd disk shrink /opt")
    os.system("sudo vmware-toolbox-cmd disk shrink /")
    d.msgbox("Process completed, the GNS3 VM will reboot now")
    os.execvp("sudo", ['/usr/bin/sudo', "reboot"])


def vm_information():
    """
    Show the VM information (IP, KVM support, SSH settings etc).
    """

    content = "Welcome to GNS3 VM\n\n"
    version = gns3_version()
    if version is None:
        content += "The GNS3 server is not installed, please manually install it or download a pre-installed VM.\n\n"
    else:
        content = """GNS3 server version: {gns3_version}
VM version: {gns3vm_version}
Ubuntu version: {ubuntu_version}
KVM support available: {kvm}\n\n""".format(
            gns3vm_version=gns3vm_version(),
            gns3_version=version,
            ubuntu_version=ubuntu_version(),
            kvm=kvm_support())

    ip = get_ip()
    if ip:
        content += "IP: {ip}\n\nTo log in using SSH:\nssh gns3@{ip}\nPassword: gns3\n\nImages and projects are stored in '/opt/gns3'""".format(ip=ip)
    else:
        content += "eth0 is not configured. Please manually configure by selecting the 'Network' entry in the menu."

    content += "\n\nRelease channel: " + get_release_channel()

    try:
        d.msgbox(content)
    except:
        os.execvp("bash", ['/bin/bash'])


def migrate():
    """
    Migrate GNS3 VM data
    """

    code, option = d.menu("Select an option",
                          choices=[("Setup", "Configure this VM to receive data from another GNS3 VM"),
                                   ("Send", "Send images and projects to another GNS3 VM")])
    d.clear()
    if code == Dialog.OK:
        (answer, destination) = d.inputbox("What is IP address or hostname of the other GNS3 VM?", init="172.16.1.128")
        if answer != d.OK:
            return
        if option == "Send":
            command = r'bash -c "rsync -avz --progress -e "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/gns3-vm-key" /opt/gns3 gns3@{}:/opt"'.format(destination)
            ret = os.system(command)
            time.sleep(10)
            if ret != 0:
                d.msgbox("Data has been successfully migrated")
            else:
                d.msgbox("Could not migrate the data")
        elif option == "Setup":
            command = r'bash -c "ssh-keygen -f ~/.ssh/gns3-vm-key -q -P "" && ssh-copy-id -i ~/.ssh/gns3-vm-key gns3@{}"'.format(destination)
            ret = os.system(command)
            #ret = os.system("curl https://raw.githubusercontent.com/GNS3/gns3-vm/bionic-stable/scripts/setup_migrate.sh > /tmp/setup_migrate.sh && bash -x /tmp/setup_migrate.sh {}".format(destination))
            time.sleep(10)
            if ret != 0:
                d.msgbox("Could not setup the migrate feature")
            else:
                d.msgbox("Configuration successful, you can now migrate data from your remote GNS3 VM")


def check_internet_connectivity():
    """
    Checks for Internet connectivity.
    """

    d.pause("Checking connection. Please wait...\n\n")
    try:
        urllib.request.urlopen('http://pypi.python.org/', timeout=5)
    except urllib.request.URLError as err:
        d.infobox("Cannot connect to Internet: {}".format(str(err)))
        time.sleep(15)
        return
    d.infobox("Connection to Internet: OK")
    time.sleep(2)


def keyboard_configuration():
    """
    Allows users to change the keyboard layout
    """

    os.system("/usr/bin/sudo dpkg-reconfigure keyboard-configuration")


def set_security():
    """
    Configures authentication on the GNS3 server.
    """

    config = get_config()
    if d.yesno("Enable GNS3 server authentication?") == d.OK:
        config.set("Server", "auth", True)
        (answer, text) = d.inputbox("Login?")
        if answer != d.OK:
            return
        config.set("Server", "user", text)
        (answer, text) = d.passwordbox("Password?")
        if answer != d.OK:
            return
        config.set("Server", "password", text)
    else:
        config.set("Server", "auth", False)
    write_config(config)


def log():
    """
    Displays the GNS3 server log.
    """

    os.system("/usr/bin/sudo chmod 755 /var/log/gns3/gns3.log")
    with open("/var/log/gns3/gns3.log") as f:
        try:
            while True:
                line = f.readline()
                sys.stdout.write(line)
        except (KeyboardInterrupt, MemoryError):
            return


def edit_config():
    """
    Edits GNS3 server configuration file.
    """
    os.system("nano ~/.config/GNS3/gns3_server.conf")


def edit_network():
    """
    Edits network configuration file.
    """

    if d.yesno("The server will reboot at the end of the process. Continue?") != d.OK:
        return
    os.system("sudo nano /etc/netplan/90_gns3vm_static_netcfg.yaml")
    os.system("sudo netplan apply")
    os.execvp("sudo", ['/usr/bin/sudo', "reboot"])


def edit_proxy():
    """
    Configures GNS3 VM proxy settings.
    """

    res, http_proxy = d.inputbox(text="HTTP proxy string, for example http://<user>:<password>@<proxy>:<port>. Leave empty for no proxy.")
    if res != d.OK:
        return
    res, https_proxy = d.inputbox(text="HTTPS proxy string, for example http://<user>:<password>@<proxy>:<port>. Leave empty for no proxy.")
    if res != d.OK:
        return

    with open('/tmp/00proxy', 'w+') as f:
        f.write('Acquire::http::Proxy "' + http_proxy + '";')
    os.system("sudo mv /tmp/00proxy /etc/apt/apt.conf.d/00proxy")
    os.system("sudo chown root /etc/apt/apt.conf.d/00proxy")
    os.system("sudo chmod 744 /etc/apt/apt.conf.d/00proxy")

    with open('/tmp/proxy.sh', 'w+') as f:
        f.write('export http_proxy="' + http_proxy + '"\n')
        f.write('export https_proxy="' + https_proxy + '"\n')
    os.system("sudo mv /tmp/proxy.sh /etc/profile.d/proxy.sh")
    os.system("sudo chown root /etc/profile.d/proxy.sh")
    os.system("sudo chmod 744 /etc/profile.d/proxy.sh")
    os.system("sudo cp /etc/profile.d/proxy.sh /etc/default/docker")

    d.msgbox("The GNS3 VM will reboot now")
    os.execvp("sudo", ['/usr/bin/sudo', "reboot"])


def kvm_support():
    """
    Returns true if KVM is supported.
    """

    return subprocess.call("kvm-ok") == 0


def ubuntu_version():
    """
    Returns the codename of the current Ubuntu distribution
    """

    return subprocess.check_output(["lsb_release", "-sc"]).strip().decode()


def kvm_control():
    """
    Checks if KVM is correctly configured for the GNS3 server.
    """

    kvm_ok = kvm_support()
    config = get_config()
    try:
        if config.getboolean("Qemu", "enable_kvm") is True:
            if kvm_ok is False:
                if d.yesno("KVM is not supported!\n\nQemu VMs will run extremely slowly!!\n\nThis could be due to unsupported hardware or another virtualization solution is already running.\n\nDisable KVM and get lower performance?") == d.OK:
                    config.set("Qemu", "enable_kvm", False)
                    write_config(config)
                    os.execvp("sudo", ['/usr/bin/sudo', "reboot"])
        else:
            if kvm_ok is True:
                if d.yesno("KVM is supported on this host.\n\nEnable KVM and get better performance?") == d.OK:
                    config.set("Qemu", "enable_kvm", True)
                    write_config(config)
                    os.execvp("sudo", ['/usr/bin/sudo', "reboot"])
    except configparser.NoSectionError:
        return


vm_information()
kvm_control()

# rsync -e "ssh -o StrictHostKeyChecking=no" -rtz /opt/gns3 gns3@IP:/opt

try:
    while True:
        code, tag = d.menu("GNS3 {}".format(gns3_version()),
                           choices=[("Information", "Display VM information"),
                            ("Update", "Update the GNS3 VM"),
                            ("Migrate", "Migrate data to a remote GNS3 VM"),
                            ("Shell", "Open a shell"),
                            ("Security", "Configure server authentication"),
                            ("Keyboard", "Change keyboard layout"),
                            ("Configure", "Edit server configuration (advanced users ONLY)"),
                            ("Proxy", "Configure proxy settings"),
                            ("Network", "Configure network settings"),
                            ("Log", "Show server log"),
                            ("Test", "Check internet connection"),
                            ("Shrink", "Shrink the VM disk"),
                            ("Version", "Select the GNS3 version"),
                            ("Restore", "Restore the VM (if a update failed)"),
                            ("Reboot", "Reboot the VM"),
                            ("Shutdown", "Shutdown the VM")])
        d.clear()
        if code == Dialog.OK:
            if tag == "Shell":
                os.execvp("bash", ['/bin/bash'])
            elif tag == "Version":
                mode()
            elif tag == "Restore":
                os.execvp("sudo", ['/usr/bin/sudo', "/usr/local/bin/gns3restore"])
            elif tag == "Reboot":
                os.execvp("sudo", ['/usr/bin/sudo', "reboot"])
            elif tag == "Shutdown":
                os.execvp("sudo", ['/usr/bin/sudo', "poweroff"])
            elif tag == "Update":
                update()
            elif tag == "Information":
                vm_information()
            elif tag == "Migrate":
                migrate()
            elif tag == "Log":
                log()
            elif tag == "Configure":
                edit_config()
            elif tag == "Network":
                edit_network()
            elif tag == "Security":
                set_security()
            elif tag == "Keyboard":
                keyboard_configuration()
            elif tag == "Test":
                check_internet_connectivity()
            elif tag == "Proxy":
                edit_proxy()
            elif tag == "Shrink":
                shrink_disk()
except KeyboardInterrupt:
    sys.exit(0)
