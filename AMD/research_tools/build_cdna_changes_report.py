from pathlib import Path
from html import escape as H
import json, re, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'sources'/'cdna_changes'
D=json.loads((SRC/'isa-diff.json').read_text(encoding='utf-8'))
MANIFEST=json.loads((SRC/'source-manifest.json').read_text(encoding='utf-8'))
URL={x['key']:x['url'] for x in MANIFEST if 'error' not in x}
TEXT={g:(SRC/f'isa{g}.txt').read_text(encoding='utf-8') for g in [4,5]}
RECORDS={g:{r['name']:r[f'cdna{g}'] for r in D['instructions'] if r[f'cdna{g}']} for g in [4,5]}

def ref(key,label=None,page=None):
 u=URL[key]+(f'#page={page}' if page else '')
 return f'<a href="{H(u,quote=True)}" target="_blank" rel="noreferrer">{H(label or key)}</a>'

def code(s): return '<code>'+H(s)+'</code>'
def codes(*ss): return '<div class="codes">'+''.join(code(s) for s in ss)+'</div>'
def page_for(g,name):
 # Prefer instruction definitions (a name followed by its decimal opcode), over references and TOC.
 matches=list(re.finditer(r'(?m)^'+re.escape(name)+r'\s+\d+\s*$',TEXT[g]))
 if not matches: matches=list(re.finditer(re.escape(name),TEXT[g]))
 if not matches: return None
 p=matches[-1].start()
 return int(re.findall(r'===== PDF PAGE (\d+) =====',TEXT[g][:p])[-1])

FEATURES=[
 ('执行模型','目标 ISA','gfx950；MI350 / MI355X','gfx1250；MI450 文档 / MI455X 产品','编译目标跨 GFX 大版本变化；手写汇编、code object 和内核调度需要重新适配。','flydsl,rga'),
 ('执行模型','计算组织与 wave','256 CU；原生 Wave64；4×SIMD16 / CU','256 WGP；原生 Wave32；4×SIMD32 / WGP','lane 映射、shuffle / ballot、EXEC mask、tile 和 workgroup wave 数都会变化；CU 与 WGP 数量不能按同构单元直接换算。','whitepaper4,whitepaper5'),
 ('执行模型','驻留与寄存器','最多 32 Wave64 / CU；每线程 256 个普通 VGPR，另有 AGPR 空间','最多 64 Wave32 / WGP；每线程可寻址 1024 个 VGPR；S_SET_VGPR_MSB / S_ALLOC_VGPR','512 KiB 物理向量寄存器容量 / 单元保持；更多 wave 槽和更大逻辑地址范围不等于寄存器总容量翻倍。','microarch4,whitepaper5,isa5'),
 ('矩阵与数值','矩阵指令模型','V_MFMA_* / V_SMFMAC_*；Wave64 与累加寄存器模型','V_WMMA_* / V_SWMMAC_*；Wave32，矩阵结果放入 VGPR','矩阵 fragment 的 lane / register 布局和 tile 形状需要重做；不是简单替换助记符。','isa-xml,isa5'),
 ('矩阵与数值','微缩放格式','已支持 MXFP4、MXFP6、MXFP8；block-32、E8M0 缩放','保留并扩展为 block-16 / 32；FP4 可用 E5M3 / E4M3 fractional scale','新增重点在缩放粒度与精度；合法 data / scale 组合有限制，不能任意混搭。','isa4,isa5'),
 ('矩阵与数值','BF16 向量与超越函数','BF16 矩阵和转换已有；无本次列表中的原生 BF16 packed 算术与 tanh 族','V_PK_ADD_BF16 / V_PK_FMA_BF16 / V_PK_MUL_BF16；V_TANH_{F32,F16,BF16}','BF16 的向量计算覆盖扩大；现有超越函数吞吐按 AMD 公布最高提升约 2×，不是所有函数实测延迟均减半。','isa-xml,whitepaper5'),
 ('矩阵与数值','4-bit LUT 与转换','已有微缩放转换和随机舍入','新增 V_PERM_PK16_B{4,6,8}_U4；扩展 packed 转换与随机舍入组合','在 VALU 中以 4-bit 索引查表，生成 4 / 6 / 8-bit 数据；适合压缩权重解量化。随机舍入本身不是本代首次出现。','helios-blog,isa-xml'),
 ('矩阵与数值','双操作与标量计算','已有 co-execution；SALU 以整数 / 控制为主','新增 VOPD / VOPD3 的 V_DUAL_*；增加 S_ADD / MUL / FMAC / CVT 等 FP16 / FP32 操作','新增显式双操作编码与更多标量浮点指令；不能把“支持双发射”整体算作 CDNA 5 首创。','isa4,isa5,isa-xml'),
 ('搬运与同步','Tensor Data Mover','已有 global / buffer → LDS 直载；无本次 TDM descriptor 指令族','TENSOR_LOAD_TO_LDS / TENSOR_STORE_FROM_LDS；描述最多 5D tensor tile，异步双向搬运','增量在专用张量描述、地址生成与异步执行，配合 multicast；免中间 VGPR 暂存并非所有路径都到本代才支持。','llvm-dma,isa5'),
 ('搬运与同步','异步 LDS DMA','GLOBAL_LOAD_LDS_*；LDS 基址的 wave 级约束','GLOBAL_LOAD_ASYNC_TO_LDS_* / GLOBAL_STORE_ASYNC_FROM_LDS_*；ASYNCCNT 与逐 lane LDS 基址','新增明确的异步 load / store 模型；不要把 LLVM 的 async intrinsic 命名直接当作 CDNA 4 没有异步硬件的证明。','llvm-dma'),
 ('搬运与同步','Workgroup cluster / multicast','以单 CU 内 workgroup 为主要协作单位','同一 SE 最多 16 个 workgroup，各在独立 WGP；cluster barrier 与广播掩码','可跨 WGP 复用加载数据、同步合作；CLUSTER_LOAD 的来源是 global，不代表任意远程 LDS 读写能力。','isa5,llvm-dma'),
 ('搬运与同步','拆分与命名 barrier','S_BARRIER：整个 workgroup 的同步点','S_BARRIER_SIGNAL / WAIT；每 workgroup 最多 16 个 named barrier，WGP 池共 64 个','可先 signal，再做独立工作，最后 wait；子集 wave 的 producer / consumer 同步更灵活。','isa5,isa-xml'),
 ('搬运与同步','等待计数与缓存控制','S_WAITCNT；VM / LGKM 等计数；VMEM 的 SC0 / SC1 / NT','LOAD / STORE / DS / KM / ASYNC / TENSOR 等独立等待；SCOPE 与 TH','更细粒度追踪搬运完成；SCOPE 区分 WGP / SE / DEV / SYS，缓存和原子语义需按新编码复核。','isa4,isa5,clang-builtins'),
 ('存储与系统','LDS 与 WGP cache','160 KiB LDS + 32 KiB vector cache / CU；LDS 读带宽 256 B / clk','320 KiB LDS + 64 KiB L0 vector cache / WGP；双端口合计可达 512 B / clk','LDS 容量 2×；跨 SIMD pair 同周期访问同一 64 KiB partition 会串行化，不能只检查 bank conflict。','whitepaper4,lds5'),
 ('存储与系统','LDS 转置读取','DS_READ_B64_TR_B{4,8,16}，DS_READ_B96_TR_B6 已存在','DS_LOAD_TR4_B64 / TR6_B96 / TR8_B64 / TR16_B128；另有 GLOBAL_LOAD_TR*','16-bit LDS 转置每 lane 读取从 B64 扩展到 B128；其他变体需逐项检查布局，不能把整族都记为新功能。','isa-xml,lds5'),
 ('存储与系统','全局 cache 层次','每 GPU 32 MiB L2（8×4）+ 256 MiB Infinity Cache','每 GPU 192 MiB 全局 L2（2×96）；官网不再列独立 Infinity Cache','L2 单层为 6×；整体层次重组，不等于把所有末级 cache 容量加起来后仍是 6×。','microarch4,architecture,whitepaper5'),
 ('存储与系统','HBM 与芯粒封装','MI355X：288 GB HBM3E，8 stacks，8 TB/s；3 nm + 6 nm','MI455X：432 GB HBM4，12 stacks，23.3 TB/s；2 nm + 3 nm','容量 1.5×、峰值带宽 2.91×。这些是指定产品的参数，不是所有 CDNA 5 SKU 的统一下限。','product4,product5'),
 ('存储与系统','Scale-up / scale-out','典型 8-GPU scale-up；MI355X 总 scale-up 约 1.07 TB/s 双向','Helios 72-GPU；每 MI455X UALoE scale-up 3.6 TB/s 双向，scale-out 最高 600 GB/s 双向','平台协作范围扩至 rack；UALoE scale-up、对 NIC 的 UALink / PCIe 接口与跨 rack Ethernet 需分开。','whitepaper5,helios-blog'),
]

