from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
import hashlib, json, zipfile, io, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'sources' / 'cdna_changes'
DEST.mkdir(parents=True, exist_ok=True)
SOURCES = {
 'architecture': 'https://www.amd.com/en/technologies/cdna.html',
 'machine-readable': 'https://gpuopen.com/machine-readable-isa/',
 'isa4': 'https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-cdna4-instruction-set-architecture.pdf',
 'isa5': 'https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-cdna5-instruction-set-architecture.pdf',
 'whitepaper4': 'https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/white-papers/amd-cdna-4-architecture-whitepaper.pdf',
 'whitepaper5': 'https://www.amd.com/content/dam/amd/en/documents/products/technologies/cdna/amd-cdna5-whitepaper.pdf',
 'lds5': 'https://rocm.blogs.amd.com/software-tools-optimization/mi450-lds-optimization/README.html',
 'attention5': 'https://rocm.blogs.amd.com/software-tools-optimization/gluon-attention-decode-mi450/README.html',
 'gemm4': 'https://rocm.blogs.amd.com/software-tools-optimization/cdna4-gemm-kernels/README.html',
 'flydsl': 'https://rocm.docs.amd.com/projects/FlyDSL/en/latest/architecture_guide.html',
 'llvm-usage': 'https://llvm.org/docs/AMDGPUUsage.html',
 'llvm-dma': 'https://www.llvm.org/docs/AMDGPUDMAOperations.html',
 'clang-builtins': 'https://releases.llvm.org/23.1.0/tools/clang/docs/AMDGPUBuiltinReference.html',
 'helios-blog': 'https://rocm.blogs.amd.com/ecosystems-and-partners/cdna5-helios/README.html',
 'product4': 'https://www.amd.com/en/products/accelerators/instinct/mi350/mi355x.html',
 'product5': 'https://www.amd.com/en/products/accelerators/instinct/mi400/mi455x.html',
 'microarch4': 'https://rocmdocs.amd.com/en/latest/reference/gpu-arch/mi350.html',
 'rga': 'https://gpuopen.com/rga/',
}

class Extract(HTMLParser):
 def __init__(self):
  super().__init__(); self.parts=[]; self.skip=0; self.links=[]
 def handle_starttag(self, tag, attrs):
  if tag in ('script','style'): self.skip+=1
  if tag in ('p','div','section','li','h1','h2','h3','h4','h5','h6','tr','br','pre'): self.parts.append('\n')
  if tag=='a': self.links.append(dict(attrs).get('href',''))
 def handle_endtag(self, tag):
  if tag in ('script','style'): self.skip-=1
  if tag in ('p','div','li','tr','pre'): self.parts.append('\n')
 def handle_data(self, data):
  if not self.skip: self.parts.append(data)

def get(url):
 host=urlparse(url).hostname or ''
 if not any(host==d or host.endswith('.'+d) for d in ('amd.com','gpuopen.com','llvm.org','github.com','raw.githubusercontent.com')):
  raise ValueError('Unexpected download host: '+host)
 with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=90) as r:
  return r.read(),r.geturl()

def collect(key,url):
 data,final=get(url); suffix='.pdf' if data.startswith(b'%PDF') else '.html'
 path=DEST/(key+suffix); path.write_bytes(data)
 rec={'key':key,'url':url,'resolved_url':final,'path':str(path.relative_to(ROOT)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'retrieved':'2026-10-15'}
 if suffix=='.pdf':
  from pypdf import PdfReader
  reader=PdfReader(io.BytesIO(data)); rec['pages']=len(reader.pages)
  texts=[]
  for i,p in enumerate(reader.pages): texts.append(f'\n===== PDF PAGE {i+1} =====\n'+(p.extract_text() or ''))
  (DEST/(key+'.txt')).write_text(''.join(texts),encoding='utf-8')
 else:
  p=Extract(); p.feed(data.decode('utf-8',errors='replace'))
  (DEST/(key+'.txt')).write_text('\n'.join(x for x in (' '.join(s.split()) for s in ''.join(p.parts).splitlines()) if x),encoding='utf-8')
  if key=='machine-readable': rec['zip_links']=[urljoin(url,x) for x in p.links if '.zip' in x or '/download/machine-readable-isa/' in x]
 return rec

def main():
 manifest=[]
 with ThreadPoolExecutor(max_workers=5) as pool:
  futures={pool.submit(collect,k,u):k for k,u in SOURCES.items()}
  for f in as_completed(futures):
   key=futures[f]
   try:
    rec=f.result(); manifest.append(rec); print(key,rec['bytes'],flush=True)
   except Exception as e: manifest.append({'key':key,'url':SOURCES[key],'error':str(e)}); print(key,'ERROR',str(e),flush=True)
 mr=next((r for r in manifest if r['key']=='machine-readable'),{})
 links=mr.get('zip_links',[])
 print('ZIP_LINKS',links,flush=True)
 if links:
  url=links[0]; data,final=get(url); (DEST/'amdgpu-isa-specifications.zip').write_bytes(data)
  extracted=[]
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   for name in z.namelist():
    if name.lower().endswith(('amdgpu_isa_cdna4.xml','amdgpu_isa_cdna5.xml')):
     file=DEST/Path(name).name; file.write_bytes(z.read(name)); extracted.append(file.name)
  manifest.append({'key':'isa-xml','url':url,'resolved_url':final,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'extracted':extracted,'retrieved':'2026-10-15'})
  print('XML',extracted,flush=True)
 (DEST/'source-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__': main()
