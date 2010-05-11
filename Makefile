RPMS_DIR=rpm/
help:
	@echo "make rpms -- generate binary rpm packages"
	@echo "make res  -- compile resources"

rpms:	
	rpmbuild --define "_rpmdir $(RPMS_DIR)" -bb qmgr.spec
	rpm --addsign $(RPMS_DIR)/x86_64/*.rpm


res:
	pyrcc4 -o qubesmanager/qrc_resources.py resources.qrc
	pyuic4 -o qubesmanager/ui_newappvmdlg.py newappvmdlg.ui