ISA_FAMILIES=[
 ('矩阵执行','V_MFMA_F32_16X16X32_F16','V_WMMA_F32_16X16X32_F16','Wave64 MFMA → Wave32 WMMA；同样的 M/N/K 文本也不代表 fragment 布局相同。'),
 ('稀疏矩阵','V_SMFMAC_F32_16X16X64_F16','V_SWMMAC_F32_16X16X64_F16','稀疏操作迁移至 SWMMAC；CDNA 5 XML 也列出 FP8 / BF8 SWMMAC，不能仅凭官网总表省略就断言 FP8 稀疏消失。'),
 ('block-16 缩放','V_MFMA_SCALE_F32_16X16X128_F8F6F4','V_WMMA_SCALE16_F32_16X16X128_F8F6F4','SCALE16 与 SCALE 分别覆盖 16 / 32 元素缩放块；FP4 还扩展 fractional scale。'),
 ('Tensor DMA',None,'TENSOR_LOAD_TO_LDS|TENSOR_STORE_FROM_LDS','专用 TDM，descriptor 驱动；完成用 TENSORCNT 等机制跟踪。'),
 ('异步 LDS load / store','GLOBAL_LOAD_LDS_DWORDX4','GLOBAL_LOAD_ASYNC_TO_LDS_B128|GLOBAL_STORE_ASYNC_FROM_LDS_B128','global↔LDS，ASYNCCNT；这是能力与地址模型扩展，不能机械建立一条旧指令等于一条新指令的映射。'),
 ('Cluster broadcast',None,'CLUSTER_LOAD_B128|CLUSTER_LOAD_ASYNC_TO_LDS_B128','global load + workgroup 广播掩码，用于 cluster 数据复用。'),
 ('Split / named barrier','S_BARRIER','S_BARRIER_INIT|S_BARRIER_SIGNAL|S_BARRIER_WAIT|S_BARRIER_JOIN|S_BARRIER_LEAVE','分开到达和等待，并支持 wave 子集成员管理。'),
 ('内存 barrier',None,'DS_ATOMIC_ASYNC_BARRIER_ARRIVE_B64|DS_ATOMIC_BARRIER_ARRIVE_RTN_B64','在 LDS 中维护 barrier 状态，可与异步搬运完成协作。'),
 ('细粒度等待','S_WAITCNT','S_WAIT_LOADCNT|S_WAIT_STORECNT|S_WAIT_DSCNT|S_WAIT_KMCNT|S_WAIT_ASYNCCNT|S_WAIT_TENSORCNT','分别等待不同管线。列表还包含 S_WAIT_XCNT、组合等待与 ALU 等待。'),
 ('VGPR 管理','V_ACCVGPR_READ|V_ACCVGPR_WRITE','S_SET_VGPR_MSB|S_ALLOC_VGPR','逻辑 VGPR 地址扩展；申请寄存器数有粒度、可用容量等约束，不能直接等同物理容量扩展。'),
 ('BF16 / tanh',None,'V_PK_ADD_BF16|V_PK_FMA_BF16|V_PK_MUL_BF16|V_TANH_F32|V_TANH_F16|V_TANH_BF16','原生 BF16 向量算术和 tanh 是明确增量。'),
 ('4-bit lookup',None,'V_PERM_PK16_B4_U4|V_PERM_PK16_B6_U4|V_PERM_PK16_B8_U4','16 个 4-bit 索引，在 VALU 中查表输出 4 / 6 / 8-bit 元素。'),
 ('双操作编码',None,'V_DUAL_FMA_F32|V_DUAL_FMA_F64','VOPD / VOPD3 描述两条并行 VALU 操作；受合法配对和寄存器端口等约束。'),
 ('标量浮点',None,'S_ADD_F32|S_MUL_F32|S_FMAC_F32|S_CVT_F32_F16','更多 wave-uniform 计算可留在 SALU。'),
 ('转置 load 扩展','DS_READ_B64_TR_B16','DS_LOAD_TR16_B128|GLOBAL_LOAD_TR16_B128','旧代已有 LDS transpose；本代扩大部分读取宽度并新增 global transpose 家族。'),
 ('名称 / 别名变化','GLOBAL_LOAD_DWORD|S_LOAD_DWORD','GLOBAL_LOAD_B32|S_LOAD_B32','XML 显式别名对应，不能计为两种新硬件功能；相同名字也不能保证编码和语义兼容。'),
]

