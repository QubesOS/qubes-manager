%{!?version: %define version %(cat version)}

Name:		qubes-manager
Version:	%{version}
Release:	1%{?dist}
Summary:	The Graphical Qubes VM Manager.

Group:		Qubes
Vendor:		Invisible Things Lab
License:	GPL
URL:		http://fixme
Requires:	python3
Requires:	python3-PyQt4
Requires:	python3-inotify
Requires:	python3-qubesadmin >= 4.0.7
Requires:	qubes-artwork
Requires:	pmount
Requires:	cryptsetup
Requires:	wmctrl
Requires:	dbus
BuildRequires:	python3-PyQt4-devel
BuildRequires:	python3-devel
BuildRequires:	qt-devel
AutoReq:	0

%define _builddir %(pwd)

%description
The Graphical Qubes VM Manager.

%build
make ui res translations
make python

%install
make python_install \
    DESTDIR=$RPM_BUILD_ROOT

mkdir -p $RPM_BUILD_ROOT/usr/libexec/qubes-manager/
cp qubesmanager/mount_for_backup.sh $RPM_BUILD_ROOT/usr/libexec/qubes-manager/
cp qubesmanager/qvm_about.sh $RPM_BUILD_ROOT/usr/libexec/qubes-manager/

mkdir -p $RPM_BUILD_ROOT/usr/share/applications
cp qubes-global-settings.desktop $RPM_BUILD_ROOT/usr/share/applications/
cp qubes-vm-create.desktop $RPM_BUILD_ROOT/usr/share/applications/


%post
update-desktop-database &> /dev/null || :
killall -1 qubes-manager || :

%postun
update-desktop-database &> /dev/null || :

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)
/usr/bin/qubes-global-settings
/usr/bin/qubes-vm-settings
/usr/bin/qubes-vm-create
/usr/bin/qubes-vm-boot-from-device
/usr/libexec/qubes-manager/mount_for_backup.sh
/usr/libexec/qubes-manager/qvm_about.sh

%dir %{python3_sitelib}/qubesmanager
%{python3_sitelib}/qubesmanager/__pycache__
%{python3_sitelib}/qubesmanager/__init__.py
%{python3_sitelib}/qubesmanager/clipboard.py
%{python3_sitelib}/qubesmanager/block.py
%{python3_sitelib}/qubesmanager/table_widgets.py
%{python3_sitelib}/qubesmanager/appmenu_select.py
%{python3_sitelib}/qubesmanager/backup.py
%{python3_sitelib}/qubesmanager/backup_utils.py
%{python3_sitelib}/qubesmanager/firewall.py
%{python3_sitelib}/qubesmanager/global_settings.py
%{python3_sitelib}/qubesmanager/multiselectwidget.py
%{python3_sitelib}/qubesmanager/restore.py
%{python3_sitelib}/qubesmanager/settings.py
%{python3_sitelib}/qubesmanager/log_dialog.py
%{python3_sitelib}/qubesmanager/about.py
%{python3_sitelib}/qubesmanager/releasenotes.py
%{python3_sitelib}/qubesmanager/informationnotes.py
%{python3_sitelib}/qubesmanager/create_new_vm.py
%{python3_sitelib}/qubesmanager/thread_monitor.py
%{python3_sitelib}/qubesmanager/utils.py
%{python3_sitelib}/qubesmanager/bootfromdevice.py

%{python3_sitelib}/qubesmanager/resources_rc.py

%{python3_sitelib}/qubesmanager/ui_backupdlg.py
%{python3_sitelib}/qubesmanager/ui_bootfromdevice.py
%{python3_sitelib}/qubesmanager/ui_globalsettingsdlg.py
%{python3_sitelib}/qubesmanager/ui_multiselectwidget.py
%{python3_sitelib}/qubesmanager/ui_newappvmdlg.py
%{python3_sitelib}/qubesmanager/ui_newfwruledlg.py
%{python3_sitelib}/qubesmanager/ui_restoredlg.py
%{python3_sitelib}/qubesmanager/ui_settingsdlg.py
%{python3_sitelib}/qubesmanager/ui_logdlg.py
%{python3_sitelib}/qubesmanager/ui_about.py
%{python3_sitelib}/qubesmanager/ui_releasenotes.py
%{python3_sitelib}/qubesmanager/ui_informationnotes.py
%{python3_sitelib}/qubesmanager/i18n/qubesmanager_*.qm
%{python3_sitelib}/qubesmanager/i18n/qubesmanager_*.ts

%dir %{python3_sitelib}/qubesmanager-*.egg-info
%{python3_sitelib}/qubesmanager-*.egg-info/*

/usr/share/applications/qubes-global-settings.desktop
/usr/share/applications/qubes-vm-create.desktop
