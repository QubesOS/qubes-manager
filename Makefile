RPMS_DIR=rpm/
help:
	@echo "make rpms -- generate binary rpm packages"
	@echo "make res  -- compile resources"
	@echo "make update-repo -- copy newly generated rpms to qubes yum repo"
	@echo "make update-repo-testing -- same, but to -testing repo"


rpms:	
	rpmbuild --define "_rpmdir $(RPMS_DIR)" -bb rpm_spec/qmgr.spec
	rpm --addsign $(RPMS_DIR)/x86_64/*.rpm

res:
	pyrcc4 -o qubesmanager/qrc_resources.py resources.qrc
	pyuic4 -o qubesmanager/ui_newappvmdlg.py newappvmdlg.ui
	pyuic4 -o qubesmanager/ui_editfwrulesdlg.py editfwrulesdlg.ui
	pyuic4 -o qubesmanager/ui_newfwruledlg.py newfwruledlg.ui

update-repo:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*.rpm ../yum/r1/dom0/rpm/

update-repo-testing:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*.rpm ../yum/r1-testing/dom0/rpm/