PERF=[
 ('MXFP4 matrix','10.1 PFLOP/s','40.3 PFLOP/s','约 4×'),
 ('MXFP6 matrix','10.1 PFLOP/s','20.1 PFLOP/s','约 2×'),
 ('MXFP8 / OCP FP8 matrix','5 PFLOP/s','20.1 PFLOP/s','约 4×'),
 ('FP16 / BF16 matrix','2.5 PFLOP/s','5 PFLOP/s','2×'),
 ('INT8 matrix','5 POP/s','5 POP/s','按公开值基本持平'),
 ('FP32 vector / matrix','157.3 TFLOP/s','315 TFLOP/s','约 2×'),
 ('FP64 vector / matrix','78.6 TFLOP/s','5 TFLOP/s','约 0.064×；下降约 93.6%'),
]

def feature_table():
 out=[]
 for group,name,old,new,why,srcs in FEATURES:
  links=' · '.join(ref(k,k.replace('whitepaper','白皮书 ').replace('isa-xml','XML')) for k in srcs.split(','))
  out.append(f'<tr><td><span class="eyebrow">{H(group)}</span><strong>{H(name)}</strong></td><td>{H(old)}</td><td>{H(new)}</td><td>{H(why)}<div class="rowrefs">{links}</div></td></tr>')
 return ''.join(out)

def instr_cell(g,s):
 if not s:return '<span class="muted">无对应指令族 / 不作一对一映射</span>'
 out=[]
 for name in s.split('|'):
  assert name in RECORDS[g],(g,name)
  out.append(ref(f'isa{g}',name,page_for(g,name)))
 return '<div class="codes">'+''.join('<code>'+x+'</code>' for x in out)+'</div>'

def isa_table():
 return ''.join(f'<tr><th>{H(title)}</th><td>{instr_cell(4,old)}</td><td>{instr_cell(5,new)}</td><td>{H(note)}</td></tr>' for title,old,new,note in ISA_FAMILIES)

def complete_rows():
 rows=[]
 for name in D['same_names']: rows.append({'status':'same','old':RECORDS[4][name],'new':RECORDS[5][name]})
 for x in D['alias_matches']: rows.append({'status':'alias','old':RECORDS[4][x['cdna4']],'new':RECORDS[5][x['cdna5']]})
 for name in D['cdna5_only']: rows.append({'status':'only5','old':None,'new':RECORDS[5][name]})
 for name in D['cdna4_only']: rows.append({'status':'only4','old':RECORDS[4][name],'new':None})
 assert len(rows)==1688
 assert len({r['old']['name'] for r in rows if r['old']})==1240
 assert len({r['new']['name'] for r in rows if r['new']})==1325
 for row in rows:
  for g,which in [(4,'old'),(5,'new')]:
   if row[which]: row[which]={**row[which],'page':page_for(g,row[which]['name'])}
 return rows

