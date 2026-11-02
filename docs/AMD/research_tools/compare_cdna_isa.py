from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter
import json, sys, hashlib

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'sources'/'cdna_changes'

def read(gen):
 path=DEST/f'amdgpu_isa_cdna{gen}.xml'
 root=ET.parse(path).getroot()
 records={}
 for i in root.findall('./ISA/Instructions/Instruction'):
  name=i.findtext('InstructionName')
  records[name]={
   'name':name,
   'aliases':[a.text for a in i.findall('./AliasedInstructionNames/InstructionName')],
   'group':i.findtext('./FunctionalGroup/Name'),
   'subgroups':[s.text for s in i.findall('./FunctionalGroup/FunctionalSubgroups/Subgroup')],
   'description':' '.join((i.findtext('Description') or '').split()),
   'encodings':[{'name':e.findtext('EncodingName'),'opcode':e.findtext('Opcode'),'condition':e.findtext('EncodingCondition')} for e in i.findall('./InstructionEncodings/InstructionEncoding')],
  }
 assert records
 return records,{'release':root.findtext('./Document/ReleaseDate'),'schema':root.findtext('./Document/SchemaVersion'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
 old,m4=read(4); new,m5=read(5)
 a,b=set(old),set(new)
 same=sorted(a&b)
 alias_matches=[]; ambiguous=[]
 for x in sorted(a-b):
  names={x,*old[x]['aliases']}
  matches=[y for y in b-a if names & {y,*new[y]['aliases']}]
  if len(matches)==1: alias_matches.append({'cdna4':x,'cdna5':matches[0],'shared_names':sorted(names & {matches[0],*new[matches[0]]['aliases']})})
  elif matches: ambiguous.append({'cdna4':x,'cdna5':matches})
 mapped_old={x['cdna4'] for x in alias_matches}; mapped_new={x['cdna5'] for x in alias_matches}
 old_only=sorted(a-b-mapped_old); new_only=sorted(b-a-mapped_new)
 records=[]
 for name in sorted(a|b):
  status='same-name' if name in a&b else 'cdna5-only' if name in new_only else 'cdna4-only' if name in old_only else 'alias-linked'
  records.append({'name':name,'status':status,'cdna4':old.get(name),'cdna5':new.get(name)})
 result={'method':'Unique direct InstructionName under ISA/Instructions; exact canonical-name intersection, then unique cross-generation alias-set intersection. This is a documentation-name diff, not an ISA compatibility proof or a count of new hardware capabilities.',
  'retrieved':'2026-10-15','metadata':{'cdna4':m4,'cdna5':m5},
  'counts':{'cdna4':len(a),'cdna5':len(b),'same_name':len(same),'raw_cdna5_only':len(b-a),'raw_cdna4_only':len(a-b),'alias_pairs':len(alias_matches),'alias_unique_old':len(mapped_old),'alias_unique_new':len(mapped_new),'unmatched_cdna5':len(new_only),'unmatched_cdna4':len(old_only),'ambiguous':len(ambiguous)},
  'same_names':same,'alias_matches':alias_matches,'ambiguous':ambiguous,'cdna5_only':new_only,'cdna4_only':old_only,
  'group_counts':{'cdna4':dict(Counter(x['group'] for x in old.values())),'cdna5':dict(Counter(x['group'] for x in new.values()))},'instructions':records}
 (DEST/'isa-diff.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result['counts'],indent=2)); print('NEW', '\n'.join(new_only)); print('OLD','\n'.join(old_only)); print('AMBIGUOUS',ambiguous)

if __name__=='__main__': main()
