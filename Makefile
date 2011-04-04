RPMS_DIR=rpm/
VERSION := $(shell cat version)
help:
	@echo "make rpms                 -- generate binary rpm packages"
	@echo "make res                  -- compile resources"
	@echo "make update-repo-current  -- copy newly generated rpms to qubes yum repo"
	@echo "make update-repo-unstable -- same, but to -testing repo"


rpms:	
	rpmbuild --define "_rpmdir $(RPMS_DIR)" -bb rpm_spec/qmgr.spec
	rpm --addsign $(RPMS_DIR)/x86_64/qubes-manager*$(VERSION)*.rpm

res:
	pyrcc4 -o qubesmanager/qrc_resources.py resources.qrc
	pyuic4 -o qubesmanager/ui_newappvmdlg.py newappvmdlg.ui
	pyuic4 -o qubesmanager/ui_editfwrulesdlg.py editfwrulesdlg.ui
	pyuic4 -o qubesmanager/ui_newfwruledlg.py newfwruledlg.ui

update-repo-current:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*$(VERSION)*.rpm ../yum/current-release/current/dom0/rpm/

update-repo-unstable:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*$(VERSION)*.rpm ../yum/current-release/unstable/dom0/rpm/
