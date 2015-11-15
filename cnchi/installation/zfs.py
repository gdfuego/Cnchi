# -*- coding: utf-8; Mode: Python; indent-tabs-mode: nil; tab-width: 4 -*-
#
#  zfs.py
#
#  Copyright © 2013-2015 Antergos
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import subprocess
import os
import logging
import math

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

try:
    from gtkbasebox import GtkBaseBox
except ImportError:
    import sys
    sys.path.append('/usr/share/cnchi/cnchi')
    from gtkbasebox import GtkBaseBox

import parted
import misc.misc as misc
from misc.misc import InstallError
import show_message as show
from installation import wrapper
from installation import action

COL_USE_ACTIVE = 0
COL_USE_VISIBLE = 1
COL_USE_SENSITIVE = 2
COL_DISK = 3
COL_SIZE = 4
COL_DEVICE_NAME = 5
COL_DISK_ID = 6

def is_int(num):
    try:
        int(num)
        return True
    except ValueError:
        return False


class InstallationZFS(GtkBaseBox):
    def __init__(self, params, prev_page="installation_ask", next_page="summary"):
        super().__init__(self, params, "zfs", prev_page, next_page)

        self.page = self.ui.get_object('zfs')

        self.disks = None
        self.diskdic = {}

        self.change_list = []

        self.device_list = self.ui.get_object('treeview')
        self.device_list_store = self.ui.get_object('liststore')
        self.prepare_device_list()
        self.device_list.set_hexpand(True)

        self.ids = {}

        # Set zfs default options
        self.zfs_options = {
            "force_4k": False,
            "encrypt_swap": False,
            "encrypt_disk": False,
            "encrypt_password": "",
            "scheme": "GPT",
            "pool_type": "None",
            "swap_size": 8192,
            "pool_name": "",
            "use_pool_name": False,
            "device_paths": []
        }

        self.pool_types = {
            0: "None",
            1: "Stripe",
            2: "Mirror",
            3: "RAID-Z",
            4: "RAID-Z2",
            5: "RAID-Z3"
        }

        self.schemes = {
            0: "GPT",
            1: "MBR"
        }

        self.pool_types_help_shown = []

        if os.path.exists("/sys/firmware/efi"):
            # UEFI, use GPT by default
            self.UEFI = True
            self.zfs_options["scheme"] = "GPT"
        else:
            # No UEFI, use MBR by default
            self.UEFI = False
            self.zfs_options["scheme"] = "MBR"

    def on_use_device_toggled(self, widget, path):
        self.device_list_store[path][COL_USE_ACTIVE] = not self.device_list_store[path][COL_USE_ACTIVE]
        self.forward_button.set_sensitive(self.check_pool_type())

    def prepare_device_list(self):
        """ Create columns for our treeview """

        # Use check | Disk (sda) | Size(GB) | Name (device name) | Device ID

        use_toggle = Gtk.CellRendererToggle()
        use_toggle.connect("toggled", self.on_use_device_toggled)

        col = Gtk.TreeViewColumn(
            _("Use"),
            use_toggle,
            active=COL_USE_ACTIVE,
            visible=COL_USE_VISIBLE,
            sensitive=COL_USE_SENSITIVE)

        self.device_list.append_column(col)

        render_text = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(_("Disk"), render_text, text=COL_DISK)
        self.device_list.append_column(col)

        render_text_right = Gtk.CellRendererText()
        render_text_right.set_property("xalign", 1)
        col = Gtk.TreeViewColumn(_("Size (GB)"), render_text_right, text=COL_SIZE)
        self.device_list.append_column(col)

        col = Gtk.TreeViewColumn(_("Device"), render_text, text=COL_DEVICE_NAME)
        self.device_list.append_column(col)

        col = Gtk.TreeViewColumn(_("Disk ID"), render_text, text=COL_DISK_ID)
        self.device_list.append_column(col)

    def fill_device_list(self):
        """ Fill the partition list with all the data. """

        # We will store our data model in 'device_list_store'
        if self.device_list_store is not None:
            self.device_list_store.clear()

        self.device_list_store = Gtk.TreeStore(bool, bool, bool, str, int, str, str)

        with misc.raised_privileges():
            devices = parted.getAllDevices()

        self.get_ids()

        for dev in devices:
            # Skip cdrom, raid, lvm volumes or encryptfs
            if not dev.path.startswith("/dev/sr") and not dev.path.startswith("/dev/mapper"):
                size_in_gigabytes = int((dev.length * dev.sectorSize) / 1000000000)
                # Use check | Disk (sda) | Size(GB) | Name (device name)
                if dev.path.startswith("/dev/"):
                    path = dev.path[len("/dev/"):]
                else:
                    path = dev.path
                disk_id = self.ids.get(path, "")
                row = [False, True, True, path, size_in_gigabytes, dev.model, disk_id]
                self.device_list_store.append(None, row)

        self.device_list.set_model(self.device_list_store)

    def translate_ui(self):
        self.header.set_subtitle(_("ZFS Setup"))

        # Encrypt disk checkbox
        btn = self.ui.get_object("encrypt_disk_btn")
        btn.set_active(self.zfs_options["encrypt_disk"])

        # Disable/Enable Encrypt disk options entries
        entries = [
            'password_entry', 'password_check_entry',
            'password_lbl', 'password_check_lbl']
        for name in entries:
            entry = self.ui.get_object(name)
            entry.set_sensitive(self.zfs_options["encrypt_disk"])

        # Pool name checkbox
        btn = self.ui.get_object("pool_name_btn")
        btn.set_active(self.zfs_options["use_pool_name"])

        # Disable/Enable Pool name entry
        entry = self.ui.get_object('pool_name_entry')
        entry.set_sensitive(self.zfs_options["use_pool_name"])

        # Set pool type label text
        lbl = self.ui.get_object('pool_type_label')
        lbl.set_markup(_("Pool type"))

        # Fill pool types combobox
        combo = self.ui.get_object('pool_type_combo')
        combo.remove_all()
        active_index = 0
        for index in self.pool_types:
            combo.append_text(self.pool_types[index])
            if self.zfs_options["pool_type"] == self.pool_types[index]:
                active_index = index
        combo.set_active(active_index)

        # Set partition scheme label text
        lbl = self.ui.get_object('partition_scheme_label')
        lbl.set_markup(_("Partition scheme"))

        # Fill partition scheme combobox
        combo = self.ui.get_object('partition_scheme_combo')
        combo.remove_all()
        active_index = 0
        for index in self.schemes:
            combo.append_text(self.schemes[index])
            if self.zfs_options["scheme"] == self.schemes[index]:
                active_index = index
        combo.set_active(active_index)

        # Set all labels
        lbl = self.ui.get_object('password_check_lbl')
        lbl.set_markup(_("Validate password"))

        lbl = self.ui.get_object('password_lbl')
        lbl.set_markup(_("Password"))

        lbl = self.ui.get_object('swap_size_lbl')
        lbl.set_markup(_("Swap size (MB)"))

        # Set button labels
        btn = self.ui.get_object('encrypt_swap_btn')
        btn.set_label(_("Encrypt swap"))

        btn = self.ui.get_object('encrypt_disk_btn')
        btn.set_label(_("Encrypt disk"))

        btn = self.ui.get_object('pool_name_btn')
        btn.set_label(_("Pool name"))

        btn = self.ui.get_object('force_4k_btn')
        btn.set_label(_("Force ZFS 4k block size"))

        # Set swap Size
        swap_size = str(self.zfs_options["swap_size"])
        entry = self.ui.get_object("swap_size_entry")
        entry.set_text(swap_size)

    def check_pool_type(self, show_warning=False):
        """ Check that the user has selected the right number
        of devices for the selected pool type """

        num_drives = 0
        msg = ""
        pool_type = self.zfs_options["pool_type"]

        for row in self.device_list_store:
            if row[COL_USE_ACTIVE]:
                num_drives += 1

        if pool_type == "None":
            if num_drives > 0:
                is_ok = True
            else:
                is_ok = False
                msg = _("You must select at least one drive")

        elif pool_type == "Stripe" or pool_type == "Mirror":
            if num_drives > 1:
                is_ok = True
            else:
                is_ok = False
                msg = _("For the {0} pool_type, you must select at least two drives").format(pool_type)

        elif "RAID" in pool_type:
            min_drives = 3
            min_parity_drives = 1

            if pool_type == "RAID-Z2":
                min_drives = 4
                min_parity_drives = 2

            elif pool_type == "RAID-Z3":
                min_drives = 5
                min_parity_drives = 3

            if num_drives < min_drives:
                is_ok = False
                msg = _("You must select at least {0} drives").format(min_drives)
            else:
                num = math.log2(num_drives - min_parity_drives)
                if not is_int(num):
                    msg = _("For the {0} pool type, you must use a 'power of two' (2,4,8,...) "
                    "plus the appropriate number of drives for the parity. RAID-Z = 1 disk, "
                    "RAIDZ-2 = 2 disks, and so on.").format(pool_type, min_parity_drives)

        if not is_ok and show_warning:
            show.message(self.get_toplevel(), msg)

        return is_ok

    def show_pool_type_help(self, pool_type):
        pool_types = list(self.pool_types.values())
        msg = ""
        if pool_type in pool_types and pool_type not in self.pool_types_help_shown:
            if pool_type == "Stripe":
                msg = _("When created together, with equal capacity, ZFS "
                "space-balancing makes a span act like a RAID0 stripe. "
                "The space is added together. Provided all the devices are "
                "of the same size, the stripe behavior will continue regardless "
                "of fullness level. If devices/vdevs are not equally sized, then "
                "they will fill mostly equally until one device/vdev is full.")
            elif pool_type == "Mirror":
                msg = _("A mirror consists of two or more devices, all data will "
                "be written to all member devices.")
            elif pool_type.startswith("RAID-Z"):
                msg = _("ZFS implements RAID-Z, a variation on standard RAID-5. ZFS supports "
                "three levels of RAID-Z which provide varying levels of redundancy in exchange "
                "for decreasing levels of usable storage. The types are named RAID-Z1 through "
                "RAID-Z3 based on the number of parity devices in the array and the number of "
                "disks which can fail while the pool remains operational.")

            self.pool_types_help_shown.append(pool_type)
            if len(msg) > 0:
                show.message(self.get_toplevel(), msg)

    def on_force_4k_help_btn_clicked(self, widget):
        msg = _("Advanced Format (AF) is a new disk format which natively uses "
        "a 4,096 byte instead of 512 byte sector size. To maintain compatibility "
        "with legacy systems AF disks emulate a sector size of 512 bytes. "
        "By default, ZFS will automatically detect the sector size of the drive. "
        "This combination will result in poorly aligned disk access which will "
        "greatly degrade the pool performance. If that might be your case, you "
        "can force ZFS to use a sector size of 4,096 bytes by selecting this option.")
        show.message(self.get_toplevel(), msg)

    def on_encrypt_swap_btn_toggled(self, widget):
        self.zfs_options["encrypt_swap"] = not self.zfs_options["encrypt_swap"]

    def on_encrypt_disk_btn_toggled(self, widget):
        status = widget.get_active()

        names = [
            'password_entry', 'password_check_entry',
            'password_lbl', 'password_check_lbl']

        for name in names:
            obj = self.ui.get_object(name)
            obj.set_sensitive(status)
        self.zfs_options["encrypt_disk"] = status
        self.settings.set('use_luks', status)

    def on_pool_name_btn_toggled(self, widget):
        obj = self.ui.get_object('pool_name_entry')
        status = not obj.get_sensitive()
        obj.set_sensitive(status)
        self.zfs_options["use_pool_name"] = status

    def on_force_4k_btn_toggled(self, widget):
        self.zfs_options["force_4k"] = not self.zfs_options["force_4k"]

    def on_partition_scheme_combo_changed(self, widget):
        tree_iter = widget.get_active_iter()
        if tree_iter != None:
            model = widget.get_model()
            self.zfs_options["scheme"] = model[tree_iter][0]

    def on_pool_type_combo_changed(self, widget):
        tree_iter = widget.get_active_iter()
        if tree_iter != None:
            model = widget.get_model()
            self.zfs_options["pool_type"] = model[tree_iter][0]
            self.show_pool_type_help(model[tree_iter][0])
            self.forward_button.set_sensitive(self.check_pool_type())

    def prepare(self, direction):
        self.zfs_options['encrypt_disk'] = self.settings.get('use_luks')

        self.translate_ui()
        self.fill_device_list()
        self.show_all()
        self.forward_button.set_sensitive(self.check_pool_type())

    def store_values(self):
        """ Store all vars """

        # Get device paths
        device_paths = []
        for row in self.device_list_store:
            if row[COL_USE_ACTIVE]:
                device_paths.append("/dev/{0}".format(row[COL_DISK]))
        self.zfs_options["device_paths"] = device_paths

        # Get swap size
        txt = self.ui.get_object("swap_size_entry").get_text()
        try:
            self.zfs_options["swap_size"] = int(txt)
        except ValueError as verror:
            # Error reading value, set 8GB as default
            self.zfs_options["swap_size"] = 8192

        # Get pool name
        txt = self.ui.get_object("pool_name_entry").get_text()
        self.zfs_options["pool_name"] = txt

        # Get password
        txt = self.ui.get_object("password_lbl").get_text()
        self.zfs_options["encrypt_password"] = txt

        # self.set_bootloader()

        return True

    # --------------------------------------------------------------------------

    def init_device(self, device_path, scheme="GPT"):
        if scheme == "GPT":
            # Clean partition table to avoid issues!
            wrapper.sgdisk("zap-all", device_path)

            # Clear all magic strings/signatures - mdadm, lvm, partition tables etc.
            wrapper.dd("/dev/zero", device_path, bs=512, count=2048)
            wrapper.wipefs(device_path)

            # Create fresh GPT
            wrapper.sgdisk("clear", device_path)

            # Inform the kernel of the partition change. Needed if the hard disk had a MBR partition table.
            try:
                subprocess.check_call(["partprobe", device_path])
            except subprocess.CalledProcessError as err:
                txt = "Error informing the kernel of the partition change. "
                "Command {0} failed: {1}".format(err.cmd, err.output)
                logging.error(txt)
                txt = _("Error informing the kernel of the partition change. "
                "Command {0} failed: {1}").format(err.cmd, err.output)
                raise InstallError(txt)
        else:
            # DOS MBR partition table
            # Start at sector 1 for 4k drive compatibility and correct alignment
            # Clean partitiontable to avoid issues!
            wrapper.dd("/dev/zero", device_path, bs=512, count=2048)
            wrapper.wipefs(device_path)

            # Create DOS MBR
            wrapper.parted_mktable(device_path, "msdos")

    def append_change(self, action_type, device, info=""):
        if action_type == "create":
            info = _("Create {0} on device {1}").format(info, device)
            # action_type, path_or_info, relabel=False, fs_format=False, mount_point="", encrypt=False):
            encrypt = self.zfs_options["encrypt_disk"]
            act = action.Action("info", info, True, True, "", encrypt)
        elif action_type == "delete":
            act = action.Action(action_type, device)
        self.change_list.append(act)

    def get_changes(self):
        """ Grab all changes for confirmation """

        self.change_list = []
        device_paths = self.zfs_options["device_paths"]

        device_path = device_paths[0]

        if self.zfs_options["scheme"] == "GPT":
            self.append_change("delete", device_path)
            if not self.UEFI:
                self.append_change("create", device_path, "BIOS boot (2MB)")
                self.append_change("create", device_path, "Antergos Boot (512MB)")
            else:
                # UEFI
                if self.bootloader == "grub":
                    self.append_change("create", device_path, "UEFI System (200MB)")
                    self.append_change("create", device_path, "Antergos Boot (512MB)")
                else:
                    self.append_change("create", device_path, "Antergos Boot (512MB)")

            self.append_change("create", device_path, "Antergos ZFS")

            for device_path in device_paths[1:]:
                self.append_change("delete", device_path)
                self.append_change("create", device_path, "Antergos ZFS")
        else:
            # MBR
            self.append_change("delete", device_path)

            self.append_change("create", device_path, "Antergos Boot (512MB)")
            self.append_change("create", device_path, "Antergos ZFS")

            # Now init all other devices that will form part of the pool
            for device_path in device_paths[1:]:
                self.append_change("delete", device_path)
                self.append_change("create", device_path, "Antergos ZFS")

        return self.change_list

    def run_format(self):
        # https://wiki.archlinux.org/index.php/Installing_Arch_Linux_on_ZFS
        # https://wiki.archlinux.org/index.php/ZFS#GRUB-compatible_pool_creation

        device_paths = self.zfs_options["device_paths"]
        logging.debug("Configuring ZFS in %s", ",".join(device_paths))

        device_path = device_paths[0]

        if self.zfs_options["scheme"] == "GPT":
            self.init_device(device_path, "GPT")

            part_num = 1

            if not self.UEFI:
                # Create BIOS Boot Partition
                # GPT GUID: 21686148-6449-6E6F-744E-656564454649
                # This partition is not required if the system is UEFI based,
                # as there is no such embedding of the second-stage code in that case
                wrapper.sgdisk_new(device_path, part_num, "BIOS_BOOT", 2, "EF02")
                part_num += 1
                wrapper.sgdisk_new(device_path, part_num, "ANTERGOS_BOOT", 512, "8300")
                part_num += 1
            else:
                # UEFI
                if self.bootloader == "grub":
                    # Create EFI System Partition (ESP)
                    # GPT GUID: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                    wrapper.sgdisk_new(device_path, part_num, "UEFI_SYSTEM", 200, "EF00")
                    part_num += 1
                    wrapper.sgdisk_new(device_path, part_num, "ANTERGOS_BOOT", 512, "8300")
                    part_num += 1
                else:
                    # systemd-boot, refind
                    wrapper.sgdisk_new(device_path, part_num, "ANTERGOS_BOOT", 512, "EF00")
                    part_num += 1

            wrapper.sgdisk_new(device_path, part_num, "ANTERGOS_ZFS", 0, "BF00")

            # Now init all other devices that will form part of the pool
            for device_path in device_paths[1:]:
                self.init_device(device_path, "GPT")
                wrapper.sgdisk_new(device_path, 1, "ANTERGOS_ZFS", 0, "BF00")
        else:
            # MBR
            self.init_device(device_path, "MBR")

            # Create boot partition (all sizes are in MiB)
            # if start is -1 wrapper.parted_mkpart assumes that our partition starts at 1 (first partition in disk)
            start = -1
            end = 512
            wrapper.parted_mkpart(device_path, "primary", start, end)

            # Set boot partition as bootable
            wrapper.parted_set(device_path, "1", "boot", "on")

            start = end
            end = "-1s"
            wrapper.parted_mkpart(device_path, "primary", start, end)

            # Now init all other devices that will form part of the pool
            for device_path in device_paths[1:]:
                self.init_device(device_path, "MBR")
                wrapper.parted_mkpart(device_path, "primary", -1, "-1s")

        # Wait until /dev initialized correct devices
        subprocess.check_call(["udevadm", "settle"])

        self.create_zfs_pool()

    def check_call(self, cmd):
        try:
            logging.debug(" ".join(cmd))
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as err:
            txt = "Command {0} has failed: {1}".format(err.cmd, err.stderr)
            logging.error(txt)
            txt = _("Command {0} has failed: {1}").format(err.cmd, err.stderr)
            raise InstallError(txt)

    def create_zfs_pool(self):
        # Create the root zpool
        device_paths = self.zfs_options["device_paths"]
        if len(device_paths) <= 0:
            txt = _("No devices were selected for ZFS")
            raise InstallError(txt)

        device_path = device_paths[0]

        # Make sure the ZFS modules are loaded
        self.check_call(["modprobe", "zfs"])

        # Command: zpool create zroot /dev/disk/by-id/id-to-partition
        device_id = self.ids[device_path]
        cmd = ["zpool", "create"]
        if self.zfs_options["force_4k"]:
            cmd.extend(["-o", "ashift=12"])
        cmd.extend(["antergos", device_id])
        self.check_call(cmd)

        # Set the mount point of the root filesystem
        self.check_call(["zfs", "set", "mountpoint=/", "antergos"])

        # Set the bootfs property on the descendant root filesystem so the
        # boot loader knows where to find the operating system.
        self.check_call(["zpool", "set", "bootfs=antergos", "antergos"])

        # Create swap zvol
        cmd = [
            "zfs", "create", "-V", "8G", "-b", os.sysconf("SC_PAGE_SIZE"),
            "-o", "primarycache=metadata", "-o", "com.sun:auto-snapshot=false",
            "antergos/swap"]
        self.check_call(cmd)

        # Export the pool
        self.check_call(["zpool", "export", "antergos"])

        # Finally, re-import the pool
        self.check_call(["zpool", "import", "-d", "/dev/disk/by-id", "-R", "/install", "antergos"])

        # Create zpool.cache file
        self.check_call(["zpool", "set", "cachefile=/etc/zfs/zpool.cache", "antergos"])

    def get_ids(self):
        """ Get disk and partitions IDs """
        path = "/dev/disk/by-id"
        for entry in os.scandir(path):
            if not entry.name.startswith('.') and entry.is_symlink() and entry.name.startswith("ata"):
                dest_path = os.readlink(entry.path)
                device = dest_path.split("/")[-1]
                self.ids[device] = entry.name

    def run_install(self, packages, metalinks):
        """ Start installation process """
        pass

try:
    _("")
except NameError as err:
    def _(message):
        return message

if __name__ == '__main__':
    # When testing, no _() is available

    from test_screen import _, run
    run('zfs')