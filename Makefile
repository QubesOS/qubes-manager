VERSION := $(shell cat version)

PYTHON ?= python3

LRELEASE_QT6 ?= $(if $(wildcard /etc/debian_version),/usr/lib/qt6/bin/lrelease,lrelease-qt6)
RCC ?= $(if $(wildcard /etc/debian_version),/usr/lib/qt6/libexec/rcc,/usr/lib64/qt6/libexec/rcc)

SETUPTOOLS_OPTS =
SETUPTOOLS_OPTS += $(if $(wildcard /etc/debian_version),--install-layout=deb,)

export QT_HASH_SEED=0
export PYTHONHASHSEED=0
export QT_SELECT=qt6

qubesmanager/ui_%.py: ui/%.ui
	pyuic6 -o $@ $<
	touch --reference=$< $@

ui: $(patsubst ui/%.ui,qubesmanager/ui_%.py,$(wildcard ui/*.ui))

res:
	$(RCC) -g python resources.qrc | sed '0,/PySide6/s//PyQt6/' > qubesmanager/resources.py
	touch --reference=resources.qrc qubesmanager/resources.py

translations:
	$(LRELEASE_QT6) qubesmanager.pro

python:
	$(PYTHON) ./setup.py build

python_install:
	$(PYTHON) ./setup.py install -O1 --skip-build --root $(DESTDIR) $(SETUPTOOLS_OPTS)

update_ts: res
	pylupdate6 qubesmanager.pro

install:
	mkdir -p $(DESTDIR)/usr/libexec/qubes-manager/
	cp qubesmanager/mount_for_backup.sh $(DESTDIR)/usr/libexec/qubes-manager/
	cp qubesmanager/qvm_about.sh $(DESTDIR)/usr/libexec/qubes-manager/

	mkdir -p $(DESTDIR)/usr/share/applications
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
