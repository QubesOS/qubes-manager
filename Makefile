RPMS_DIR=rpm/
VERSION := $(shell cat version)
help:
	@echo "make rpms                  -- generate binary rpm packages"
	@echo "make res                   -- compile resources"
	@echo "make update-repo-current   -- copy newly generated rpms to qubes yum repo"
	@echo "make update-repo-unstable  -- same, but to -testing repo"
	@echo "make update-repo-installer -- copy dom0 rpms to installer repo"


rpms: rpms-dom0

rpms-vm:

rpms-dom0:
	rpmbuild --define "_rpmdir $(RPMS_DIR)" -bb rpm_spec/qmgr.spec
	rpm --addsign $(RPMS_DIR)/x86_64/qubes-manager*$(VERSION)*.rpm

qubesmanager/ui_%.py: ui/%.ui
	pyuic4 -o $@ $<

ui: $(patsubst ui/%.ui,qubesmanager/ui_%.py,$(wildcard ui/*.ui))

res:
	pyrcc4 -o qubesmanager/resources_rc.py resources.qrc

translations:
	lrelease-qt4 qubesmanager.pro

update_ts: res
	pylupdate4 qubesmanager.pro

update-repo-current:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*$(VERSION)*.rpm ../yum/current-release/current/dom0/rpm/

update-repo-current-testing:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*$(VERSION)*.rpm ../yum/current-release/current-testing/dom0/rpm/

update-repo-unstable:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*$(VERSION)*.rpm ../yum/current-release/unstable/dom0/rpm/

update-repo-installer:
	ln -f $(RPMS_DIR)/x86_64/qubes-manager-*$(VERSION)*.rpm ../installer/yum/qubes-dom0/rpm/

clean:
