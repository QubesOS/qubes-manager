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
            'qubesmanager': ['i18n/*']
        },
        entry_points={
            'console_scripts': [
                'qubes-global-settings = qubesmanager.global_settings:main',
                'qubes-vm-settings = qubesmanager.settings:main',
                'qubes-vm-create = qubesmanager.create_new_vm:main',
            ],
        })
