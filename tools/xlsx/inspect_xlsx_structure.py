from pathlib import Path
from typing import Any
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
        workbook_root = ET.fromstring(z.read("xl/workbook.xml"))
        rel_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rel_map: dict[str, str] = {
            rel.attrib['Id']: rel.attrib['Target']
            for rel in rel_root.findall('rel:Relationship', NS_REL)
            if 'Id' in rel.attrib and 'Target' in rel.attrib
        }
        shared: list[str] = []
        if 'xl/sharedStrings.xml' in names:
            shared_root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in shared_root.findall('m:si', NS_MAIN):
                shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS_MAIN['m'])))
        for sheet in workbook_root.findall('m:sheets/m:sheet', NS_MAIN):
            rid = sheet.attrib.get('{%s}id' % NS_MAIN['r'])
            target = rel_map.get(rid, '') if rid else ''
            if target.startswith('/'):
                target = target[1:]
            elif not target.startswith('xl/'):
                target = 'xl/' + target
            target = target.replace('xl//', 'xl/')
            xml = z.read(target).decode('utf-8', 'replace') if target in names else ''
            dim = re.search(r'<dimension\b[^>]*ref="([^"]+)"', xml)
            rows = len(re.findall(r'<row\b', xml))
            headers: list[tuple[str, str, Any]] = []
            first_row = re.search(r'<row\b[^>]*r="1"[^>]*>(.*?)</row>', xml, re.S)
            if first_row:
                for cell in re.finditer(r'<c\b([^>]*)>(.*?)</c>', first_row.group(1), re.S):
                    attrs_cell = dict(re.findall(r'(\w+)="([^"]*)"', cell.group(1)))
                    value = re.search(r'<v>(.*?)</v>', cell.group(2), re.S)
                    raw = value.group(1) if value else ''
                    if attrs_cell.get('t') == 's' and raw.isdigit() and int(raw) < len(shared):
                        raw = shared[int(raw)]
                    headers.append((attrs_cell.get('r', ''), attrs_cell.get('t', ''), raw))
            print({"name": sheet.attrib.get('name'), "sheet_id": sheet.attrib.get('sheetId'), "target": target, "dimension": dim.group(1) if dim else None, "xml_rows": rows, "header_cells": headers[:20]})
