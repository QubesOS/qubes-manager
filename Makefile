VERSION := $(shell cat version)

res:
	pyrcc4 -o qubesmanager/resources_rc.py resources.qrc
	pyuic4 -o qubesmanager/ui_mainwindow.py mainwindow.ui
	pyuic4 -o qubesmanager/ui_newappvmdlg.py newappvmdlg.ui
	pyuic4 -o qubesmanager/ui_editfwrulesdlg.py editfwrulesdlg.ui
	pyuic4 -o qubesmanager/ui_newfwruledlg.py newfwruledlg.ui
	pyuic4 -o qubesmanager/ui_multiselectwidget.py multiselectwidget.ui
clean:
