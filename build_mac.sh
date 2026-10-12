#!/bin/sh
# Build "dist/File Organiser.app" and dist/FileOrganiser-mac.dmg. Run on a Mac.
#
# The version comes from APP_VERSION (the release workflow sets it from the
# tag) or organiser/__init__.py.
set -e
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3}
APP="dist/File Organiser.app"
"$PYTHON" -m pip install --quiet pyinstaller pillow certifi
mkdir -p build
"$PYTHON" -c "from organiser.icon import save_icns; save_icns('build/icon.icns')"
VERSION=${APP_VERSION:-$("$PYTHON" -c "import organiser; print(organiser.__version__)")}

rm -rf "$APP"
"$PYTHON" -m PyInstaller --noconfirm --windowed --name "File Organiser" \
    --icon build/icon.icns --osx-bundle-identifier io.github.vavoss123.fileorganiser \
    app.py

# PyInstaller writes version 0.0.0 and no reason for the Finder prompt.
"$PYTHON" - "$APP/Contents/Info.plist" "$VERSION" <<'EOF'
import plistlib, sys
path, version = sys.argv[1], sys.argv[2]
with open(path, "rb") as handle:
    info = plistlib.load(handle)
info.update({
    "CFBundleShortVersionString": version,
    "CFBundleVersion": version,
    "CFBundleDisplayName": "File Organiser",
    "LSApplicationCategoryType": "public.app-category.utilities",
    "NSAppleEventsUsageDescription": "File Organiser asks Finder to move the duplicates "
        "and old installers you pick to the Trash, so you can put them back if you "
        "change your mind.",
})
with open(path, "wb") as handle:
    plistlib.dump(info, handle)
EOF
# Editing Info.plist breaks PyInstaller's signature; Apple silicon Macs refuse
# to run an app with a broken one, so sign it again (ad hoc: no certificate).
codesign --force --deep --sign - "$APP"

# A disk image holding the app and a shortcut to Applications to drag it onto.
rm -rf build/dmg dist/FileOrganiser-mac.dmg
mkdir -p build/dmg
cp -R "$APP" build/dmg/
ln -s /Applications build/dmg/Applications
hdiutil create -volname "File Organiser" -srcfolder build/dmg -ov -format UDZO \
    dist/FileOrganiser-mac.dmg
echo "Built $APP and dist/FileOrganiser-mac.dmg (version $VERSION)"
