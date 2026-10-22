import os, plistlib, pathlib
p = pathlib.Path(os.environ['ATV_APP_PATH'])/'Contents/Info.plist'
v = os.environ['ATV_BUILD_VERSION']
d = dict(CFBundleName='ATVLoadly', CFBundleDisplayName='ATVLoadly', CFBundleIdentifier='local.atvloadly.native', CFBundleExecutable='ATVLoadly', CFBundlePackageType='APPL', CFBundleShortVersionString=v, CFBundleVersion=os.environ.get("ATV_BUILD_NUMBER", v), LSMinimumSystemVersion='13.0', LSUIElement=True, NSLocalNetworkUsageDescription='Discover and pair with your Apple TV.', NSBonjourServices=['_remotepairing._tcp','_remotepairing-manual-pairing._tcp','_apple-mobdev2._tcp'], SUEnableAutomaticChecks=True, SUAutomaticallyUpdate=False, SUVerifyUpdateBeforeExtraction=True, SURequireSignedFeed=True)
feed, key = os.environ.get('ATV_UPDATE_FEED'), os.environ.get('ATV_UPDATE_PUBLIC_KEY')
if bool(feed) != bool(key): raise SystemExit('Both the HTTPS feed and trusted signing public key are required')
if feed:
 if not feed.startswith('https://'): raise SystemExit('Update feed must use HTTPS')
 d.update(SUFeedURL=feed, SUPublicEDKey=key)
p.write_bytes(plistlib.dumps(d))
