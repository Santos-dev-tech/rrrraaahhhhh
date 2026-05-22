import os

paths = [
    r"C:\Users\ADMIN\AppData\Roaming\MetaQuotes\Terminal\59C07D676775FCCF79E223EC24AB0D86\config\common.ini",
    r"C:\Users\ADMIN\AppData\Roaming\MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\config\common.ini",
    r"C:\Users\ADMIN\AppData\Roaming\MetaQuotes\Terminal\53785E099C927DB68A545C249CDBCE06\config\common.ini",
    r"C:\Users\ADMIN\AppData\Roaming\MetaQuotes\Terminal\9C24AC3B8966969552CE94C53FF78B1B\config\common.ini"
]

for path in paths:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-16le') as f:
            content = f.read()
        
        content = content.replace("Enabled=0", "Enabled=1")
        content = content.replace("Account=1", "Account=0")
        content = content.replace("Profile=1", "Profile=0")
        
        with open(path, 'w', encoding='utf-16le') as f:
            f.write(content)
        print(f"Patched {path}")
