import re
with open(r"C:\Program Files\MetaTrader 5 EXNESS\config\servers.dat", 'rb') as f:
    data = f.read().decode('utf-16le', errors='ignore')

matches = re.findall(r'[\w\-]+(?:Live|Demo|Server)[\w\-]*', data)
print("Possible server names:")
for m in set(matches):
    if "Next" in m or "NLF" in m or "Level" in m:
        print(m)
