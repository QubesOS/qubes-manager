%{!?python_sitearch: %define python_sitearch %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib(1)")}

%{!?version: %define version %(cat version)}

Name:		qubes-manager
Version:	%{version}
Release:	1%{?dist}
Summary:	The Graphical Qubes VM Manager.

Group:		Qubes
Vendor:		Invisible Things Lab
License:	GPL
URL:		http://fixme
Requires:	python, PyQt4, qubes-core-dom0-linux >= 2.0.22, qubes-core-dom0 >= 3.0.18
Requires:	pmount, cryptsetup, wmctrl
Requires:	dbus
Requires:	qubes-artwork
BuildRequires:	PyQt4-devel
AutoReq:	0

%define _builddir %(pwd)

%description
The Graphical Qubes VM Manager.

%build
make res
python -m compileall qubesmanager
python -O -m compileall qubesmanager

%install
mkdir -p $RPM_BUILD_ROOT/usr/bin/
cp qubes-manager $RPM_BUILD_ROOT/usr/bin
cp qubes-vm-settings $RPM_BUILD_ROOT/usr/bin

mkdir -p $RPM_BUILD_ROOT/usr/libexec/qubes-manager/
cp qubesmanager/mount_for_backup.sh $RPM_BUILD_ROOT/usr/libexec/qubes-manager/

mkdir -p $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager/
cp qubesmanager/main.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/block.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/table_widgets.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/appmenu_select.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/backup.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/backup_utils.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/firewall.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/global_settings.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/multiselectwidget.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/restore.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/settings.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/log_dialog.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/about.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/releasenotes.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/create_new_vm.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/thread_monitor.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/resources_rc.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/__init__.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_backupdlg.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_globalsettingsdlg.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_mainwindow.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_multiselectwidget.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_newappvmdlg.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_newfwruledlg.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_restoredlg.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_settingsdlg.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_logdlg.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_about.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager
cp qubesmanager/ui_releasenotes.py{,c,o} $RPM_BUILD_ROOT%{python_sitearch}/qubesmanager

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
%dir %{python_sitearch}/qubesmanager
%{python_sitearch}/qubesmanager/__init__.py
%{python_sitearch}/qubesmanager/__init__.pyo
%{python_sitearch}/qubesmanager/__init__.pyc
%{python_sitearch}/qubesmanager/main.py
%{python_sitearch}/qubesmanager/main.pyc
%{python_sitearch}/qubesmanager/main.pyo
%{python_sitearch}/qubesmanager/block.py
%{python_sitearch}/qubesmanager/block.pyc
%{python_sitearch}/qubesmanager/block.pyo
%{python_sitearch}/qubesmanager/table_widgets.py
%{python_sitearch}/qubesmanager/table_widgets.pyc
%{python_sitearch}/qubesmanager/table_widgets.pyo
%{python_sitearch}/qubesmanager/appmenu_select.py
%{python_sitearch}/qubesmanager/appmenu_select.pyc
%{python_sitearch}/qubesmanager/appmenu_select.pyo
%{python_sitearch}/qubesmanager/backup.py
%{python_sitearch}/qubesmanager/backup.pyc
%{python_sitearch}/qubesmanager/backup.pyo
%{python_sitearch}/qubesmanager/backup_utils.py
%{python_sitearch}/qubesmanager/backup_utils.pyc
%{python_sitearch}/qubesmanager/backup_utils.pyo
%{python_sitearch}/qubesmanager/firewall.py
%{python_sitearch}/qubesmanager/firewall.pyc
%{python_sitearch}/qubesmanager/firewall.pyo
%{python_sitearch}/qubesmanager/global_settings.py
%{python_sitearch}/qubesmanager/global_settings.pyc
%{python_sitearch}/qubesmanager/global_settings.pyo
%{python_sitearch}/qubesmanager/multiselectwidget.py
%{python_sitearch}/qubesmanager/multiselectwidget.pyc
%{python_sitearch}/qubesmanager/multiselectwidget.pyo
%{python_sitearch}/qubesmanager/restore.py
%{python_sitearch}/qubesmanager/restore.pyc
%{python_sitearch}/qubesmanager/restore.pyo
%{python_sitearch}/qubesmanager/settings.py
%{python_sitearch}/qubesmanager/settings.pyc
%{python_sitearch}/qubesmanager/settings.pyo
%{python_sitearch}/qubesmanager/log_dialog.py
%{python_sitearch}/qubesmanager/log_dialog.pyc
%{python_sitearch}/qubesmanager/log_dialog.pyo
%{python_sitearch}/qubesmanager/about.py
%{python_sitearch}/qubesmanager/about.pyc
%{python_sitearch}/qubesmanager/about.pyo
%{python_sitearch}/qubesmanager/releasenotes.py
%{python_sitearch}/qubesmanager/releasenotes.pyc
%{python_sitearch}/qubesmanager/releasenotes.pyo
%{python_sitearch}/qubesmanager/create_new_vm.py
%{python_sitearch}/qubesmanager/create_new_vm.pyc
%{python_sitearch}/qubesmanager/create_new_vm.pyo
%{python_sitearch}/qubesmanager/thread_monitor.py
%{python_sitearch}/qubesmanager/thread_monitor.pyc
%{python_sitearch}/qubesmanager/thread_monitor.pyo
%{python_sitearch}/qubesmanager/resources_rc.py
%{python_sitearch}/qubesmanager/resources_rc.pyc
%{python_sitearch}/qubesmanager/resources_rc.pyo
%{python_sitearch}/qubesmanager/ui_backupdlg.py
%{python_sitearch}/qubesmanager/ui_backupdlg.pyc
%{python_sitearch}/qubesmanager/ui_backupdlg.pyo
%{python_sitearch}/qubesmanager/ui_globalsettingsdlg.py
%{python_sitearch}/qubesmanager/ui_globalsettingsdlg.pyc
%{python_sitearch}/qubesmanager/ui_globalsettingsdlg.pyo
%{python_sitearch}/qubesmanager/ui_mainwindow.py
%{python_sitearch}/qubesmanager/ui_mainwindow.pyc
%{python_sitearch}/qubesmanager/ui_mainwindow.pyo
%{python_sitearch}/qubesmanager/ui_multiselectwidget.py
%{python_sitearch}/qubesmanager/ui_multiselectwidget.pyc
%{python_sitearch}/qubesmanager/ui_multiselectwidget.pyo
%{python_sitearch}/qubesmanager/ui_newappvmdlg.py
%{python_sitearch}/qubesmanager/ui_newappvmdlg.pyc
%{python_sitearch}/qubesmanager/ui_newappvmdlg.pyo
%{python_sitearch}/qubesmanager/ui_newfwruledlg.py
%{python_sitearch}/qubesmanager/ui_newfwruledlg.pyc
%{python_sitearch}/qubesmanager/ui_newfwruledlg.pyo
%{python_sitearch}/qubesmanager/ui_restoredlg.py
%{python_sitearch}/qubesmanager/ui_restoredlg.pyc
%{python_sitearch}/qubesmanager/ui_restoredlg.pyo
%{python_sitearch}/qubesmanager/ui_settingsdlg.py
%{python_sitearch}/qubesmanager/ui_settingsdlg.pyc
%{python_sitearch}/qubesmanager/ui_settingsdlg.pyo
%{python_sitearch}/qubesmanager/ui_logdlg.py
%{python_sitearch}/qubesmanager/ui_logdlg.pyc
%{python_sitearch}/qubesmanager/ui_logdlg.pyo
%{python_sitearch}/qubesmanager/ui_about.py
%{python_sitearch}/qubesmanager/ui_about.pyc
%{python_sitearch}/qubesmanager/ui_about.pyo
%{python_sitearch}/qubesmanager/ui_releasenotes.py
%{python_sitearch}/qubesmanager/ui_releasenotes.pyc
%{python_sitearch}/qubesmanager/ui_releasenotes.pyo


/usr/share/applications/qubes-manager.desktop
/etc/xdg/autostart/qubes-manager.desktop
/etc/dbus-1/system.d/org.qubesos.QubesManager.conf
/usr/share/dbus-1/interfaces/org.qubesos.QubesManager.xml
