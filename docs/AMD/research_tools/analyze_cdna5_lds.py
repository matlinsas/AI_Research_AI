"""CDNA5 dense GEMM payload roofline, using MI455X peak normalization.

This is a capacity/traffic model, not measured latency, scheduling, or bandwidth.
"""
from pathlib import Path
import json,csv,math
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'sources/cdna5_lds_analysis';OUT.mkdir(parents=True,exist_ok=True)
FORMATS=[
 ('FP16/BF16',2,8192,(16,16,32)),
 ('FP8',1,32768,(16,16,128)),
 ('FP6 packed',.75,32768,(16,16,128)),
 ('FP4 packed',.5,65536,(32,16,128)),
 ('INT8',1,8192,(16,16,64)),
 ('FP32',4,512,(16,16,4)),
]
native=[];waves=[];regs=[];scales=[];staging=[]
for name,s,p,(m,n,kr) in FORMATS:
 payload=kr*s*(m+n);ops=2*m*n*kr
 native.append(dict(format=name,native_m=m,native_n=n,native_k=kr,peak_ops_per_wgp_cycle=p,ab_payload_B_per_wave=payload,ab_required_B_per_wgp_cycle=p*payload/ops))
 for wm,wn in [(32,32),(64,64),(64,128),(96,96),(128,128),(160,160)]:
  b=p*s*(1/wm+1/wn)/2
  waves.append(dict(format=name,wave_m=wm,wave_n=wn,ab_required_B_per_wgp_cycle=b,dual_port_read_only_roof_fraction=min(1,512/b),serialized_port_read_only_roof_fraction=min(1,256/b)))
  if name not in ['FP16/BF16','FP8','FP6 packed','FP4 packed']:continue
  if (wm,wn) not in [(32,32),(64,64),(64,128),(128,128)]:continue
  rc=wm*wn/32
  rab=kr*s*(wm+wn)/128
  for q in [1,2]:
   other=16;total=math.ceil((rc+q*rab+other)/16)*16
   regs.append(dict(format=name,wave_tile=f'{wm}x{wn}',live_native_k=kr,c_regs_per_lane=rc,ab_regs_per_lane_one_buffer=rab,ab_register_buffers=q,assumed_other_vgprs_per_lane=other,allocated_vgprs_per_lane=total,fits_1024=total<=1024,rf_only_max_waves_per_simd=min(16,1024//total),allocated_kB_per_wave=total/8,ab_required_B_per_wgp_cycle=b))
for name,s,p in [('MXFP8',1,32768),('MXFP6',.75,32768),('MXFP4',.5,65536)]:
 for group in [32,16]:
  for wm,wn in [(32,32),(64,64),(64,128),(128,128)]:
   demand=p*(s+1/group)*(1/wm+1/wn)/2
   scales.append(dict(format=name,scale_group_elements=group,wave_tile=f'{wm}x{wn}',ab_and_scale_required_B_per_wgp_cycle=demand,dual_port_roof_fraction=min(1,512/demand),serialized_port_roof_fraction=min(1,256/demand)))
for side in [64,128]:
 # Four waves laid out 2x2; logical LDS footprint excludes partition allocator padding.
 bm=bn=2*side;bk=128;s=1;p=32768
 duration=2*bm*bn*bk/p
 unique=(bm+bn)*bk*s
 staging.append(dict(format='FP8',wave_tile=f'{side}x{side}',workgroup_tile=f'{bm}x{bn}',lds_buffer_k=bk,logical_double_buffer_kB=2*unique/1024,ab_read_B_per_wgp_cycle=4*(2*side)*bk*s/duration,stage_write_B_per_wgp_cycle=unique/duration,physical_partition_padding_included=False))
sources={
 'isa':'https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-cdna5-instruction-set-architecture.pdf',
 'whitepaper':'https://www.amd.com/content/dam/amd/en/documents/products/technologies/cdna/amd-cdna5-whitepaper.pdf',
 'sku_peaks':'https://www.amd.com/content/dam/amd/en/documents/products/accelerators/instinct/amd-instinct-mi455x_brochure.pdf',
 'lds_partition_ports':'https://rocm.blogs.amd.com/software-tools-optimization/mi450-lds-optimization/README.html',
 'fp8_8cycle_model':'https://rocm.blogs.amd.com/software-tools-optimization/gluon-attention-decode-mi450/README.html',
}
data={'date':'2026-11-03','scope':'MI455X, CDNA5 gfx1250; per WGP, not per hypothetical CU','sources':sources,
 'hardware':{'simds_per_wgp':4,'lanes_per_wave':32,'vgpr_bytes_per_simd':131072,'vgpr_bytes_per_wgp':524288,'vgpr_entries_per_lane_per_simd':1024,'max_waves_per_simd':16,'vgpr_allocation_granule':16,'lds_bytes_per_wgp':327680,'lds_read_peak_B_per_wgp_cycle_distinct_partitions':512,'lds_read_B_per_wgp_cycle_serialized':256},
 'peak_basis':'Normalize brochure peaks by 256 WGP x 2.4 GHz and restore architectural integer granularity. Native instruction dimensions do not imply all variants reach the SKU peak; no derived quotient is presented as measured instruction latency.',
 'assumptions':['Dense, target full SKU peak; retained FP32 C/D and in-place accumulation; no inner-loop C/D LDS traffic','Packed A/B payload; no spills, duplicate lane layouts, scale overhead (except scales table), or bank conflicts','A/B unique per wave live tile, reused among WMMA subtiles; no cross-wave LDS multicast assumed','Native row bandwidth is required throughput if that matrix form sustains target peak; not a measured instruction-rate claim','Register model buffers whole A/B wave panels for one native K-step; 16 illustrative other VGPRs/lane; round to 16; no scale register budget included','No extra asynchronous write bandwidth is assumed beyond cited read peak; concurrent TDM/DS writes and L0 traffic may contend','Logical LDS footprint is not partition-aware allocator physical footprint','1 kB=1024 B'],
 'formula':'LDS_read_B_per_WGP_cycle = P/2 * (sA/Nwave + sB/Mwave)',
 'native':native,'wave_tiles':waves,'registers':regs,'scales':scales,'staging':staging}
(OUT/'analysis.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
for key in ['native','wave_tiles','registers','scales','staging']:
 with (OUT/(key+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(data[key][0]));w.writeheader();w.writerows(data[key])
print('native',json.dumps(native))
print('registers_64_128',json.dumps([r for r in regs if r['wave_tile'] in ['64x64','128x128'] and r['ab_register_buffers']==2]))
print('scales',json.dumps([r for r in scales if r['scale_group_elements']==32 and r['wave_tile'] in ['64x64','128x128']]))
print('staging',json.dumps(staging))
