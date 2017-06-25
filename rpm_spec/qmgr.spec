%{!?version: %define version %(cat version)}

Name:		qubes-manager
Version:	%{version}
Release:	1%{?dist}
Summary:	The Graphical Qubes VM Manager.

Group:		Qubes
Vendor:		Invisible Things Lab
License:	GPL
URL:		http://fixme
Requires:	python3, PyQt4, qubes-core-dom0-linux >= 2.0.22, qubes-core-dom0 >= 3.0.18
Requires:	pmount, cryptsetup, wmctrl
Requires:	dbus
Requires:	qubes-artwork
BuildRequires:	python3-PyQt4-devel
BuildRequires:  python3-devel
BuildRequires:  qt-devel
AutoReq:	0

%define _builddir %(pwd)

%description
The Graphical Qubes VM Manager.

%build
make res translations
python3 -m compileall qubesmanager
python3 -O -m compileall qubesmanager

%install
mkdir -p $RPM_BUILD_ROOT/usr/bin/
cp qubes-manager $RPM_BUILD_ROOT/usr/bin
cp qubes-vm-settings $RPM_BUILD_ROOT/usr/bin

mkdir -p $RPM_BUILD_ROOT/usr/libexec/qubes-manager/
cp qubesmanager/mount_for_backup.sh $RPM_BUILD_ROOT/usr/libexec/qubes-manager/
cp qubesmanager/qvm_about.sh $RPM_BUILD_ROOT/usr/libexec/qubes-manager/
cp qubesmanager/qvm_net.py $RPM_BUILD_ROOT/usr/libexec/qubes-manager/

mkdir -p $RPM_BUILD_ROOT%{python3_sitelib}/qubesmanager/
cp -r qubesmanager/__pycache__ $RPM_BUILD_ROOT%{python3_sitelib}/qubesmanager/
cp qubesmanager/*.py $RPM_BUILD_ROOT%{python3_sitelib}/qubesmanager/

mkdir -p $RPM_BUILD_ROOT%{python3_sitelib}/qubesmanager/i18n
cp i18n/qubesmanager_*.qm $RPM_BUILD_ROOT%{python3_sitelib}/qubesmanager/i18n/

mkdir -p $RPM_BUILD_ROOT/usr/share/applications
cp qubes-manager.desktop $RPM_BUILD_ROOT/usr/share/applications
mkdir -p $RPM_BUILD_ROOT/etc/xdg/autostart/
cp qubes-manager.desktop $RPM_BUILD_ROOT/etc/xdg/autostart/

install -D org.qubesos.QubesManager.conf $RPM_BUILD_ROOT/etc/dbus-1/system.d/org.qubesos.QubesManager.conf
install -D org.qubesos.QubesManager.xml $RPM_BUILD_ROOT/usr/share/dbus-1/interfaces/org.qubesos.QubesManager.xml

%post
update-desktop-database &> /dev/null || :
killall -1 qubes-manager || :

%postun
update-desktop-database &> /dev/null || :

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)
/usr/bin/qubes-manager
/usr/bin/qubes-vm-settings
/usr/libexec/qubes-manager/mount_for_backup.sh
/usr/libexec/qubes-manager/qvm_about.sh
/usr/libexec/qubes-manager/qvm_net.py
/usr/libexec/qubes-manager/qvm_net.pyo
/usr/libexec/qubes-manager/qvm_net.pyc
%dir %{python3_sitelib}/qubesmanager
%{python3_sitelib}/qubesmanager/__pycache__
%{python3_sitelib}/qubesmanager/__init__.py
%{python3_sitelib}/qubesmanager/main.py
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
%{python3_sitelib}/qubesmanager/networknotes.py
%{python3_sitelib}/qubesmanager/create_new_vm.py
%{python3_sitelib}/qubesmanager/thread_monitor.py
%{python3_sitelib}/qubesmanager/resources_rc.py
%{python3_sitelib}/qubesmanager/qvm_net.py
%{python3_sitelib}/qubesmanager/ui_backupdlg.py
%{python3_sitelib}/qubesmanager/ui_globalsettingsdlg.py
%{python3_sitelib}/qubesmanager/ui_mainwindow.py
%{python3_sitelib}/qubesmanager/ui_multiselectwidget.py
%{python3_sitelib}/qubesmanager/ui_newappvmdlg.py
%{python3_sitelib}/qubesmanager/ui_newfwruledlg.py
%{python3_sitelib}/qubesmanager/ui_restoredlg.py
%{python3_sitelib}/qubesmanager/ui_settingsdlg.py
%{python3_sitelib}/qubesmanager/ui_logdlg.py
%{python3_sitelib}/qubesmanager/ui_about.py
%{python3_sitelib}/qubesmanager/ui_releasenotes.py
%{python3_sitelib}/qubesmanager/ui_informationnotes.py
%{python3_sitelib}/qubesmanager/ui_networknotes.py
%{python3_sitelib}/qubesmanager/i18n/qubesmanager_*.qm
/usr/share/applications/qubes-manager.desktop
/etc/xdg/autostart/qubes-manager.desktop
/etc/dbus-1/system.d/org.qubesos.QubesManager.conf
/usr/share/dbus-1/interfaces/org.qubesos.QubesManager.xml