SOURCE_NOTES={
 'architecture':'架构总览；MI430X 的 CDNA 5 特性可能与 MI455X 不同，页面明确提示。',
 'product4':'MI355X 产品规格；作为本报告 CDNA 4 产品比较基线。',
 'product5':'MI455X 产品规格；FP64、INT8、HBM 和互联参数的直接来源。',
 'whitepaper4':'CDNA 4 白皮书；CU、已有 microscaling、160 KB LDS 和 cache 组织。',
 'whitepaper5':'CDNA 5 白皮书，24 页；Wave32、寄存器、TDM、HBM4、scale-up / out。',
 'isa4':'ISA 参考指南，2025-08-05，608 个 PDF 页面；页面锚点使用 PDF 页序。',
 'isa5':'ISA 参考指南，2026-07-27，832 个 PDF 页面；章节页码与 PDF 页序不同。',
 'machine-readable':'官方 XML 下载入口；2026 年 8 月更新，CDNA 5 schema 1.2.0。',
 'isa-xml':'实际下载 ZIP；CDNA 4 XML 日期 2026-02-20 / schema 1.1.1，CDNA 5 为 2026-08-03 / 1.2.0。',
 'helios-blog':'2026-08-04 官方博客；4-bit LUT、E5M3 scale 和 rack-scale 网络。',
 'lds5':'2026-08-28 官方优化博客；gfx1250 的 LDS transpose、64 KiB partition conflict。',
 'attention5':'MI450 attention decode 实例；WMMA 布局、TDM direct path 与流水调度约束。',
 'microarch4':'ROCm MI350 微架构；gfx950、L2 / Infinity Cache 与资源配置。',
 'flydsl':'ROCm FlyDSL：gfx950 / gfx1250、LDS 容量与后端功能映射。',
 'llvm-dma':'LLVM DMA 文档；区分 GFX9 旧式直载、GFX1250 async LDS 和 Tensor DMA。',
 'clang-builtins':'固定 LLVM 23.1.0 文档；Tensor DMA、WMMA、cpol 的 compiler-facing 接口。',
 'rga':'GPUOpen RGA 2.15.0（2026 年 10 月）确认 CDNA 5 / gfx1250 目标。',
}

def source_list():
 out=[]
 for key,note in SOURCE_NOTES.items():
  m=next(x for x in MANIFEST if x['key']==key and 'error' not in x)
  path=m.get('path','sources/cdna_changes/amdgpu-isa-specifications.zip').replace('\\','/')
  out.append(f'<li><div>{ref(key,key)} <a class="local" href="{H(path)}">本地快照</a></div><p>{H(note)}</p></li>')
 return ''.join(out)

