#!/usr/bin/python3 -O
# vim: fileencoding=utf-8

import setuptools

if __name__ == '__main__':
    setuptools.setup(
        name='qubesmanager',
        version=open('version').read().strip(),
        author='Invisible Things Lab',
        author_email='qubes-devel@googlegroups.com',
        description='Qubes OS Manager',
        license='GPL2+',
        url='https://www.qubes-os.org/',
        packages=setuptools.find_packages(),
        package_data={
            'qubesmanager': ['i18n/*', '*.css']
        },
        entry_points={
            'console_scripts': [
                'qubes-vm-settings = qubesmanager.settings:main',
                'qubes-vm-clone = qubesmanager.clone_vm:main',
                'qubes-vm-boot-from-device = qubesmanager.bootfromdevice:main',
                'qubes-backup = qubesmanager.backup:main',
                'qubes-backup-restore = qubesmanager.restore:main',
                'qubes-qube-manager = qubesmanager.qube_manager:main',
                'qubes-log-viewer = qubesmanager.log_dialog:main',
                'qubes-template-manager = qubesmanager.template_manager:main',
                'qvm-template-gui = qubesmanager.qvm_template_gui:main'
            ],
        })
