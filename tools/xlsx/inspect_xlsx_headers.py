from pathlib import Path
from zipfile import ZipFile
import re
import sys
import xml.etree.ElementTree as ET

NS_MAIN = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
NS_REL = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
for raw_path in sys.argv[1:]:
    path = Path(raw_path)
    print(f"=== {path.name} ===")
    with ZipFile(path) as z:
        names = set(z.namelist())
        shared=[]
        if 'xl/sharedStrings.xml' in names:
            root=ET.fromstring(z.read('xl/sharedStrings.xml'))
            shared=[''.join(t.text or '' for t in si.iter('{%s}t' % NS_MAIN['m'])) for si in root.findall('m:si', NS_MAIN)]
        wb=ET.fromstring(z.read('xl/workbook.xml'))
        rel=ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))
        relmap={x.attrib['Id']:x.attrib['Target'] for x in rel.findall('rel:Relationship',NS_REL)}
        for sheet in wb.findall('m:sheets/m:sheet',NS_MAIN):
            target='xl/'+relmap[sheet.attrib['{%s}id'%NS_MAIN['r']]].lstrip('/')
            xml=z.read(target).decode('utf8','replace')
            rows=re.findall(r'<row\b[^>]*>(.*?)</row>',xml,re.S)[:8]
            print('TAB',sheet.attrib.get('name'),target)
            for row in rows:
                rn=re.search(r'<row\b[^>]*\br="(\d+)"',row)
                vals=[]
                for cm in re.finditer(r'<c\b([^>]*)>(.*?)</c>',row,re.S):
                    attrs=dict(re.findall(r'(\w+)="([^"]*)"',cm.group(1)))
                    v=re.search(r'<v>(.*?)</v>',cm.group(2),re.S)
                    val=v.group(1) if v else ''
                    if attrs.get('t')=='s' and val.isdigit() and int(val)<len(shared): val=shared[int(val)]
                    if val: vals.append((attrs.get('r',''),val[:80]))
                print(' row',rn.group(1) if rn else '?',vals[:18])