html='''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AMD CDNA 4 → CDNA 5：架构 Feature 与完整 ISA 对比</title>
<style>
:root{--paper:#f5f3ee;--ink:#192b31;--muted:#5b6d73;--line:#d9dfdc;--teal:#086a69;--red:#bd352e;--soft:#e8efeb;--white:#fffefa}*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:72px}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,"Segoe UI","Microsoft YaHei",sans-serif;line-height:1.75}a{color:var(--teal);text-underline-offset:3px}a:hover{color:var(--red)}header,main,footer{max-width:1340px;margin:auto;padding:0 42px}header{padding-top:60px;padding-bottom:30px}.kicker,.eyebrow{font:600 11px/1.6 "Segoe UI",sans-serif;letter-spacing:1.4px;text-transform:uppercase;color:var(--teal)}h1{font-size:clamp(32px,4vw,58px);line-height:1.15;letter-spacing:-1.6px;margin:20px 0}h1 span{color:var(--red)}.lead{font-size:18px;max-width:940px;margin:20px 0}.meta,.muted,.note{color:var(--muted)}.meta{font-size:12px}.chips{display:flex;gap:8px;flex-wrap:wrap;margin-top:25px}.chips a,.badge{background:var(--soft);border-radius:4px;padding:5px 10px;font-size:12px;text-decoration:none}.scope{border-left:3px solid var(--red);padding:12px 20px;background:#fff6ef;margin-top:28px;font-size:14px}nav{position:sticky;top:0;z-index:5;background:rgba(245,243,238,.97);border-block:1px solid var(--line);backdrop-filter:blur(10px)}nav>div{max-width:1340px;margin:auto;padding:11px 42px;display:flex;gap:22px;overflow:auto;white-space:nowrap}nav a{text-decoration:none;font-size:13px}section{padding:42px 0;border-bottom:1px solid var(--line)}h2{font-size:27px;line-height:1.4;margin:9px 0 20px}h3{font-size:18px;margin:12px 0}p{margin:10px 0 16px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}.card{padding:22px;background:var(--white);border:1px solid var(--line);border-top:3px solid var(--teal)}.card h3{margin-top:0}.card p{font-size:14px;color:var(--muted);margin-bottom:0}.big{font-size:36px;line-height:1.2;letter-spacing:-1px;font-weight:650}.stats .card{border-top:0}.stats .card small{display:block;margin-top:8px;color:var(--muted)}.tablewrap{overflow:auto;border:1px solid var(--line);background:var(--white)}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.7}th,td{text-align:left;vertical-align:top;padding:17px 18px;border-bottom:1px solid var(--line)}thead th{background:#e8ece7;color:var(--ink);font-size:12px;white-space:nowrap}tbody th{font-weight:600;min-width:120px}tr:last-child>*{border-bottom:0}#feature-table{min-width:1000px}#feature-table td:nth-child(1){width:15%}#feature-table td:nth-child(2),#feature-table td:nth-child(3){width:24%}#feature-table .eyebrow{display:block;font-size:10px;letter-spacing:0;margin-bottom:4px}strong{font-weight:650}.rowrefs{font-size:11px;line-height:1.5;margin-top:9px}.codes{display:flex;gap:6px;flex-direction:column;align-items:flex-start}code{font-family:Consolas,"Cascadia Code",monospace;font-size:11.5px;background:#edf1ee;border-radius:3px;padding:2px 5px;overflow-wrap:anywhere;word-break:break-word}code a{text-decoration:none}.callout{border-left:3px solid var(--teal);background:#eaf0eb;padding:16px 22px;margin:22px 0;font-size:14px}.warn{border-color:var(--red);background:#fff1e8}.split{display:grid;grid-template-columns:1fr 1fr;gap:20px}.pipeline{padding:26px;border:1px solid var(--line);background:var(--white)}.node{border:1px solid #97ada6;border-radius:4px;padding:10px;text-align:center;font-size:13px}.node.accent{border:2px solid var(--teal);background:var(--soft);font-weight:600}.arrow{text-align:center;color:var(--teal);font-size:20px;line-height:1.5}.pipeline .note{font-size:12px}.three{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.three article{padding:18px 22px;border:1px solid var(--line);background:var(--white);font-size:14px}.three h3{font-size:16px}.controls{display:flex;gap:10px;flex-wrap:wrap;padding:16px;background:#e8ece7;border:1px solid var(--line);border-bottom:0}input,select,button{font:inherit;font-size:13px;padding:10px 12px;border:1px solid #aabbb3;border-radius:4px;background:var(--white);color:var(--ink)}input{flex:1;min-width:170px}button{cursor:pointer}button:hover{background:var(--soft)}button:disabled{opacity:.4;cursor:default}.pagination{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:12px 0;font-size:13px}.pagination>div{display:flex;gap:8px;align-items:center}#full-table{min-width:860px;table-layout:fixed}#full-table th:first-child{width:100px}#full-table th:nth-child(2),#full-table th:nth-child(3){width:28%}#full-table td{padding:12px}.instruction-name{font-weight:600}.aliases{font-size:11px;color:var(--muted);margin-top:7px;overflow-wrap:anywhere;line-height:1.5}.enc{font:11px/1.5 Consolas,monospace;color:var(--muted);margin-top:8px;overflow-wrap:anywhere}.status{font-size:11px;border-radius:3px;display:inline-block;padding:3px 7px;background:#e8ece7}.status.only5{color:#08635c;background:#e0f0e8}.status.only4{color:#9e4c2c;background:#fbebdc}.sourcegrid{columns:2;column-gap:40px;padding-left:22px}.sourcegrid li{break-inside:avoid;margin-bottom:18px;font-size:13px}.sourcegrid p{margin:5px 0;color:var(--muted);font-size:12px}.local{font-size:11px;margin-left:9px}details{margin:15px 0;border:1px solid var(--line);background:var(--white);padding:16px 20px}summary{cursor:pointer;font-weight:600}footer{padding-top:28px;padding-bottom:50px;font-size:12px;color:var(--muted)}.empty{padding:30px;text-align:center}#isa-families{min-width:1050px}#isa-families td:nth-child(2),#isa-families td:nth-child(3){width:29%}.perf td:last-child{font-weight:600}.perf tbody tr:last-child{background:#fff0e4}
@media(max-width:900px){header,main,footer{padding-left:22px;padding-right:22px}nav>div{padding-inline:22px}.cards,.three{grid-template-columns:1fr 1fr}.split{grid-template-columns:1fr}.sourcegrid{columns:1}h1{letter-spacing:-.8px}.lead{font-size:16px}}
@media(max-width:540px){header{padding-top:32px}.cards,.three{grid-template-columns:1fr}.card{padding:18px}section{padding:30px 0}h2{font-size:23px}.controls{display:grid;grid-template-columns:1fr}input,select,button{width:100%;min-width:0}.pagination{align-items:flex-start;gap:10px;flex-direction:column}.pagination>div{width:100%}.big{font-size:30px}.scope{padding:12px 15px}.tablewrap{max-width:100%}}
@media print{nav,.controls,.pagination,.chips{display:none!important}body{background:#fff}header,main,footer{max-width:none;padding-inline:0}h1{font-size:34px}section{break-inside:auto}.card,.pipeline,.three article{break-inside:avoid}.tablewrap{overflow:visible}table,#feature-table,#isa-families,#full-table{min-width:0!important;font-size:10px}th,td{padding:8px}a{color:inherit;text-decoration:none}.sourcegrid{columns:1}#list{break-before:page}.printnote{display:block!important}}
</style></head><body>
<header><div class="kicker">AMD INSTINCT · ARCHITECTURE & ISA RESEARCH</div><h1>CDNA 4 <span>→</span> CDNA 5</h1><p class="lead">从 Wave64 / MFMA，走向 Wave32 / WMMA、Tensor Data Mover 与多 WGP 协作。将架构变化、具体 ISA 和产品规格放在同一份证据索引中。</p><p class="meta">检索截止：2026-10-15（Asia/Shanghai） · 仅采用 AMD / GPUOpen / ROCm / LLVM 官方资料 · ISA 清单由实际 XML 差分生成</p><div class="chips"><a href="AMD-CDNA1-to-CDNA5-Per-CU-Throughput.html">各代每 CU 吞吐</a><a href="#matrix">18 项 feature 对比</a><a href="#isa">16 组关键 ISA</a><a href="#list">完整可检索清单</a><a href="sources/cdna_changes/isa-diff.json">下载差分 JSON</a><a href="#sources">官方来源</a></div><div class="scope"><strong>比较口径：</strong>按用户确认比较 CDNA 4 → CDNA 5；产品参数选 MI355X → MI455X。MI450 是部分官方 ISA / 优化文档使用的系列名。MI430X 等其他 CDNA 5 产品的启用特性可能不同，本报告不把 MI455X 参数外推至所有 SKU。</div></header>
<nav aria-label="报告目录"><div><a href="#takeaways">核心结论</a><a href="#matrix">Feature 对比</a><a href="#isa">关键 ISA</a><a href="#dataflow">搬运与同步</a><a href="#performance">性能与退化</a><a href="#pitfalls">易误判项</a><a href="#list">完整 ISA list</a><a href="#sources">来源与复核</a></div></nav>
<main>
<section id="takeaways"><div class="eyebrow">01 / What changed</div><h2>变化集中在执行方式、搬运和协作</h2><div class="cards"><article class="card"><h3>Wave32 + WMMA</h3><p>执行宽度、矩阵 fragment 和累加寄存器模型一起调整，旧的汇编调优假设需要重审。</p></article><article class="card"><h3>TDM + Cluster</h3><p>张量描述符驱动异步 global↔LDS 搬运，结合广播和 cluster 级同步扩大数据复用范围。</p></article><article class="card"><h3>低精度细化</h3><p>MX 格式延续；增加 block-16、fractional scale、4-bit LUT、BF16 向量和 tanh 指令。</p></article><article class="card"><h3>AI 与 HPC 分化</h3><p>MI455X 的低精度和内存显著增强，但其公开 FP64 为 5 TFLOP/s，低于 MI355X 的 78.6。</p></article></div><p class="note">这些结论分别可在下方的具体指令、产品参数和官方来源中逐项核查。“新列表出现”与“新硬件能力”采用不同口径。</p></section>
<section id="matrix"><div class="eyebrow">02 / Feature matrix</div><h2>CDNA 4 → CDNA 5 的 feature 变化</h2><div class="tablewrap"><table id="feature-table"><thead><tr><th>维度</th><th>CDNA 4 / MI355X 基线</th><th>CDNA 5 / MI455X 变化</th><th>影响与证据</th></tr></thead><tbody>__FEATURES__</tbody></table></div></section>
<section id="isa"><div class="eyebrow">03 / Instruction families</div><h2>关键 ISA：看具体指令，而不只看宣传名称</h2><p class="note">以下是概念与代表指令的对应，不保证语义、二进制编码或性能等价。点击助记符可跳到官方 ISA PDF 中对应定义的页序。</p><div class="tablewrap"><table id="isa-families"><thead><tr><th>功能</th><th>CDNA 4 代表指令</th><th>CDNA 5 代表指令</th><th>如何理解变化</th></tr></thead><tbody>__ISA__</tbody></table></div></section>
<section id="dataflow"><div class="eyebrow">04 / Data movement</div><h2>TDM 改变的是 tile 搬运路径与调度方式</h2><div class="split"><article class="pipeline"><h3>CDNA 4 的已有能力</h3><div class="node">Global / HBM</div><div class="arrow">↓</div><div class="node">通用 load → VGPR → LDS<br>或 GLOBAL_LOAD_LDS_* 直接加载到 LDS</div><div class="arrow">↓</div><div class="node">LDS → VGPR / AGPR fragment → MFMA</div><p class="note">旧代已能避免部分 global→LDS 路径的 VGPR 暂存。不能把“直达 LDS”作为 TDM 唯一新增点。</p></article><article class="pipeline"><h3>CDNA 5 的扩展能力</h3><div class="node">Global / HBM 中的 tensor tile</div><div class="arrow">↓ ↑</div><div class="node accent">SGPR descriptor → TDM<br>异步 global↔LDS，可配合 multicast</div><div class="arrow">↓</div><div class="node">LDS → VGPR fragment → WMMA</div><p class="note">TDM 搬运可与计算重叠；LDS→矩阵操作数寄存器这一步仍然存在。另有逐 lane async LDS DMA 家族。</p></article></div><div class="three"><article><h3>① 发起与计算重叠</h3><p>先提交下一块 tile 的 DMA，再计算当前 tile。等待应贴近真正的依赖点；TENSORCNT、ASYNCCNT 与 barrier 不是可以互相随意替代的机制。</p></article><article><h3>② 多 WGP 复用</h3><p>Cluster 将最多 16 个 workgroup 放在同一 SE；广播掩码选择参与者。适合复用相同的权重或激活，具体收益取决于布局和调度。</p></article><article><h3>③ 保留布局约束</h3><p>MI450 官方示例指出，TDM direct path 的最内层维度至少 128 B，推荐 256 B；LDS 仍需同时检查 bank 与 partition 冲突。</p></article></div><p class="rowrefs">证据：__DMA__ · __ATTN__ · __LDS__。调优建议是由这些机制推导出的研究方向，不是本环境的硬件实测结果。</p></section>
<section id="performance"><div class="eyebrow">05 / Product-level trade-offs</div><h2>不能把“最高 4×”应用到所有数据类型</h2><p>下表取 MI355X → MI455X 官方公开峰值；矩阵项使用未计结构化稀疏加速的基础值。TFLOP/s 与 PFLOP/s 单位保持原量级，避免把稀疏值与 dense 值混比。</p><div class="tablewrap"><table class="perf"><thead><tr><th>类型</th><th>MI355X</th><th>MI455X</th><th>变化</th></tr></thead><tbody>__PERF__</tbody></table></div><div class="callout warn"><strong>FP64 是明确退化项：</strong>MI455X 的 FP64 vector 和 matrix 规格均列为 5 TFLOP/s。CDNA 5 XML 未列 V_MFMA_F64 或 V_WMMA_F64，但仍有 V_FMA_F64 / V_DUAL_FMA_F64 等向量指令。这说明不能把它概括成“完全不支持 FP64”，也不能替其他 CDNA 5 SKU 下结论。</div><p class="rowrefs">规格来源：__P4__ · __P5__；指令存在性：__XML__。数值经官方显示值四舍五入，倍数按近似值表达。</p></section>
<section id="pitfalls"><div class="eyebrow">06 / Interpretation checks</div><h2>整理 feature 时，六个地方容易误判</h2><div class="three"><article><h3>MXFP4 / 6 / 8 并非首增</h3><p>CDNA 4 已有。CDNA 5 要关注 scale 粒度、fractional scale、LUT 与吞吐，而不是把支持格式重新列为新增。</p></article><article><h3>Transpose 与直载已有基线</h3><p>CDNA 4 已有 DS_READ_*_TR 和 GLOBAL_LOAD_LDS_*。新增部分要逐个比较宽度、地址模型、同步与 global 变体。</p></article><article><h3>名称差分不等于功能差分</h3><p>DWORD→B32、READ→LOAD 等有大量显式别名。即使排除别名，矩阵模型和转换族的重写也会产生剩余名称差异。</p></article><article><h3>更大地址空间不等于更多 SRAM</h3><p>1024 VGPR 是每线程可寻址上限；物理文件容量和 occupancy 仍约束可用资源。64 Wave32 也不是两倍的驻留线程数。</p></article><article><h3>L2、Infinity Cache 分层比较</h3><p>32→192 MiB 是 L2 一层的 6×；旧代另有 256 MiB Infinity Cache。不要将不同层级混成同一容量指标。</p></article><article><h3>Cluster、稀疏和 SKU 边界</h3><p>Cluster broadcast 不是任意 peer LDS 访问的证据；FP8 SWMMAC 在 XML 中仍可见。功能、峰值规格和不同 SKU 的启用情况应分开记录。</p></article></div></section>
<section id="list"><div class="eyebrow">07 / Complete ISA list</div><h2>完整 XML 清单与别名校正差分</h2><div class="cards stats"><article class="card"><div class="big">1,240</div><small>CDNA 4 规范指令名</small></article><article class="card"><div class="big">1,325</div><small>CDNA 5 规范指令名</small></article><article class="card"><div class="big">283</div><small>跨代显式别名对应</small></article><article class="card"><div class="big">448</div><small>别名匹配后仅在 CDNA 5 列出</small></article></div><p>原始规范名差分：CDNA 5 新出现 731 个，CDNA 4 不再以同名列出 646 个；其中 283 对可用两代 XML 的显式别名关联。校正后剩余 448 个 CDNA 5 名称、363 个 CDNA 4 名称，另有 594 个两代同名条目。</p><div class="callout"><strong>统计口径：</strong>只统计 <code>ISA/Instructions/Instruction/InstructionName</code> 的直接规范名。先匹配同名，再对剩余条目求规范名与显式别名集合交集；本次 283 对均一对一，无歧义候选。未用拼写相似度或猜测的语义合并。“仅 CDNA 5 列出”不是 448 项全新 feature，“仅 CDNA 4 列出”也不是 363 项硬件能力全部删除。两代同名不代表二进制兼容。</div><p class="note">XML 快照：CDNA 4 为 2026-02-20 / schema 1.1.1；CDNA 5 为 2026-08-03 / schema 1.2.0。完整清单将对应别名并为一行，共 1,688 行，覆盖两代全部规范名。</p><div class="controls"><input type="search" id="query" placeholder="搜索指令名、别名或英文描述，如 tensor / bf16 / barrier" aria-label="搜索 ISA"><select id="status" aria-label="差分状态"><option value="only5">仅 CDNA 5 列出（448）</option><option value="only4">仅 CDNA 4 列出（363）</option><option value="alias">显式别名对应（283）</option><option value="same">两代同名（594）</option><option value="all">全部对应行（1688）</option></select><select id="group" aria-label="指令功能组"><option value="all">全部功能组</option></select><button id="reset">重置</button></div><div class="tablewrap"><table id="full-table"><thead><tr><th>状态 / 功能组</th><th>CDNA 4</th><th>CDNA 5</th><th>XML 英文说明</th></tr></thead><tbody id="instructions"></tbody></table><div id="empty" class="empty" hidden>没有匹配条目。可清空搜索或切换差分状态。</div></div><div class="pagination"><span id="count" aria-live="polite"></span><div><button id="prev">上一页</button><span id="page"></span><button id="next">下一页</button></div></div><p class="note printnote" style="display:none">完整清单采用分页，打印仅包含当前筛选页。完整数据请使用原始 XML 或 isa-diff.json。</p><details><summary>下载原始文件与复现统计</summary><p><a href="sources/cdna_changes/amdgpu_isa_cdna4.xml">CDNA 4 XML</a> · <a href="sources/cdna_changes/amdgpu_isa_cdna5.xml">CDNA 5 XML</a> · <a href="sources/cdna_changes/isa-diff.json">完整差分 JSON</a> · <a href="sources/cdna_changes/source-manifest.json">来源、抓取日期与 SHA-256</a></p><p><a href="research_tools/collect_cdna_changes.py">采集脚本</a> → <a href="research_tools/compare_cdna_isa.py">指令比较脚本</a> → <a href="research_tools/build_cdna_changes_report.py">报告生成脚本</a>。默认筛选显示“仅 CDNA 5 列出”，每页 80 行；所有筛选均在本地执行。</p><p class="note">XML 标注 AMD Public Use、MIT；来源文件保留原版权和许可信息。XML 的显式别名与描述用于查证名称，完整操作数语义以 ISA 定义为准。</p></details></section>
<section id="sources"><div class="eyebrow">08 / Primary sources</div><h2>官方资料与复核入口</h2><p class="note">推荐阅读顺序：产品规格确认比较对象 → 白皮书把握架构 → ISA PDF 核对语义 → XML 统计清单 → ROCm / LLVM 查编译和调优约束。全部快照检索于 2026-10-15；在线文档后续可能更新。</p><ol class="sourcegrid">__SOURCES__</ol><details><summary>证据强度与本报告的边界</summary><p>功能存在性以官方 ISA / XML 为依据，SKU 峰值以产品页为依据，机制解释使用白皮书与官方开发博客。示意图是整理后的概念路径，不是芯片布线图。优化建议属于基于公开机制的推导；本报告未运行 MI355X / MI455X 微基准，也未把编译器 intrinsic、官方产品峰值和硬件实测混为一类。</p><p>产品页标为 Matrix FP64 并不自动证明有独立 FP64 WMMA 指令；反过来，某个指令名没有被 XML 列出也不足以单独判定数学运算无法实现。遇到来源粒度不同，保留这种边界。</p></details></section>
</main><footer>AMD CDNA 4 → CDNA 5 · 本地研究报告 · 2026-10-15<br>HTML 无外部字体、脚本、图片或网络请求；相邻 sources / research_tools 目录用于原文追溯和复现。</footer>
<script id="isa-data" type="application/json">__DATA__</script><script>
'use strict';
const data=JSON.parse(document.querySelector('#isa-data').textContent), urls=__URLS__;
const labels={only5:'仅 CDNA 5 列出',only4:'仅 CDNA 4 列出',alias:'显式别名对应',same:'两代同名'};
const query=document.querySelector('#query'),status=document.querySelector('#status'),group=document.querySelector('#group'),body=document.querySelector('#instructions');
let page=0,filtered=[],pageSize=80;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
for(const g of [...new Set(data.flatMap(r=>[r.old?.group,r.new?.group]).filter(Boolean))].sort()){const o=document.createElement('option');o.value=g;o.textContent=g;group.append(o)}
for(const r of data)r.search=JSON.stringify(r).toLowerCase();
function cell(x,g){if(!x)return '<span class="muted">—</span>';return `<div class="instruction-name"><code><a target="_blank" rel="noreferrer" href="${urls['isa'+g]}${x.page?'#page='+x.page:''}">${esc(x.name)}</a></code></div>${x.aliases.length?'<div class="aliases">别名：'+x.aliases.map(esc).join(' · ')+'</div>':''}<div class="enc">${x.encodings.map(e=>esc(e.name)+' / op '+esc(e.opcode)).join('<br>')}</div>`}
function render(){const terms=query.value.trim().toLowerCase().split(/\s+/).filter(Boolean);filtered=data.filter(r=>(status.value==='all'||r.status===status.value)&&(group.value==='all'||[r.old?.group,r.new?.group].includes(group.value))&&terms.every(t=>r.search.includes(t)));const pages=Math.ceil(filtered.length/pageSize);page=Math.max(0,Math.min(page,Math.max(0,pages-1)));const show=filtered.slice(page*pageSize,(page+1)*pageSize);body.innerHTML=show.map(r=>`<tr><td><span class="status ${r.status}">${labels[r.status]}</span><div class="enc">${esc((r.new||r.old).group)}</div></td><td>${cell(r.old,4)}</td><td>${cell(r.new,5)}</td><td>${r.old&&r.new&&r.old.description!==r.new.description?'<small class="muted">CDNA 4</small><p>'+esc(r.old.description)+'</p><small class="muted">CDNA 5</small><p>'+esc(r.new.description)+'</p>':esc((r.new||r.old).description)}</td></tr>`).join('');document.querySelector('#empty').hidden=filtered.length>0;document.querySelector('#count').textContent=`匹配 ${filtered.length.toLocaleString()} / 1,688 行；当前 ${filtered.length?page*pageSize+1:0}–${Math.min((page+1)*pageSize,filtered.length)}`;document.querySelector('#page').textContent=pages?`${page+1} / ${pages}`:'0 / 0';document.querySelector('#prev').disabled=page===0;document.querySelector('#next').disabled=page+1>=pages;}
for(const e of [query,status,group])e.addEventListener(e===query?'input':'change',()=>{page=0;render()});
document.querySelector('#reset').addEventListener('click',()=>{query.value='';status.value='only5';group.value='all';page=0;render()});
document.querySelector('#prev').addEventListener('click',()=>{page--;render()});document.querySelector('#next').addEventListener('click',()=>{page++;render()});render();
</script></body></html>'''

def main():
 values={'__FEATURES__':feature_table(),'__ISA__':isa_table(),
  '__PERF__':''.join('<tr>'+''.join(f'<td>{H(c)}</td>' for c in r)+'</tr>' for r in PERF),
  '__DMA__':ref('llvm-dma','LLVM DMA'),'__ATTN__':ref('attention5','AMD attention decode'),'__LDS__':ref('lds5','AMD LDS 优化'),
  '__P4__':ref('product4','MI355X 官方规格'),'__P5__':ref('product5','MI455X 官方规格'),'__XML__':ref('machine-readable','GPUOpen XML'),
  '__SOURCES__':source_list(),'__DATA__':json.dumps(complete_rows(),ensure_ascii=False).replace('</','<\\/'),
  '__URLS__':json.dumps({'isa4':URL['isa4'],'isa5':URL['isa5']})}
 out=html
 for k,v in values.items():out=out.replace(k,v)
 assert not re.search(r'__[A-Z]+__',out)
 path=ROOT/'AMD-CDNA4-to-CDNA5-Feature-ISA-Changes.html';path.write_text(out,encoding='utf-8');print(path, path.stat().st_size)

if __name__=='__main__':main()
