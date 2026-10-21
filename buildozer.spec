[app]

title = Sskid Obfuscator
package.name = sskid
package.domain = com.sskid
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.exclude_dirs = .github,pycache,.buildozer,bin,.git
version = 2.0.0

requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.2.1,cython==0.29.36,pyjnius,android

orientation = portrait
fullscreen = 0

android.api = 31
android.minapi = 21
android.ndk = 25b
android.ndk_api = 21
android.archs = arm64-v8a
android.permissions =
android.allow_backup = True
android.accept_sdk_license = True

android.debug_manifest_package = com.sskid.sskid
android.release_artifact = aab

p4a.branch = master
p4a.source_dir =

log_level = 2
warn_on_root = 1
