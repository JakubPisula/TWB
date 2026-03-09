"""
Tests for test_regex_parsing_v2.
Migrated from root directory during AI-Update cleanup.
"""
import re
html = '<div><span class="icon header wood" title="Drewno"></span>1.000&nbsp;99</div>'
for loot_entry in re.findall(
        r'<span class="icon header (wood|stone|iron)".+?</span>([\d\.,\s&nbsp;]+)', html
):
    amount = re.sub(r'[^\d]', '', loot_entry[1])
    print(loot_entry[0], amount)
