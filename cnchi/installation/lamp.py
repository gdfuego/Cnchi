#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  lamp.py
#
#  Copyright © 2013-2015 Antergos
#
#  This file is part of Cnchi.
#
#  Cnchi is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  Cnchi is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Cnchi; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

import subprocess
import os
import sys
import logging

import chroot

DEST_DIR = '/install'

def chroot_run(cmd):
    chroot.run(cmd, DEST_DIR)

def setup_lamp():
	try:
	    cmd = ["systemctl", "stop", "httpd"]
	    subprocess.check_call(cmd)
	except subprocess.CalledProcessError as process_error:
		pass

	mariadb_setup()
	apache_setup()
	php_setup()


def mariadb_setup():
	cmd = [
		"mysql_install_db",
		"--user=mysql",
		"--basedir=/usr",
		"--datadir=/var/lib/mysql"]
	chroot_run(cmd)

def apache_setup():
	# Allow site virtualization
	with open('/etc/httpd/conf/httpd.conf','a') as httpd_conf:
		httpd_conf.write('IncludeOptional conf/sites-enabled/*.conf\n')
		httpd_conf.write('IncludeOptional conf/mods-enabled/*.conf\n')

	# We create config directories
	dirs = [
		"etc/httpd/conf/sites-available",
		"etc/httpd/conf/sites-enabled",
		"etc/httpd/conf/mods-enabled"]

	for path in dirs:
		path = os.path.join(DEST_DIR, path)
		if not os.path.exists(path):
			try:
				os.mkdir(path)
			except OSError:
				pass

	# Copy a2ensite and a2dissite scripts
	scripts = ["a2ensite", "a2dissite"]
	for script in scripts:
	    try:
			src = os.path.join("/usr/share/cnchi/scripts", script)
			dst = os.path.join(DEST_DIR, 'usr/local/bin', script)
	        shutil.copy2(src, dst)
	    except (FileExistsError, shutil.Error) as file_error:
	        logging.warning(file_error)

    chroot_run(["chmod", "a+x", "/usr/local/bin/a2ensite"])
    chroot_run(["chmod", "a+x", "/usr/local/bin/a2dissite"])

	# Create localhost.conf in /etc/httpd/conf/sites-available/
	localhost_path = os.path.join(DEST_DIR, "etc/httpd/conf/sites-available/localhost.conf")
	with open(localhost_path, 'w') as localhost_conf:
		localhost_conf.write('Alias /phpmyadmin "/usr/share/webapps/phpMyAdmin"\n')
		localhost_conf.write('<Directory "/usr/share/webapps/phpMyAdmin">\n')
		localhost_conf.write('    DirectoryIndex index.html index.php\n')
		localhost_conf.write('    AllowOverride All\n')
		localhost_conf.write('    Options FollowSymlinks\n')
		localhost_conf.write('    Require all granted\n')
		localhost_conf.write('</Directory>\n')

	# We activate the virtual localhost site
	chroot_run(["a2ensite", "localhost"])

def php_setup():
	# Comment mpm_event_module
	httpd_path = os.path.join(DEST_DIR, 'etc/httpd/conf/httpd.conf')
	with open(httpd_path, 'r') as load_module:
		lines = load_module.readlines()
	with open(httpd_path, 'w') as load_module:
		for line in lines:
			if "LoadModule mpm_event_module" in line:
				line = '# LoadModule mpm_event_module modules/mod_mpm_event.so\n'
			load_module.write(line)

	# Add mpm_prefork_module and php5_module
	php_path = os.path.join(DEST_DIR, '/etc/httpd/conf/mods-enabled/php.conf')
	with open(php_path, 'w') as php_conf:
		php_conf.write("LoadModule mpm_prefork_module /etc/httpd/modules/mod_mpm_prefork.so\n")
		php_conf.write("LoadModule php5_module /etc/httpd/modules/libphp5.so\n")
		php_conf.write("Include conf/extra/php5_module.conf\n")

	# Setup /etc/php/php.ini
	php_ini_path = os.path.join(DEST_DIR, '/etc/php/php.ini')
	with open(php_ini_path, 'r') as php_ini:
		lines = php_ini.readlines()

	with open(php_ini_path, 'w') as php_ini:
		for line in phpmyadmin:
			# Locate and uncomment the above extensions.
			# extension=mysql.so
			if ";extension=mysql.so" in line:
				line = 'extension=mysql.so\n'
			# extension=mcrypt.so
			if ";extension=mcrypt.so" in line:
				line = 'extension=mcrypt.so\n'
			# extension=mssql.so
			if ";extension=mssql.so" in line:
				line = 'extension=mssql.so\n'
			# extension=mysqli.so
			if ";extension=mysqli.so" in line:
				line = 'extension=mysqli.so\n'
			# extension=openssl.so
			if ";extension=openssl.so" in line:
				line = 'extension=openssl.so\n'
			# extension=iconv.so
			if ";extension=iconv.so" in line:
				line = 'extension=iconv.so\n'
			# extension=imap.so
			if ";extension=imap.so" in line:
				line = 'extension=imap.so\n'
			# extension=zip.so
			if ";extension=zip.so" in line:
				line = 'extension=zip.so\n'
			# extension=bz2.so
			if ";extension=bz2.so" in line:
				line = 'extension=bz2.so\n'
			# Al mateix fitxer buscar i localitzar "open_basedir" statement and add PhpMyAdmin system path
			# (/etc/webapps/ and /usr/share/webapps/) to make sure PHP can access and read files under those directories
			if "open_basedir =" in line:
				line = 'open_basedir = /srv/http/:/home/:/tmp/:/usr/share/pear/:/usr/share/webapps/:/etc/webapps/\n'
			php_ini.write(line)

	ln1 = os.path.join(DEST_PATH, 'etc/httpd/conf/sites-enabled/localhost.conf')
	ln2 = os.path.join(DEST_PATH, 'etc/httpd/conf/sites-available/localhost.conf')
	chroot_run(["ln", "-s", ln2, ln1])
