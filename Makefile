VERSION := $(shell cat version)

PYTHON ?= python3

LRELEASE_QT5 ?= $(if $(wildcard /etc/debian_version),lrelease,lrelease-qt5)

SETUPTOOLS_OPTS =
SETUPTOOLS_OPTS += $(if $(wildcard /etc/debian_version),--install-layout=deb,)

export QT_HASH_SEED=0
export PYTHONHASHSEED=0

qubesmanager/ui_%.py: ui/%.ui
	pyuic5 --from-imports -o $@ $<
	touch --reference=$< $@

ui: $(patsubst ui/%.ui,qubesmanager/ui_%.py,$(wildcard ui/*.ui))

res:
	pyrcc5 -o qubesmanager/resources_rc.py resources.qrc
	touch --reference=resources.qrc qubesmanager/resources_rc.py

translations:
	$(LRELEASE_QT5) qubesmanager.pro

python:
	$(PYTHON) ./setup.py build

python_install:
	$(PYTHON) ./setup.py install -O1 --skip-build --root $(DESTDIR) $(SETUPTOOLS_OPTS)

update_ts: res
	pylupdate5 qubesmanager.pro

install:
	mkdir -p $(DESTDIR)/usr/libexec/qubes-manager/
	cp qubesmanager/mount_for_backup.sh $(DESTDIR)/usr/libexec/qubes-manager/
	cp qubesmanager/qvm_about.sh $(DESTDIR)/usr/libexec/qubes-manager/

	mkdir -p $(DESTDIR)/usr/share/applications
	cp qubes-global-settings.desktop $(DESTDIR)/usr/share/applications/
	cp qubes-vm-create.desktop $(DESTDIR)/usr/share/applications/
	cp qubes-backup.desktop $(DESTDIR)/usr/share/applications/
	cp qubes-backup-restore.desktop $(DESTDIR)/usr/share/applications/
	cp qubes-qube-manager.desktop $(DESTDIR)/usr/share/applications/
	cp qubes-template-manager.desktop $(DESTDIR)/usr/share/applications/
	cp qubes-template-switcher.desktop $(DESTDIR)/usr/share/applications/

	mkdir -p $(DESTDIR)/usr/share/desktop-directories/
	cp qubes-tools.directory $(DESTDIR)/usr/share/desktop-directories/

	mkdir -p $(DESTDIR)/etc/xdg/menus/applications-merged/
	cp qubes-tools.menu $(DESTDIR)/etc/xdg/menus/applications-merged/

clean:
	rm -f qubesmanager/ui_*.py
	rm -rf debian/changelog.*
	rm -rf pkgs
